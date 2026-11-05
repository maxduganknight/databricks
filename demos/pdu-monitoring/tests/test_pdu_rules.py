"""Unit tests for the shared threshold / status rules used by the pipeline."""

from datetime import datetime, timedelta

import pytest
from pyspark.sql import Row

from utilities import pdu_rules as R

T0 = datetime(2026, 1, 1, 12, 0, 0)


# --------------------------------------------------------------------------- thresholds CSV
def test_seed_csv_parses(thresholds_csv):
    rows = R.parse_thresholds_csv(thresholds_csv)
    by_key = {(r[0], r[1], r[2]): r for r in rows}
    assert ("GLOBAL", None, "voltage") in by_key
    assert ("GLOBAL", None, "temperature") in by_key
    assert by_key[("GLOBAL", None, "voltage")][3:7] == (220.0, 228.0, 252.0, 260.0)
    # Temperature has no lower bounds.
    assert by_key[("GLOBAL", None, "temperature")][3:7] == (None, None, 45.0, 55.0)


def _write(tmp_path, body):
    p = tmp_path / "t.csv"
    p.write_text("scope_type,scope_value,metric,breach_min,warn_min,warn_max,breach_max,description\n" + body)
    return str(p)


def test_csv_skips_blank_and_comment_lines(tmp_path):
    rows = R.parse_thresholds_csv(_write(tmp_path, "\n#RACK,R01,voltage,1,2,3,4,ignored\nglobal,,Voltage,1,2,3,4,x\n"))
    assert rows == [("GLOBAL", None, "voltage", 1.0, 2.0, 3.0, 4.0, "x")]


@pytest.mark.parametrize(
    "line, message",
    [
        ("SHELF,S1,voltage,1,2,3,4,x", "unknown scope_type"),
        ("GLOBAL,,humidity,1,2,3,4,x", "unknown metric"),
        ("RACK,,voltage,1,2,3,4,x", "scope_value required"),
        ("GLOBAL,,voltage,1,3,2,4,x", "bounds must satisfy"),
    ],
)
def test_csv_validation_errors(tmp_path, line, message):
    with pytest.raises(ValueError, match=message):
        R.parse_thresholds_csv(_write(tmp_path, line + "\n"))


# --------------------------------------------------------------------------- threshold resolution
def test_most_specific_scope_wins(spark, thresholds_csv):
    rows = R.parse_thresholds_csv(thresholds_csv) + [
        ("UNIT", "R02-S1-P1", "voltage", 200.0, 210.0, 270.0, 280.0, "test override"),
    ]
    thresholds = spark.createDataFrame(rows, R.THRESHOLD_SCHEMA)
    units = spark.createDataFrame(
        [
            ("R01-S1-P1", "R01", "PDU-STD-24A"),
            ("R02-S1-P2", "R02", "PDU-STD-24A"),
            ("R02-S1-P1", "R02", "PDU-STD-24A"),
            ("R04-S1-P1", "R04", "PDU-HD-32A"),
        ],
        "unit_id string, rack_id string, unit_model string",
    )
    got = {r.unit_id: r for r in R.resolve_thresholds(units, thresholds).collect()}

    assert got["R01-S1-P1"].voltage_threshold_scope == "GLOBAL"
    assert got["R01-S1-P1"].temperature_warn_max == 45.0
    assert got["R02-S1-P2"].voltage_threshold_scope == "RACK:R02"
    assert got["R02-S1-P2"].voltage_breach_min == 222.0
    assert got["R02-S1-P1"].voltage_threshold_scope == "UNIT:R02-S1-P1"  # UNIT beats RACK
    assert got["R02-S1-P1"].voltage_breach_min == 200.0
    assert got["R04-S1-P1"].temperature_threshold_scope == "MODEL:PDU-HD-32A"
    assert got["R04-S1-P1"].temperature_breach_max == 60.0
    assert got["R04-S1-P1"].voltage_threshold_scope == "GLOBAL"  # model override is temperature-only


# --------------------------------------------------------------------------- cleaning
def test_sanitize_nulls_implausible_readings(spark):
    df = spark.createDataFrame(
        [("a", 240.0, 35.0), ("b", 500.0, -40.0), ("c", None, 30.0)],
        "unit_id string, voltage_v double, temperature_c double",
    )
    got = {r.unit_id: (r.voltage_v, r.temperature_c) for r in R.sanitize_readings(df).collect()}
    assert got == {"a": (240.0, 35.0), "b": (None, None), "c": (None, 30.0)}


# --------------------------------------------------------------------------- classification
GLOBAL_BOUNDS = dict(
    voltage_breach_min=220.0, voltage_warn_min=228.0, voltage_warn_max=252.0, voltage_breach_max=260.0,
    temperature_breach_min=None, temperature_warn_min=None, temperature_warn_max=45.0, temperature_breach_max=55.0,
)
CLASSIFY_SCHEMA = (
    "case string, voltage_min double, voltage_max double, temperature_min double, temperature_max double, "
    + ", ".join(f"{k} double" for k in GLOBAL_BOUNDS)
)


def _classify(spark, cases):
    rows = [(name, vmin, vmax, tmin, tmax, *GLOBAL_BOUNDS.values()) for name, vmin, vmax, tmin, tmax in cases]
    return {r.case: r for r in R.classify(spark.createDataFrame(rows, CLASSIFY_SCHEMA)).collect()}


def test_classify_statuses(spark):
    got = _classify(
        spark,
        [
            ("ok", 238.0, 242.0, 30.0, 35.0),
            ("warn_temp", 238.0, 242.0, 40.0, 47.0),
            ("breach_low_v", 215.0, 242.0, 30.0, 35.0),
            ("breach_and_warn", 238.0, 255.0, 40.0, 56.0),  # V warn high + T breach high
            ("no_samples", None, None, None, None),
            ("at_warn_bound", 228.0, 252.0, 30.0, 45.0),     # bounds are inclusive -> OK
        ],
    )
    assert got["ok"].status == "OK" and got["ok"].severity_score == 0.0
    assert got["warn_temp"].status == "WARN" and got["warn_temp"].warn_metrics == ["temperature_high"]
    assert got["breach_low_v"].status == "BREACH" and got["breach_low_v"].breached_metrics == ["voltage_low"]
    assert got["breach_and_warn"].status == "BREACH"
    assert got["breach_and_warn"].breached_metrics == ["temperature_high"]
    assert got["breach_and_warn"].warn_metrics == ["voltage_high"]
    assert got["no_samples"].status == "OK" and got["no_samples"].breached_metrics == []
    assert got["at_warn_bound"].status == "OK"


def test_severity_scale(spark):
    got = _classify(spark, [("half", 240.0, 240.0, 30.0, 50.0), ("at_breach", 240.0, 240.0, 30.0, 55.0),
                            ("low_v", 216.0, 240.0, 30.0, 30.0)])
    assert got["half"].severity_score == pytest.approx(0.5)       # halfway from warn_max 45 to breach_max 55
    assert got["at_breach"].severity_score == pytest.approx(1.0)
    assert got["low_v"].severity_score == pytest.approx(1.5)      # (228 - 216) / (228 - 220)


# --------------------------------------------------------------------------- latest status
def _minute(unit, minutes_after_t0, status):
    ts = T0 + timedelta(minutes=minutes_after_t0)
    return Row(unit_id=unit, minute_start=ts, last_event_ts=ts + timedelta(seconds=59), status=status)


def test_latest_status_breach_streak_and_staleness(spark):
    rows = [
        # A: OK then an ongoing two-minute breach -> breach started at minute 1
        _minute("A", 0, "OK"), _minute("A", 1, "BREACH"), _minute("A", 2, "BREACH"),
        # B: breach that has recovered -> no current breach, but history kept
        _minute("B", 0, "BREACH"), _minute("B", 1, "OK"), _minute("B", 2, "OK"),
        # C: breach, recovery, new breach -> streak starts at the most recent breach only
        _minute("C", 0, "BREACH"), _minute("C", 1, "OK"), _minute("C", 2, "BREACH"),
        # D: in breach from the start of the lookback
        _minute("D", 0, "BREACH"), _minute("D", 1, "BREACH"), _minute("D", 2, "BREACH"),
        # E: stopped reporting 10 minutes before the fleet
        _minute("E", -8, "OK"),
    ]
    got = {r.unit_id: r for r in R.latest_status(spark.createDataFrame(rows), stale_after_minutes=3).collect()}

    assert len(got) == 5
    assert got["A"].status == "BREACH" and got["A"].breach_started_ts == T0 + timedelta(minutes=1)
    assert got["A"].breach_minutes_lookback == 2
    assert got["B"].status == "OK" and got["B"].breach_started_ts is None
    assert got["B"].last_breach_ts == T0 + timedelta(seconds=59)
    assert got["C"].breach_started_ts == T0 + timedelta(minutes=2)
    assert got["D"].breach_started_ts == T0
    assert not any(got[u].is_stale for u in "ABCD")
    assert got["E"].is_stale
