-- Gold: inventory position by warehouse and SKU, protected by a row filter.
-- gov_warehouse_row_filter + gov_warehouse_access are created by src/notebooks/02_setup_governance
-- (functions cannot be created inside a pipeline). Users only see warehouses mapped to them (or ALL) in gov_warehouse_access.

CREATE OR REFRESH MATERIALIZED VIEW gold_inventory_position (
  warehouse STRING NOT NULL COMMENT 'Warehouse: Delta BC or Toronto (row-filtered per user via gov_warehouse_access)',
  sku STRING NOT NULL COMMENT 'SKU (FK dim_product)',
  product_name STRING COMMENT 'Product name',
  category STRING COMMENT 'Product category',
  on_hand_qty INT COMMENT 'Units on hand',
  allocated_qty INT COMMENT 'Units allocated to open orders',
  available_qty INT COMMENT 'Available stock = on hand - allocated',
  on_order_qty INT COMMENT 'Units on open purchase orders',
  reorder_point INT COMMENT 'Reorder point, units',
  safety_stock INT COMMENT 'Safety stock, units',
  avg_daily_demand_90d DOUBLE COMMENT 'Average units ordered per day from this warehouse over the last 90 days',
  days_of_cover DOUBLE COMMENT 'Available units / average daily demand (null when no demand)',
  below_reorder_point BOOLEAN COMMENT 'True when available + on order < reorder point (business rule backorder_definition.md)',
  stock_status STRING COMMENT 'Out of stock, Below reorder point, Healthy or No demand',
  inventory_value_cad DECIMAL(14,2) COMMENT 'On-hand units x standard cost, CAD',
  snapshot_date DATE COMMENT 'Inventory snapshot date',
  CONSTRAINT pk_inventory_position PRIMARY KEY (warehouse, sku)
)
WITH ROW FILTER t_hardware.gov_warehouse_row_filter ON (warehouse)
COMMENT 'Inventory position and days of cover by warehouse x SKU. Row-level security: each user only sees the warehouses granted in gov_warehouse_access.'
AS WITH dem AS (
  SELECT o.warehouse, l.sku, CAST(sum(l.qty_ordered) AS DOUBLE) / 90 AS adu
  FROM silver_order_lines l JOIN silver_sales_orders o USING (order_id)
  WHERE o.status <> 'Cancelled' AND o.order_date > (SELECT date_sub(max(order_date), 90) FROM silver_sales_orders)
  GROUP BY ALL
)
SELECT i.warehouse, i.sku, p.product_name, p.category, i.on_hand_qty, i.allocated_qty,
  i.on_hand_qty - i.allocated_qty AS available_qty, i.on_order_qty, i.reorder_point, i.safety_stock,
  round(coalesce(d.adu, 0), 2) AS avg_daily_demand_90d,
  round(try_divide(i.on_hand_qty - i.allocated_qty, d.adu), 1) AS days_of_cover,
  (i.on_hand_qty - i.allocated_qty + i.on_order_qty) < i.reorder_point AS below_reorder_point,
  CASE WHEN i.on_hand_qty - i.allocated_qty <= 0 AND coalesce(d.adu, 0) > 0 THEN 'Out of stock'
       WHEN (i.on_hand_qty - i.allocated_qty + i.on_order_qty) < i.reorder_point THEN 'Below reorder point'
       WHEN coalesce(d.adu, 0) = 0 THEN 'No demand'
       ELSE 'Healthy' END AS stock_status,
  CAST(i.on_hand_qty * p.cost_cad AS DECIMAL(14,2)) AS inventory_value_cad, i.snapshot_date
FROM silver_inventory i
JOIN silver_products p ON p.sku = i.sku
LEFT JOIN dem d ON d.warehouse = i.warehouse AND d.sku = i.sku;
