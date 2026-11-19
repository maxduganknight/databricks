"""pdu_recent_readings: second-level readings per PDU for the last hour only (silver).

Serves the app's unit troubleshooting charts so the app never queries bronze. A materialized view
over bronze filtered to readings newer than the retention window: each pipeline update keeps exactly
that window, so rows that age out drop off without a separate trim step.

Time functions such as current_timestamp() are allowed in WHERE for incremental refresh, and bronze
has row tracking and is clustered by (unit_id, event_ts), so a refresh can process only new readings
and readings that left the window (a full recompute still only reads about the last hour of files).
Null keys are filtered with WHERE rather than drop expectations, which would block incremental
refresh together with bronze's NOT NULL columns. Implausible readings are nulled as in pdu_minute_stats.
"""

from pyspark import pipelines as dp
from pyspark.sql import functions as F

from utilities import pdu_rules

BRONZE_TABLE = spark.conf.get("pdu.bronze_table")
RETENTION_MINUTES = int(spark.conf.get("pdu.recent_readings_minutes", "60"))

READING_COLUMNS = [
    "unit_id", "rack_id", "unit_model", "shelf", "position", "event_ts",
    "voltage_v", "current_a", "power_kw", "temperature_c", "humidity_pct",
]


@dp.materialized_view(
    name="pdu_recent_readings",
    comment=(
        f"Second-level PDU readings from the last {RETENTION_MINUTES} minutes as of the latest pipeline update "
        "(silver), for unit troubleshooting. Implausible voltage / temperature readings are nulled."
    ),
    cluster_by=["unit_id", "event_ts"],
)
def pdu_recent_readings():
    cutoff = F.current_timestamp() - F.expr(f"INTERVAL {RETENTION_MINUTES} MINUTES")
    recent = (
        spark.read.table(BRONZE_TABLE)
        .where(F.col("unit_id").isNotNull() & F.col("event_ts").isNotNull() & (F.col("event_ts") >= cutoff))
    )
    return pdu_rules.sanitize_readings(recent).select(*READING_COLUMNS)
