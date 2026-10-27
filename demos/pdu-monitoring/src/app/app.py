"""PDU Monitoring - Databricks App (Dash).

Pages
* /                 rack grid + KPIs + worst offenders, refreshed from Lakebase every REFRESH_SECONDS.
* /unit/<unit_id>   troubleshooting: second-level bronze for that unit only (SQL warehouse, cached),
                    threshold bands, acknowledge breach, unit notes (Lakebase).

Bronze is never queried by the monitoring page; on the unit page it is queried on open, on window
change / Refresh, and auto-refreshed only while the unit is in BREACH.
"""

import logging
import os
import re

import dash_bootstrap_components as dbc
from dash import Dash, Input, Output, State, dcc, html, no_update
from flask import has_request_context, request

import components as ui
import data

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("pdu-monitor")

REFRESH_MS = int(os.getenv("REFRESH_SECONDS", "30")) * 1000
BREACH_BRONZE_REFRESH_MS = int(os.getenv("BREACH_BRONZE_REFRESH_SECONDS", "60")) * 1000
UNIT_PATH_RE = re.compile(r"^/unit/([A-Za-z0-9_-]{1,64})/?$")

app = Dash(
    __name__,
    title="PDU Monitoring",
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    suppress_callback_exceptions=True,
    update_title=None,
)
server = app.server


def operator() -> str:
    """Signed-in user, from the headers the Databricks Apps proxy forwards."""
    if has_request_context():
        h = request.headers
        return h.get("X-Forwarded-Email") or h.get("X-Forwarded-Preferred-Username") or h.get("X-Forwarded-User") or "unknown"
    return "unknown"


def error_alert(what: str, exc: Exception):
    log.exception("%s failed", what)
    return dbc.Alert(f"{what} failed: {type(exc).__name__}: {exc}", color="danger", className="small")


app.layout = html.Div(
    [
        dcc.Location(id="url"),
        dbc.Navbar(
            dbc.Container(
                [
                    dcc.Link(dbc.NavbarBrand("PDU Monitoring"), href="/", className="text-decoration-none"),
                    html.Small(id="nav-user", className="text-light"),
                ],
                fluid=True,
            ),
            color="dark",
            dark=True,
            className="mb-3",
        ),
        dbc.Container(id="page", fluid=True, className="pb-4"),
    ]
)


@app.callback(Output("page", "children"), Output("nav-user", "children"), Input("url", "pathname"))
def route(pathname):
    m = UNIT_PATH_RE.match(pathname or "")
    page = unit_layout(m.group(1)) if m else monitor_layout()
    return page, f"Signed in as {operator()}"


# =========================================================================== monitoring page
def monitor_layout():
    try:
        rack_options = data.racks()
    except Exception:  # noqa: BLE001 - page still renders; the refresh callback shows the error
        rack_options = []
    return html.Div(
        [
            dcc.Interval(id="mon-tick", interval=REFRESH_MS),
            dbc.Row(
                [
                    dbc.Col(dcc.Dropdown(id="rack-filter", options=rack_options, multi=True, placeholder="All racks"), md=4),
                    dbc.Col(ui.legend(), md=5, className="pt-2"),
                    dbc.Col(html.Small(id="mon-updated", className="text-muted"), md=3, className="text-end pt-2"),
                ],
                className="mb-2",
            ),
            html.Div(id="mon-kpis"),
            dbc.Row(
                [
                    dbc.Col(html.Div(id="mon-grid"), xl=9),
                    dbc.Col(dbc.Card([dbc.CardHeader("Worst offenders"), dbc.CardBody(html.Div(id="mon-offenders"))]), xl=3),
                ],
                className="g-3",
            ),
        ]
    )


@app.callback(
    Output("mon-kpis", "children"),
    Output("mon-grid", "children"),
    Output("mon-offenders", "children"),
    Output("mon-updated", "children"),
    Input("mon-tick", "n_intervals"),
    Input("rack-filter", "value"),
)
def refresh_monitor(_, selected_racks):
    try:
        df = data.latest_status()
    except Exception as e:  # noqa: BLE001
        return error_alert("Loading unit status from Lakebase", e), None, None, ""
    if df.empty:
        return dbc.Alert("No unit status yet - is the pipeline running?", color="warning"), None, None, ""
    df, hidden = data.split_by_layout(df)
    view = df[df["rack_id"].isin(selected_racks)] if selected_racks else df
    grid = ui.rack_grid(view, data.RACK_SHELVES, data.RACK_POSITIONS)
    if hidden:
        grid = html.Div([
            dbc.Alert(f"{len(hidden)} units outside the {data.RACK_SHELVES}x{data.RACK_POSITIONS} rack layout are hidden "
                      f"(e.g. {', '.join(hidden[:4])}).", color="light", className="small py-1"),
            grid,
        ])
    return ui.kpi_row(view), grid, ui.offenders_table(view), f"Auto-refresh every {REFRESH_MS // 1000}s"


# =========================================================================== troubleshooting page
def unit_layout(unit_id: str):
    return html.Div(
        [
            dcc.Store(id="ts-unit", data=unit_id),
            dcc.Store(id="ts-ops-version", data=0),
            dcc.Interval(id="ts-status-tick", interval=REFRESH_MS),  # Lakebase only
            dcc.Interval(id="ts-bronze-tick", interval=BREACH_BRONZE_REFRESH_MS, disabled=True),  # only while BREACH
            dcc.Link("< Back to racks", href="/", className="small"),
            html.Div(id="ts-header", className="my-2"),
            dbc.Row(
                [
                    dbc.Col(
                        dcc.Dropdown(
                            id="ts-window",
                            options=[{"label": f"Last {m} min", "value": m} for m in data.ALLOWED_WINDOWS_MIN],
                            value=30,
                            clearable=False,
                        ),
                        md=2,
                    ),
                    dbc.Col(dbc.Button("Refresh readings", id="ts-refresh", size="sm", color="secondary"), width="auto"),
                    dbc.Col(html.Small(id="ts-query-info", className="text-muted"), className="pt-1"),
                ],
                className="g-2 mb-2",
            ),
            dcc.Loading(
                dbc.Row(
                    [
                        dbc.Col(dbc.Card(dcc.Graph(id="ts-voltage", config={"displaylogo": False})), lg=6),
                        dbc.Col(dbc.Card(dcc.Graph(id="ts-temperature", config={"displaylogo": False})), lg=6),
                    ],
                    className="g-3 mb-3",
                ),
                type="default",
            ),
            dbc.Row(
                [
                    dbc.Col(
                        dbc.Card(
                            [
                                dbc.CardHeader("Acknowledge breach"),
                                dbc.CardBody(
                                    [
                                        html.Div(id="ack-state", className="small mb-2"),
                                        dbc.Textarea(id="ack-note", placeholder="Optional note (cause, ticket, action taken)",
                                                     maxLength=data.MAX_NOTE_CHARS, rows=2, className="mb-2"),
                                        dbc.Button("Acknowledge", id="ack-btn", color="danger", size="sm", disabled=True),
                                        html.Div(id="ack-msg", className="small mt-2"),
                                        html.Hr(),
                                        html.Div("Acknowledgement history", className="fw-semibold small mb-1"),
                                        html.Div(id="ack-history"),
                                    ]
                                ),
                            ]
                        ),
                        lg=6,
                    ),
                    dbc.Col(
                        dbc.Card(
                            [
                                dbc.CardHeader("Unit notes"),
                                dbc.CardBody(
                                    [
                                        dbc.Textarea(id="note-text", placeholder="Add a troubleshooting note",
                                                     maxLength=data.MAX_NOTE_CHARS, rows=2, className="mb-2"),
                                        dbc.Button("Add note", id="note-btn", color="primary", size="sm"),
                                        html.Div(id="note-msg", className="small mt-2"),
                                        html.Hr(),
                                        html.Div(id="note-history"),
                                    ]
                                ),
                            ]
                        ),
                        lg=6,
                    ),
                ],
                className="g-3",
            ),
        ]
    )


def _header(s: dict):
    thr = lambda m: f"{ui.fmt(s[f'{m}_breach_min'], 0)} / {ui.fmt(s[f'{m}_warn_min'], 0)} / {ui.fmt(s[f'{m}_warn_max'], 0)} / {ui.fmt(s[f'{m}_breach_max'], 0)}"
    facts = [
        ("Rack / shelf / position", f"{s['rack_id']} / S{s['shelf']} / P{s['position']}"),
        ("Model", s["unit_model"]),
        ("Breached", ui.metrics_text(s["breached_metrics"]) or "-"),
        ("Warning", ui.metrics_text(s["warn_metrics"]) or "-"),
        ("Breach since", ui.fmt_ts(s["breach_started_ts"]) if s["status"] == "BREACH" else "-"),
        ("Breach minutes (24h)", int(s["breach_minutes_lookback"] or 0)),
        ("Last minute (V min-max / T max)", f"{ui.fmt(s['voltage_min'])}-{ui.fmt(s['voltage_max'])} V / {ui.fmt(s['temperature_max'])} C"),
        ("Last reading", f"{ui.fmt_ts(s['last_event_ts'])} ({ui.fmt_age(s['last_event_ts'])} ago)"),
        ("Voltage thresholds", f"{thr('voltage')} V ({s['voltage_threshold_scope']})"),
        ("Temperature thresholds", f"{thr('temperature')} C ({s['temperature_threshold_scope']})"),
    ]
    return dbc.Card(
        dbc.CardBody(
            [
                html.H4([s["unit_id"], " ", ui.status_badge(s["status"], bool(s["is_stale"]))], className="mb-2"),
                dbc.Row([dbc.Col([html.Div(k, className="kpi-title"), html.Div(v)], xs=6, md=3, xl=2, className="mb-2") for k, v in facts]),
                html.Small("Thresholds: breach min / warn min / warn max / breach max (scope)", className="text-muted"),
            ]
        )
    )


@app.callback(
    Output("ts-header", "children"),
    Output("ts-bronze-tick", "disabled"),
    Output("ack-btn", "disabled"),
    Output("ack-state", "children"),
    Input("ts-unit", "data"),
    Input("ts-status-tick", "n_intervals"),
    Input("ts-ops-version", "data"),
)
def refresh_unit_status(unit_id, _tick, _ops):
    try:
        s = data.unit_status(unit_id)
    except Exception as e:  # noqa: BLE001
        return error_alert("Loading unit status", e), True, True, ""
    if s is None:
        return dbc.Alert(f"Unknown unit {unit_id}", color="warning"), True, True, ""
    in_breach = s["status"] == "BREACH"
    if not in_breach:
        state = "Unit is not in breach - nothing to acknowledge."
    elif s["unacked_breach"]:
        state = f"Open breach since {ui.fmt_ts(s['breach_started_ts'])} - not yet acknowledged."
    else:
        state = f"Acknowledged by {s['ack_by']} at {ui.fmt_ts(s['ack_at'])}."
    return _header(s), not in_breach, not (in_breach and s["unacked_breach"]), state


@app.callback(
    Output("ts-voltage", "figure"),
    Output("ts-temperature", "figure"),
    Output("ts-query-info", "children"),
    Input("ts-unit", "data"),
    Input("ts-window", "value"),
    Input("ts-refresh", "n_clicks"),
    Input("ts-bronze-tick", "n_intervals"),
)
def refresh_unit_charts(unit_id, minutes, _clicks, _tick):
    try:
        s = data.unit_status(unit_id) or {}
        df, age = data.bronze_window(unit_id, minutes)
    except Exception as e:  # noqa: BLE001
        log.exception("bronze query failed")
        return {}, {}, f"Bronze query failed: {type(e).__name__}: {e}"
    b = lambda m: tuple(s.get(f"{m}_{k}") for k in ("breach_min", "warn_min", "warn_max", "breach_max"))
    start = s.get("breach_started_ts") if s.get("status") == "BREACH" else None
    v = ui.metric_figure(df, "voltage_v", "Voltage", "V", b("voltage"), start)
    t = ui.metric_figure(df, "temperature_c", "Temperature", "C", b("temperature"), start)
    auto = " - auto-refreshing while in breach" if s.get("status") == "BREACH" else ""
    return v, t, f"{len(df):,} second-level readings from bronze (cached {int(age)}s ago){auto}"


@app.callback(
    Output("ack-msg", "children"),
    Output("ack-note", "value"),
    Output("ts-ops-version", "data", allow_duplicate=True),
    Input("ack-btn", "n_clicks"),
    State("ts-unit", "data"),
    State("ack-note", "value"),
    State("ts-ops-version", "data"),
    prevent_initial_call=True,
)
def acknowledge(_clicks, unit_id, note, version):
    try:
        s = data.unit_status(unit_id)
        if not s or s["status"] != "BREACH":
            return dbc.Alert("Unit is no longer in breach.", color="info"), no_update, (version or 0) + 1
        data.add_ack(unit_id, s["breach_started_ts"], operator(), note)
    except Exception as e:  # noqa: BLE001
        return error_alert("Saving acknowledgement", e), no_update, no_update
    return dbc.Alert("Breach acknowledged.", color="success"), "", (version or 0) + 1


@app.callback(
    Output("note-msg", "children"),
    Output("note-text", "value"),
    Output("ts-ops-version", "data", allow_duplicate=True),
    Input("note-btn", "n_clicks"),
    State("ts-unit", "data"),
    State("note-text", "value"),
    State("ts-ops-version", "data"),
    prevent_initial_call=True,
)
def add_note(_clicks, unit_id, text, version):
    if not (text or "").strip():
        return dbc.Alert("Write a note first.", color="warning"), no_update, no_update
    try:
        data.add_note(unit_id, operator(), text)
    except Exception as e:  # noqa: BLE001
        return error_alert("Saving note", e), no_update, no_update
    return dbc.Alert("Note saved.", color="success"), "", (version or 0) + 1


@app.callback(
    Output("ack-history", "children"),
    Output("note-history", "children"),
    Input("ts-unit", "data"),
    Input("ts-ops-version", "data"),
)
def refresh_history(unit_id, _version):
    try:
        return ui.history_list(data.acks(unit_id), "ack"), ui.history_list(data.notes(unit_id), "note")
    except Exception as e:  # noqa: BLE001
        alert = error_alert("Loading history", e)
        return alert, alert


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("DATABRICKS_APP_PORT", "8000")), debug=False, threaded=True)
