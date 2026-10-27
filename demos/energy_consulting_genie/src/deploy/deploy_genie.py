# Databricks notebook source
"""
Deploy the Scenario Strategy Genie Space — DAB setup-job task.

Loads the committed serialized space (src/genie/genie_space.json), substitutes
the authored catalog.schema with the deployed one, then creates or updates the
space via the SDK. Idempotent: searches by title, updates if present.

REQUIRES: databricks-sdk>=0.114.0 (environment_key: sdk_latest).

Parameters: catalog, schema, warehouse_id
Outputs (task value): genie_space_id
"""

# COMMAND ----------

SPACE_TITLE = "Scenario Strategy_015b3e"
SPACE_DESCRIPTION = (
    "Strategic scenario projections for a consultant advising on 10-20 year "
    "energy profitability. The Accelerated Transition scenario swung from attractive (~$4.2B) "
    "to marginal (~$2.6B), -38%, ~3 weeks ago, driven by carbon-price floor, policy timing, and "
    "gas demand assumptions. Ask which scenario changed and why; the assumptions-memo PDF is queryable."
)

# The catalog.schema the committed genie_space.json was authored against.
SRC_QUALIFIER = "solution_builder.demo_scenario_shift_alert_015b3e"

# COMMAND ----------

dbutils.widgets.text("catalog", "", "Catalog")
dbutils.widgets.text("schema", "", "Schema")
dbutils.widgets.text("warehouse_id", "", "Warehouse ID")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
warehouse_id = dbutils.widgets.get("warehouse_id")
assert catalog and schema and warehouse_id, "catalog + schema + warehouse_id are required"

print(f"Deploying Genie Space: '{SPACE_TITLE}'  ->  {catalog}.{schema}")

# COMMAND ----------

import json
import os
from databricks.sdk import WorkspaceClient

notebook_path = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
bundle_root = os.path.dirname(os.path.dirname(os.path.dirname(notebook_path)))
config_path = f"/Workspace{bundle_root}/src/genie/genie_space.json"
print(f"Loading: {config_path}")

with open(config_path) as f:
    serialized = f.read()

DST_QUALIFIER = f"{catalog}.{schema}"
n = serialized.count(SRC_QUALIFIER)
substituted = serialized.replace(SRC_QUALIFIER, DST_QUALIFIER)
print(f"Substituted {n} occurrences of {SRC_QUALIFIER} -> {DST_QUALIFIER}")

space_payload = json.loads(substituted)  # validate it still parses
print(f"data_sources.tables: {len(space_payload['data_sources']['tables'])}")

# COMMAND ----------

w = WorkspaceClient()

existing_id = None
page_token = None
while True:
    resp = w.genie.list_spaces(page_size=200, page_token=page_token)
    for sp in (resp.spaces or []):
        if sp.title == SPACE_TITLE:
            existing_id = sp.space_id
            break
    if existing_id or not getattr(resp, "next_page_token", None):
        break
    page_token = resp.next_page_token

# COMMAND ----------

if existing_id:
    print(f"Updating space {existing_id}...")
    w.genie.update_space(space_id=existing_id, warehouse_id=warehouse_id, serialized_space=substituted)
    space_id = existing_id
else:
    print("Creating new space...")
    created = w.genie.create_space(
        warehouse_id=warehouse_id, title=SPACE_TITLE,
        description=SPACE_DESCRIPTION, serialized_space=substituted,
    )
    space_id = created.space_id

print(f"Genie space ready: {space_id}")
dbutils.jobs.taskValues.set(key="genie_space_id", value=space_id)
