# Databricks notebook source
"""
Deploy the governed NPV metric view — DAB setup-job task.

Runs src/metric_view/mv_scenario_npv.sql (CREATE OR REPLACE VIEW ... WITH METRICS
LANGUAGE YAML) via spark.sql so the multi-line YAML body is passed intact, then
validates the governed MEASURE() returns the expected per-scenario NPV.

NPV ($B) = SUM(annual_cashflow_musd)/1000 over the horizon — coherent with the
stored cumulative_npv_busd the dashboard reads. This is the single governed
definition of NPV the Genie space + dashboard both reference.

Parameters: catalog, schema
"""

# COMMAND ----------

dbutils.widgets.text("catalog", "", "Catalog")
dbutils.widgets.text("schema", "", "Schema")
catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
assert catalog and schema, "catalog + schema are required"

# COMMAND ----------

import os

notebook_path = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
bundle_root = os.path.dirname(os.path.dirname(os.path.dirname(notebook_path)))
sql_path = f"/Workspace{bundle_root}/src/metric_view/mv_scenario_npv.sql"
print(f"Loading: {sql_path}")

with open(sql_path) as f:
    sql = f.read()

# The committed SQL is authored against the source catalog.schema; rebind to the
# deployed one (appears in the view name AND the source: line).
SRC_QUALIFIER = "solution_builder.demo_scenario_shift_alert_015b3e"
DST_QUALIFIER = f"{catalog}.{schema}"
sql = sql.replace(SRC_QUALIFIER, DST_QUALIFIER)
print(f"Rebound {SRC_QUALIFIER} -> {DST_QUALIFIER}")

# COMMAND ----------

spark.sql(sql)
print("Metric view mv_scenario_npv created.")

# COMMAND ----------

rows = spark.sql(f"""
  SELECT Scenario, ROUND(MEASURE(`NPV ($B)`), 2) AS npv
  FROM {catalog}.{schema}.mv_scenario_npv
  WHERE Vintage = 'Current'
  GROUP BY Scenario ORDER BY npv DESC
""").collect()
print("Governed NPV by scenario (Current vintage):")
for r in rows:
    print(f"  {r['Scenario']:24s} {r['npv']}")
assert len(rows) == 5, f"expected 5 scenarios, got {len(rows)}"
