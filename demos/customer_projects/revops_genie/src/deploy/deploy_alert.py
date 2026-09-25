# Databricks notebook source
"""
Deploy the Genie One scheduled insight — DAB setup-job task (spec 06 §B).

Reads the portable template alert/scheduled_insight.json, substitutes
${USER_ID}/${CATALOG}/${SCHEMA}, and POSTs it to the Genie One scheduled-insights
API. This is the "retention-control" check that finds Maya Chen: it monitors
Mid-Market NRR vs the 100% control line and at-risk Enterprise ARR, weekly
Mondays 06:00 ET.

Depends on: generate_data + run_extract_churn (the insight resolves against the
sem_* views + fact_churn_reason).

Parameters (base_parameters): catalog, schema
"""

# COMMAND ----------

dbutils.widgets.text("catalog", "", "Catalog")
dbutils.widgets.text("schema",  "", "Schema")
catalog = dbutils.widgets.get("catalog")
schema  = dbutils.widgets.get("schema")
assert catalog and schema

# COMMAND ----------

import json, os
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
user_id = w.current_user.me().id

notebook_path = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
bundle_root = os.path.dirname(os.path.dirname(os.path.dirname(notebook_path)))
tmpl_path = f"/Workspace{bundle_root}/alert/scheduled_insight.json"
print(f"Loading: {tmpl_path}")

with open(tmpl_path) as f:
    raw = f.read()

# Explicit token replace (NOT string.Template / expandvars — the prompt contains
# a literal "$5,000,000" that a $-placeholder parser would choke on).
raw = (raw.replace("${USER_ID}", str(user_id))
          .replace("${CATALOG}", catalog)
          .replace("${SCHEMA}", schema))
body = json.loads(raw)

# COMMAND ----------

resp = w.api_client.do(
    "POST", "/api/2.0/alerts-internal/scheduled-insights", body=body,
)
insight_name = resp.get("name") if isinstance(resp, dict) else str(resp)
print(f"Scheduled insight created: {insight_name}")
dbutils.jobs.taskValues.set(key="scheduled_insight_name", value=str(insight_name))
