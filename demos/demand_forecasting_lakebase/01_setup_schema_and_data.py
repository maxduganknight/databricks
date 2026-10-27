# Databricks notebook source
# MAGIC %md
# MAGIC # 01 - Setup Schema & Generate Historical Sales Data
# MAGIC
# MAGIC This notebook creates the catalog/schema structure and generates 2 years of
# MAGIC realistic historical transactional data for ~50 product SKUs across multiple
# MAGIC warehouses. The data includes seasonality patterns, trend, and noise to make
# MAGIC the forecasting problem realistic.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Configuration

# COMMAND ----------

CATALOG = "demand_forecast_demo_catalog"  # Update to match your FEVM workspace catalog
SCHEMA = "demand_forecasting"

spark.sql(f"USE CATALOG {CATALOG}")
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
spark.sql(f"USE SCHEMA {SCHEMA}")

print(f"Using {CATALOG}.{SCHEMA}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Create Products Table

# COMMAND ----------

from pyspark.sql.types import *
from pyspark.sql import functions as F
import numpy as np

products_data = [
    ("SKU-001", "Wireless Mouse", "Electronics", 8.50, 24.99),
    ("SKU-002", "USB-C Hub", "Electronics", 15.00, 49.99),
    ("SKU-003", "Mechanical Keyboard", "Electronics", 25.00, 79.99),
    ("SKU-004", "Monitor Stand", "Accessories", 12.00, 39.99),
    ("SKU-005", "Laptop Sleeve 15in", "Accessories", 5.00, 19.99),
    ("SKU-006", "Webcam HD", "Electronics", 18.00, 59.99),
    ("SKU-007", "Desk Lamp LED", "Office", 10.00, 34.99),
    ("SKU-008", "Ergonomic Chair Pad", "Office", 8.00, 29.99),
    ("SKU-009", "Cable Management Kit", "Accessories", 3.00, 14.99),
    ("SKU-010", "Portable SSD 1TB", "Electronics", 35.00, 89.99),
    ("SKU-011", "Noise Cancelling Headphones", "Electronics", 40.00, 129.99),
    ("SKU-012", "Standing Desk Converter", "Office", 55.00, 179.99),
    ("SKU-013", "Wireless Charger Pad", "Electronics", 6.00, 24.99),
    ("SKU-014", "Blue Light Glasses", "Accessories", 4.00, 19.99),
    ("SKU-015", "Desk Organizer", "Office", 7.00, 22.99),
    ("SKU-016", "HDMI Cable 6ft", "Accessories", 2.50, 12.99),
    ("SKU-017", "Whiteboard 24x36", "Office", 15.00, 44.99),
    ("SKU-018", "Dry Erase Markers 12pk", "Office", 3.00, 11.99),
    ("SKU-019", "USB Flash Drive 64GB", "Electronics", 4.00, 14.99),
    ("SKU-020", "Mouse Pad XL", "Accessories", 3.50, 16.99),
    ("SKU-021", "Surge Protector 6-outlet", "Electronics", 8.00, 27.99),
    ("SKU-022", "Document Scanner", "Electronics", 45.00, 149.99),
    ("SKU-023", "Pen Holder", "Office", 2.00, 9.99),
    ("SKU-024", "Sticky Notes 12pk", "Office", 2.50, 8.99),
    ("SKU-025", "Ethernet Cable 25ft", "Accessories", 3.00, 14.99),
    ("SKU-026", "Portable Monitor 15in", "Electronics", 65.00, 199.99),
    ("SKU-027", "Desk Fan USB", "Office", 6.00, 19.99),
    ("SKU-028", "Privacy Screen 15in", "Accessories", 12.00, 39.99),
    ("SKU-029", "Laptop Stand Adjustable", "Accessories", 10.00, 34.99),
    ("SKU-030", "Wireless Presenter", "Electronics", 9.00, 29.99),
    ("SKU-031", "Tape Dispenser", "Office", 1.50, 6.99),
    ("SKU-032", "File Folders 50pk", "Office", 4.00, 12.99),
    ("SKU-033", "Binder Clips 100pk", "Office", 2.00, 7.99),
    ("SKU-034", "USB Microphone", "Electronics", 20.00, 69.99),
    ("SKU-035", "Ring Light 10in", "Electronics", 12.00, 39.99),
    ("SKU-036", "Cable Ties 100pk", "Accessories", 1.50, 5.99),
    ("SKU-037", "Power Bank 20000mAh", "Electronics", 14.00, 44.99),
    ("SKU-038", "Screen Cleaning Kit", "Accessories", 3.00, 9.99),
    ("SKU-039", "Footrest Ergonomic", "Office", 12.00, 39.99),
    ("SKU-040", "Desk Mat Leather", "Accessories", 8.00, 29.99),
    ("SKU-041", "Smart Plug 4-pack", "Electronics", 10.00, 34.99),
    ("SKU-042", "Label Maker", "Office", 15.00, 49.99),
    ("SKU-043", "Wrist Rest Keyboard", "Accessories", 5.00, 17.99),
    ("SKU-044", "USB Hub 7-port", "Electronics", 12.00, 39.99),
    ("SKU-045", "Clipboard Letter Size", "Office", 1.00, 4.99),
    ("SKU-046", "Stapler Heavy Duty", "Office", 5.00, 16.99),
    ("SKU-047", "Paper Shredder", "Office", 30.00, 89.99),
    ("SKU-048", "Desk Clock Digital", "Office", 6.00, 19.99),
    ("SKU-049", "Bookends Metal", "Office", 4.00, 14.99),
    ("SKU-050", "Air Duster Compressed", "Accessories", 3.00, 8.99),
]

products_schema = StructType([
    StructField("sku", StringType(), False),
    StructField("name", StringType(), False),
    StructField("category", StringType(), False),
    StructField("unit_cost", DoubleType(), False),
    StructField("unit_price", DoubleType(), False),
])

products_df = spark.createDataFrame(products_data, schema=products_schema)
products_df.write.mode("overwrite").saveAsTable("products")
print(f"Created products table with {products_df.count()} SKUs")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Generate Historical Sales Transactions
# MAGIC
# MAGIC 2 years of daily sales data per SKU with:
# MAGIC - **Seasonality**: Q4 holiday bump, summer dip for office supplies, etc.
# MAGIC - **Trend**: slight upward trend for electronics, flat for office
# MAGIC - **Weekly pattern**: lower weekend sales
# MAGIC - **Random noise**: Poisson-distributed daily quantities

# COMMAND ----------

import pandas as pd
from datetime import datetime, timedelta

np.random.seed(42)

start_date = datetime(2024, 1, 1)
end_date = datetime(2026, 3, 15)  # ~2.25 years of history
dates = pd.date_range(start_date, end_date, freq="D")

warehouses = ["WH-EAST", "WH-WEST", "WH-CENTRAL"]

# Per-SKU base daily demand (units/day) and seasonality profile
sku_profiles = {}
for i, row in enumerate(products_data):
    sku = row[0]
    category = row[2]
    price = row[4]

    # Higher-priced items sell fewer units; cheaper items sell more
    base_demand = max(2, int(80 / price))

    # Seasonality multipliers by month [Jan..Dec]
    if category == "Electronics":
        # Electronics: holiday spike in Nov/Dec, back-to-school in Aug/Sep
        seasonality = [0.8, 0.75, 0.85, 0.9, 0.95, 0.9, 0.95, 1.15, 1.1, 1.0, 1.3, 1.5]
        trend_per_day = 0.0003  # slight upward trend
    elif category == "Office":
        # Office supplies: Q1 budget season bump, steady otherwise
        seasonality = [1.2, 1.15, 1.1, 1.0, 0.95, 0.85, 0.8, 0.9, 1.1, 1.0, 1.0, 0.95]
        trend_per_day = 0.0001
    else:  # Accessories
        # Accessories: relatively flat with mild holiday bump
        seasonality = [0.9, 0.9, 0.95, 1.0, 1.0, 1.0, 0.95, 1.0, 1.0, 1.0, 1.1, 1.15]
        trend_per_day = 0.0002

    sku_profiles[sku] = {
        "base_demand": base_demand,
        "seasonality": seasonality,
        "trend_per_day": trend_per_day,
    }

# Generate transactions
records = []
txn_id = 1
for date in dates:
    day_of_week = date.dayofweek  # 0=Mon, 6=Sun
    weekend_factor = 0.4 if day_of_week >= 5 else 1.0

    for sku, profile in sku_profiles.items():
        month_idx = date.month - 1
        days_since_start = (date - pd.Timestamp(start_date)).days
        seasonal = profile["seasonality"][month_idx]
        trend = 1.0 + profile["trend_per_day"] * days_since_start

        expected = profile["base_demand"] * seasonal * trend * weekend_factor

        # Split across warehouses (weighted)
        for wh, wh_share in [("WH-EAST", 0.45), ("WH-WEST", 0.35), ("WH-CENTRAL", 0.20)]:
            qty = np.random.poisson(lam=max(0.5, expected * wh_share))
            if qty > 0:
                records.append((
                    txn_id,
                    date.strftime("%Y-%m-%d"),
                    sku,
                    wh,
                    int(qty),
                ))
                txn_id += 1

print(f"Generated {len(records):,} transaction records")

# COMMAND ----------

txn_schema = StructType([
    StructField("transaction_id", IntegerType(), False),
    StructField("sale_date", StringType(), False),
    StructField("sku", StringType(), False),
    StructField("warehouse", StringType(), False),
    StructField("quantity_sold", IntegerType(), False),
])

txn_df = spark.createDataFrame(records, schema=txn_schema)
txn_df = txn_df.withColumn("sale_date", F.col("sale_date").cast("date"))

txn_df.write.mode("overwrite").saveAsTable("sales_transactions")

display(
    txn_df.groupBy("sku")
    .agg(
        F.sum("quantity_sold").alias("total_sold"),
        F.countDistinct("sale_date").alias("active_days"),
    )
    .orderBy("sku")
    .limit(10)
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Verify Data

# COMMAND ----------

for table in ["products", "sales_transactions"]:
    count = spark.table(table).count()
    print(f"{CATALOG}.{SCHEMA}.{table}: {count:,} rows")
