"""Predictive-maintenance features and labels for PDU breach-risk scoring.

Shared by the training notebook and the 12-hourly batch scoring job so both compute exactly
the same inputs.

* Labels: one row per unit per scoring time (00:00 and 12:00 UTC). ``label`` = 1 when the unit has
  a *sustained* breach (at least ``min_breach_minutes`` minutes whose minute-average voltage or
  temperature is outside the unit's effective breach limits) in the following ``horizon_hours``.
* Features: Feature Views (Databricks Feature Store) rolling-window aggregations over
  ``pdu_minute_stats`` and the maintenance actions table, computed point-in-time correctly by
  ``FeatureEngineeringClient.create_training_set``. A few cheap derived columns (trends, headroom)
  are added afterwards in pandas by :func:`add_derived_features`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import numpy as np
import pandas as pd

SCORING_CADENCE_HOURS = 12
ENTITY = "unit_id"
TS = "scoring_ts"


@dataclass(frozen=True)
class PMConfig:
    catalog: str = "mdk_demo_catalog"
    schema: str = "pdu_monitoring"
    ops_schema: str = "ops_history"
    maintenance_table: str = "maintenance_actions"
    horizon_hours: int = 12
    min_breach_minutes: int = 5
    # Rows where the unit is already in a sustained breach just before scoring time are flagged:
    # those are monitoring problems, not predictions.
    already_breaching_lookback_hours: int = 2

    @property
    def minute_stats(self) -> str:
        return f"{self.catalog}.{self.schema}.pdu_minute_stats"

    @property
    def latest_status(self) -> str:
        return f"{self.catalog}.{self.schema}.pdu_latest_status"

    @property
    def maintenance(self) -> str:
        return f"{self.catalog}.{self.ops_schema}.{self.maintenance_table}"


# --------------------------------------------------------------------------- labels / spine

def unit_attributes(spark, cfg: PMConfig):
    """Static per-unit attributes and effective breach limits (current fleet = latest status)."""
    return spark.sql(f"""
      SELECT unit_id, rack_id, unit_model, shelf, position,
             voltage_breach_min, voltage_breach_max, voltage_warn_min, voltage_warn_max,
             temperature_breach_max, temperature_warn_max
      FROM {cfg.latest_status}
    """)


def label_spine(spark, cfg: PMConfig, start_ts=None, end_ts=None):
    """One row per unit per 12 h scoring time with the breach-in-next-horizon label.

    Columns: unit_id, scoring_ts, label, breach_minutes_next, already_breaching, label_complete,
    plus static unit attributes. ``label_complete`` is False when the horizon extends past the
    newest telemetry (those rows are only usable for scoring, never for training/evaluation).
    """
    h = cfg.horizon_hours
    cad = SCORING_CADENCE_HOURS * 3600
    lb = cfg.already_breaching_lookback_hours
    where = []
    if start_ts:
        where.append(f"minute_start >= timestamp'{start_ts}' - INTERVAL {lb} HOURS")
    if end_ts:
        where.append(f"minute_start < timestamp'{end_ts}' + INTERVAL {h} HOURS")
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    return spark.sql(f"""
      WITH attrs AS (
        SELECT unit_id, rack_id, unit_model, shelf, position,
               voltage_breach_min, voltage_breach_max, temperature_breach_max,
               temperature_warn_max, voltage_warn_min, voltage_warn_max
        FROM {cfg.latest_status}
      ),
      m AS (
        SELECT s.unit_id, s.minute_start,
               CASE WHEN s.temperature_avg > a.temperature_breach_max
                      OR s.voltage_avg < a.voltage_breach_min
                      OR s.voltage_avg > a.voltage_breach_max THEN 1 ELSE 0 END AS is_breach
        FROM {cfg.minute_stats} s JOIN attrs a USING (unit_id)
        {where_sql}
      ),
      bounds AS (SELECT max(minute_start) AS max_minute FROM m),
      grid AS (
        SELECT a.unit_id, t.scoring_ts
        FROM attrs a
        CROSS JOIN (
          SELECT explode(sequence(lo, hi, INTERVAL {SCORING_CADENCE_HOURS} HOURS)) AS scoring_ts
          FROM (
            SELECT timestamp_seconds((CAST(floor(unix_timestamp(min(minute_start)) / {cad}) AS BIGINT) + 1) * {cad}) AS lo,
                   timestamp_seconds(CAST(floor(unix_timestamp(max(minute_start)) / {cad}) AS BIGINT) * {cad}) AS hi
            FROM m)) t
      )
      SELECT g.unit_id, g.scoring_ts,
             coalesce(sum(CASE WHEN m.minute_start >= g.scoring_ts
                                AND m.minute_start < g.scoring_ts + INTERVAL {h} HOURS
                               THEN m.is_breach END), 0) AS breach_minutes_next,
             coalesce(sum(CASE WHEN m.minute_start < g.scoring_ts THEN m.is_breach END), 0)
               >= {cfg.min_breach_minutes} AS already_breaching,
             g.scoring_ts + INTERVAL {h} HOURS <= (SELECT max_minute FROM bounds) AS label_complete
      FROM grid g
      LEFT JOIN m
        ON m.unit_id = g.unit_id
       AND m.minute_start >= g.scoring_ts - INTERVAL {lb} HOURS
       AND m.minute_start < g.scoring_ts + INTERVAL {h} HOURS
      GROUP BY g.unit_id, g.scoring_ts
    """).selectExpr("*", f"CAST(breach_minutes_next >= {cfg.min_breach_minutes} AS INT) AS label") \
        .join(unit_attributes(spark, cfg), "unit_id")


# --------------------------------------------------------------------------- Feature Views

def _windows():
    return {"1h": timedelta(hours=1), "6h": timedelta(hours=6),
            "24h": timedelta(hours=24), "72h": timedelta(hours=72)}


def feature_specs(cfg: PMConfig, include_maintenance: bool = True):
    """Name -> (source table, filter_condition, aggregation class name, input column, window)."""
    ms = cfg.minute_stats
    w = _windows()
    specs = {}
    for win in ("1h", "6h", "24h", "72h"):
        specs[f"temp_avg_{win}"] = (ms, None, "Avg", "temperature_avg", w[win])
        specs[f"temp_max_{win}"] = (ms, None, "Max", "temperature_max", w[win])
        specs[f"current_avg_{win}"] = (ms, None, "Avg", "current_avg", w[win])
        specs[f"volt_avg_{win}"] = (ms, None, "Avg", "voltage_avg", w[win])
    for win in ("6h", "24h"):
        specs[f"volt_min_{win}"] = (ms, None, "Min", "voltage_min", w[win])
        specs[f"volt_std_{win}"] = (ms, None, "StddevPop", "voltage_avg", w[win])
        specs[f"temp_std_{win}"] = (ms, None, "StddevPop", "temperature_avg", w[win])
        specs[f"current_std_{win}"] = (ms, None, "StddevPop", "current_avg", w[win])
        # Minutes with a voltage sag / spike into the warning band, and hot minutes.
        specs[f"sag_minutes_{win}"] = (ms, "voltage_min < 228 OR voltage_max > 252", "Count", "unit_id", w[win])
        specs[f"hot_minutes_{win}"] = (ms, "temperature_max > 45", "Count", "unit_id", w[win])
        specs[f"sample_minutes_{win}"] = (ms, None, "Count", "unit_id", w[win])
    if include_maintenance:
        mt = cfg.maintenance
        reset = "action_type IN ('PREVENTIVE_REPAIR','CORRECTIVE_REPAIR','REPLACEMENT')"
        specs["last_repair_ts_30d"] = (mt, reset, "Max", "action_ts", timedelta(days=30))
        specs["repairs_30d"] = (mt, reset, "Count", "action_id", timedelta(days=30))
    return specs


def _ts_column(table: str) -> str:
    return "action_ts" if table.endswith("maintenance_actions") else "minute_start"


# RollingWindow (continuous) supports only SUM / AVG / COUNT / STDDEV_POP. Min / Max use a batch
# SlidingWindow that slides every hour; scoring times are on the hour, so the latest slide ending
# at or before scoring time covers exactly the preceding window.
_ROLLING_OPS = {"Sum", "Avg", "Count", "StddevPop"}


def _window(E, op: str, duration: timedelta):
    if op in _ROLLING_OPS:
        return E.RollingWindow(window_duration=duration)
    # slide must be strictly shorter than the window (1 h windows slide every 30 min).
    slide = min(timedelta(hours=1), duration / 2)
    return E.SlidingWindow(window_duration=duration, slide_duration=slide)


def training_frame(spine_df):
    """Add the timeseries column names the Feature definitions declare (minute_start for
    pdu_minute_stats features, action_ts for maintenance features), both equal to scoring_ts."""
    return (spine_df.withColumn("minute_start", spine_df[TS])
                    .withColumn("action_ts", spine_df[TS]))


def get_or_create_features(fe, cfg: PMConfig, names: list[str], include_maintenance: bool = True):
    """Return Unity Catalog Feature objects for ``names``, creating any that do not exist yet."""
    from databricks.feature_engineering import entities as E

    specs = feature_specs(cfg, include_maintenance)
    out = []
    for name in names:
        table, cond, op, col, window = specs[name]
        full = f"{cfg.catalog}.{cfg.schema}.pm_{name}"
        try:
            out.append(fe.get_feature(full_name=full))
            continue
        except Exception:  # noqa: BLE001 - not found -> create
            pass
        cat, sch, tbl = table.split(".")
        src_kwargs = dict(catalog_name=cat, schema_name=sch, table_name=tbl)
        if cond:
            src_kwargs["filter_condition"] = cond
        out.append(fe.create_feature(
            catalog_name=cfg.catalog,
            schema_name=cfg.schema,
            name=f"pm_{name}",
            source=E.DeltaTableSource(**src_kwargs),
            entity=[ENTITY],
            timeseries_column=_ts_column(table),
            function=E.AggregationFunction(getattr(E, op)(input=col), _window(E, op, window)),
        ))
    return out


# --------------------------------------------------------------------------- derived features

def add_derived_features(pdf: pd.DataFrame) -> pd.DataFrame:
    """Strip the pm_ prefix and add trend / headroom / maintenance-recency columns."""
    pdf = pdf.rename(columns={c: c[3:] for c in pdf.columns if c.startswith("pm_")}).copy()
    pdf = pdf.drop(columns=[c for c in ("minute_start", "action_ts") if c in pdf.columns])
    g = pdf.get
    if g("temp_avg_6h") is not None and g("temp_avg_24h") is not None:
        pdf["temp_trend_6h_vs_24h"] = pdf["temp_avg_6h"] - pdf["temp_avg_24h"]
    if g("temp_avg_24h") is not None and g("temp_avg_72h") is not None:
        pdf["temp_trend_24h_vs_72h"] = pdf["temp_avg_24h"] - pdf["temp_avg_72h"]
    if g("temp_avg_1h") is not None and g("temp_avg_6h") is not None:
        pdf["temp_trend_1h_vs_6h"] = pdf["temp_avg_1h"] - pdf["temp_avg_6h"]
    if g("current_avg_6h") is not None and g("current_avg_72h") is not None:
        pdf["current_trend_6h_vs_72h"] = pdf["current_avg_6h"] - pdf["current_avg_72h"]
    if g("temp_avg_1h") is not None:
        pdf["temp_headroom_1h"] = pdf["temperature_breach_max"] - pdf["temp_avg_1h"]
        pdf["temp_warn_headroom_1h"] = pdf["temperature_warn_max"] - pdf["temp_avg_1h"]
    if g("temp_max_6h") is not None:
        pdf["temp_max_headroom_6h"] = pdf["temperature_breach_max"] - pdf["temp_max_6h"]
    if g("volt_min_6h") is not None:
        pdf["volt_low_headroom_6h"] = pdf["volt_min_6h"] - pdf["voltage_breach_min"]
    for win in ("6h", "24h"):
        if g(f"sample_minutes_{win}") is not None:
            denom = pdf[f"sample_minutes_{win}"].replace(0, np.nan)
            for kind in ("sag", "hot"):
                if g(f"{kind}_minutes_{win}") is not None:
                    pdf[f"{kind}_share_{win}"] = pdf[f"{kind}_minutes_{win}"].fillna(0) / denom
    if g("last_repair_ts_30d") is not None:
        last = pd.to_datetime(pdf["last_repair_ts_30d"], utc=True)
        now = pd.to_datetime(pdf[TS], utc=True)
        pdf["hours_since_repair"] = ((now - last).dt.total_seconds() / 3600).fillna(24 * 30)
        pdf["repairs_30d"] = pdf["repairs_30d"].fillna(0)
        pdf = pdf.drop(columns=["last_repair_ts_30d"])
    pdf["is_hd_model"] = (pdf["unit_model"] == "PDU-HD-32A").astype(int)
    return pdf


# --------------------------------------------------------------------------- feature lists

RAW_BY_LIST = {
    # 1. What the unit looks like right now.
    "current_state": ["temp_avg_1h", "temp_max_1h", "current_avg_1h", "volt_avg_1h",
                      "temp_avg_6h", "temp_max_6h", "current_avg_6h", "volt_min_6h"],
    # 2. + longer windows so the model can see drift.
    "trend": ["temp_avg_1h", "temp_max_1h", "current_avg_1h", "volt_avg_1h",
              "temp_avg_6h", "temp_max_6h", "current_avg_6h", "volt_min_6h",
              "temp_avg_24h", "temp_avg_72h", "current_avg_24h", "current_avg_72h",
              "volt_avg_24h", "volt_avg_72h"],
    # 3. + volatility and event counts (sags, hot minutes).
    "trend_volatility": ["temp_avg_1h", "temp_max_1h", "current_avg_1h", "volt_avg_1h",
                         "temp_avg_6h", "temp_max_6h", "current_avg_6h", "volt_min_6h",
                         "temp_avg_24h", "temp_avg_72h", "current_avg_24h", "current_avg_72h",
                         "volt_avg_24h", "volt_avg_72h", "volt_min_24h",
                         "volt_std_6h", "volt_std_24h", "temp_std_6h", "temp_std_24h",
                         "current_std_6h", "current_std_24h",
                         "sag_minutes_6h", "sag_minutes_24h", "hot_minutes_6h", "hot_minutes_24h",
                         "sample_minutes_6h", "sample_minutes_24h"],
}
RAW_BY_LIST["full"] = RAW_BY_LIST["trend_volatility"] + ["last_repair_ts_30d", "repairs_30d"]

DERIVED_BY_LIST = {
    "current_state": ["temp_headroom_1h", "temp_warn_headroom_1h", "temp_max_headroom_6h",
                      "volt_low_headroom_6h"],
    "trend": ["temp_headroom_1h", "temp_warn_headroom_1h", "temp_max_headroom_6h",
              "volt_low_headroom_6h", "temp_trend_1h_vs_6h", "temp_trend_6h_vs_24h",
              "temp_trend_24h_vs_72h", "current_trend_6h_vs_72h"],
}
DERIVED_BY_LIST["trend_volatility"] = DERIVED_BY_LIST["trend"] + [
    "sag_share_6h", "sag_share_24h", "hot_share_6h", "hot_share_24h"]
DERIVED_BY_LIST["full"] = DERIVED_BY_LIST["trend_volatility"] + [
    "hours_since_repair", "repairs_30d", "is_hd_model", "shelf"]


def model_columns(feature_list: str) -> list[str]:
    """Columns fed to the model for a feature list (raw window features + derived columns)."""
    raw = [c for c in RAW_BY_LIST[feature_list] if c != "last_repair_ts_30d"]
    cols = raw + [c for c in DERIVED_BY_LIST[feature_list] if c not in raw]
    return list(dict.fromkeys(cols))


def all_raw_feature_names(include_maintenance: bool = True) -> list[str]:
    names = list(dict.fromkeys(n for lst in RAW_BY_LIST.values() for n in lst))
    if not include_maintenance:
        names = [n for n in names if n not in ("last_repair_ts_30d", "repairs_30d")]
    return names
