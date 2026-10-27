"""pdu_latest_status: one row per PDU (PK unit_id) with latest minute stats, thresholds and status.

Recomputed each update over a short lookback of pdu_minute_stats (96 units x 24 h = ~140k rows),
which is cheap and lets threshold edits apply immediately. This is the table synced to Lakebase.
"""

from pyspark import pipelines as dp
from pyspark.sql import functions as F

from utilities import pdu_rules

LOOKBACK_HOURS = int(spark.conf.get("pdu.status_lookback_hours", "24"))
STALE_AFTER_MINUTES = int(spark.conf.get("pdu.stale_after_minutes", "3"))

OUTPUT_COLUMNS = [
    "unit_id", "rack_id", "unit_model", "shelf", "position",
    "status", "breached_metrics", "warn_metrics", "severity_score",
    "breach_started_ts", "last_breach_ts", "breach_minutes_lookback",
    "minute_start", "last_event_ts", "is_stale", "sample_count",
    *[f"{m}_{s}" for m in pdu_rules.METRICS for s in ("min", "max", "avg")],
    "current_avg", "power_kw_avg",
    *[f"{m}_{b}" for m in pdu_rules.METRICS for b in pdu_rules.BOUNDS],
    *[f"{m}_threshold_scope" for m in pdu_rules.METRICS],
    "updated_at",
]


@dp.materialized_view(
    name="pdu_latest_status",
    comment="Latest status per PDU (OK / WARN / BREACH) with breached metrics, breach start and thresholds. PK unit_id.",
    schema="""
      unit_id STRING NOT NULL, rack_id STRING, unit_model STRING, shelf INT, position INT,
      status STRING NOT NULL, breached_metrics ARRAY<STRING>, warn_metrics ARRAY<STRING>, severity_score DOUBLE,
      breach_started_ts TIMESTAMP, last_breach_ts TIMESTAMP, breach_minutes_lookback BIGINT,
      minute_start TIMESTAMP, last_event_ts TIMESTAMP, is_stale BOOLEAN, sample_count BIGINT,
      voltage_min DOUBLE, voltage_max DOUBLE, voltage_avg DOUBLE,
      temperature_min DOUBLE, temperature_max DOUBLE, temperature_avg DOUBLE,
      current_avg DOUBLE, power_kw_avg DOUBLE,
      voltage_breach_min DOUBLE, voltage_warn_min DOUBLE, voltage_warn_max DOUBLE, voltage_breach_max DOUBLE,
      temperature_breach_min DOUBLE, temperature_warn_min DOUBLE, temperature_warn_max DOUBLE, temperature_breach_max DOUBLE,
      voltage_threshold_scope STRING, temperature_threshold_scope STRING,
      updated_at TIMESTAMP,
      CONSTRAINT pdu_latest_status_pk PRIMARY KEY (unit_id)
    """,
)
@dp.expect("thresholds_resolved", "voltage_warn_max IS NOT NULL AND temperature_warn_max IS NOT NULL")
@dp.expect("breach_has_start", "status <> 'BREACH' OR breach_started_ts IS NOT NULL")
def pdu_latest_status():
    stats = spark.read.table("pdu_minute_stats")
    latest_minute = stats.agg(F.max("minute_start").alias("_max_minute"))
    recent = (
        stats.crossJoin(latest_minute)
        .where(F.col("minute_start") >= F.col("_max_minute") - F.expr(f"INTERVAL {LOOKBACK_HOURS} HOURS"))
        .drop("_max_minute")
    )
    thresholds = pdu_rules.resolve_thresholds(recent, spark.read.table("pdu_thresholds"))
    classified = pdu_rules.classify(recent.join(thresholds, "unit_id", "left"))
    return (
        pdu_rules.latest_status(classified, STALE_AFTER_MINUTES)
        .withColumn("updated_at", F.current_timestamp())
        .select(*OUTPUT_COLUMNS)
    )
