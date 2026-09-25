# Databricks notebook source
# MAGIC %md
# MAGIC # Revenue Forecasting - Feature Engineering & Feature Store
# MAGIC
# MAGIC Builds the `sales_features` table with:
# MAGIC - **Historical sales features**: rolling sales totals by category (e.g., `2_quarter_total_sales_tables`)
# MAGIC - **Seasonality features**: `days_before_xmas`, `days_until_summer`, etc.
# MAGIC - **Weather/geographic features**: `days_over_17_degrees_c`, `days_over_17_degrees_c_toronto`
# MAGIC
# MAGIC Grain: one row per **week_start_date** (Monday)

# COMMAND ----------

CATALOG = "demand_forecast_demo_catalog"
SCHEMA = "revenue_forecasting"

spark.sql(f"USE CATALOG {CATALOG}")
spark.sql(f"USE SCHEMA {SCHEMA}")

# COMMAND ----------

import pandas as pd
import numpy as np
from datetime import date, timedelta

# Load all source data
sales_pd = spark.table("sales_transactions").toPandas()
sales_pd["sale_date"] = pd.to_datetime(sales_pd["sale_date"])

products_pd = spark.table("products").toPandas()
weather_pd = spark.table("weather_daily").toPandas()
weather_pd["date"] = pd.to_datetime(weather_pd["date"])

dates_pd = spark.table("relevant_dates").toPandas()
dates_pd["date"] = pd.to_datetime(dates_pd["date"])

# Merge category into sales
sales_pd = sales_pd.merge(products_pd[["sku", "category"]], on="sku", how="left")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Weekly Revenue Aggregation

# COMMAND ----------

# Assign each sale to its week (Monday start)
sales_pd["week_start"] = sales_pd["sale_date"] - pd.to_timedelta(sales_pd["sale_date"].dt.weekday, unit="D")

# Total weekly revenue (target variable)
weekly_revenue = sales_pd.groupby("week_start").agg(
    total_revenue=("revenue", "sum"),
    total_units=("quantity_sold", "sum"),
    transaction_count=("transaction_id", "count"),
).reset_index()

# Weekly revenue by category
for cat in ["Tables", "Beds", "Chairs", "Patio Furniture", "Sofas", "Desks"]:
    cat_col = cat.lower().replace(" ", "_")
    cat_weekly = (
        sales_pd[sales_pd["category"] == cat]
        .groupby("week_start")
        .agg(revenue=("revenue", "sum"), units=("quantity_sold", "sum"))
        .reset_index()
        .rename(columns={"revenue": f"weekly_revenue_{cat_col}", "units": f"weekly_units_{cat_col}"})
    )
    weekly_revenue = weekly_revenue.merge(cat_weekly, on="week_start", how="left")

weekly_revenue = weekly_revenue.fillna(0)

# Weekly revenue by city
for city in ["Toronto", "Vancouver", "Montreal", "Calgary", "Edmonton"]:
    city_col = city.lower()
    city_weekly = (
        sales_pd[sales_pd["city"] == city]
        .groupby("week_start")
        .agg(revenue=("revenue", "sum"))
        .reset_index()
        .rename(columns={"revenue": f"weekly_revenue_{city_col}"})
    )
    weekly_revenue = weekly_revenue.merge(city_weekly, on="week_start", how="left")

weekly_revenue = weekly_revenue.fillna(0)
weekly_revenue = weekly_revenue.sort_values("week_start").reset_index(drop=True)

print(f"Weekly revenue rows: {len(weekly_revenue)}")
print(f"Date range: {weekly_revenue['week_start'].min()} to {weekly_revenue['week_start'].max()}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Historical Sales Features (Rolling Windows)

# COMMAND ----------

# Rolling sales features by category
# Format: {window}_total_sales_{category} and {window}_total_revenue_{category}

categories = {
    "tables": "weekly_revenue_tables",
    "beds": "weekly_revenue_beds",
    "chairs": "weekly_revenue_chairs",
    "patio_furniture": "weekly_revenue_patio_furniture",
    "sofas": "weekly_revenue_sofas",
    "desks": "weekly_revenue_desks",
}

# Define rolling windows
windows = {
    "1_week": 1,
    "4_week": 4,
    "1_quarter": 13,   # ~13 weeks
    "2_quarter": 26,    # ~26 weeks
    "4_quarter": 52,    # ~52 weeks
}

for window_name, window_weeks in windows.items():
    # Total revenue rolling window
    weekly_revenue[f"{window_name}_total_revenue"] = (
        weekly_revenue["total_revenue"].rolling(window=window_weeks, min_periods=1).sum()
    )
    # Per-category rolling windows
    for cat_key, cat_col in categories.items():
        weekly_revenue[f"{window_name}_total_sales_{cat_key}"] = (
            weekly_revenue[cat_col].rolling(window=window_weeks, min_periods=1).sum()
        )

# Revenue velocity ratios
weekly_revenue["velocity_4w_vs_13w"] = (
    weekly_revenue["4_week_total_revenue"] / weekly_revenue["1_quarter_total_revenue"].clip(lower=1)
)
weekly_revenue["velocity_13w_vs_52w"] = (
    weekly_revenue["1_quarter_total_revenue"] / weekly_revenue["4_quarter_total_revenue"].clip(lower=1)
)

# Week-over-week and quarter-over-quarter growth
weekly_revenue["wow_revenue_growth"] = weekly_revenue["total_revenue"].pct_change(1).fillna(0)
weekly_revenue["qoq_revenue_growth"] = weekly_revenue["total_revenue"].pct_change(13).fillna(0)

# Lag features
for lag in [1, 2, 4, 13, 26]:
    weekly_revenue[f"revenue_lag_{lag}w"] = weekly_revenue["total_revenue"].shift(lag)

weekly_revenue = weekly_revenue.fillna(0)

print(f"After historical features: {weekly_revenue.shape[1]} columns")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Seasonality Features

# COMMAND ----------

def days_until_christmas(d):
    """Days until the next Christmas from date d."""
    xmas = pd.Timestamp(year=d.year, month=12, day=25)
    delta = (xmas - d).days
    if delta < 0:
        xmas = pd.Timestamp(year=d.year + 1, month=12, day=25)
        delta = (xmas - d).days
    return delta

def days_until_summer(d):
    """Days until June 21 (summer solstice)."""
    summer = pd.Timestamp(year=d.year, month=6, day=21)
    delta = (summer - d).days
    if delta < 0:
        summer = pd.Timestamp(year=d.year + 1, month=6, day=21)
        delta = (summer - d).days
    return delta

def days_until_spring(d):
    """Days until March 20 (spring equinox)."""
    spring = pd.Timestamp(year=d.year, month=3, day=20)
    delta = (spring - d).days
    if delta < 0:
        spring = pd.Timestamp(year=d.year + 1, month=3, day=20)
        delta = (spring - d).days
    return delta

weekly_revenue["days_before_xmas"] = weekly_revenue["week_start"].apply(days_until_christmas)
weekly_revenue["days_until_summer"] = weekly_revenue["week_start"].apply(days_until_summer)
weekly_revenue["days_until_spring"] = weekly_revenue["week_start"].apply(days_until_spring)

# Cyclical encoding of week-of-year and month
weekly_revenue["week_of_year"] = weekly_revenue["week_start"].dt.isocalendar().week.astype(int)
weekly_revenue["month"] = weekly_revenue["week_start"].dt.month
weekly_revenue["quarter"] = weekly_revenue["week_start"].dt.quarter

weekly_revenue["week_sin"] = np.sin(2 * np.pi * weekly_revenue["week_of_year"] / 52)
weekly_revenue["week_cos"] = np.cos(2 * np.pi * weekly_revenue["week_of_year"] / 52)
weekly_revenue["month_sin"] = np.sin(2 * np.pi * weekly_revenue["month"] / 12)
weekly_revenue["month_cos"] = np.cos(2 * np.pi * weekly_revenue["month"] / 12)

# Is near a major sale event (within 2 weeks)
sale_events = dates_pd[dates_pd["event_name"].isin([
    "Black Friday", "Cyber Monday", "Boxing Day",
    "New Year Furniture Sale Start", "Spring Patio Collection Launch"
])]["date"].tolist()

def near_sale_event(d, events, window_days=14):
    for event in events:
        if 0 <= (event - d).days <= window_days:
            return 1
    return 0

weekly_revenue["near_sale_event"] = weekly_revenue["week_start"].apply(
    lambda d: near_sale_event(d, sale_events)
)

# Days in proximity to stat holidays (this week contains a holiday)
stat_holidays = set(dates_pd[dates_pd["is_stat_holiday"] == True]["date"].tolist())

def has_stat_holiday(week_start, holidays):
    for offset in range(7):
        if (week_start + timedelta(days=offset)) in holidays:
            return 1
    return 0

weekly_revenue["has_stat_holiday"] = weekly_revenue["week_start"].apply(
    lambda d: has_stat_holiday(d, stat_holidays)
)

print(f"After seasonality features: {weekly_revenue.shape[1]} columns")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Weather & Geographic Features

# COMMAND ----------

# National weather features (averaged across cities, per week)
weather_pd["week_start"] = weather_pd["date"] - pd.to_timedelta(weather_pd["date"].dt.weekday, unit="D")

# National weekly averages
national_weekly = weather_pd.groupby("week_start").agg(
    avg_temp_c=("avg_temp_c", "mean"),
    max_temp_c=("max_temp_c", "max"),
    total_precip_mm=("precipitation_mm", "sum"),
).reset_index()

# Days over 17C nationally (across all cities, count of city-days)
days_over_17 = (
    weather_pd[weather_pd["avg_temp_c"] > 17]
    .groupby("week_start")
    .size()
    .reset_index(name="days_over_17_degrees_c")
)

weekly_revenue = weekly_revenue.merge(national_weekly, on="week_start", how="left")
weekly_revenue = weekly_revenue.merge(days_over_17, on="week_start", how="left")
weekly_revenue["days_over_17_degrees_c"] = weekly_revenue["days_over_17_degrees_c"].fillna(0)

# City-specific warm day counts
for city in ["Toronto", "Vancouver", "Montreal", "Calgary"]:
    city_warm = (
        weather_pd[(weather_pd["city"] == city) & (weather_pd["avg_temp_c"] > 17)]
        .groupby("week_start")
        .size()
        .reset_index(name=f"days_over_17_degrees_c_{city.lower()}")
    )
    weekly_revenue = weekly_revenue.merge(city_warm, on="week_start", how="left")
    weekly_revenue[f"days_over_17_degrees_c_{city.lower()}"] = (
        weekly_revenue[f"days_over_17_degrees_c_{city.lower()}"].fillna(0)
    )

# Rolling 4-week average temperature (trend)
weekly_revenue["avg_temp_4w"] = weekly_revenue["avg_temp_c"].rolling(4, min_periods=1).mean()
weekly_revenue["temp_change_4w"] = weekly_revenue["avg_temp_c"] - weekly_revenue["avg_temp_4w"]

# Temperature-season interaction
weekly_revenue["temp_x_patio_season"] = (
    weekly_revenue["avg_temp_c"].clip(lower=0) *
    (weekly_revenue["month"].isin([4, 5, 6, 7, 8, 9])).astype(int)
)

weekly_revenue = weekly_revenue.fillna(0)

print(f"After weather features: {weekly_revenue.shape[1]} columns")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Write Feature Store Table

# COMMAND ----------

# Select and order columns for the feature store
feature_cols = [c for c in weekly_revenue.columns if c != "week_start"]
feature_cols = ["week_start"] + sorted([c for c in feature_cols])

df_features = spark.createDataFrame(weekly_revenue[feature_cols])
df_features = df_features.withColumn("week_start", df_features["week_start"].cast("date"))
df_features.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable("sales_features")

print(f"Created sales_features table: {df_features.count()} rows, {len(feature_cols)} columns")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Feature Preview

# COMMAND ----------

# Show sample of key features
key_features = [
    "week_start", "total_revenue",
    "2_quarter_total_sales_tables", "4_quarter_total_sales_beds",
    "1_week_total_sales_chairs", "1_quarter_total_sales_patio_furniture",
    "days_before_xmas", "days_until_summer",
    "days_over_17_degrees_c", "days_over_17_degrees_c_toronto",
    "avg_temp_c", "near_sale_event", "velocity_4w_vs_13w",
]

display(spark.table("sales_features").select(key_features).orderBy("week_start"))
