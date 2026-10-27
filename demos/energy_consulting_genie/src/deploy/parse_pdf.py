# Databricks notebook source
"""
Parse the assumptions-memo PDF in the UC Volume into a queryable text table —
DAB setup-job task for the Scenario Shift Alert demo.

Runs ai_parse_document over every PDF in the Volume and writes
{catalog}.{schema}.gold_assumptions_doc(doc_path, scenario_id, parsed_text,
page_count). Genie reads parsed_text to quote the analyst rationale for the
SCEN-02 revision. This is the AI Functions beat of the demo.

Requires DBR 17.3+ for ai_parse_document (serverless notebook environment is fine).

Parameters: catalog, schema
"""

# COMMAND ----------

VOLUME = "assumptions_docs"
VOLUME_SUBDIR = "raw_data/pdf"
SCENARIO_ID = "SCEN-02"  # the memo is the Accelerated Transition revision

# COMMAND ----------

dbutils.widgets.text("catalog", "", "Catalog")
dbutils.widgets.text("schema", "", "Schema")
catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
assert catalog and schema, "catalog + schema are required"

volume_path = f"/Volumes/{catalog}/{schema}/{VOLUME}/{VOLUME_SUBDIR}/"
print(f"Parsing PDFs in: {volume_path}")

# COMMAND ----------

spark.sql(f"""
    CREATE OR REPLACE TABLE {catalog}.{schema}.gold_assumptions_doc
    COMMENT 'Parsed text of the assumptions-memo PDF (via ai_parse_document). Genie reads parsed_text to quote the analyst rationale for the SCEN-02 revision.'
    AS
    SELECT
      path AS doc_path,
      '{SCENARIO_ID}' AS scenario_id,
      concat_ws('\\n', transform(variant_get(parsed, '$.document.elements', 'ARRAY<VARIANT>'), e -> variant_get(e, '$.content', 'STRING'))) AS parsed_text,
      CAST(1 AS INT) AS page_count
    FROM (
      SELECT path, ai_parse_document(content, map('version','2.0')) AS parsed
      FROM read_files('{volume_path}', format => 'binaryFile')
    )
    WHERE variant_get(parsed, '$.error_status', 'STRING') IS NULL
""")

# COMMAND ----------

row = spark.sql(f"SELECT COUNT(*) c, MAX(length(parsed_text)) n FROM {catalog}.{schema}.gold_assumptions_doc").collect()[0]
print(f"gold_assumptions_doc: {row['c']} row(s), longest parsed_text = {row['n']} chars")
assert row["c"] >= 1, "No PDF parsed — check upload_pdfs ran and the Volume holds the memo."
