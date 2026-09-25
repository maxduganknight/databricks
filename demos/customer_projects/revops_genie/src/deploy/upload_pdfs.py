# Databricks notebook source
"""
Copy the churn/QBR PDFs from the synced workspace to the UC volume — DAB
setup-job task. run_extract_churn.py reads them back via ai_parse_document.

The bundle's sync.include uploads unstructured/raw_data/pdf/*.pdf to the
workspace; this notebook copies them into
/Volumes/{catalog}/{schema}/raw_churn_docs/pdf/ (the path the extraction SQL
reads from).

Parameters (base_parameters): catalog, schema
"""

# COMMAND ----------

import os

# UC volume the PDFs land in (extract_churn_docs.sql reads from raw_churn_docs/pdf/).
VOLUME = "raw_churn_docs"
SUBDIR = "pdf"

# COMMAND ----------

dbutils.widgets.text("catalog", "", "Catalog")
dbutils.widgets.text("schema",  "", "Schema")
catalog = dbutils.widgets.get("catalog")
schema  = dbutils.widgets.get("schema")
assert catalog and schema

VOLUME_PATH = f"/Volumes/{catalog}/{schema}/{VOLUME}/{SUBDIR}"
os.makedirs(VOLUME_PATH, exist_ok=True)
print(f"Target: {VOLUME_PATH}")

# COMMAND ----------

notebook_path = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
# {bundle_root}/src/deploy/upload_pdfs -> bundle_root
bundle_root = os.path.dirname(os.path.dirname(os.path.dirname(notebook_path)))
pdf_source  = f"/Workspace{bundle_root}/unstructured/raw_data/pdf"
print(f"PDF source: {pdf_source}")

try:
    pdf_files = sorted([f for f in os.listdir(pdf_source) if f.lower().endswith(".pdf")])
except FileNotFoundError:
    raise SystemExit(
        f"No PDFs found at {pdf_source}. Pre-render them locally with "
        f"`python unstructured/generate_churn_docs.py` before `databricks bundle deploy`."
    )
print(f"Found {len(pdf_files)} PDFs")

# COMMAND ----------

uploaded = 0
for fn in pdf_files:
    with open(f"{pdf_source}/{fn}", "rb") as fr:
        data = fr.read()
    with open(f"{VOLUME_PATH}/{fn}", "wb") as fw:
        fw.write(data)
    print(f"  {fn:35s} → {VOLUME_PATH}/{fn}  ({len(data):,} bytes)")
    uploaded += 1

print(f"\nUploaded {uploaded}/{len(pdf_files)} PDFs.")
