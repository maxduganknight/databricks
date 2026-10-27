"""Tests for the app's presentational helpers (no Lakebase / warehouse needed)."""

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

pytest.importorskip("dash")
pytest.importorskip("dash_bootstrap_components")
import components as ui  # noqa: E402

NOW = datetime.now(timezone.utc)


def _unit(rack, shelf, pos, status="OK", **kw):
    row = dict(
        unit_id=f"{rack}-S{shelf}-P{pos}", rack_id=rack, unit_model="PDU-STD-24A", shelf=shelf, position=pos,
        status=status, breached_metrics=[], warn_metrics=[], severity_score=0.0, breach_minutes_lookback=0,
        is_stale=False, unacked_breach=False, ack_by=None, voltage_min=238.0, voltage_max=242.0,
        temperature_max=33.0, last_event_ts=NOW,
    )
    row.update(kw)
    return row


def _tiles(component):
    return [c for c in component.children if "tile" in (getattr(c, "className", "") or "").split()]


def test_rack_grid_fixed_layout_stacks_racks_and_fills_empty_slots():
    df = pd.DataFrame([_unit("R01", s, p) for s in range(1, 6) for p in range(1, 6) if (s, p) != (3, 3)]
                      + [_unit("R02", 1, 1, "BREACH", unacked_breach=True)])
    grid = ui.rack_grid(df, shelves=5, positions=5)
    assert len(grid.children) == 2  # one stacked card per rack
    r1 = grid.children[0].children[1].children
    tiles = _tiles(r1)
    assert len(tiles) == 25
    assert sum("tile-empty" in t.className for t in tiles) == 1
    # Highest shelf is drawn first, positions left to right.
    assert tiles[0].href == "/unit/R01-S5-P1" and tiles[4].href == "/unit/R01-S5-P5"
    r2 = _tiles(grid.children[1].children[1].children)
    assert sum("tile-breach" in t.className for t in r2) == 1
    assert sum("tile-empty" in t.className for t in r2) == 24


def test_acked_and_stale_tiles():
    df = pd.DataFrame([_unit("R01", 1, 1, "BREACH", unacked_breach=False, ack_by="op@example.com"),
                       _unit("R01", 1, 2, is_stale=True)])
    tiles = [t for t in _tiles(ui.rack_grid(df, 1, 2).children[0].children[1].children)]
    assert "tile-acked" in tiles[0].className and "ACK" in tiles[0].children[-1].children
    assert "tile-stale" in tiles[1].className


def test_metric_figure_marks_only_breach_readings():
    ts = pd.date_range(NOW - timedelta(minutes=5), periods=6, freq="min")
    df = pd.DataFrame({"event_ts": ts, "temperature_c": [40.0, 46.0, 54.9, 55.1, 61.0, 30.0]})
    fig = ui.metric_figure(df, "temperature_c", "Temperature", "C", (None, None, 45.0, 55.0))
    assert len(fig.data) == 2
    assert list(fig.data[1].y) == [55.1, 61.0]
    lo, hi = fig.layout.yaxis.range
    assert lo < 30.0 and hi > 61.0


def test_metric_figure_empty_window():
    fig = ui.metric_figure(pd.DataFrame(), "voltage_v", "Voltage", "V", (220, 228, 252, 260))
    assert len(fig.data) == 0
    assert fig.layout.annotations[-1].text == "No readings in this window"


def test_offenders_ranks_breach_first():
    df = pd.DataFrame([
        _unit("R01", 1, 1, "WARN", severity_score=0.9, warn_metrics=["temperature_high"]),
        _unit("R01", 1, 2, "BREACH", severity_score=0.2, breached_metrics=["voltage_low"], unacked_breach=True),
        _unit("R01", 1, 3),
    ])
    rows = ui.offenders_table(df).children[1].children
    assert [r.children[0].children.children for r in rows] == ["R01-S1-P2", "R01-S1-P1"]
