# Databricks notebook source
"""
Export the resolved demo resource IDs as the job's exit value — FINAL task of
the Scenario Shift Alert setup job.

Collects the bundle-resolved IDs (base_parameters) plus the SDK-created Genie
space + alert IDs (task values) and emits them as one JSON via
dbutils.notebook.exit(). This doubles as the demo's resources.json manifest.

Parameters (base_parameters): catalog, schema, dashboard_id, warehouse_id
                              genie_space_id, alert_id (from task values)
"""

# COMMAND ----------

import json

names = ["catalog", "schema", "dashboard_id", "warehouse_id", "genie_space_id", "alert_id"]
for n in names:
    dbutils.widgets.text(n, "", n)
vals = {n: dbutils.widgets.get(n) for n in names}

# Guard: if task-value substitution didn't fire, the value is the literal template.
for k in ("genie_space_id", "alert_id"):
    v = vals[k]
    if v.startswith("{{") and v.endswith("}}"):
        raise RuntimeError(f"{k}={v!r} — task value substitution didn't fire.")

resources = {
    "catalog": vals["catalog"],
    "schema": vals["schema"],
    "warehouse_id": vals["warehouse_id"],
    "dashboard_id": vals["dashboard_id"],
    "genie_space_id": vals["genie_space_id"],
    "alert_id": vals["alert_id"],
    "volume": f"{vals['catalog']}.{vals['schema']}.assumptions_docs",
    "ai_parsed_doc_table": f"{vals['catalog']}.{vals['schema']}.gold_assumptions_doc",
    "alert_source_view": f"{vals['catalog']}.{vals['schema']}.vw_scenario_alert",
}

print("Exporting resources:")
for k, v in resources.items():
    print(f"  {k} = {v}")

# COMMAND ----------

dbutils.notebook.exit(json.dumps(resources))
