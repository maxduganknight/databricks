"""Threshold resolution and PDU status rules.

Pure PySpark (no pipeline imports) so the same logic is used by the pipeline and by unit tests.

Threshold semantics (per metric, all bounds optional / nullable):
    breach_min < warn_min <= [accepted range] <= warn_max < breach_max
    * BREACH: minute min < breach_min  or  minute max > breach_max
    * WARN:   not BREACH, and minute min < warn_min  or  minute max > warn_max
    * OK:     otherwise (a metric with no valid samples in the minute is not evaluated)

Scope precedence (most specific wins, per metric): UNIT > RACK > MODEL > GLOBAL.
"""

import csv
from typing import Dict, List, Tuple

from pyspark.sql import Column, DataFrame, Window
from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType, StringType, StructField, StructType

# Metric key (used in thresholds CSV and output column prefixes) -> bronze column
METRICS: Dict[str, str] = {"voltage": "voltage_v", "temperature": "temperature_c"}

# Physically plausible ranges; readings outside are treated as sensor faults (not evaluated).
PLAUSIBLE_RANGES: Dict[str, Tuple[float, float]] = {
    "voltage": (50.0, 400.0),
    "temperature": (-20.0, 120.0),
}

SCOPE_PRIORITY: Dict[str, int] = {"UNIT": 4, "RACK": 3, "MODEL": 2, "GLOBAL": 1}
BOUNDS: List[str] = ["breach_min", "warn_min", "warn_max", "breach_max"]

THRESHOLD_SCHEMA = StructType(
    [
        StructField("scope_type", StringType(), False),
        StructField("scope_value", StringType(), True),
        StructField("metric", StringType(), False),
        StructField("breach_min", DoubleType(), True),
        StructField("warn_min", DoubleType(), True),
        StructField("warn_max", DoubleType(), True),
        StructField("breach_max", DoubleType(), True),
        StructField("description", StringType(), True),
    ]
)

STATUS_OK, STATUS_WARN, STATUS_BREACH = "OK", "WARN", "BREACH"


# --------------------------------------------------------------------------- thresholds
def _to_float(value: str):
    value = (value or "").strip()
    return float(value) if value else None


def parse_thresholds_csv(path: str) -> List[tuple]:
    """Read the (small) thresholds seed CSV into rows matching THRESHOLD_SCHEMA, with validation."""
    rows = []
    with open(path, newline="") as fh:
        for line_no, rec in enumerate(csv.DictReader(fh), start=2):
            if not any((v or "").strip() for v in rec.values()) or (rec.get("scope_type") or "").startswith("#"):
                continue
            scope_type = rec["scope_type"].strip().upper()
            metric = rec["metric"].strip().lower()
            if scope_type not in SCOPE_PRIORITY:
                raise ValueError(f"line {line_no}: unknown scope_type {scope_type!r}")
            if metric not in METRICS:
                raise ValueError(f"line {line_no}: unknown metric {metric!r}")
            scope_value = (rec.get("scope_value") or "").strip() or None
            if scope_type != "GLOBAL" and scope_value is None:
                raise ValueError(f"line {line_no}: scope_value required for {scope_type}")
            b = {k: _to_float(rec.get(k)) for k in BOUNDS}
            ordered = [b[k] for k in BOUNDS if b[k] is not None]
            if ordered != sorted(ordered):
                raise ValueError(f"line {line_no}: bounds must satisfy breach_min <= warn_min <= warn_max <= breach_max")
            rows.append((scope_type, None if scope_type == "GLOBAL" else scope_value, metric,
                         b["breach_min"], b["warn_min"], b["warn_max"], b["breach_max"],
                         (rec.get("description") or "").strip() or None))
    return rows


def resolve_thresholds(units: DataFrame, thresholds: DataFrame) -> DataFrame:
    """One row per unit with the most specific threshold per metric, pivoted wide.

    units: unit_id, rack_id, unit_model.  Output: unit_id, <metric>_<bound>..., <metric>_threshold_scope.
    """
    priority = F.coalesce(
        *[F.when(F.col("t.scope_type") == k, F.lit(v)) for k, v in SCOPE_PRIORITY.items()]
    )
    matches = (
        (F.col("t.scope_type") == "GLOBAL")
        | ((F.col("t.scope_type") == "MODEL") & (F.col("t.scope_value") == F.col("u.unit_model")))
        | ((F.col("t.scope_type") == "RACK") & (F.col("t.scope_value") == F.col("u.rack_id")))
        | ((F.col("t.scope_type") == "UNIT") & (F.col("t.scope_value") == F.col("u.unit_id")))
    )
    candidates = (
        units.select("unit_id", "rack_id", "unit_model").distinct().alias("u")
        .join(F.broadcast(thresholds.alias("t")), matches, "inner")
        .select("u.unit_id", "t.metric", *[f"t.{b}" for b in BOUNDS],
                F.concat_ws(":", "t.scope_type", "t.scope_value").alias("scope"),
                priority.alias("priority"))
    )
    best = (
        candidates
        .withColumn("rn", F.row_number().over(Window.partitionBy("unit_id", "metric").orderBy(F.desc("priority"))))
        .where("rn = 1")
    )
    aggs = []
    for m in METRICS:
        for b in BOUNDS:
            aggs.append(F.max(F.when(F.col("metric") == m, F.col(b))).alias(f"{m}_{b}"))
        aggs.append(F.max(F.when(F.col("metric") == m, F.col("scope"))).alias(f"{m}_threshold_scope"))
    return best.groupBy("unit_id").agg(*aggs)


# --------------------------------------------------------------------------- bronze cleaning
def plausible(metric: str) -> Column:
    lo, hi = PLAUSIBLE_RANGES[metric]
    c = F.col(METRICS[metric])
    return c.isNotNull() & (c >= lo) & (c <= hi)


def plausible_sql(metric: str) -> str:
    lo, hi = PLAUSIBLE_RANGES[metric]
    c = METRICS[metric]
    return f"{c} IS NOT NULL AND {c} BETWEEN {lo} AND {hi}"


def sanitize_readings(df: DataFrame) -> DataFrame:
    """Null out implausible readings so they are excluded from stats without dropping the row."""
    for m, col in METRICS.items():
        df = df.withColumn(col, F.when(plausible(m), F.col(col)))
    return df


def minute_aggregations() -> List[Column]:
    aggs = [F.count(F.lit(1)).alias("sample_count"), F.max("event_ts").alias("last_event_ts")]
    for m, col in METRICS.items():
        aggs += [
            F.count(col).alias(f"{m}_sample_count"),
            F.round(F.min(col), 2).alias(f"{m}_min"),
            F.round(F.max(col), 2).alias(f"{m}_max"),
            F.round(F.avg(col), 2).alias(f"{m}_avg"),
        ]
    aggs += [F.round(F.avg("current_a"), 2).alias("current_avg"), F.round(F.avg("power_kw"), 3).alias("power_kw_avg")]
    return aggs


# --------------------------------------------------------------------------- classification
def _gt(a: Column, b: Column) -> Column:
    return F.coalesce(a > b, F.lit(False))


def _lt(a: Column, b: Column) -> Column:
    return F.coalesce(a < b, F.lit(False))


def classify(df: DataFrame) -> DataFrame:
    """Add status, breached_metrics, warn_metrics and severity_score.

    Requires <metric>_min/_max stats and <metric>_<bound> threshold columns for every metric.
    breached_metrics / warn_metrics contain directional tags such as 'voltage_low', 'temperature_high'.
    severity_score: 0 = inside warn band, 1.0 = at the breach bound, >1 = beyond breach.
    """
    breach_tags, warn_tags, severities = [], [], []
    for m in METRICS:
        mn, mx = F.col(f"{m}_min"), F.col(f"{m}_max")
        bmin, wmin, wmax, bmax = (F.col(f"{m}_{b}") for b in BOUNDS)
        breach_low, breach_high = _lt(mn, bmin), _gt(mx, bmax)
        warn_low = ~breach_low & _lt(mn, wmin)
        warn_high = ~breach_high & _gt(mx, wmax)
        breach_tags += [F.when(breach_low, F.lit(f"{m}_low")), F.when(breach_high, F.lit(f"{m}_high"))]
        warn_tags += [F.when(warn_low, F.lit(f"{m}_low")), F.when(warn_high, F.lit(f"{m}_high"))]
        severities += [
            (mx - wmax) / F.when(bmax > wmax, bmax - wmax),
            (wmin - mn) / F.when(wmin > bmin, wmin - bmin),
        ]
    breached = F.filter(F.array(*breach_tags), lambda x: x.isNotNull())
    warned = F.filter(F.array(*warn_tags), lambda x: x.isNotNull())
    return (
        df.withColumn("breached_metrics", breached)
        .withColumn("warn_metrics", warned)
        .withColumn(
            "status",
            F.when(F.size("breached_metrics") > 0, F.lit(STATUS_BREACH))
            .when(F.size("warn_metrics") > 0, F.lit(STATUS_WARN))
            .otherwise(F.lit(STATUS_OK)),
        )
        .withColumn("severity_score", F.round(F.greatest(F.lit(0.0), *severities), 3))
    )


def latest_status(classified: DataFrame, stale_after_minutes: int = 3) -> DataFrame:
    """Collapse per-minute classified rows (recent lookback) into one row per unit.

    Adds breach_started_ts (start of the current uninterrupted BREACH streak, else null),
    last_breach_ts, breach_minutes_lookback and is_stale (unit's latest minute lags the fleet).
    """
    w_unit = Window.partitionBy("unit_id")
    w_latest = Window.partitionBy("unit_id").orderBy(F.desc("minute_start"))
    is_breach = F.col("status") == STATUS_BREACH
    enriched = (
        classified
        .withColumn("_last_non_breach", F.max(F.when(~is_breach, F.col("minute_start"))).over(w_unit))
        .withColumn("_streak_start", F.min(
            F.when(is_breach & (F.col("_last_non_breach").isNull() | (F.col("minute_start") > F.col("_last_non_breach"))),
                   F.col("minute_start"))).over(w_unit))
        .withColumn("last_breach_ts", F.max(F.when(is_breach, F.col("last_event_ts"))).over(w_unit))
        .withColumn("breach_minutes_lookback", F.sum(is_breach.cast("int")).over(w_unit))
        .withColumn("_fleet_latest", F.max("minute_start").over(Window.partitionBy()))
        .withColumn("_rn", F.row_number().over(w_latest))
    )
    return (
        enriched.where("_rn = 1")
        .withColumn("breach_started_ts", F.when(is_breach, F.col("_streak_start")))
        .withColumn("is_stale", F.col("minute_start") < F.col("_fleet_latest") - F.expr(f"INTERVAL {int(stale_after_minutes)} MINUTES"))
        .drop("_last_non_breach", "_streak_start", "_fleet_latest", "_rn")
    )
