# Databricks notebook source
# MAGIC %md
# MAGIC # 05 - ETL Feedback Loop
# MAGIC
# MAGIC This notebook syncs operational outcomes back to the Lakehouse so the
# MAGIC forecasting model can learn from manager overrides and stockout events.
# MAGIC
# MAGIC **Feedback signals:**
# MAGIC 1. Reorder decisions (approved/modified/rejected) → Did the manager agree with the model?
# MAGIC 2. Stockout events → The model under-predicted demand
# MAGIC 3. Overstock writedowns → The model over-predicted demand
# MAGIC
# MAGIC Designed to run on a schedule (daily or after each model refresh).

# COMMAND ----------

# MAGIC %md
# MAGIC ## Configuration

# COMMAND ----------

CATALOG = "demand_forecast_demo_catalog"  # Update to match your FEVM workspace catalog
SCHEMA = "demand_forecasting"
LAKEBASE = "demand_forecast_ops"

spark.sql(f"USE CATALOG {CATALOG}")
spark.sql(f"USE SCHEMA {SCHEMA}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Sync Reorder Decisions from Lakebase → Lakehouse

# COMMAND ----------

from pyspark.sql import functions as F

# Read actioned reorder decisions from Lakebase
reorder_decisions = spark.sql(f"""
    SELECT
        queue_id,
        sku,
        warehouse,
        recommended_quantity,
        manager_action,
        modified_quantity,
        manager_notes,
        created_at,
        actioned_at
    FROM {LAKEBASE}.reorder_queue
    WHERE manager_action IS NOT NULL
""")

# Write to Lakehouse Delta table for model training feedback
reorder_decisions.write.mode("append").saveAsTable("reorder_decisions")

decision_counts = (
    reorder_decisions
    .groupBy("manager_action")
    .count()
    .collect()
)
for row in decision_counts:
    print(f"  {row.manager_action}: {row['count']} decisions")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Sync Stockout Events from Lakebase → Lakehouse

# COMMAND ----------

stockout_events = spark.sql(f"""
    SELECT
        event_id,
        sku,
        warehouse,
        stockout_date,
        days_out_of_stock,
        estimated_lost_units,
        resolved_date,
        created_at
    FROM {LAKEBASE}.stockout_events
""")

stockout_events.write.mode("overwrite").saveAsTable("stockout_events")

count = stockout_events.count()
print(f"Synced {count} stockout events to Lakehouse")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Compute Model Accuracy Metrics
# MAGIC
# MAGIC Compare predictions vs. actuals and manager override patterns.

# COMMAND ----------

# MAGIC %sql
# MAGIC -- Model accuracy: how often did the manager agree vs override?
# MAGIC CREATE OR REPLACE VIEW model_accuracy AS
# MAGIC SELECT
# MAGIC     rd.sku,
# MAGIC     p.name AS product_name,
# MAGIC     p.category,
# MAGIC     COUNT(*) AS total_recommendations,
# MAGIC     SUM(CASE WHEN rd.manager_action = 'approved' THEN 1 ELSE 0 END) AS approved,
# MAGIC     SUM(CASE WHEN rd.manager_action = 'modified' THEN 1 ELSE 0 END) AS modified,
# MAGIC     SUM(CASE WHEN rd.manager_action = 'rejected' THEN 1 ELSE 0 END) AS rejected,
# MAGIC     ROUND(
# MAGIC         SUM(CASE WHEN rd.manager_action = 'approved' THEN 1 ELSE 0 END) * 100.0
# MAGIC         / NULLIF(COUNT(*), 0), 1
# MAGIC     ) AS approval_rate_pct,
# MAGIC     -- Average modification delta (how much did managers adjust?)
# MAGIC     ROUND(AVG(
# MAGIC         CASE WHEN rd.manager_action = 'modified'
# MAGIC              THEN rd.modified_quantity - rd.recommended_quantity
# MAGIC              ELSE NULL END
# MAGIC     ), 1) AS avg_modification_delta
# MAGIC FROM reorder_decisions rd
# MAGIC JOIN products p ON rd.sku = p.sku
# MAGIC GROUP BY rd.sku, p.name, p.category
# MAGIC ORDER BY total_recommendations DESC;

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT * FROM model_accuracy;

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Stockout Analysis — Where Did We Under-Predict?

# COMMAND ----------

# MAGIC %sql
# MAGIC CREATE OR REPLACE VIEW stockout_analysis AS
# MAGIC SELECT
# MAGIC     se.sku,
# MAGIC     p.name AS product_name,
# MAGIC     p.category,
# MAGIC     COUNT(*) AS stockout_count,
# MAGIC     SUM(se.days_out_of_stock) AS total_days_out,
# MAGIC     SUM(se.estimated_lost_units) AS total_lost_units,
# MAGIC     ROUND(SUM(se.estimated_lost_units) * p.unit_price, 2) AS estimated_lost_revenue,
# MAGIC     sp.current_quarter_forecast,
# MAGIC     sp.next_quarter_forecast
# MAGIC FROM stockout_events se
# MAGIC JOIN products p ON se.sku = p.sku
# MAGIC LEFT JOIN sales_predictions sp ON se.sku = sp.sku
# MAGIC GROUP BY se.sku, p.name, p.category, p.unit_price,
# MAGIC          sp.current_quarter_forecast, sp.next_quarter_forecast
# MAGIC ORDER BY estimated_lost_revenue DESC;

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT * FROM stockout_analysis;

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Create Weighted Training Signal
# MAGIC
# MAGIC Build a training signal table that the next model training run can use to
# MAGIC weight samples. SKUs where the manager frequently overrides get adjusted
# MAGIC predictions; SKUs with stockouts get higher demand bias.

# COMMAND ----------

# MAGIC %sql
# MAGIC CREATE OR REPLACE TABLE model_feedback_signals AS
# MAGIC SELECT
# MAGIC     p.sku,
# MAGIC     p.category,
# MAGIC     -- Override signal: if managers consistently increase, model underestimates
# MAGIC     COALESCE(ma.avg_modification_delta, 0) AS avg_override_delta,
# MAGIC     COALESCE(ma.approval_rate_pct, 100) AS approval_rate,
# MAGIC     -- Stockout signal: model definitely underestimated
# MAGIC     COALESCE(sa.stockout_count, 0) AS stockout_count,
# MAGIC     COALESCE(sa.total_lost_units, 0) AS total_lost_units,
# MAGIC     -- Demand adjustment factor for next training run
# MAGIC     CASE
# MAGIC         WHEN COALESCE(sa.stockout_count, 0) > 2 THEN 1.15  -- chronic stockouts: +15%
# MAGIC         WHEN COALESCE(sa.stockout_count, 0) > 0 THEN 1.05  -- occasional stockout: +5%
# MAGIC         WHEN COALESCE(ma.avg_modification_delta, 0) > 0 THEN 1.0 + LEAST(0.10, ma.avg_modification_delta / NULLIF(sp.current_quarter_forecast, 0))
# MAGIC         WHEN COALESCE(ma.avg_modification_delta, 0) < 0 THEN 1.0 + GREATEST(-0.10, ma.avg_modification_delta / NULLIF(sp.current_quarter_forecast, 0))
# MAGIC         ELSE 1.0
# MAGIC     END AS demand_adjustment_factor
# MAGIC FROM products p
# MAGIC LEFT JOIN model_accuracy ma ON p.sku = ma.sku
# MAGIC LEFT JOIN stockout_analysis sa ON p.sku = sa.sku
# MAGIC LEFT JOIN sales_predictions sp ON p.sku = sp.sku;

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT * FROM model_feedback_signals
# MAGIC WHERE demand_adjustment_factor != 1.0
# MAGIC ORDER BY demand_adjustment_factor DESC;

# COMMAND ----------

# MAGIC %md
# MAGIC ## Summary
# MAGIC
# MAGIC This ETL feedback loop:
# MAGIC 1. Synced **reorder decisions** and **stockout events** from Lakebase to Lakehouse
# MAGIC 2. Computed **model accuracy metrics** (approval rate, override patterns)
# MAGIC 3. Built a **demand adjustment factor** per SKU for the next model training run
# MAGIC
# MAGIC The `model_feedback_signals` table is consumed by notebook 02 on its next
# MAGIC scheduled run to bias predictions toward real-world outcomes.
