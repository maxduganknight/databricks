-- Gold: Genie / BI-ready sales model. Net sales follows the Finance rule (gross - discounts - returns, excl. freight/tax, cancelled orders excluded).

CREATE OR REFRESH MATERIALIZED VIEW gold_dim_product (
  sku STRING NOT NULL COMMENT 'T Industries SKU (TH-XX-nnnn)',
  product_name STRING COMMENT 'Product display name',
  category STRING COMMENT 'Product category: Locks, Levers, Door Closers, Hinges, Exit Devices, Faucets, Grab Bars, Bath Accessories',
  product_group STRING COMMENT 'Door Hardware or Bathroom Fixtures',
  subcategory STRING COMMENT 'Product subtype, e.g. Rim Exit Device',
  product_line STRING COMMENT 'Design collection, e.g. Granville',
  finish STRING COMMENT 'Finish name, e.g. Matte Black, Satin Chrome',
  finish_code STRING COMMENT 'BHMA finish code (US26D, US32D, BLK, US4, US10B, US26)',
  material STRING COMMENT 'Primary material',
  ansi_grade INT COMMENT 'ANSI/BHMA grade 1-3 (1 = commercial heavy duty); null for bathroom fixtures',
  list_price_cad DECIMAL(10,2) COMMENT 'Current list price, CAD',
  cost_cad DECIMAL(10,2) COMMENT 'Standard unit cost, CAD',
  image_path STRING COMMENT 'UC volume path of the product image (null if none)',
  short_description STRING COMMENT 'Short description',
  is_active BOOLEAN COMMENT 'SKU currently sellable',
  CONSTRAINT pk_dim_product PRIMARY KEY (sku)
)
COMMENT 'Product dimension: one row per T Industries SKU.'
AS SELECT sku, product_name, category, product_group, subcategory, product_line, finish, finish_code, material, ansi_grade,
  list_price_cad, cost_cad, image_path, short_description, is_active
FROM silver_products;

CREATE OR REFRESH MATERIALIZED VIEW gold_dim_customer (
  customer_id STRING NOT NULL COMMENT 'ERP customer id',
  customer_name STRING COMMENT 'Customer name',
  segment STRING COMMENT 'General Contractor, Condo Developer or Property Manager',
  region STRING COMMENT 'Sales region: BC (British Columbia), ON (Ontario) or US',
  city STRING COMMENT 'City',
  country STRING COMMENT 'Canada or USA',
  account_manager STRING COMMENT 'Assigned account manager',
  payment_terms STRING COMMENT 'Payment terms',
  hubspot_company_id BIGINT COMMENT 'Linked HubSpot company id',
  CONSTRAINT pk_dim_customer PRIMARY KEY (customer_id)
)
COMMENT 'Customer dimension (ERP master + HubSpot company link).'
AS SELECT c.customer_id, c.customer_name, c.segment, c.region, c.city, c.country, c.account_manager, c.payment_terms, h.company_id AS hubspot_company_id
FROM silver_customers c LEFT JOIN silver_hubspot_companies h ON h.customer_id = c.customer_id;

CREATE OR REFRESH MATERIALIZED VIEW gold_sales_daily (
  order_date DATE NOT NULL COMMENT 'Order date',
  customer_id STRING NOT NULL COMMENT 'ERP customer id (FK dim_customer)',
  sku STRING NOT NULL COMMENT 'SKU (FK dim_product)',
  warehouse STRING NOT NULL COMMENT 'Fulfilling warehouse: Delta BC or Toronto',
  channel STRING NOT NULL COMMENT 'Order channel',
  order_lines BIGINT COMMENT 'Number of order lines',
  units_ordered BIGINT COMMENT 'Units ordered',
  units_shipped BIGINT COMMENT 'Units shipped',
  units_backordered BIGINT COMMENT 'Units backordered',
  units_returned BIGINT COMMENT 'Units returned',
  gross_sales_cad DECIMAL(16,2) COMMENT 'Gross sales = shipped units x list price, CAD',
  discount_cad DECIMAL(16,2) COMMENT 'Discounts off list, CAD',
  returns_cad DECIMAL(16,2) COMMENT 'Returns credited, CAD',
  net_sales_cad DECIMAL(16,2) COMMENT 'Net sales = gross - discounts - returns, CAD (excl. freight and tax)',
  cogs_cad DECIMAL(16,2) COMMENT 'Cost of goods sold, CAD',
  gross_margin_cad DECIMAL(16,2) COMMENT 'Gross margin = net sales - COGS, CAD',
  CONSTRAINT pk_sales_daily PRIMARY KEY (order_date, customer_id, sku, warehouse, channel)
)
COMMENT 'Daily sales fact at order date x customer x SKU x warehouse x channel grain. Cancelled orders excluded. Source of metric view t_sales_metrics.'
CLUSTER BY (order_date)
AS SELECT o.order_date, o.customer_id, l.sku, o.warehouse, o.channel,
  count(*) AS order_lines, sum(l.qty_ordered) AS units_ordered, sum(l.qty_shipped) AS units_shipped,
  sum(l.qty_backordered) AS units_backordered, sum(l.qty_returned) AS units_returned,
  CAST(sum(l.gross_sales_cad) AS DECIMAL(16,2)) AS gross_sales_cad, CAST(sum(l.discount_cad) AS DECIMAL(16,2)) AS discount_cad,
  CAST(sum(l.returns_cad) AS DECIMAL(16,2)) AS returns_cad, CAST(sum(l.net_sales_cad) AS DECIMAL(16,2)) AS net_sales_cad,
  CAST(sum(l.cogs_cad) AS DECIMAL(16,2)) AS cogs_cad, CAST(sum(l.net_sales_cad) - sum(l.cogs_cad) AS DECIMAL(16,2)) AS gross_margin_cad
FROM silver_order_lines l JOIN silver_sales_orders o USING (order_id)
WHERE o.status <> 'Cancelled'
GROUP BY ALL;

CREATE OR REFRESH MATERIALIZED VIEW gold_product_margin (
  sku STRING NOT NULL COMMENT 'SKU',
  product_name STRING COMMENT 'Product name',
  category STRING COMMENT 'Product category',
  finish STRING COMMENT 'Finish',
  list_price_cad DECIMAL(10,2) COMMENT 'Current list price, CAD',
  units_shipped_t12m BIGINT COMMENT 'Units shipped in the trailing 12 months',
  net_sales_t12m_cad DECIMAL(16,2) COMMENT 'Net sales, trailing 12 months, CAD',
  gross_margin_t12m_cad DECIMAL(16,2) COMMENT 'Gross margin, trailing 12 months, CAD',
  gross_margin_pct_t12m DOUBLE COMMENT 'Gross margin % = gross margin / net sales, trailing 12 months',
  avg_selling_price_t12m_cad DECIMAL(10,2) COMMENT 'Average selling price = net sales / shipped units, trailing 12 months',
  avg_discount_pct_t12m DOUBLE COMMENT 'Average discount off list = discounts / gross sales, trailing 12 months',
  return_rate_t12m DOUBLE COMMENT 'Units returned / units shipped, trailing 12 months',
  CONSTRAINT pk_product_margin PRIMARY KEY (sku)
)
COMMENT 'SKU profitability over the trailing 12 months (ending at the latest order date): net sales, gross margin %, ASP, discount and return rate.'
AS WITH w AS (
  SELECT s.* FROM gold_sales_daily s
  WHERE s.order_date > (SELECT add_months(max(order_date), -12) FROM gold_sales_daily)
)
SELECT p.sku, p.product_name, p.category, p.finish, p.list_price_cad,
  coalesce(sum(w.units_shipped), 0) AS units_shipped_t12m,
  CAST(coalesce(sum(w.net_sales_cad), 0) AS DECIMAL(16,2)) AS net_sales_t12m_cad,
  CAST(coalesce(sum(w.gross_margin_cad), 0) AS DECIMAL(16,2)) AS gross_margin_t12m_cad,
  CAST(round(try_divide(sum(w.gross_margin_cad), sum(w.net_sales_cad)), 4) AS DOUBLE) AS gross_margin_pct_t12m,
  CAST(try_divide(sum(w.net_sales_cad), sum(w.units_shipped)) AS DECIMAL(10,2)) AS avg_selling_price_t12m_cad,
  CAST(round(try_divide(sum(w.discount_cad), sum(w.gross_sales_cad)), 4) AS DOUBLE) AS avg_discount_pct_t12m,
  CAST(round(try_divide(sum(w.units_returned), sum(w.units_shipped)), 4) AS DOUBLE) AS return_rate_t12m
FROM silver_products p LEFT JOIN w ON w.sku = p.sku
GROUP BY ALL;
