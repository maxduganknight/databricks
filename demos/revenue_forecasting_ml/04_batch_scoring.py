# Databricks notebook source
# MAGIC %md
# MAGIC # Revenue Forecasting - Batch Scoring Job
# MAGIC
# MAGIC Runs weekly to:
# MAGIC 1. Load latest features from `sales_features`
# MAGIC 2. Score with the production model
# MAGIC 3. Write predictions to `revenue_predictions` table
# MAGIC
# MAGIC Designed to be scheduled as a Databricks Job (weekly, Monday AM)

# COMMAND ----------

CATALOG = "demand_forecast_demo_catalog"
SCHEMA = "revenue_forecasting"
MODEL_NAME = f"{CATALOG}.{SCHEMA}.revenue_forecast_model"

spark.sql(f"USE CATALOG {CATALOG}")
spark.sql(f"USE SCHEMA {SCHEMA}")

# COMMAND ----------

import pandas as pd
import numpy as np
import mlflow
from datetime import date, timedelta

# Load the production model
model_uri = f"models:/{MODEL_NAME}@production"
model = mlflow.sklearn.load_model(model_uri)

# Get model version info
from mlflow import MlflowClient
client = MlflowClient()
model_version_info = client.get_model_version_by_alias(MODEL_NAME, "production")
model_version = model_version_info.version
print(f"Loaded model version: {model_version}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Load Latest Features

# COMMAND ----------

features_pd = spark.table("sales_features").toPandas()
features_pd["week_start"] = pd.to_datetime(features_pd["week_start"])
features_pd = features_pd.sort_values("week_start")

# Use the most recent row as the scoring input
latest_row = features_pd.iloc[-1:]
scoring_date = latest_row["week_start"].values[0]

print(f"Scoring from week: {scoring_date}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Feature Selection (must match training)

# COMMAND ----------

exclude_cols = [
    "week_start", "total_revenue", "total_units", "transaction_count",
    "target_next_quarter_revenue",
    "weekly_revenue_tables", "weekly_revenue_beds", "weekly_revenue_chairs",
    "weekly_revenue_patio_furniture", "weekly_revenue_sofas", "weekly_revenue_desks",
    "weekly_units_tables", "weekly_units_beds", "weekly_units_chairs",
    "weekly_units_patio_furniture", "weekly_units_sofas", "weekly_units_desks",
    "weekly_revenue_toronto", "weekly_revenue_vancouver", "weekly_revenue_montreal",
    "weekly_revenue_calgary", "weekly_revenue_edmonton",
]

feature_columns = [c for c in features_pd.columns if c not in exclude_cols]

# COMMAND ----------

# MAGIC %md
# MAGIC ## Score: Predict Next Quarter Revenue

# COMMAND ----------

# Compute city revenue shares from last 52 weeks of actuals
sales_pd = spark.table("sales_transactions").toPandas()
sales_pd["sale_date"] = pd.to_datetime(sales_pd["sale_date"])
recent_sales = sales_pd[sales_pd["sale_date"] >= sales_pd["sale_date"].max() - pd.DateOffset(weeks=52)]
city_totals = recent_sales.groupby("city")["revenue"].sum()
city_shares = (city_totals / city_totals.sum()).to_dict()
print(f"City shares: {city_shares}")

# Score the latest week plus a rolling window of recent weeks for trend visualization
recent_weeks = features_pd.tail(26)  # Last 6 months of scoring context

predictions = []
for _, row in recent_weeks.iterrows():
    X = row[feature_columns].values.reshape(1, -1)
    predicted_revenue = model.predict(X)[0]

    # Confidence interval (based on historical model error)
    # Using 10% band as approximate - could be replaced with quantile regression
    lower = predicted_revenue * 0.90
    upper = predicted_revenue * 1.10

    week_start = row["week_start"]
    next_q_month = ((week_start.month - 1) // 3) * 3 + 4
    if next_q_month > 12:
        quarter_start = pd.Timestamp(year=week_start.year + 1, month=next_q_month - 12, day=1)
    else:
        quarter_start = pd.Timestamp(year=week_start.year, month=next_q_month, day=1)

    quarter_end = quarter_start + pd.DateOffset(months=3) - pd.DateOffset(days=1)

    for city, share in city_shares.items():
        predictions.append({
            "scoring_date": pd.Timestamp(date.today()),
            "week_start": week_start,
            "city": city,
            "predicted_quarter": f"{quarter_start.year}-Q{(quarter_start.month - 1) // 3 + 1}",
            "predicted_quarter_start": quarter_start,
            "predicted_quarter_end": quarter_end,
            "predicted_revenue": round(predicted_revenue * share, 2),
            "predicted_revenue_lower": round(lower * share, 2),
            "predicted_revenue_upper": round(upper * share, 2),
            "actual_weekly_revenue": round(row["total_revenue"] * share, 2),
            "model_version": int(model_version),
        })

predictions_df = pd.DataFrame(predictions)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Write to revenue_predictions Table

# COMMAND ----------

from pyspark.sql.types import StructType, StructField, StringType, DoubleType, DateType, IntegerType, TimestampType

df_predictions = spark.createDataFrame(predictions_df)

# Cast date columns
for col in ["scoring_date", "week_start", "predicted_quarter_start", "predicted_quarter_end"]:
    df_predictions = df_predictions.withColumn(col, df_predictions[col].cast("date"))

# Overwrite predictions table (schema changed to include city column)
df_predictions.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable("revenue_predictions")

print(f"Wrote {len(predictions_df)} prediction rows")
print(f"Latest prediction: {predictions_df.iloc[-1]['predicted_quarter']} = "
      f"${predictions_df.iloc[-1]['predicted_revenue']:,.0f}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Verification

# COMMAND ----------

# Show latest predictions
display(
    spark.sql("""
        SELECT scoring_date, week_start, predicted_quarter,
               predicted_revenue, predicted_revenue_lower, predicted_revenue_upper,
               actual_weekly_revenue, model_version
        FROM revenue_predictions
        ORDER BY scoring_date DESC, week_start DESC
        LIMIT 20
    """)
)
