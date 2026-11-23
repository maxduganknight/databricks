-- Gold: T Industries vs competitor pricing, using each competitor SKU's latest scrape.
-- % gap > 0 means T is MORE expensive than the competitor.

CREATE OR REFRESH MATERIALIZED VIEW gold_price_benchmark_by_competitor (
  sku STRING NOT NULL COMMENT 'T Industries SKU',
  competitor_name STRING NOT NULL COMMENT 'Competitor: NorthBuild Supply, Pacific Hardware Co or DoorPro Direct',
  competitor_sku STRING COMMENT 'Competitor equivalent SKU',
  category STRING COMMENT 'T product category',
  t_list_price_cad DECIMAL(10,2) COMMENT 'T list price, CAD',
  competitor_price_cad DECIMAL(10,2) COMMENT 'Competitor latest web price, CAD',
  pct_gap DOUBLE COMMENT '(T list - competitor price) / competitor price; positive = T is more expensive',
  price_date DATE COMMENT 'Date of the latest competitor scrape',
  source_url STRING COMMENT 'Competitor product page URL',
  CONSTRAINT pk_price_benchmark_by_competitor PRIMARY KEY (sku, competitor_name)
)
COMMENT 'Latest competitor price per T SKU and competitor with the % price gap (long format, for heatmaps).'
AS SELECT p.sku, c.competitor_name, c.competitor_sku, p.category, p.list_price_cad AS t_list_price_cad,
  c.competitor_price_cad, CAST(round((p.list_price_cad - c.competitor_price_cad) / c.competitor_price_cad, 4) AS DOUBLE) AS pct_gap,
  c.price_date, c.source_url
FROM silver_competitor_prices c JOIN silver_products p ON p.sku = c.t_sku
WHERE c.is_latest;

CREATE OR REFRESH MATERIALIZED VIEW gold_price_benchmark (
  sku STRING NOT NULL COMMENT 'T Industries SKU (FK dim_product)',
  product_name STRING COMMENT 'Product name',
  category STRING COMMENT 'Product category',
  finish STRING COMMENT 'Finish',
  t_list_price_cad DECIMAL(10,2) COMMENT 'T list price, CAD',
  t_avg_selling_price_90d_cad DECIMAL(10,2) COMMENT 'T average net selling price over the last 90 days (after customer discounts), CAD',
  competitor_count INT COMMENT 'Number of competitors with an equivalent SKU',
  competitor_min_price_cad DECIMAL(10,2) COMMENT 'Lowest latest competitor price, CAD',
  competitor_avg_price_cad DECIMAL(10,2) COMMENT 'Average latest competitor price, CAD',
  cheapest_competitor STRING COMMENT 'Competitor with the lowest price',
  pct_gap_vs_min DOUBLE COMMENT '(T list - competitor min) / competitor min; > 0.10 means T is priced more than 10% above the cheapest competitor',
  pct_gap_vs_avg DOUBLE COMMENT '(T list - competitor avg) / competitor avg',
  price_position STRING COMMENT 'More than 10% above, Within 10%, or More than 10% below the cheapest competitor',
  latest_price_date DATE COMMENT 'Most recent competitor scrape date',
  CONSTRAINT pk_price_benchmark PRIMARY KEY (sku)
)
COMMENT 'Price benchmark per T SKU: T list price vs competitor min / avg price and % gap. Use pct_gap_vs_min > 0.10 for "priced more than 10% above competitors".'
AS WITH asp AS (
  SELECT sku, try_divide(sum(net_sales_cad), sum(units_shipped)) AS asp
  FROM gold_sales_daily
  WHERE order_date > (SELECT date_sub(max(order_date), 90) FROM gold_sales_daily)
  GROUP BY sku
), agg AS (
  SELECT sku, CAST(count(*) AS INT) AS n, min(competitor_price_cad) AS mn, avg(competitor_price_cad) AS av,
         min_by(competitor_name, competitor_price_cad) AS cheapest, max(price_date) AS pd
  FROM gold_price_benchmark_by_competitor GROUP BY sku
)
SELECT p.sku, p.product_name, p.category, p.finish, p.list_price_cad AS t_list_price_cad,
  CAST(asp.asp AS DECIMAL(10,2)) AS t_avg_selling_price_90d_cad,
  agg.n AS competitor_count, CAST(agg.mn AS DECIMAL(10,2)) AS competitor_min_price_cad, CAST(agg.av AS DECIMAL(10,2)) AS competitor_avg_price_cad,
  agg.cheapest AS cheapest_competitor,
  CAST(round((p.list_price_cad - agg.mn) / agg.mn, 4) AS DOUBLE) AS pct_gap_vs_min,
  CAST(round((p.list_price_cad - agg.av) / agg.av, 4) AS DOUBLE) AS pct_gap_vs_avg,
  CASE WHEN (p.list_price_cad - agg.mn) / agg.mn > 0.10 THEN 'More than 10% above'
       WHEN (p.list_price_cad - agg.mn) / agg.mn < -0.10 THEN 'More than 10% below'
       ELSE 'Within 10%' END AS price_position,
  agg.pd AS latest_price_date
FROM silver_products p JOIN agg ON agg.sku = p.sku LEFT JOIN asp ON asp.sku = p.sku;
