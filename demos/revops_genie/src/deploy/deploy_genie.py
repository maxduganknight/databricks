# Databricks notebook source
"""
Deploy the 5 RevOps Genie spaces — DAB setup-job task.

Reuses the authored space definitions in src/genie/build_spaces.py (SPACES), so
there is ONE source of truth for the curated questions / SQLs / story. Builds
the serialized_space payload, rebinds the authored catalog.schema qualifier to
the deployed target, and creates-or-updates each space via the SDK (idempotent
by title).

Spaces (spec 04-ai-bi.md §A):
  Net Revenue Retention · Net-New ARR & Renewal Risk ·
  Forecast Accuracy & Plan Attainment · Churn & Renewal Intelligence ·
  GTM Efficiency & Quota

Depends on: generate_data (tables + sem_* views + predict_net_new_arr) and
run_extract_churn (fact_churn_reason — used by the Churn space).

REQUIRES: databricks-sdk>=0.114.0 (environment_key: sdk_latest).
Parameters (base_parameters): catalog, schema, warehouse_id
"""

# COMMAND ----------

dbutils.widgets.text("catalog", "", "Catalog")
dbutils.widgets.text("schema",  "", "Schema")
dbutils.widgets.text("warehouse_id", "", "Warehouse ID")
catalog      = dbutils.widgets.get("catalog")
schema       = dbutils.widgets.get("schema")
warehouse_id = dbutils.widgets.get("warehouse_id")
assert catalog and schema and warehouse_id, "catalog + schema + warehouse_id required"

SRC_CS = "solution_builder.demo_revops_intelligence"
DST_CS = f"{catalog}.{schema}"

# COMMAND ----------

import json, uuid, os, sys
from databricks.sdk import WorkspaceClient

notebook_path = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
bundle_root = os.path.dirname(os.path.dirname(os.path.dirname(notebook_path)))
sys.path.insert(0, f"/Workspace{bundle_root}/src/genie")
from build_spaces import SPACES  # noqa: E402  (authored space definitions)

def nid():
    return uuid.uuid4().hex

def serialized_space(s):
    """Same payload shape as build_spaces.space(), returned as a JSON string."""
    sq = sorted([{"id": nid(), "question": [q]} for q in s["chips"]], key=lambda x: x["id"])
    ex = sorted([{"id": nid(), "question": [q], "sql": [sql]} for q, sql in s["examples"]],
                key=lambda x: x["id"])
    payload = {
        "version": 2,
        "config": {"sample_questions": sq},
        "data_sources": {"tables": sorted(
            [{"identifier": f"{SRC_CS}.{t}"} for t in s["tables"]],
            key=lambda x: x["identifier"])},
        "instructions": {
            "text_instructions": [{"id": nid(), "content": [s["story"]]}],
            "example_question_sqls": ex,
        },
    }
    # Rebind the authored qualifier to the deployed target (matches table
    # identifiers AND the qualifiers baked inside example SQL bodies).
    return json.dumps(payload).replace(SRC_CS, DST_CS)

# COMMAND ----------

w = WorkspaceClient()
me = w.current_user.me().user_name
parent_path = f"/Workspace/Users/{me}/genie_spaces"
w.workspace.mkdirs(parent_path)

# Index existing spaces by title (paginate — list_spaces returns a response
# object with .spaces + .next_page_token, NOT a generator).
existing = {}
page_token = None
while True:
    resp = w.genie.list_spaces(page_size=200, page_token=page_token)
    for sp in (resp.spaces or []):
        existing[sp.title] = sp.space_id
    if not getattr(resp, "next_page_token", None):
        break
    page_token = resp.next_page_token

# COMMAND ----------

ids = {}
for s in SPACES:
    ss = serialized_space(s)
    title = s["title"]
    if title in existing:
        sid = existing[title]
        print(f"Updating '{title}' -> {sid}")
        w.genie.update_space(space_id=sid, warehouse_id=warehouse_id, serialized_space=ss)
    else:
        print(f"Creating '{title}'")
        created = w.genie.create_space(
            warehouse_id=warehouse_id, title=title, description=s["desc"],
            parent_path=parent_path, serialized_space=ss)
        sid = created.space_id
    ids[title] = sid
    print(f"  {title} -> {sid}")

print(json.dumps(ids, indent=2))
dbutils.jobs.taskValues.set(key="genie_space_ids", value=json.dumps(ids))
