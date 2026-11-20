-- Silver: cleaned ERP / WMS / price-scrape tables. Default catalog + schema come from the pipeline settings
-- (mdk_demo_catalog.t_hardware); layers are table-name prefixes: sources bronze_<table>, outputs silver_<table>.

CREATE OR REFRESH MATERIALIZED VIEW silver_products (
  sku STRING NOT NULL COMMENT 'T Industries SKU (TH-<category code>-<number>)',
  product_name STRING COMMENT 'Product display name',
  category STRING COMMENT 'Product category: Locks, Levers, Door Closers, Hinges, Exit Devices, Faucets, Grab Bars, Bath Accessories',
  product_group STRING COMMENT 'Door Hardware or Bathroom Fixtures',
  subcategory STRING COMMENT 'Product subtype, e.g. Surface Door Closer',
  product_line STRING COMMENT 'Design collection / product line',
  finish STRING COMMENT 'Finish name, e.g. Matte Black',
  finish_code STRING COMMENT 'BHMA finish code (US26D, US32D, BLK, US4, US10B, US26)',
  material STRING COMMENT 'Primary material',
  ansi_grade INT COMMENT 'ANSI/BHMA grade 1-3 (1 = heaviest duty, commercial); null for bathroom fixtures',
  list_price_cad DECIMAL(10,2) COMMENT 'National list price, CAD',
  cost_cad DECIMAL(10,2) COMMENT 'Standard unit cost, CAD',
  list_margin_pct DOUBLE COMMENT 'Margin at list price = (list - cost) / list',
  image_path STRING COMMENT 'UC volume path of the product image (null if none)',
  short_description STRING COMMENT 'Short marketing description',
  launch_date DATE COMMENT 'SKU launch date',
  is_active BOOLEAN COMMENT 'SKU currently sellable',
  CONSTRAINT pk_products PRIMARY KEY (sku)
)
COMMENT 'Cleaned item master: one row per SKU with typed prices and grades.'
AS SELECT
  upper(trim(sku)) AS sku, name AS product_name, category,
  CASE WHEN category IN ('Faucets','Grab Bars','Bath Accessories') THEN 'Bathroom Fixtures' ELSE 'Door Hardware' END AS product_group,
  subcategory, product_line, finish, finish_code, material,
  CAST(ansi_grade AS INT) AS ansi_grade,
  CAST(list_price_cad AS DECIMAL(10,2)) AS list_price_cad,
  CAST(cost_cad AS DECIMAL(10,2)) AS cost_cad,
  CAST(round((list_price_cad - cost_cad) / list_price_cad, 4) AS DOUBLE) AS list_margin_pct,
  image_path, short_description, to_date(launch_date) AS launch_date, is_active
FROM bronze_products;

CREATE OR REFRESH MATERIALIZED VIEW silver_customers (
  customer_id STRING NOT NULL COMMENT 'ERP customer id',
  customer_name STRING COMMENT 'Customer name',
  segment STRING COMMENT 'General Contractor, Condo Developer or Property Manager',
  region STRING COMMENT 'Standardized sales region: BC, ON or US',
  city STRING COMMENT 'City (US cities include the state)',
  country STRING COMMENT 'Canada or USA',
  account_manager STRING COMMENT 'Assigned account manager',
  payment_terms STRING COMMENT 'Payment terms',
  credit_limit_cad DECIMAL(12,2) COMMENT 'Credit limit, CAD',
  created_date DATE COMMENT 'Account creation date',
  CONSTRAINT pk_customers PRIMARY KEY (customer_id)
)
COMMENT 'Cleaned customer master with standardized regions (BC / ON / US).'
AS SELECT
  customer_id, customer_name, segment,
  CASE WHEN upper(trim(region_raw)) IN ('BC','B.C.','BRITISH COLUMBIA') THEN 'BC'
       WHEN upper(trim(region_raw)) IN ('ON','ONT.','ONTARIO') THEN 'ON'
       WHEN upper(trim(region_raw)) IN ('US','USA','UNITED STATES') THEN 'US' END AS region,
  city, country, account_manager, payment_terms,
  CAST(credit_limit_cad AS DECIMAL(12,2)) AS credit_limit_cad, to_date(created_date) AS created_date
FROM bronze_customers;

CREATE OR REFRESH MATERIALIZED VIEW silver_sales_orders (
  order_id STRING NOT NULL COMMENT 'Sales order number SO-nnnnnn',
  customer_id STRING COMMENT 'ERP customer id',
  order_date DATE COMMENT 'Order date (parsed from mixed source formats)',
  ship_date DATE COMMENT 'Ship date; null when cancelled',
  warehouse STRING COMMENT 'Fulfilling warehouse: Delta BC or Toronto',
  sales_rep STRING COMMENT 'Sales rep on the order',
  channel STRING COMMENT 'Inside Sales, Field Sales, Web Portal or EDI',
  status STRING COMMENT 'Shipped or Cancelled (cancelled orders are excluded from net sales)',
  po_number STRING COMMENT 'Customer PO number',
  freight_cad DECIMAL(10,2) COMMENT 'Freight charged, CAD (excluded from net sales)',
  CONSTRAINT valid_order_date EXPECT (order_date IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT pk_sales_orders PRIMARY KEY (order_id)
)
COMMENT 'Cleaned sales order headers with parsed dates.'
AS SELECT
  order_id, customer_id,
  coalesce(try_to_date(order_date, 'yyyy-MM-dd'), try_to_date(order_date, 'MM/dd/yyyy')) AS order_date,
  try_to_date(ship_date, 'yyyy-MM-dd') AS ship_date,
  warehouse, sales_rep, channel, status, po_number, CAST(freight_cad AS DECIMAL(10,2)) AS freight_cad
FROM bronze_sales_orders;

CREATE OR REFRESH MATERIALIZED VIEW silver_order_lines (
  order_id STRING NOT NULL COMMENT 'Sales order number',
  line_no INT NOT NULL COMMENT 'Line number within the order',
  sku STRING COMMENT 'Standardized SKU (TH-XX-nnnn)',
  qty_ordered INT COMMENT 'Units ordered',
  qty_shipped INT COMMENT 'Units shipped',
  qty_backordered INT COMMENT 'Units backordered',
  qty_returned INT COMMENT 'Units returned (credit memo)',
  unit_list_price DECIMAL(10,2) COMMENT 'List price per unit at order time, CAD',
  discount_pct DOUBLE COMMENT 'Discount off list (0-1)',
  unit_net_price DECIMAL(10,2) COMMENT 'Net invoiced price per unit, CAD',
  unit_cost DECIMAL(10,2) COMMENT 'Standard cost per unit, CAD',
  gross_sales_cad DECIMAL(14,2) COMMENT 'Shipped units x list price',
  discount_cad DECIMAL(14,2) COMMENT 'Shipped units x (list - net price)',
  returns_cad DECIMAL(14,2) COMMENT 'Returned units x net price',
  net_sales_cad DECIMAL(14,2) COMMENT 'Net sales = gross sales - discounts - returns (business rule net_sales_definition.md)',
  cogs_cad DECIMAL(14,2) COMMENT 'COGS = (shipped - returned units) x standard cost',
  CONSTRAINT valid_sku EXPECT (sku RLIKE '^TH-[A-Z]{2}-[0-9]{4}$'),
  CONSTRAINT pk_order_lines PRIMARY KEY (order_id, line_no)
)
COMMENT 'Deduplicated order lines with standardized SKUs and the governed net-sales components.'
AS WITH d AS (
  SELECT DISTINCT order_id, line_no, sku, qty_ordered, qty_shipped, qty_backordered, qty_returned,
         unit_list_price, discount_pct, unit_net_price, unit_cost
  FROM bronze_order_lines
), s AS (
  SELECT *, regexp_replace(upper(sku), '[^A-Z0-9]', '') AS k FROM d
)
SELECT
  order_id, CAST(line_no AS INT) AS line_no,
  concat('TH-', substr(k, 3, 2), '-', substr(k, 5)) AS sku,
  CAST(qty_ordered AS INT) AS qty_ordered, CAST(qty_shipped AS INT) AS qty_shipped,
  CAST(qty_backordered AS INT) AS qty_backordered, CAST(qty_returned AS INT) AS qty_returned,
  CAST(unit_list_price AS DECIMAL(10,2)) AS unit_list_price, CAST(discount_pct AS DOUBLE) AS discount_pct,
  CAST(unit_net_price AS DECIMAL(10,2)) AS unit_net_price, CAST(unit_cost AS DECIMAL(10,2)) AS unit_cost,
  CAST(qty_shipped * unit_list_price AS DECIMAL(14,2)) AS gross_sales_cad,
  CAST(qty_shipped * (unit_list_price - unit_net_price) AS DECIMAL(14,2)) AS discount_cad,
  CAST(qty_returned * unit_net_price AS DECIMAL(14,2)) AS returns_cad,
  CAST(qty_shipped * unit_net_price - qty_returned * unit_net_price AS DECIMAL(14,2)) AS net_sales_cad,
  CAST((qty_shipped - qty_returned) * unit_cost AS DECIMAL(14,2)) AS cogs_cad
FROM s;

CREATE OR REFRESH MATERIALIZED VIEW silver_inventory (
  warehouse STRING NOT NULL COMMENT 'Warehouse: Delta BC or Toronto',
  sku STRING NOT NULL COMMENT 'SKU',
  on_hand_qty INT COMMENT 'Units on hand',
  allocated_qty INT COMMENT 'Units allocated to open orders',
  on_order_qty INT COMMENT 'Units on open purchase orders',
  reorder_point INT COMMENT 'Reorder point, units',
  safety_stock INT COMMENT 'Safety stock, units',
  bin_location STRING COMMENT 'Bin location',
  snapshot_date DATE COMMENT 'Snapshot date',
  last_receipt_date DATE COMMENT 'Last receipt date',
  CONSTRAINT pk_inventory PRIMARY KEY (warehouse, sku)
)
COMMENT 'Typed WMS inventory snapshot by warehouse and SKU.'
AS SELECT warehouse, upper(sku) AS sku, CAST(on_hand_qty AS INT) AS on_hand_qty, CAST(allocated_qty AS INT) AS allocated_qty,
  CAST(on_order_qty AS INT) AS on_order_qty, CAST(reorder_point AS INT) AS reorder_point, CAST(safety_stock AS INT) AS safety_stock,
  bin_location, to_date(snapshot_date) AS snapshot_date, to_date(last_receipt_date) AS last_receipt_date
FROM bronze_inventory;

CREATE OR REFRESH MATERIALIZED VIEW silver_competitor_prices (
  competitor_name STRING COMMENT 'Competitor: NorthBuild Supply, Pacific Hardware Co or DoorPro Direct',
  competitor_sku STRING COMMENT 'Competitor SKU',
  t_sku STRING COMMENT 'Equivalent T Industries SKU',
  competitor_product_name STRING COMMENT 'Competitor product description',
  competitor_price_cad DECIMAL(10,2) COMMENT 'Competitor web price, CAD',
  price_date DATE COMMENT 'Scrape date',
  source_url STRING COMMENT 'Competitor product page URL',
  in_stock BOOLEAN COMMENT 'Competitor showed the item in stock',
  is_latest BOOLEAN COMMENT 'True for the most recent scrape of this competitor SKU'
)
COMMENT 'Typed competitor price history with a latest-scrape flag.'
AS SELECT competitor_name, competitor_sku, upper(t_sku) AS t_sku, competitor_product_name,
  CAST(competitor_price_cad AS DECIMAL(10,2)) AS competitor_price_cad, to_date(price_date) AS price_date, source_url, in_stock,
  row_number() OVER (PARTITION BY competitor_sku ORDER BY to_date(price_date) DESC) = 1 AS is_latest
FROM bronze_competitor_prices;
