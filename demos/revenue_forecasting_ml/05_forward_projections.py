# Databricks notebook source
# MAGIC %md
# MAGIC # Revenue Forecasting - Forward Projections (Q1, Q2 & Q3 2026)
# MAGIC
# MAGIC Generates predictions for future quarters where we don't yet have actuals.
# MAGIC
# MAGIC **Approach**: Use same-week-last-year features as a baseline (captures
# MAGIC seasonality in weather and sales patterns), then update calendar/time
# MAGIC features to reflect the actual future dates. Score with the production model.

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
import math

# Load the production model
model_uri = f"models:/{MODEL_NAME}@production"
model = mlflow.sklearn.load_model(model_uri)

from mlflow import MlflowClient
client = MlflowClient()
model_version_info = client.get_model_version_by_alias(MODEL_NAME, "production")
model_version = model_version_info.version
print(f"Loaded model version: {model_version}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Load Historical Features (for same-week-last-year lookup)

# COMMAND ----------

features_pd = spark.table("sales_features").toPandas()
features_pd["week_start"] = pd.to_datetime(features_pd["week_start"])
features_pd = features_pd.sort_values("week_start").reset_index(drop=True)
features_pd["week_of_year"] = features_pd["week_start"].dt.isocalendar().week.astype(int)

print(f"Feature data: {features_pd['week_start'].min()} to {features_pd['week_start'].max()}")
print(f"Total rows: {len(features_pd)}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Load Weather Data for Seasonal Averages

# COMMAND ----------

weather_pd = spark.table("weather_daily").toPandas()
weather_pd["date"] = pd.to_datetime(weather_pd["date"])
weather_pd["week_of_year"] = weather_pd["date"].dt.isocalendar().week.astype(int)

# Compute average weather by week-of-year across all years (climatological normals)
weather_weekly = weather_pd.groupby("week_of_year").agg(
    avg_temp_c=("avg_temp_c", "mean"),
    max_temp_c=("max_temp_c", "mean"),
    total_precip_mm=("precipitation_mm", "mean"),
).reset_index()

# Days over 17 degrees by week
weather_hot = weather_pd[weather_pd["avg_temp_c"] > 17].groupby(
    ["week_of_year"]
).size().reset_index(name="days_over_17")

# City-specific hot days
cities_of_interest = ["toronto", "vancouver", "montreal", "calgary"]
city_hot = {}
for city in cities_of_interest:
    city_data = weather_pd[(weather_pd["city"] == city.capitalize()) | (weather_pd["city"] == city)]
    city_hot_wk = city_data[city_data["avg_temp_c"] > 17].groupby("week_of_year").size().reset_index(name=f"days_over_17_{city}")
    city_hot[city] = city_hot_wk

print("Weather normals loaded")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Generate Future Feature Rows
# MAGIC
# MAGIC For each future week:
# MAGIC 1. Start with the same-week-last-year feature row as baseline
# MAGIC 2. Update all time/calendar features for the actual future date
# MAGIC 3. Update weather features using climatological averages

# COMMAND ----------

# Define the future weeks we want to project
# Q1 2026: Jan 5 - Mar 30 (13 weeks)
# Q2 2026: April 6 - June 29 (13 weeks)
# Q3 2026: July 6 - Sep 28 (13 weeks)
future_weeks = pd.date_range(start="2026-01-05", periods=39, freq="W-MON")
print(f"Projecting {len(future_weeks)} future weeks: {future_weeks[0].date()} to {future_weeks[-1].date()}")

# Feature columns (must match training)
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

future_rows = []

for future_date in future_weeks:
    woy = future_date.isocalendar()[1]

    # Find same-week-last-year row as baseline
    last_year_match = features_pd[features_pd["week_of_year"] == woy]
    if len(last_year_match) == 0:
        last_year_match = features_pd[abs(features_pd["week_of_year"] - woy) <= 1]

    # Use the most recent year's match
    baseline = last_year_match.iloc[-1].copy()

    # --- Update calendar/time features ---
    baseline["week_start"] = future_date
    baseline["week_of_year"] = woy
    baseline["month"] = future_date.month
    baseline["quarter"] = (future_date.month - 1) // 3 + 1

    # Cyclical encodings
    baseline["week_sin"] = math.sin(2 * math.pi * woy / 52)
    baseline["week_cos"] = math.cos(2 * math.pi * woy / 52)
    baseline["month_sin"] = math.sin(2 * math.pi * future_date.month / 12)
    baseline["month_cos"] = math.cos(2 * math.pi * future_date.month / 12)

    # Days-until features
    xmas = pd.Timestamp(year=2026, month=12, day=25)
    summer_solstice = pd.Timestamp(year=2026, month=6, day=21)
    spring_equinox = pd.Timestamp(year=2026, month=3, day=20)

    baseline["days_before_xmas"] = max((xmas - future_date).days, 0)
    baseline["days_until_summer"] = max((summer_solstice - future_date).days, 0)
    baseline["days_until_spring"] = max((spring_equinox - future_date).days, 0)

    # Holiday / sale event flags (approximate)
    baseline["has_stat_holiday"] = 1 if future_date.month in [7] and woy == 27 else 0  # Canada Day
    baseline["near_sale_event"] = 0

    # --- Update weather features using climatological averages ---
    wx = weather_weekly[weather_weekly["week_of_year"] == woy]
    if len(wx) > 0:
        baseline["avg_temp_c"] = wx.iloc[0]["avg_temp_c"]
        baseline["max_temp_c"] = wx.iloc[0]["max_temp_c"]
        baseline["total_precip_mm"] = wx.iloc[0]["total_precip_mm"]

    # 4-week rolling avg temp (approximate from neighbors)
    nearby_wks = weather_weekly[weather_weekly["week_of_year"].between(max(1, woy - 3), woy)]
    baseline["avg_temp_4w"] = nearby_wks["avg_temp_c"].mean() if len(nearby_wks) > 0 else baseline["avg_temp_c"]
    baseline["temp_change_4w"] = baseline["avg_temp_c"] - baseline["avg_temp_4w"]

    # Days over 17 degrees
    hot = weather_hot[weather_hot["week_of_year"] == woy]
    baseline["days_over_17_degrees_c"] = hot.iloc[0]["days_over_17"] / len(weather_pd["date"].dt.year.unique()) if len(hot) > 0 else 0

    for city in cities_of_interest:
        col_name = f"days_over_17_degrees_c_{city}"
        ch = city_hot[city]
        ch_wk = ch[ch["week_of_year"] == woy]
        baseline[col_name] = ch_wk.iloc[0][f"days_over_17_{city}"] / len(weather_pd["date"].dt.year.unique()) if len(ch_wk) > 0 else 0

    # Temperature x patio season interaction
    baseline["temp_x_patio_season"] = max(baseline["avg_temp_c"], 0) * (1 if baseline["avg_temp_c"] > 17 else 0)

    future_rows.append(baseline)

future_df = pd.DataFrame(future_rows)
print(f"Generated {len(future_df)} future feature rows")
print(f"Date range: {future_df['week_start'].min().date()} to {future_df['week_start'].max().date()}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Score Future Weeks

# COMMAND ----------

# Compute city revenue shares from last 52 weeks of actuals
sales_pd = spark.table("sales_transactions").toPandas()
sales_pd["sale_date"] = pd.to_datetime(sales_pd["sale_date"])
recent_sales = sales_pd[sales_pd["sale_date"] >= sales_pd["sale_date"].max() - pd.DateOffset(weeks=52)]
city_totals = recent_sales.groupby("city")["revenue"].sum()
city_shares = (city_totals / city_totals.sum()).to_dict()

predictions = []

for _, row in future_df.iterrows():
    X = row[feature_columns].values.reshape(1, -1)
    predicted_revenue = model.predict(X)[0]

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
            "actual_weekly_revenue": None,  # No actuals for future weeks
            "model_version": int(model_version),
        })

predictions_df = pd.DataFrame(predictions)

print(f"\nForward Projections:")
for q in predictions_df["predicted_quarter"].unique():
    q_data = predictions_df[predictions_df["predicted_quarter"] == q]
    avg_pred = q_data["predicted_revenue"].mean()
    print(f"  {q}: avg predicted quarterly revenue = ${avg_pred:,.0f} ({len(q_data)} weeks)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Write to revenue_predictions Table

# COMMAND ----------

# Remove any previous forward projection rows (where actual_weekly_revenue IS NULL)
spark.sql("DELETE FROM revenue_predictions WHERE actual_weekly_revenue IS NULL")

df_predictions = spark.createDataFrame(predictions_df)

for col in ["scoring_date", "week_start", "predicted_quarter_start", "predicted_quarter_end"]:
    df_predictions = df_predictions.withColumn(col, df_predictions[col].cast("date"))

df_predictions.write.mode("append").saveAsTable("revenue_predictions")

print(f"Wrote {len(predictions_df)} forward projection rows")
print(f"Quarters covered: {predictions_df['predicted_quarter'].unique().tolist()}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Verification

# COMMAND ----------

display(
    spark.sql("""
        SELECT predicted_quarter,
               COUNT(*) AS weeks,
               ROUND(AVG(predicted_revenue), 0) AS avg_predicted_revenue,
               ROUND(MIN(predicted_revenue), 0) AS min_predicted,
               ROUND(MAX(predicted_revenue), 0) AS max_predicted
        FROM revenue_predictions
        WHERE scoring_date = CURRENT_DATE()
        GROUP BY predicted_quarter
        ORDER BY predicted_quarter
    """)
)
