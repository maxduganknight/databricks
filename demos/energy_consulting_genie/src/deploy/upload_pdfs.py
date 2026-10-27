# Databricks notebook source
"""
Copy the pre-rendered assumptions-memo PDF from the synced workspace into the
UC Volume — DAB setup-job task for the Scenario Shift Alert demo.

The PDF is committed at src/documents/pdf/ and synced to the workspace by the
bundle; this task copies it into
/Volumes/{catalog}/{schema}/assumptions_docs/raw_data/pdf/ where the next task
(parse_pdf) reads it with ai_parse_document.

The user can replace the shipped memo with their own PDF by dropping it into the
same Volume folder and re-running parse_pdf.

Parameters: catalog, schema
"""

# COMMAND ----------

VOLUME = "assumptions_docs"
VOLUME_SUBDIR = "raw_data/pdf"

# COMMAND ----------

dbutils.widgets.text("catalog", "", "Catalog")
dbutils.widgets.text("schema", "", "Schema")
catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
assert catalog and schema, "catalog + schema are required"

VOLUME_PATH = f"/Volumes/{catalog}/{schema}/{VOLUME}/{VOLUME_SUBDIR}"
print(f"Target: {VOLUME_PATH}")

# COMMAND ----------

import os

# Notebook at {bundle_root}/src/deploy/upload_pdfs;
# PDFs at      {bundle_root}/src/documents/pdf/
notebook_path = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
bundle_root = os.path.dirname(os.path.dirname(os.path.dirname(notebook_path)))
pdf_source = f"/Workspace{bundle_root}/src/documents/pdf"
print(f"PDF source: {pdf_source}")

try:
    pdf_files = sorted([f for f in os.listdir(pdf_source) if f.lower().endswith(".pdf")])
except FileNotFoundError:
    raise SystemExit(f"No PDFs found at {pdf_source}. Commit the rendered PDF under src/documents/pdf/.")

print(f"Found {len(pdf_files)} PDFs")

# COMMAND ----------

os.makedirs(VOLUME_PATH, exist_ok=True)
uploaded = 0
for fn in pdf_files:
    src = f"{pdf_source}/{fn}"
    dst = f"{VOLUME_PATH}/{fn}"
    with open(src, "rb") as fr, open(dst, "wb") as fw:
        data = fr.read()
        fw.write(data)
    print(f"  {fn:55s} -> {dst}  ({len(data):,} bytes)")
    uploaded += 1

print(f"\nUploaded {uploaded}/{len(pdf_files)} PDFs.")
