# Databricks notebook source
# MAGIC %md
# MAGIC # 02 - Feature Engineering & Demand Forecasting Model
# MAGIC
# MAGIC This notebook:
# MAGIC 1. Engineers time-series features from historical sales (lags, rolling stats, seasonality)
# MAGIC 2. Trains an XGBoost demand forecasting model per SKU, logged to MLflow
# MAGIC 3. Uses recursive multi-step forecasting for 6-month horizon
# MAGIC 4. Writes predictions to the `sales_predictions` table
# MAGIC
# MAGIC Designed to be scheduled weekly to refresh predictions.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Configuration

# COMMAND ----------

CATALOG = "demand_forecast_demo_catalog"
SCHEMA = "demand_forecasting"

spark.sql(f"USE CATALOG {CATALOG}")
spark.sql(f"USE SCHEMA {SCHEMA}")

# COMMAND ----------

# MAGIC %pip install xgboost mlflow
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

CATALOG = "demand_forecast_demo_catalog"
SCHEMA = "demand_forecasting"
spark.sql(f"USE CATALOG {CATALOG}")
spark.sql(f"USE SCHEMA {SCHEMA}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Build Daily Sales Base Table

# COMMAND ----------

from pyspark.sql import functions as F
from pyspark.sql.types import *

# Aggregate daily sales per SKU (across all warehouses)
daily_sales = (
    spark.table("sales_transactions")
    .groupBy("sku", "sale_date")
    .agg(F.sum("quantity_sold").alias("daily_qty"))
    .orderBy("sku", "sale_date")
)

print(f"Daily sales rows: {daily_sales.count():,}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Feature Engineering
# MAGIC
# MAGIC All featurization happens in pandas per-SKU so we can compute lags cleanly.
# MAGIC Features:
# MAGIC - **Seasonal**: month, day_of_week, quarter, is_weekend
# MAGIC - **Lags**: lag_7, lag_14, lag_28 (raw daily qty)
# MAGIC - **Rolling stats**: rolling_7d_avg/std, rolling_28d_avg, rolling_90d_avg
# MAGIC - **Velocity**: ratio of short-term to medium/long-term averages
# MAGIC - **Trend**: days_since_start (linear trend proxy)

# COMMAND ----------

import pandas as pd
import numpy as np

FEATURE_COLS = [
    "month", "day_of_week", "quarter", "is_weekend",
    "lag_7", "lag_14", "lag_28",
    "rolling_7d_avg", "rolling_7d_std", "rolling_28d_avg", "rolling_90d_avg",
    "velocity_ratio_7_28", "velocity_ratio_7_90",
    "days_since_start",
]

def featurize_sku(pdf: pd.DataFrame) -> pd.DataFrame:
    """Add all ML features to a single SKU's daily sales dataframe."""
    pdf = pdf.sort_values("sale_date").reset_index(drop=True)
    pdf["sale_date"] = pd.to_datetime(pdf["sale_date"])

    # Seasonal
    pdf["month"] = pdf["sale_date"].dt.month
    pdf["day_of_week"] = pdf["sale_date"].dt.dayofweek + 1  # 1=Mon..7=Sun
    pdf["quarter"] = pdf["sale_date"].dt.quarter
    pdf["is_weekend"] = (pdf["day_of_week"] >= 6).astype(int)

    # Lags
    pdf["lag_7"] = pdf["daily_qty"].shift(7)
    pdf["lag_14"] = pdf["daily_qty"].shift(14)
    pdf["lag_28"] = pdf["daily_qty"].shift(28)

    # Rolling statistics
    pdf["rolling_7d_avg"] = pdf["daily_qty"].rolling(7, min_periods=1).mean()
    pdf["rolling_7d_std"] = pdf["daily_qty"].rolling(7, min_periods=1).std().fillna(0)
    pdf["rolling_28d_avg"] = pdf["daily_qty"].rolling(28, min_periods=1).mean()
    pdf["rolling_90d_avg"] = pdf["daily_qty"].rolling(90, min_periods=1).mean()

    # Velocity ratios
    pdf["velocity_ratio_7_28"] = pdf["rolling_7d_avg"] / pdf["rolling_28d_avg"].replace(0, np.nan)
    pdf["velocity_ratio_7_90"] = pdf["rolling_7d_avg"] / pdf["rolling_90d_avg"].replace(0, np.nan)

    # Trend
    pdf["days_since_start"] = (pdf["sale_date"] - pdf["sale_date"].min()).dt.days

    # Fill NaN from early-window lags
    pdf[FEATURE_COLS] = pdf[FEATURE_COLS].ffill().bfill().fillna(0)

    return pdf

# COMMAND ----------

# MAGIC %md
# MAGIC ### Featurize all SKUs and persist to Feature Table

# COMMAND ----------

all_daily = daily_sales.toPandas()
skus = all_daily["sku"].unique()
print(f"Featurizing {len(skus)} SKUs...")

featurized_frames = []
for sku in skus:
    sku_pdf = all_daily[all_daily["sku"] == sku].copy()
    featurized_frames.append(featurize_sku(sku_pdf))

features_pdf = pd.concat(featurized_frames, ignore_index=True)
features_df = spark.createDataFrame(features_pdf)
features_df = features_df.withColumn("sale_date", F.col("sale_date").cast("date"))
features_df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable("sales_features")

print(f"Feature table written: {len(features_pdf):,} rows, {len(FEATURE_COLS)} features")
display(features_df.filter(F.col("sku") == "SKU-001").orderBy(F.desc("sale_date")).limit(10))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Train XGBoost per SKU with MLflow
# MAGIC
# MAGIC - Train/val split: last 28 days held out for validation
# MAGIC - Recursive multi-step forecast: predict day t+1, update lag/rolling features, repeat for 180 days
# MAGIC - Each SKU model logged as a nested MLflow run

# COMMAND ----------

import mlflow
import mlflow.xgboost
import xgboost as xgb
from datetime import datetime, timedelta
from sklearn.metrics import mean_absolute_error, mean_squared_error

mlflow.set_experiment(f"/Users/{spark.sql('SELECT current_user()').first()[0]}/demand_forecasting")

# COMMAND ----------

today = datetime.today().date()
current_quarter_end = today + timedelta(days=90)
next_quarter_end = today + timedelta(days=180)

print(f"Forecast period: {today} -> {next_quarter_end}")
print(f"  Current quarter: {today} -> {current_quarter_end}")
print(f"  Next quarter:    {current_quarter_end} -> {next_quarter_end}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Training Loop

# COMMAND ----------

all_predictions = []

with mlflow.start_run(run_name="demand_forecast_xgb_batch") as parent_run:
    mlflow.log_param("num_skus", len(skus))
    mlflow.log_param("forecast_start", str(today))
    mlflow.log_param("forecast_end", str(next_quarter_end))
    mlflow.log_param("model_type", "XGBRegressor")
    mlflow.log_param("features", FEATURE_COLS)

    for sku in skus:
        sku_pdf = features_pdf[features_pdf["sku"] == sku].copy()

        if len(sku_pdf) < 90:
            print(f"  Skipping {sku}: only {len(sku_pdf)} days")
            continue

        # --- Train/Val Split ---
        train = sku_pdf.iloc[:-28]
        val = sku_pdf.iloc[-28:]

        X_train = train[FEATURE_COLS].values
        y_train = train["daily_qty"].values
        X_val = val[FEATURE_COLS].values
        y_val = val["daily_qty"].values

        with mlflow.start_run(run_name=f"xgb_{sku}", nested=True):
            model = xgb.XGBRegressor(
                n_estimators=300,
                max_depth=5,
                learning_rate=0.08,
                subsample=0.8,
                colsample_bytree=0.8,
                reg_alpha=0.1,
                reg_lambda=1.0,
                random_state=42,
            )
            model.fit(
                X_train, y_train,
                eval_set=[(X_val, y_val)],
                verbose=False,
            )

            # --- Validation Metrics ---
            y_pred_val = model.predict(X_val)
            mae = mean_absolute_error(y_val, y_pred_val)
            rmse = float(np.sqrt(mean_squared_error(y_val, y_pred_val)))

            # --- Recursive Multi-Step Forecast ---
            # Seed the rolling state from the last row of actual data
            last_row = sku_pdf.iloc[-1]
            last_date = pd.Timestamp(last_row["sale_date"])
            days_base = int(last_row["days_since_start"])

            # Keep a buffer of recent predictions to compute rolling features
            recent_buffer = list(sku_pdf["daily_qty"].values[-90:])

            future_preds = []
            for offset in range(1, 181):
                fdate = last_date + timedelta(days=offset)

                # Seasonal features
                month = fdate.month
                dow = fdate.weekday() + 1
                quarter = (fdate.month - 1) // 3 + 1
                is_wknd = 1 if dow >= 6 else 0

                # Lag features from buffer
                buf_len = len(recent_buffer)
                lag_7  = recent_buffer[-7]  if buf_len >= 7  else recent_buffer[-1]
                lag_14 = recent_buffer[-14] if buf_len >= 14 else recent_buffer[-1]
                lag_28 = recent_buffer[-28] if buf_len >= 28 else recent_buffer[-1]

                # Rolling features from buffer
                r7  = np.mean(recent_buffer[-7:])
                r7s = np.std(recent_buffer[-7:])  if len(recent_buffer[-7:]) > 1 else 0.0
                r28 = np.mean(recent_buffer[-28:])
                r90 = np.mean(recent_buffer[-90:])

                v_7_28 = r7 / r28 if r28 > 0 else 1.0
                v_7_90 = r7 / r90 if r90 > 0 else 1.0
                ds = days_base + offset

                row = [month, dow, quarter, is_wknd,
                       lag_7, lag_14, lag_28,
                       r7, r7s, r28, r90,
                       v_7_28, v_7_90, ds]

                pred = max(0, float(model.predict(np.array([row]))[0]))
                future_preds.append({"date": fdate, "yhat": pred})
                recent_buffer.append(pred)

            future_df = pd.DataFrame(future_preds)

            # --- Aggregate by Quarter ---
            cq = future_df[future_df["date"].dt.date <= current_quarter_end]
            nq = future_df[
                (future_df["date"].dt.date > current_quarter_end)
                & (future_df["date"].dt.date <= next_quarter_end)
            ]

            cq_total = max(0, int(cq["yhat"].sum()))
            nq_total = max(0, int(nq["yhat"].sum()))

            # Confidence intervals based on validation MAE scaled by horizon
            cq_unc = mae * np.sqrt(len(cq))
            nq_unc = mae * np.sqrt(len(nq))
            cq_lower = max(0, int(cq_total - cq_unc))
            cq_upper = int(cq_total + cq_unc)
            nq_lower = max(0, int(nq_total - nq_unc))
            nq_upper = int(nq_total + nq_unc)

            # --- Log to MLflow ---
            mlflow.log_metrics({
                "val_mae": mae,
                "val_rmse": rmse,
                "current_q_forecast": cq_total,
                "next_q_forecast": nq_total,
                "training_days": len(train),
            })

            # Log feature importance
            importance = dict(zip(FEATURE_COLS, model.feature_importances_))
            for feat, imp in importance.items():
                mlflow.log_metric(f"fi_{feat}", float(imp))

            mlflow.xgboost.log_model(model, artifact_path="xgb_model")

            all_predictions.append({
                "sku": sku,
                "prediction_date": str(today),
                "current_quarter_start": str(today),
                "current_quarter_end": str(current_quarter_end),
                "current_quarter_forecast": cq_total,
                "current_quarter_lower": cq_lower,
                "current_quarter_upper": cq_upper,
                "next_quarter_start": str(current_quarter_end),
                "next_quarter_end": str(next_quarter_end),
                "next_quarter_forecast": nq_total,
                "next_quarter_lower": nq_lower,
                "next_quarter_upper": nq_upper,
                "model_version": parent_run.info.run_id[:8],
            })

        print(f"  {sku}: MAE={mae:.1f} RMSE={rmse:.1f} | cq={cq_total:,} nq={nq_total:,}")

    mlflow.log_param("skus_trained", len(all_predictions))
    mlflow.log_metric("total_skus_trained", len(all_predictions))

print(f"\nCompleted: {len(all_predictions)} SKU forecasts")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Write Predictions Table

# COMMAND ----------

predictions_schema = StructType([
    StructField("sku", StringType(), False),
    StructField("prediction_date", StringType(), False),
    StructField("current_quarter_start", StringType(), False),
    StructField("current_quarter_end", StringType(), False),
    StructField("current_quarter_forecast", IntegerType(), False),
    StructField("current_quarter_lower", IntegerType(), False),
    StructField("current_quarter_upper", IntegerType(), False),
    StructField("next_quarter_start", StringType(), False),
    StructField("next_quarter_end", StringType(), False),
    StructField("next_quarter_forecast", IntegerType(), False),
    StructField("next_quarter_lower", IntegerType(), False),
    StructField("next_quarter_upper", IntegerType(), False),
    StructField("model_version", StringType(), False),
])

pred_df = spark.createDataFrame(all_predictions, schema=predictions_schema)
for col_name in ["prediction_date", "current_quarter_start", "current_quarter_end",
                  "next_quarter_start", "next_quarter_end"]:
    pred_df = pred_df.withColumn(col_name, F.col(col_name).cast("date"))

pred_df.write.mode("overwrite").saveAsTable("sales_predictions")

display(pred_df.orderBy("sku"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Feature Importance Analysis

# COMMAND ----------

# Show which features drive predictions (from last trained model as example)
import json

fi = sorted(importance.items(), key=lambda x: x[1], reverse=True)
print("Top features (last SKU model):")
for feat, imp in fi:
    bar = "#" * int(imp * 100)
    print(f"  {feat:25s} {imp:.3f} {bar}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Revenue Forecast Summary

# COMMAND ----------

summary = (
    pred_df.alias("p")
    .join(spark.table("products").alias("pr"), F.col("p.sku") == F.col("pr.sku"))
    .select(
        "p.sku",
        "pr.name",
        "pr.category",
        "pr.unit_price",
        "p.current_quarter_forecast",
        "p.next_quarter_forecast",
        (F.col("p.current_quarter_forecast") * F.col("pr.unit_price")).alias("current_q_revenue_est"),
        (F.col("p.next_quarter_forecast") * F.col("pr.unit_price")).alias("next_q_revenue_est"),
    )
    .orderBy(F.desc("current_q_revenue_est"))
)

display(summary)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Next Steps
# MAGIC
# MAGIC - Run **03_lakebase_setup** to create the Lakebase operational database
# MAGIC - The `sales_predictions` table will be synced to Lakebase via reverse ETL
# MAGIC - The warehouse manager app reads from Lakebase for real-time decisions
