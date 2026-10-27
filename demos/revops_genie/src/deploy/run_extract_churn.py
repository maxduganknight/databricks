# Databricks notebook source
"""
Run the churn/QBR PDF extraction — DAB setup-job task.

Reads the committed SQL (unstructured/extract_churn_docs.sql), rebinds the
authored catalog/schema (both the dotted `cat.schema` table qualifier AND the
`/Volumes/cat/schema/...` volume path) to the deployed target, splits on ';',
and executes each statement. Produces raw_churn_parsed → churn_extracted →
fact_churn_reason via ai_parse_document + ai_extract (per-row LLM calls).

Depends on: generate_data (schema exists) + upload_pdfs (PDFs in the volume).

Parameters (base_parameters): catalog, schema
"""

# COMMAND ----------

dbutils.widgets.text("catalog", "", "Catalog")
dbutils.widgets.text("schema",  "", "Schema")
catalog = dbutils.widgets.get("catalog")
schema  = dbutils.widgets.get("schema")
assert catalog and schema, "catalog + schema are required"

# The qualifier the committed SQL was authored against.
SRC_CS = "solution_builder.demo_revops_intelligence"
DST_CS = f"{catalog}.{schema}"

# COMMAND ----------

import os

notebook_path = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
# {bundle_root}/src/deploy/run_extract_churn -> bundle_root
bundle_root = os.path.dirname(os.path.dirname(os.path.dirname(notebook_path)))
sql_path = f"/Workspace{bundle_root}/unstructured/extract_churn_docs.sql"
print(f"Loading SQL: {sql_path}")

with open(sql_path) as f:
    sql_text = f.read()

# Rebind both the dotted table qualifier and the slashed volume path.
sql_text = sql_text.replace(SRC_CS, DST_CS)
sql_text = sql_text.replace(
    "solution_builder/demo_revops_intelligence",
    f"{catalog}/{schema}",
)

# COMMAND ----------

# Drop full-line `--` comments, then split into statements on ';'.
lines = [ln for ln in sql_text.splitlines() if not ln.lstrip().startswith("--")]
statements = [s.strip() for s in "\n".join(lines).split(";") if s.strip()]
print(f"Executing {len(statements)} statements against {DST_CS}")

for i, stmt in enumerate(statements, 1):
    head = " ".join(stmt.split())[:80]
    print(f"[{i}/{len(statements)}] {head}…")
    spark.sql(stmt)

# COMMAND ----------

n = spark.table(f"{DST_CS}.fact_churn_reason").count()
print(f"fact_churn_reason rows: {n}")
assert n > 0, "fact_churn_reason is empty — check the PDFs landed in the volume"
