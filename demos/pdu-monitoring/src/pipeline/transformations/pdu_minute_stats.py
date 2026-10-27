"""pdu_minute_stats: per unit per minute voltage/temperature stats from second-level bronze.

Incremental: a streaming read of bronze with a 1-minute watermark and tumbling 1-minute windows,
so each run only processes newly appended seconds. Bronze retention DELETEs are ignored via
skipChangeCommits.
"""

from pyspark import pipelines as dp
from pyspark.sql import functions as F

from utilities import pdu_rules

BRONZE_TABLE = spark.conf.get("pdu.bronze_table")
WATERMARK = spark.conf.get("pdu.watermark", "1 minute")


@dp.temporary_view(name="bronze_pdu_telemetry_clean")
@dp.expect_all_or_drop({
    "has_unit_id": "unit_id IS NOT NULL",
    "has_event_ts": "event_ts IS NOT NULL",
})
@dp.expect_all({
    "plausible_voltage": pdu_rules.plausible_sql("voltage"),
    "plausible_temperature": pdu_rules.plausible_sql("temperature"),
})
def bronze_pdu_telemetry_clean():
    # Implausible readings are kept (so other metrics still count) but nulled before aggregation.
    return spark.readStream.option("skipChangeCommits", "true").table(BRONZE_TABLE)


@dp.table(
    name="pdu_minute_stats",
    comment="Per unit per minute min/max/avg voltage and temperature, sample counts, avg current and power.",
    cluster_by=["unit_id", "minute_start"],
)
@dp.expect("has_samples", "sample_count > 0")
def pdu_minute_stats():
    return (
        pdu_rules.sanitize_readings(spark.readStream.table("bronze_pdu_telemetry_clean"))
        .withWatermark("event_ts", WATERMARK)
        .groupBy("unit_id", "rack_id", "unit_model", "shelf", "position", F.window("event_ts", "1 minute"))
        .agg(*pdu_rules.minute_aggregations())
        .withColumn("minute_start", F.col("window.start"))
        .drop("window")
    )
