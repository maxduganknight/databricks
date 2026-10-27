# Databricks notebook source
# MAGIC %md
# MAGIC # Revenue Forecasting Demo - Data Setup
# MAGIC **Industry: Furniture Retail (Canada)**
# MAGIC
# MAGIC Generates:
# MAGIC 1. `products` - Furniture SKU catalog
# MAGIC 2. `sales_transactions` - 5 years of weekly sales history (2021-01 to 2025-12)
# MAGIC 3. `weather_daily` - Daily Canadian weather data (public-style dataset)
# MAGIC 4. `relevant_dates` - Holidays, events, and seasonal markers

# COMMAND ----------

CATALOG = "demand_forecast_demo_catalog"
SCHEMA = "revenue_forecasting"

spark.sql(f"USE CATALOG {CATALOG}")
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
spark.sql(f"USE SCHEMA {SCHEMA}")

print(f"Using {CATALOG}.{SCHEMA}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Products Table - Furniture SKUs

# COMMAND ----------

import pandas as pd
from pyspark.sql.types import DoubleType, StringType, StructField, StructType

products = [
    # Tables
    ("TBL-DINING-OAK", "Oak Dining Table", "Tables", 320.0, 799.0),
    ("TBL-DINING-WALNUT", "Walnut Dining Table", "Tables", 410.0, 1099.0),
    ("TBL-COFFEE-MARBLE", "Marble Coffee Table", "Tables", 180.0, 549.0),
    ("TBL-CONSOLE-MODERN", "Modern Console Table", "Tables", 150.0, 449.0),
    ("TBL-SIDE-BRASS", "Brass Side Table", "Tables", 85.0, 249.0),
    ("TBL-PATIO-TEAK", "Teak Patio Dining Table", "Patio Furniture", 280.0, 699.0),
    # Beds
    ("BED-QUEEN-PLATFORM", "Queen Platform Bed", "Beds", 290.0, 899.0),
    ("BED-KING-UPHOLSTERED", "King Upholstered Bed", "Beds", 420.0, 1299.0),
    ("BED-TWIN-WOOD", "Twin Wood Bed Frame", "Beds", 130.0, 399.0),
    ("BED-QUEEN-CANOPY", "Queen Canopy Bed", "Beds", 380.0, 1199.0),
    ("BED-DAYBED-LINEN", "Linen Daybed", "Beds", 210.0, 649.0),
    # Chairs
    ("CHR-DINING-SET4", "Dining Chair Set (4)", "Chairs", 200.0, 599.0),
    ("CHR-ACCENT-VELVET", "Velvet Accent Chair", "Chairs", 160.0, 499.0),
    ("CHR-OFFICE-ERGO", "Ergonomic Office Chair", "Chairs", 220.0, 699.0),
    ("CHR-LOUNGE-LEATHER", "Leather Lounge Chair", "Chairs", 340.0, 1049.0),
    ("CHR-ROCKING-MODERN", "Modern Rocking Chair", "Chairs", 175.0, 549.0),
    # Patio Furniture
    ("PAT-SOFA-WICKER", "Wicker Patio Sofa", "Patio Furniture", 250.0, 749.0),
    ("PAT-SET-5PC", "5-Piece Patio Set", "Patio Furniture", 400.0, 1199.0),
    ("PAT-LOUNGER-TEAK", "Teak Sun Lounger", "Patio Furniture", 180.0, 549.0),
    (
        "PAT-UMBRELLA-CANTILEVER",
        "Cantilever Patio Umbrella",
        "Patio Furniture",
        90.0,
        299.0,
    ),
    ("PAT-FIREPIT-TABLE", "Fire Pit Coffee Table", "Patio Furniture", 220.0, 699.0),
    ("PAT-ADIRONDACK-RESIN", "Resin Adirondack Chair", "Patio Furniture", 60.0, 189.0),
    # Sofas
    ("SOF-SECTIONAL-GREY", "Grey Sectional Sofa", "Sofas", 550.0, 1699.0),
    ("SOF-LOVESEAT-BLUE", "Blue Loveseat", "Sofas", 280.0, 849.0),
    ("SOF-3SEAT-LEATHER", "3-Seat Leather Sofa", "Sofas", 620.0, 1899.0),
    ("SOF-SLEEPER-QUEEN", "Queen Sleeper Sofa", "Sofas", 480.0, 1499.0),
    ("SOF-MODULAR-4PC", "4-Piece Modular Sofa", "Sofas", 700.0, 2199.0),
    # Desks
    ("DSK-STANDING-BAMBOO", "Bamboo Standing Desk", "Desks", 190.0, 599.0),
    ("DSK-WRITING-MID", "Mid-Century Writing Desk", "Desks", 170.0, 549.0),
    ("DSK-EXECUTIVE-WALNUT", "Walnut Executive Desk", "Desks", 350.0, 1099.0),
]

schema = StructType(
    [
        StructField("sku", StringType()),
        StructField("name", StringType()),
        StructField("category", StringType()),
        StructField("unit_cost", DoubleType()),
        StructField("unit_price", DoubleType()),
    ]
)

df_products = spark.createDataFrame(products, schema=schema)
df_products.write.mode("overwrite").saveAsTable("products")
print(f"Created products table: {df_products.count()} SKUs")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Canadian Cities / Regions

# COMMAND ----------

cities = [
    ("Toronto", "Ontario", 43.65, -79.38),
    ("Vancouver", "British Columbia", 49.28, -123.12),
    ("Montreal", "Quebec", 45.50, -73.57),
    ("Calgary", "Alberta", 51.05, -114.07),
    ("Edmonton", "Alberta", 53.55, -113.49),
    ("Ottawa", "Ontario", 45.42, -75.70),
    ("Winnipeg", "Manitoba", 49.90, -97.14),
    ("Halifax", "Nova Scotia", 44.65, -63.57),
]

schema_cities = StructType(
    [
        StructField("city", StringType()),
        StructField("province", StringType()),
        StructField("latitude", DoubleType()),
        StructField("longitude", DoubleType()),
    ]
)

df_cities = spark.createDataFrame(cities, schema=schema_cities)
df_cities.write.mode("overwrite").saveAsTable("cities")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Weather Data - Daily Temperatures by City (5 years)

# COMMAND ----------

from datetime import date, timedelta

import numpy as np

np.random.seed(42)

start_date = date(2021, 1, 1)
end_date = date(2025, 12, 31)
dates = [
    start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1)
]

# Average monthly temps (C) by city - realistic Canadian climate
city_monthly_avg = {
    "Toronto": [-4, -3, 2, 9, 16, 21, 24, 23, 18, 11, 5, -1],
    "Vancouver": [4, 5, 7, 10, 13, 16, 18, 18, 15, 10, 6, 3],
    "Montreal": [-8, -6, 0, 8, 15, 20, 23, 22, 17, 10, 3, -5],
    "Calgary": [-7, -5, -1, 6, 11, 16, 19, 18, 13, 6, -2, -7],
    "Edmonton": [-11, -8, -3, 5, 11, 15, 18, 17, 11, 4, -5, -11],
    "Ottawa": [-9, -7, -1, 7, 14, 20, 22, 21, 16, 9, 2, -6],
    "Winnipeg": [-16, -13, -5, 4, 12, 18, 20, 19, 13, 5, -5, -14],
    "Halifax": [-4, -4, 0, 5, 11, 16, 20, 20, 16, 10, 5, -1],
}

weather_rows = []
for d in dates:
    month_idx = d.month - 1
    day_of_year = d.timetuple().tm_yday
    for city, monthly_temps in city_monthly_avg.items():
        # Smooth between months using sinusoidal interpolation
        base_temp = monthly_temps[month_idx]
        next_month = monthly_temps[(month_idx + 1) % 12]
        day_in_month_pct = d.day / 30.0
        smooth_temp = base_temp + (next_month - base_temp) * day_in_month_pct * 0.3

        # Add daily noise (+/- 5C)
        daily_temp = smooth_temp + np.random.normal(0, 3.0)

        # Year-over-year slight warming trend (+0.1C/year)
        year_offset = (d.year - 2021) * 0.1
        daily_temp += year_offset

        # Precipitation (mm) - higher in spring/fall
        precip_base = 2.5 + 1.5 * np.sin(2 * np.pi * (day_of_year - 100) / 365)
        daily_precip = max(0, np.random.exponential(max(0.5, precip_base)))

        weather_rows.append(
            (
                d.isoformat(),
                city,
                round(daily_temp, 1),
                round(daily_temp - np.random.uniform(3, 8), 1),  # min temp
                round(daily_temp + np.random.uniform(2, 6), 1),  # max temp
                round(daily_precip, 1),
            )
        )

schema_weather = StructType(
    [
        StructField("date", StringType()),
        StructField("city", StringType()),
        StructField("avg_temp_c", DoubleType()),
        StructField("min_temp_c", DoubleType()),
        StructField("max_temp_c", DoubleType()),
        StructField("precipitation_mm", DoubleType()),
    ]
)

df_weather = spark.createDataFrame(weather_rows, schema=schema_weather)
df_weather = df_weather.withColumn("date", df_weather["date"].cast("date"))
df_weather.write.mode("overwrite").saveAsTable("weather_daily")
print(f"Created weather_daily table: {df_weather.count()} rows")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Relevant Dates Table - Holidays & Seasonal Events

# COMMAND ----------

from pyspark.sql.types import BooleanType, IntegerType

relevant_dates_rows = []

for year in range(2021, 2026):
    events = [
        (f"{year}-01-01", "New Year's Day", "holiday", True),
        (f"{year}-02-14", "Valentine's Day", "retail_event", False),
        (f"{year}-02-21", "Family Day", "holiday", True),  # approx
        (f"{year}-03-20", "Spring Equinox", "seasonal", False),
        (f"{year}-04-02", "Good Friday", "holiday", True),  # approx
        (f"{year}-05-24", "Victoria Day", "holiday", True),  # approx
        (f"{year}-05-01", "Spring Sale Season Start", "retail_event", False),
        (f"{year}-06-21", "Summer Solstice", "seasonal", False),
        (f"{year}-06-01", "Patio Season Start", "seasonal", False),
        (f"{year}-07-01", "Canada Day", "holiday", True),
        (f"{year}-08-01", "Civic Holiday", "holiday", True),
        (f"{year}-09-01", "Labour Day", "holiday", True),  # approx
        (f"{year}-09-22", "Fall Equinox", "seasonal", False),
        (f"{year}-10-11", "Thanksgiving", "holiday", True),  # approx
        (f"{year}-10-31", "Halloween", "retail_event", False),
        (f"{year}-11-11", "Remembrance Day", "holiday", True),
        (f"{year}-11-25", "Black Friday", "retail_event", False),  # approx
        (f"{year}-11-28", "Cyber Monday", "retail_event", False),  # approx
        (f"{year}-12-21", "Winter Solstice", "seasonal", False),
        (f"{year}-12-25", "Christmas Day", "holiday", True),
        (f"{year}-12-26", "Boxing Day", "retail_event", True),
        (f"{year}-12-31", "New Year's Eve", "holiday", False),
        # Furniture-specific events
        (f"{year}-01-15", "New Year Furniture Sale Start", "retail_event", False),
        (f"{year}-05-15", "Spring Patio Collection Launch", "retail_event", False),
        (f"{year}-09-10", "Fall Indoor Collection Launch", "retail_event", False),
        (f"{year}-11-01", "Holiday Gift Guide Launch", "retail_event", False),
    ]
    relevant_dates_rows.extend(events)

schema_dates = StructType(
    [
        StructField("date", StringType()),
        StructField("event_name", StringType()),
        StructField("event_type", StringType()),
        StructField("is_stat_holiday", BooleanType()),
    ]
)

df_dates = spark.createDataFrame(relevant_dates_rows, schema=schema_dates)
df_dates = df_dates.withColumn("date", df_dates["date"].cast("date"))
df_dates.write.mode("overwrite").saveAsTable("relevant_dates")
print(f"Created relevant_dates table: {df_dates.count()} rows")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Sales Transactions - 5 Years of Furniture Sales

# COMMAND ----------

from datetime import date, timedelta

import numpy as np

np.random.seed(123)

products_pd = spark.table("products").toPandas()
cities_list = [
    "Toronto",
    "Vancouver",
    "Montreal",
    "Calgary",
    "Edmonton",
    "Ottawa",
    "Winnipeg",
    "Halifax",
]

# City population weights (approximate market share)
city_weights = {
    "Toronto": 0.28,
    "Vancouver": 0.15,
    "Montreal": 0.18,
    "Calgary": 0.10,
    "Edmonton": 0.08,
    "Ottawa": 0.08,
    "Winnipeg": 0.07,
    "Halifax": 0.06,
}

# Category seasonality profiles (monthly multipliers Jan-Dec)
# Key: patio furniture peaks in spring/summer, sofas/beds peak in fall/winter
category_seasonality = {
    "Tables": [0.85, 0.80, 0.90, 1.00, 1.05, 1.00, 0.95, 1.10, 1.15, 1.05, 1.20, 1.30],
    "Beds": [1.15, 1.10, 1.05, 0.95, 0.90, 0.85, 0.80, 0.95, 1.10, 1.05, 1.10, 1.20],
    "Chairs": [0.90, 0.85, 0.95, 1.00, 1.05, 1.00, 0.95, 1.05, 1.10, 1.05, 1.15, 1.25],
    "Patio Furniture": [
        0.20,
        0.25,
        0.50,
        0.90,
        1.40,
        1.70,
        1.80,
        1.50,
        0.90,
        0.40,
        0.15,
        0.10,
    ],
    "Sofas": [1.10, 1.05, 1.00, 0.95, 0.90, 0.85, 0.80, 0.95, 1.15, 1.10, 1.25, 1.35],
    "Desks": [1.20, 1.10, 1.00, 0.95, 0.90, 0.85, 0.85, 1.10, 1.15, 1.00, 1.05, 1.10],
}

# Long-term growth trends per category (daily multiplier)
category_trend = {
    "Tables": 0.00008,
    "Beds": 0.00005,
    "Chairs": 0.00006,
    "Patio Furniture": 0.00012,  # Growing category
    "Sofas": 0.00004,
    "Desks": 0.00010,  # WFH trend
}

# Global compound annual growth rate — ensures multi-quarter revenue trends upward
# even though week-to-week variation creates noise
ANNUAL_GROWTH_RATE = 0.08  # 8% YoY compound growth

# Individual SKU momentum effects (some products gain popularity over time)
sku_momentum = {
    "TBL-COFFEE-MARBLE": 0.00015,  # Viral/trending table - accelerating sales
    "PAT-FIREPIT-TABLE": 0.00020,  # Hot new product - strong momentum
    "DSK-STANDING-BAMBOO": 0.00018,  # WFH boom product
    "CHR-OFFICE-ERGO": 0.00012,  # WFH boom
}

# Patio furniture is temperature-sensitive: sales increase when temps > 10C
# and really spike when temps > 17C

start_date = date(2021, 1, 1)
end_date = date(2025, 12, 31)
total_days = (end_date - start_date).days + 1

# Pre-load weather data for temperature-driven effects
weather_pd = spark.table("weather_daily").toPandas()
weather_pd["date"] = pd.to_datetime(weather_pd["date"]).dt.date

# Pre-compute national average temp by date
national_avg_temp = weather_pd.groupby("date")["avg_temp_c"].mean().to_dict()

# Pre-compute city-level temps
city_temps = {}
for _, row in weather_pd.iterrows():
    city_temps[(row["date"], row["city"])] = row["avg_temp_c"]

# Holiday/event proximity effects
relevant_dates_pd = spark.table("relevant_dates").toPandas()
relevant_dates_pd["date"] = pd.to_datetime(relevant_dates_pd["date"]).dt.date

# Black Friday / Boxing Day dates for sales spikes
sale_event_dates = set()
for _, row in relevant_dates_pd.iterrows():
    if row["event_name"] in (
        "Black Friday",
        "Cyber Monday",
        "Boxing Day",
        "New Year Furniture Sale Start",
        "Spring Patio Collection Launch",
    ):
        # Add a window around the event
        for offset in range(-2, 5):
            sale_event_dates.add(row["date"] + timedelta(days=offset))


# Christmas proximity effect (gift buying ramps up 6 weeks before)
def days_until_christmas(d):
    xmas = date(d.year, 12, 25)
    delta = (xmas - d).days
    if delta < 0:
        xmas = date(d.year + 1, 12, 25)
        delta = (xmas - d).days
    return delta


sales_rows = []
transaction_id = 0

for day_offset in range(total_days):
    current_date = start_date + timedelta(days=day_offset)
    day_of_week = current_date.weekday()
    month_idx = current_date.month - 1
    days_from_start = day_offset

    # Weekend effect: furniture shopping is higher on weekends
    weekend_mult = 1.2 if day_of_week >= 5 else 1.0

    # Holiday/event sale multiplier
    sale_mult = 1.3 if current_date in sale_event_dates else 1.0

    # Christmas proximity (ramps up for gift-able items)
    xmas_days = days_until_christmas(current_date)
    xmas_mult = 1.0 + max(0, (42 - xmas_days) / 42) * 0.2 if xmas_days <= 42 else 1.0

    # National average temp for the day
    nat_temp = national_avg_temp.get(current_date, 5.0)

    for _, product in products_pd.iterrows():
        sku = product["sku"]
        category = product["category"]
        unit_price = product["unit_price"]

        # Base weekly demand (lower-priced items sell more units)
        base_daily = max(1, int(40 / (unit_price / 100)))

        # Seasonality
        seasonal_mult = category_seasonality[category][month_idx]

        # Long-term trend
        trend_mult = 1.0 + category_trend[category] * days_from_start

        # SKU-specific momentum
        if sku in sku_momentum:
            trend_mult += sku_momentum[sku] * days_from_start

        # Temperature effect on patio furniture
        temp_mult = 1.0
        if category == "Patio Furniture":
            if nat_temp > 17:
                temp_mult = 1.5 + (nat_temp - 17) * 0.05
            elif nat_temp > 10:
                temp_mult = 0.8 + (nat_temp - 10) * 0.1
            else:
                temp_mult = max(0.1, 0.3 + nat_temp * 0.05)

        # Compound growth factor (exponential, not linear)
        growth_factor = (1 + ANNUAL_GROWTH_RATE) ** (days_from_start / 365.0)

        # Combined multiplier
        expected_qty = (
            base_daily
            * seasonal_mult
            * trend_mult
            * growth_factor
            * weekend_mult
            * sale_mult
            * xmas_mult
            * temp_mult
        )

        # Distribute across cities
        for city, weight in city_weights.items():
            city_qty = expected_qty * weight

            # City-specific temperature adjustment for patio furniture
            if category == "Patio Furniture":
                city_temp = city_temps.get((current_date, city), nat_temp)
                if city_temp > 17:
                    city_qty *= 1.2
                elif city_temp < 5:
                    city_qty *= 0.5

            # Normally-distributed quantity (tighter variance than Poisson for smoother weekly totals)
            actual_qty = max(0, int(np.random.normal(city_qty, city_qty * 0.05)))

            if actual_qty > 0:
                transaction_id += 1
                revenue = round(actual_qty * unit_price, 2)
                sales_rows.append(
                    (
                        f"TXN-{transaction_id:08d}",
                        current_date.isoformat(),
                        sku,
                        city,
                        int(actual_qty),
                        revenue,
                    )
                )

    # Progress every 6 months
    if day_offset % 180 == 0:
        print(
            f"  Generated through {current_date} ({len(sales_rows):,} transactions so far)"
        )

print(f"Total transactions: {len(sales_rows):,}")

# COMMAND ----------

from pyspark.sql.types import IntegerType

schema_sales = StructType(
    [
        StructField("transaction_id", StringType()),
        StructField("sale_date", StringType()),
        StructField("sku", StringType()),
        StructField("city", StringType()),
        StructField("quantity_sold", IntegerType()),
        StructField("revenue", DoubleType()),
    ]
)

df_sales = spark.createDataFrame(sales_rows, schema=schema_sales)
df_sales = df_sales.withColumn("sale_date", df_sales["sale_date"].cast("date"))
df_sales.write.mode("overwrite").saveAsTable("sales_transactions")

row_count = df_sales.count()
print(f"Created sales_transactions table: {row_count:,} rows")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Verification

# COMMAND ----------

print("=== Data Summary ===")
for table in [
    "products",
    "cities",
    "weather_daily",
    "relevant_dates",
    "sales_transactions",
]:
    count = spark.table(table).count()
    print(f"  {table}: {count:,} rows")

# Quick revenue check
spark.sql("""
    SELECT YEAR(sale_date) as year,
           SUM(revenue) as total_revenue,
           COUNT(*) as transactions
    FROM sales_transactions
    GROUP BY YEAR(sale_date)
    ORDER BY year
""").show()

# Category breakdown
spark.sql("""
    SELECT p.category,
           ROUND(SUM(s.revenue), 0) as total_revenue,
           SUM(s.quantity_sold) as total_units
    FROM sales_transactions s
    JOIN products p ON s.sku = p.sku
    GROUP BY p.category
    ORDER BY total_revenue DESC
""").show()
