"""pdu_thresholds: accepted bounds per metric, seeded from src/sql/pdu_thresholds_seed.csv.

The CSV in Git is the source of truth: edit it, `databricks bundle deploy`, and the next pipeline
update republishes this table (and re-evaluates pdu_latest_status) - auditable via pull requests.
"""

from pyspark import pipelines as dp

from utilities import pdu_rules

THRESHOLDS_CSV = spark.conf.get("pdu.thresholds_csv")


@dp.materialized_view(
    name="pdu_thresholds",
    comment="Accepted bounds per metric (GLOBAL, MODEL, RACK or UNIT scope). Seeded from the repo CSV.",
)
@dp.expect_all_or_fail({
    "known_scope": "scope_type IN ('GLOBAL', 'MODEL', 'RACK', 'UNIT')",
    "scoped_rows_have_value": "scope_type = 'GLOBAL' OR scope_value IS NOT NULL",
})
def pdu_thresholds():
    rows = pdu_rules.parse_thresholds_csv(THRESHOLDS_CSV)
    return spark.createDataFrame(rows, pdu_rules.THRESHOLD_SCHEMA)
