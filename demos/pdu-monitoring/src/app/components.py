"""Presentational helpers: rack grid, KPI cards, offenders table, threshold-banded charts."""

import math
from datetime import datetime, timezone

import dash_bootstrap_components as dbc
import pandas as pd
import plotly.graph_objects as go
from dash import dcc, html

GREEN, AMBER, RED, GREY = "#2e7d32", "#f9a825", "#c62828", "#757575"
STATUS_COLOR = {"OK": GREEN, "WARN": AMBER, "BREACH": RED}
STATUS_RANK = {"BREACH": 2, "WARN": 1, "OK": 0}
METRIC_LABEL = {"voltage_low": "V low", "voltage_high": "V high", "temperature_low": "T low", "temperature_high": "T high"}


def _num(v):
    """None for null/NaN, else float."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def fmt(v, digits=1, suffix=""):
    f = _num(v)
    return "-" if f is None else f"{f:.{digits}f}{suffix}"


def fmt_ts(ts) -> str:
    if ts is None or (isinstance(ts, float) and math.isnan(ts)) or ts is pd.NaT:
        return "-"
    return pd.Timestamp(ts).tz_convert("UTC").strftime("%Y-%m-%d %H:%M:%S UTC")


def fmt_age(ts) -> str:
    if ts is None or ts is pd.NaT:
        return "-"
    secs = int((datetime.now(timezone.utc) - pd.Timestamp(ts).to_pydatetime()).total_seconds())
    if secs < 0:
        return "0s"
    m, s = divmod(secs, 60)
    h, m = divmod(m, 60)
    return f"{h}h {m}m" if h else (f"{m}m {s}s" if m else f"{s}s")


def metrics_text(values) -> str:
    return ", ".join(METRIC_LABEL.get(m, m) for m in (values or []))


def status_badge(status: str, stale: bool = False):
    badges = [dbc.Badge(status, style={"backgroundColor": STATUS_COLOR.get(status, GREY)}, className="me-1 fs-6")]
    if stale:
        badges.append(dbc.Badge("STALE", color="secondary", className="me-1 fs-6"))
    return html.Span(badges)


# --------------------------------------------------------------------------- KPIs
def _kpi(title, value, color=None, sub=None):
    return dbc.Col(
        dbc.Card(
            dbc.CardBody(
                [
                    html.Div(title, className="kpi-title"),
                    html.Div(value, className="kpi-value", style={"color": color} if color else None),
                    html.Div(sub, className="kpi-sub") if sub else None,
                ]
            ),
            className="kpi-card",
        ),
        xs=6, md=4, xl=2,
    )


def kpi_row(df: pd.DataFrame):
    counts = df["status"].value_counts()
    unacked = int(df["unacked_breach"].fillna(False).sum())
    return dbc.Row(
        [
            _kpi("Units in breach", int(counts.get("BREACH", 0)), RED, f"{unacked} unacknowledged"),
            _kpi("Warning", int(counts.get("WARN", 0)), AMBER),
            _kpi("OK", int(counts.get("OK", 0)), GREEN, f"of {len(df)} units"),
            _kpi("Stale units", int(df["is_stale"].fillna(False).sum()), GREY, "no recent minute stats"),
            _kpi("Newest reading", fmt_age(df["last_event_ts"].max()) + " ago", sub=fmt_ts(df["last_event_ts"].max())),
            _kpi("Status computed", fmt_age(df["updated_at"].max()) + " ago", sub="pipeline + sync"),
        ],
        className="g-2 mb-3",
    )


# --------------------------------------------------------------------------- rack grid
def _tile(r: dict):
    status = r["status"]
    classes = ["tile", f"tile-{status.lower()}"]
    if r.get("is_stale"):
        classes.append("tile-stale")
    if status == "BREACH" and not r.get("unacked_breach"):
        classes.append("tile-acked")
    tooltip = (
        f"{r['unit_id']} ({r['unit_model']}) - {status}"
        + (" / STALE" if r.get("is_stale") else "")
        + f"\nVoltage {fmt(r['voltage_min'])}-{fmt(r['voltage_max'])} V, temp max {fmt(r['temperature_max'])} C"
        + (f"\nBreached: {metrics_text(r['breached_metrics'])}" if r.get("breached_metrics") else "")
        + (f"\nWarning: {metrics_text(r['warn_metrics'])}" if r.get("warn_metrics") else "")
        + (f"\nAcknowledged by {r['ack_by']}" if status == "BREACH" and r.get("ack_by") else "")
        + f"\nLast reading {fmt_ts(r['last_event_ts'])}"
    )
    flag = "ACK" if "tile-acked" in classes else ("STALE" if r.get("is_stale") else "")
    return dcc.Link(
        [
            html.Span(f"S{r['shelf']}-P{r['position']}", className="tile-id"),
            html.Span(f"{fmt(r['voltage_min'], 0)}-{fmt(r['voltage_max'], 0)} V", className="tile-metric"),
            html.Span(f"{fmt(r['temperature_max'])} C", className="tile-metric"),
            html.Span(flag, className="tile-flag"),
        ],
        href=f"/unit/{r['unit_id']}",
        className=" ".join(classes),
        title=tooltip,
    )


def rack_grid(df: pd.DataFrame, shelves: int, positions: int):
    """Racks stacked vertically, one full-width card each, drawn as a fixed shelves x positions layout;
    shelves run top-to-bottom (highest shelf first), positions left-to-right. Tiles are landscape."""
    cards = []
    for rack_id, rack in df.groupby("rack_id", sort=True):
        by_slot = {(int(r["shelf"]), int(r["position"])): r for r in rack.to_dict("records")}
        cells = [html.Div("", className="grid-label")] + [html.Div(f"P{p}", className="grid-label") for p in range(1, positions + 1)]
        for s in range(shelves, 0, -1):
            cells.append(html.Div(f"S{s}", className="grid-label"))
            for p in range(1, positions + 1):
                r = by_slot.get((s, p))
                cells.append(_tile(r) if r else html.Div(f"S{s}-P{p} - no data", className="tile tile-empty"))
        counts = rack["status"].value_counts()
        header = html.Div(
            [
                html.Strong(rack_id, className="me-2"),
                html.Small(f"{rack['unit_model'].iloc[0]}", className="text-muted me-2"),
                *[
                    dbc.Badge(f"{counts.get(s, 0)} {s}", style={"backgroundColor": STATUS_COLOR[s]}, className="me-1")
                    for s in ("BREACH", "WARN")
                    if counts.get(s, 0)
                ],
            ]
        )
        cards.append(
            dbc.Card(
                [
                    dbc.CardHeader(header),
                    dbc.CardBody(
                        html.Div(cells, className="rack-grid",
                                 style={"gridTemplateColumns": f"28px repeat({positions}, minmax(150px, 1fr))"}),
                        className="rack-body",
                    ),
                ],
                className="rack-card mb-3",
            )
        )
    return html.Div(cards)


def legend():
    item = lambda cls, text: html.Span([html.Span(className=f"legend-swatch {cls}"), text], className="me-3")
    return html.Div(
        [item("tile-ok", "OK"), item("tile-warn", "Warning"), item("tile-breach", "Breach (unacknowledged)"),
         item("tile-breach tile-acked", "Breach (acknowledged)"), item("tile-ok tile-stale", "Stale data")],
        className="small text-muted mb-2",
    )


# --------------------------------------------------------------------------- worst offenders
def offenders_table(df: pd.DataFrame, limit: int = 10):
    d = df[(df["status"] != "OK") | (df["breach_minutes_lookback"].fillna(0) > 0) | df["is_stale"].fillna(False)].copy()
    if d.empty:
        return html.Div("All units healthy over the lookback window.", className="text-muted")
    d["rank"] = d["status"].map(STATUS_RANK).fillna(0)
    d = d.sort_values(["rank", "severity_score", "breach_minutes_lookback"], ascending=False).head(limit)
    rows = []
    for r in d.to_dict("records"):
        issue = metrics_text(r["breached_metrics"]) or metrics_text(r["warn_metrics"]) or ("stale" if r["is_stale"] else "recovered")
        ack = ""
        if r["status"] == "BREACH":
            ack = "acked" if not r["unacked_breach"] else "open"
        rows.append(
            html.Tr(
                [
                    html.Td(dcc.Link(r["unit_id"], href=f"/unit/{r['unit_id']}")),
                    html.Td(status_badge(r["status"], bool(r["is_stale"]))),
                    html.Td(issue),
                    html.Td(fmt(r["severity_score"], 2)),
                    html.Td(int(r["breach_minutes_lookback"] or 0)),
                    html.Td(ack),
                ]
            )
        )
    head = html.Thead(html.Tr([html.Th(h) for h in ("Unit", "Status", "Issue", "Severity", "Breach min (24h)", "Ack")]))
    return dbc.Table([head, html.Tbody(rows)], size="sm", hover=True, className="offenders")


# --------------------------------------------------------------------------- troubleshooting charts
def metric_figure(df: pd.DataFrame, col: str, title: str, unit: str, bounds: tuple, breach_started_ts=None):
    """Line chart with shaded OK / warning / breach bands; out-of-breach readings marked red."""
    bmin, wmin, wmax, bmax = (_num(b) for b in bounds)
    fig = go.Figure()
    y = df[col].dropna() if not df.empty else pd.Series(dtype=float)
    candidates = [v for v in (bmin, wmin, wmax, bmax) if v is not None]
    lo = min([y.min()] + candidates) if len(y) else (min(candidates) if candidates else 0)
    hi = max([y.max()] + candidates) if len(y) else (max(candidates) if candidates else 1)
    pad = max((hi - lo) * 0.08, 1.0)
    lo, hi = lo - pad, hi + pad

    def band(y0, y1, color, opacity):
        if y0 is not None and y1 is not None and y1 > y0:
            fig.add_hrect(y0=y0, y1=y1, fillcolor=color, opacity=opacity, line_width=0, layer="below")

    band(wmin if wmin is not None else lo, wmax if wmax is not None else hi, GREEN, 0.07)
    band(bmin, wmin, AMBER, 0.18)
    band(wmax, bmax, AMBER, 0.18)
    band(lo, bmin, RED, 0.12)
    band(bmax, hi, RED, 0.12)
    for v, name, color in ((bmin, "breach min", RED), (wmin, "warn min", AMBER), (wmax, "warn max", AMBER), (bmax, "breach max", RED)):
        if v is not None:
            fig.add_hline(y=v, line_dash="dot", line_color=color, line_width=1,
                          annotation_text=f"{name} {v:g}", annotation_position="top left", annotation_font_size=10)

    if not df.empty:
        fig.add_trace(go.Scattergl(x=df["event_ts"], y=df[col], mode="lines", name=title, line={"width": 1.2, "color": "#1565c0"}))
        out = df[((bmin is not None) & (df[col] < (bmin if bmin is not None else -math.inf))) |
                 ((bmax is not None) & (df[col] > (bmax if bmax is not None else math.inf)))]
        if not out.empty:
            fig.add_trace(go.Scattergl(x=out["event_ts"], y=out[col], mode="markers", name="breach",
                                       marker={"color": RED, "size": 5}))
        if breach_started_ts is not None and not pd.isna(breach_started_ts):
            ts = pd.Timestamp(breach_started_ts)
            if df["event_ts"].min() <= ts <= df["event_ts"].max():
                fig.add_vline(x=ts, line_dash="dash", line_color=RED, line_width=1)
    else:
        fig.add_annotation(text="No readings in this window", showarrow=False, xref="paper", yref="paper", x=0.5, y=0.5)

    fig.update_layout(
        title={"text": f"{title} ({unit})", "font": {"size": 14}},
        height=300, margin={"l": 50, "r": 20, "t": 40, "b": 30},
        yaxis={"range": [lo, hi]}, showlegend=False, template="plotly_white", uirevision=col,
    )
    return fig


def history_list(items: list, kind: str):
    if not items:
        return html.Div("None yet.", className="text-muted small")
    out = []
    for i in items:
        if kind == "ack":
            head = f"{i['acknowledged_by']} - {fmt_ts(i['acknowledged_at'])}"
            sub = f"breach since {fmt_ts(i['breach_started_ts'])}"
            body = i["note"]
        else:
            head = f"{i['author']} - {fmt_ts(i['created_at'])}"
            sub, body = None, i["note"]
        out.append(html.Li([html.Div(head, className="fw-semibold small"),
                            html.Div(sub, className="text-muted small") if sub else None,
                            html.Div(body, className="small note-body") if body else None],
                           className="list-group-item"))
    return html.Ul(out, className="list-group list-group-flush")
