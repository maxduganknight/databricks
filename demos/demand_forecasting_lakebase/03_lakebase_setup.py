# Databricks notebook source
# MAGIC %md
# MAGIC # 03 - Lakebase Seed Data & Reverse ETL
# MAGIC
# MAGIC This notebook:
# MAGIC 1. Connects to the Lakebase PostgreSQL instance (already created via CLI)
# MAGIC 2. Seeds operational tables with realistic data based on historical sales velocity
# MAGIC 3. Syncs ML predictions from Lakehouse to Lakebase (reverse ETL)
# MAGIC 4. Generates reorder recommendations for the warehouse manager app
# MAGIC
# MAGIC **Prerequisites**: Lakebase project `demand-forecast-ops` and database `demand_forecast_ops`
# MAGIC must already exist (created via `databricks postgres` CLI).

# COMMAND ----------

# MAGIC %md
# MAGIC ## Configuration

# COMMAND ----------

CATALOG = "demand_forecast_demo_catalog"
SCHEMA = "demand_forecasting"

# Lakebase connection details
LAKEBASE_PROJECT = "demand-forecast-ops"
LAKEBASE_DB = "demand_forecast_ops"

spark.sql(f"USE CATALOG {CATALOG}")
spark.sql(f"USE SCHEMA {SCHEMA}")

# COMMAND ----------

# MAGIC %pip install psycopg2-binary
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

CATALOG = "demand_forecast_demo_catalog"
SCHEMA = "demand_forecasting"
LAKEBASE_PROJECT = "demand-forecast-ops"
LAKEBASE_DB = "demand_forecast_ops"
spark.sql(f"USE CATALOG {CATALOG}")
spark.sql(f"USE SCHEMA {SCHEMA}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Connect to Lakebase

# COMMAND ----------

import json, requests

# Lakebase endpoint (from `databricks postgres list-endpoints`)
LAKEBASE_HOST = "ep-fancy-math-d20pa502.database.us-east-1.cloud.databricks.com"

def get_lakebase_connection():
    """Get a psycopg2 connection to Lakebase using Databricks SDK for auth."""
    import psycopg2
    from databricks.sdk import WorkspaceClient

    w = WorkspaceClient()

    # Generate credential via REST API using SDK auth
    api_base = w.config.host.rstrip("/")
    # Get auth token from SDK config
    from databricks.sdk.core import Config
    cfg = w.config
    header_factory = cfg.authenticate
    auth_headers = header_factory()
    headers = dict(auth_headers)

    resp = requests.post(
        f"{api_base}/api/2.0/postgres/projects/{LAKEBASE_PROJECT}/branches/production/endpoints/primary:generateCredential",
        headers=headers, json={}
    )
    resp.raise_for_status()
    token = resp.json()["token"]

    user = w.current_user.me().user_name

    conn = psycopg2.connect(
        host=LAKEBASE_HOST, port=5432, dbname=LAKEBASE_DB,
        user=user, password=token, sslmode="require"
    )
    conn.autocommit = True
    print(f"Connected to Lakebase: {LAKEBASE_HOST}/{LAKEBASE_DB}")
    return conn

conn = get_lakebase_connection()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Seed Operational Data
# MAGIC
# MAGIC Use historical sales velocity to set intelligent reorder points and inventory levels.

# COMMAND ----------

import random
from pyspark.sql import functions as F

random.seed(42)

products = spark.table(f"{CATALOG}.{SCHEMA}.products").collect()

# Calculate recent 28-day velocity per SKU
recent_velocity = (
    spark.table(f"{CATALOG}.{SCHEMA}.sales_transactions")
    .filter(F.col("sale_date") >= F.date_sub(F.current_date(), 28))
    .groupBy("sku")
    .agg((F.sum("quantity_sold") / 28).alias("daily_velocity"))
    .collect()
)
velocity_map = {row.sku: float(row.daily_velocity) for row in recent_velocity}
print(f"Calculated velocity for {len(velocity_map)} SKUs")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Seed Reorder Thresholds

# COMMAND ----------

cur = conn.cursor()

for p in products:
    sku = p.sku
    velocity = velocity_map.get(sku, 5.0)
    lead_time = random.choice([5, 7, 10, 14])
    safety_stock = int(velocity * 3)
    reorder_point = int(velocity * lead_time) + safety_stock
    reorder_qty = int(velocity * 30)

    cur.execute("""
        INSERT INTO reorder_thresholds (sku, reorder_point, reorder_quantity, lead_time_days, safety_stock)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (sku) DO UPDATE SET
            reorder_point = EXCLUDED.reorder_point,
            reorder_quantity = EXCLUDED.reorder_quantity,
            lead_time_days = EXCLUDED.lead_time_days,
            safety_stock = EXCLUDED.safety_stock
    """, (sku, reorder_point, reorder_qty, lead_time, safety_stock))

print(f"Seeded reorder thresholds for {len(products)} SKUs")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Seed Inventory

# COMMAND ----------

inventory_count = 0
for p in products:
    sku = p.sku
    velocity = velocity_map.get(sku, 5.0)
    for wh in ["WH-EAST", "WH-WEST", "WH-CENTRAL"]:
        # ~60% healthy, ~25% low, ~15% critically low
        roll = random.random()
        if roll < 0.15:
            stock = int(velocity * random.uniform(0, 2))  # critical
        elif roll < 0.40:
            stock = int(velocity * random.uniform(2, 7))  # low
        else:
            stock = int(velocity * random.uniform(10, 30))  # healthy

        days_ago = random.randint(1, 30)
        cur.execute("""
            INSERT INTO inventory (sku, warehouse, current_stock, last_restock_date)
            VALUES (%s, %s, %s, CURRENT_DATE - INTERVAL '%s days')
            ON CONFLICT (sku, warehouse) DO UPDATE SET
                current_stock = EXCLUDED.current_stock,
                last_restock_date = EXCLUDED.last_restock_date,
                last_updated = CURRENT_TIMESTAMP
        """, (sku, wh, stock, days_ago))
        inventory_count += 1

print(f"Seeded inventory for {inventory_count} SKU/warehouse combos")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Seed Pending Orders

# COMMAND ----------

for _ in range(8):
    p = random.choice(products)
    wh = random.choice(["WH-EAST", "WH-WEST", "WH-CENTRAL"])
    qty = int(velocity_map.get(p.sku, 5.0) * random.uniform(15, 45))
    supplier = random.choice(["TechDist Inc.", "OfficeSupply Co.", "GlobalParts Ltd."])
    lead = random.randint(3, 12)

    cur.execute("""
        INSERT INTO pending_orders (sku, warehouse, quantity, supplier, order_date, expected_delivery, status)
        VALUES (%s, %s, %s, %s, CURRENT_DATE - INTERVAL '%s days', CURRENT_DATE + INTERVAL '%s days', 'pending')
    """, (p.sku, wh, qty, supplier, random.randint(1, 5), lead))

print("Seeded 8 pending orders")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Reverse ETL: Sync Predictions to Lakebase

# COMMAND ----------

predictions = spark.table(f"{CATALOG}.{SCHEMA}.sales_predictions").collect()

for row in predictions:
    cur.execute("""
        INSERT INTO sales_predictions
            (sku, prediction_date, current_quarter_forecast, current_quarter_lower,
             current_quarter_upper, next_quarter_forecast, next_quarter_lower,
             next_quarter_upper, model_version)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (sku) DO UPDATE SET
            prediction_date = EXCLUDED.prediction_date,
            current_quarter_forecast = EXCLUDED.current_quarter_forecast,
            current_quarter_lower = EXCLUDED.current_quarter_lower,
            current_quarter_upper = EXCLUDED.current_quarter_upper,
            next_quarter_forecast = EXCLUDED.next_quarter_forecast,
            next_quarter_lower = EXCLUDED.next_quarter_lower,
            next_quarter_upper = EXCLUDED.next_quarter_upper,
            model_version = EXCLUDED.model_version,
            synced_at = CURRENT_TIMESTAMP
    """, (row.sku, str(row.prediction_date), row.current_quarter_forecast,
          row.current_quarter_lower, row.current_quarter_upper,
          row.next_quarter_forecast, row.next_quarter_lower,
          row.next_quarter_upper, row.model_version))

print(f"Synced {len(predictions)} predictions to Lakebase")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Generate Reorder Recommendations

# COMMAND ----------

cur.execute("""
    INSERT INTO reorder_queue (sku, warehouse, recommended_quantity, recommendation_reason)
    SELECT
        i.sku,
        i.warehouse,
        GREATEST(rt.reorder_quantity,
                 sp.current_quarter_forecast / 3 - i.current_stock - COALESCE(po.pending_qty, 0)
        ),
        CONCAT(
            'Current stock: ', i.current_stock,
            ' | Pending: ', COALESCE(po.pending_qty, 0),
            ' | Forecast demand (current Q): ', sp.current_quarter_forecast,
            ' | Reorder point: ', rt.reorder_point
        )
    FROM inventory i
    JOIN reorder_thresholds rt ON i.sku = rt.sku
    JOIN sales_predictions sp ON i.sku = sp.sku
    LEFT JOIN (
        SELECT sku, warehouse, SUM(quantity) AS pending_qty
        FROM pending_orders
        WHERE status = 'pending'
        GROUP BY sku, warehouse
    ) po ON i.sku = po.sku AND i.warehouse = po.warehouse
    WHERE i.current_stock + COALESCE(po.pending_qty, 0) < rt.reorder_point
      AND i.sku NOT IN (SELECT sku FROM reorder_queue WHERE manager_action IS NULL)
""")

cur.execute("SELECT COUNT(*) FROM reorder_queue WHERE manager_action IS NULL")
queue_count = cur.fetchone()[0]
print(f"Generated {queue_count} reorder recommendations")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Verification

# COMMAND ----------

for table in ["inventory", "reorder_thresholds", "pending_orders",
              "sales_predictions", "reorder_queue", "stockout_events"]:
    cur.execute(f"SELECT COUNT(*) FROM {table}")
    count = cur.fetchone()[0]
    print(f"demand_forecast_ops.{table}: {count} rows")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Preview Reorder Queue

# COMMAND ----------

import pandas as pd

cur.execute("""
    SELECT q.queue_id, q.sku, q.warehouse, q.recommended_quantity,
           q.recommendation_reason, q.created_at
    FROM reorder_queue q
    WHERE q.manager_action IS NULL
    ORDER BY q.recommended_quantity DESC
    LIMIT 20
""")
cols = [desc[0] for desc in cur.description]
rows = cur.fetchall()
queue_df = spark.createDataFrame(pd.DataFrame(rows, columns=cols))
display(queue_df)

# COMMAND ----------

conn.close()
print("Lakebase seeding complete!")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Next Steps
# MAGIC
# MAGIC - Deploy **04_warehouse_manager_app** as a Databricks App
# MAGIC - The app reads from Lakebase for real-time inventory + predictions
# MAGIC - Manager actions write back to the `reorder_queue` table
