"""Generate Revenue Intelligence dashboard JSON (spec 04-ai-bi.md §B, 5 pages)."""
import json

# ---- segment / semantic color pins ----
SEG = {"Mid-Market": "#FE9000", "Enterprise": "#3C6997", "SMB": "#094074", "Startup": "#5ADBFF"}
DANGER, HEALTHY, WARN = "#FE9000", "#3C6997", "#FFDD4A"


def cur(places=2):
    return {"type": "number-currency", "currencyCode": "USD", "abbreviation": "compact",
            "decimalPlaces": {"type": "max", "places": places}}
def pct(places=1):
    return {"type": "number-percent", "decimalPlaces": {"type": "max", "places": places}}
def num(places=1):
    return {"type": "number", "decimalPlaces": {"type": "max", "places": places}}


def seg_map():
    return {"type": "categorical", "mappings": [{"value": k, "color": v} for k, v in SEG.items()]}


def text(name, lines, x, y, w, h):
    return {"widget": {"name": name, "multilineTextboxSpec": {"lines": lines}},
            "position": {"x": x, "y": y, "width": w, "height": h}}


def counter(name, ds, fld, expr, title, x, y, w=3, h=3, fmt=None, period=None, disagg=True):
    fields = [{"name": fld, "expression": expr}]
    enc = {"value": {"fieldName": fld, "displayName": title}}
    if fmt:
        enc["value"]["format"] = fmt
    if period:
        fields.append({"name": period[0], "expression": period[1]})
        enc["period"] = {"fieldName": period[0]}
        disagg = False
    return {"widget": {"name": name, "queries": [{"name": "main_query", "query": {
        "datasetName": ds, "fields": fields, "disaggregated": disagg}}],
        "spec": {"version": 2, "widgetType": "counter", "encodings": enc,
                 "frame": {"showTitle": True, "title": title}}},
        "position": {"x": x, "y": y, "width": w, "height": h}}


def _q(ds, fields, disagg=False, filters=None):
    q = {"datasetName": ds, "fields": fields, "disaggregated": disagg}
    if filters:
        q["filters"] = filters
    return {"name": "main_query", "query": q}


def line(name, ds, xf, xexpr, yf, yexpr, title, x, y, w, h, color=None, xtype="temporal",
         yfmt=None, mappings=None, annotations=None, filters=None):
    fields = [{"name": xf, "expression": xexpr}, {"name": yf, "expression": yexpr}]
    xenc = {"fieldName": xf, "scale": {"type": xtype}}
    yenc = {"fieldName": yf, "scale": {"type": "quantitative"}}
    if yfmt:
        yenc["format"] = yfmt
    enc = {"x": xenc, "y": yenc}
    if color:
        fields.append({"name": color, "expression": f"`{color}`"})
        cenc = {"fieldName": color, "scale": {"type": "categorical"}}
        if mappings:
            cenc["scale"]["mappings"] = mappings
        enc["color"] = cenc
    spec = {"version": 3, "widgetType": "line", "encodings": enc,
            "frame": {"showTitle": True, "title": title}}
    if annotations:
        spec["annotations"] = annotations
    return {"widget": {"name": name, "queries": [_q(ds, fields, filters=filters)], "spec": spec},
            "position": {"x": x, "y": y, "width": w, "height": h}}


def bar(name, ds, catf, catexpr, valf, valexpr, title, x, y, w, h, horizontal=False,
        color=None, mappings=None, valfmt=None, cattype="categorical", grouped=False, filters=None):
    fields = [{"name": catf, "expression": catexpr}, {"name": valf, "expression": valexpr}]
    catenc = {"fieldName": catf, "scale": {"type": cattype}}
    valenc = {"fieldName": valf, "scale": {"type": "quantitative"}}
    if valfmt:
        valenc["format"] = valfmt
    enc = ({"y": catenc, "x": valenc} if horizontal else {"x": catenc, "y": valenc})
    if color:
        fields.append({"name": color, "expression": f"`{color}`"})
        cenc = {"fieldName": color, "scale": {"type": "categorical"}}
        if mappings:
            cenc["scale"]["mappings"] = mappings
        enc["color"] = cenc
    spec = {"version": 3, "widgetType": "bar", "encodings": enc,
            "frame": {"showTitle": True, "title": title}}
    if grouped:
        spec["mark"] = {"layout": "group"}
    return {"widget": {"name": name, "queries": [_q(ds, fields, filters=filters)], "spec": spec},
            "position": {"x": x, "y": y, "width": w, "height": h}}


def pie(name, ds, angf, angexpr, colf, title, x, y, w, h):
    fields = [{"name": angf, "expression": angexpr}, {"name": colf, "expression": f"`{colf}`"}]
    enc = {"angle": {"fieldName": angf, "scale": {"type": "quantitative"}},
           "color": {"fieldName": colf, "scale": {"type": "categorical"}}, "label": {"show": True}}
    return {"widget": {"name": name, "queries": [_q(ds, fields)],
            "spec": {"version": 3, "widgetType": "pie", "encodings": enc,
                     "frame": {"showTitle": True, "title": title}}},
            "position": {"x": x, "y": y, "width": w, "height": h}}


def scatter(name, ds, xf, yf, sizef, colorf, title, x, y, w, h, mappings=None, xfmt=None, yfmt=None):
    fields = [{"name": f, "expression": f"`{f}`"} for f in [xf, yf, sizef, colorf]]
    xenc = {"fieldName": xf, "scale": {"type": "quantitative"}}
    yenc = {"fieldName": yf, "scale": {"type": "quantitative"}}
    if xfmt: xenc["format"] = xfmt
    if yfmt: yenc["format"] = yfmt
    cenc = {"fieldName": colorf, "scale": {"type": "categorical"}}
    if mappings:
        cenc["scale"]["mappings"] = mappings
    enc = {"x": xenc, "y": yenc, "size": {"fieldName": sizef, "scale": {"type": "quantitative"}}, "color": cenc}
    return {"widget": {"name": name, "queries": [_q(ds, fields, disagg=True)],
            "spec": {"version": 3, "widgetType": "scatter", "encodings": enc,
                     "frame": {"showTitle": True, "title": title}}},
            "position": {"x": x, "y": y, "width": w, "height": h}}


def table(name, ds, cols, title, x, y, w, h, styles=None):
    fields = [{"name": c[0], "expression": f"`{c[0]}`"} for c in cols]
    columns = []
    for c in cols:
        col = {"fieldName": c[0], "displayName": c[1]}
        if len(c) > 2 and c[2]:
            col["format"] = c[2]
        if styles and c[0] in styles:
            col["style"] = styles[c[0]]
        columns.append(col)
    return {"widget": {"name": name, "queries": [_q(ds, fields, disagg=True)],
            "spec": {"version": 2, "widgetType": "table", "encodings": {"columns": columns},
                     "frame": {"showTitle": True, "title": title}}},
            "position": {"x": x, "y": y, "width": w, "height": h}}


def combo(name, ds, xf, xexpr, prim, sec, title, x, y, w, h, xtype="temporal", annotations=None):
    fields = [{"name": xf, "expression": xexpr}]
    for f, e, _ in prim + sec:
        fields.append({"name": f, "expression": e})
    enc = {"x": {"fieldName": xf, "scale": {"type": xtype}},
           "y": {"scale": {"type": "quantitative"},
                 "primary": {"fields": [{"fieldName": f, "displayName": d} for f, _, d in prim]},
                 "secondary": {"fields": [{"fieldName": f, "displayName": d} for f, _, d in sec]}},
           "label": {"show": False}}
    spec = {"version": 1, "widgetType": "combo", "encodings": enc,
            "frame": {"showTitle": True, "title": title}}
    if annotations:
        spec["annotations"] = annotations
    return {"widget": {"name": name, "queries": [_q(ds, fields)], "spec": spec},
            "position": {"x": x, "y": y, "width": w, "height": h}}


def filt(name, wtype, title, binds, x, y, w=4, h=2):
    queries, fields = [], []
    for i, (ds, col) in enumerate(binds):
        qn = f"q_{i}"
        queries.append({"name": qn, "query": {"datasetName": ds,
                        "fields": [{"name": col, "expression": f"`{col}`"}], "disaggregated": False}})
        fields.append({"fieldName": col, "queryName": qn})
    return {"widget": {"name": name, "queries": queries,
            "spec": {"version": 2, "widgetType": wtype, "encodings": {"fields": fields},
                     "frame": {"showTitle": True, "title": title}}},
            "position": {"x": x, "y": y, "width": w, "height": h}}


# ============ DATASETS ============
datasets = [
    {"name": "ds_nrr", "displayName": "NRR by segment", "queryLines": [
        "SELECT segment_name, period, starting_arr_usd, new_arr_usd, expansion_arr_usd, ",
        "contraction_arr_usd, churned_arr_usd, ending_arr_usd, nrr_pct, nrr_rolling_pct, ",
        "nrr_rolling_pct/100.0 AS nrr_rolling_frac, ",
        "(contraction_arr_usd + churned_arr_usd) AS churn_contraction_usd ",
        "FROM sem_nrr_retention "]},
    {"name": "ds_health", "displayName": "Account health", "queryLines": [
        "SELECT account_id, account_name, region, segment_name, arr_usd, health_score, ",
        "product_usage_pct, product_usage_pct/100.0 AS usage_frac, support_tickets_90d, ",
        "days_to_renewal, at_risk_arr_usd, is_at_risk FROM sem_account_health "]},
    {"name": "ds_atrisk", "displayName": "Top at-risk accounts", "queryLines": [
        "SELECT account_name, region, segment_name, health_score, product_usage_pct, ",
        "days_to_renewal, at_risk_arr_usd, arr_usd FROM sem_account_health ",
        "WHERE is_at_risk = TRUE OR days_to_renewal <= 90 ORDER BY at_risk_arr_usd DESC LIMIT 10 "]},
    {"name": "ds_health_bottom", "displayName": "Bottom-15 health accounts", "queryLines": [
        "SELECT account_name, region, health_score FROM sem_account_health ",
        "ORDER BY health_score ASC LIMIT 15 "]},
    {"name": "ds_forecast_plan", "displayName": "Forecast vs plan", "queryLines": [
        "SELECT segment_name, period, actual_nnarr_usd, plan_nnarr_usd, variance_usd, variance_pct, ",
        "variance_pct/100.0 AS variance_frac, ",
        "CASE WHEN variance_pct < 0 THEN 'Below plan' ELSE 'Above plan' END AS plan_status ",
        "FROM sem_forecast_plan "]},
    {"name": "ds_nnarr", "displayName": "Mid-Market net-new ARR actual vs forecast", "queryLines": [
        "SELECT period, net_new_arr_usd AS actual_nnarr, CAST(NULL AS DOUBLE) AS forecast_nnarr ",
        "FROM metric_net_new_arr WHERE segment_name = 'Mid-Market' ",
        "UNION ALL SELECT DATE'2026-06-01', NULL, (SELECT net_new_arr_usd FROM metric_net_new_arr WHERE segment_name='Mid-Market' AND period=DATE'2026-06-01') ",
        "UNION ALL SELECT DATE'2026-07-01', NULL, 1200000.0 ",
        "UNION ALL SELECT DATE'2026-08-01', NULL, 1140000.0 ",
        "UNION ALL SELECT DATE'2026-09-01', NULL, 1360000.0 "]},
    {"name": "ds_forecast_mm", "displayName": "Mid-Market forecast tiles", "queryLines": [
        "SELECT * FROM predict_net_new_arr('Mid-Market') "]},
    {"name": "ds_arr_proj", "displayName": "8-quarter ending-ARR projection", "queryLines": [
        "WITH b AS (SELECT ending_arr_usd AS e0 FROM sem_nrr_retention ",
        "WHERE segment_name='Mid-Market' ORDER BY period DESC LIMIT 1) ",
        "SELECT q AS quarter, b.e0*pow(1.02,q) AS baseline_arr, b.e0*pow(0.965,q) AS worst_case_arr ",
        "FROM b, (SELECT explode(sequence(0,8)) AS q) "]},
    {"name": "ds_quota", "displayName": "Quota attainment", "queryLines": [
        "SELECT segment_name, team, period, bookings_usd, quota_usd, attainment_pct, ",
        "attainment_pct/100.0 AS attainment_frac, pipeline_coverage_x, win_rate_pct, ",
        "win_rate_pct/100.0 AS win_rate_frac, rep_count FROM sem_quota_attainment "]},
    {"name": "ds_gtm", "displayName": "GTM efficiency by channel", "queryLines": [
        "SELECT channel_name, SUM(sm_spend_usd) AS sm_spend, SUM(new_logos) AS new_logos, ",
        "SUM(attributed_pipeline_usd) AS attributed_pipeline, ",
        "SUM(sm_spend_usd)/NULLIF(SUM(new_logos),0) AS cac, ",
        "SUM(attributed_pipeline_usd)/NULLIF(SUM(sm_spend_usd),0) AS magic_number ",
        "FROM sem_gtm_spend GROUP BY channel_name "]},
    {"name": "ds_gtm_month", "displayName": "S&M spend by month", "queryLines": [
        "SELECT DATE_TRUNC('MONTH', spend_date) AS month, SUM(amount_usd) AS sm_spend, ",
        "CASE WHEN DATE_TRUNC('QUARTER', spend_date)=DATE'2026-04-01' THEN 'Q2 2026' ELSE 'Other' END AS is_q2 ",
        "FROM fact_gtm_spend GROUP BY 1, 3 "]},
    {"name": "ds_sync", "displayName": "CRM vs billing unmatched", "queryLines": [
        "SELECT DATE_TRUNC('MONTH', booking_date) AS month, SUM(mismatch_usd) AS mismatch_usd ",
        "FROM fact_sync_exception WHERE NOT is_matched ",
        "AND booking_date >= add_months((SELECT MAX(booking_date) FROM fact_sync_exception), -3) GROUP BY 1 "]},
    {"name": "ds_churn", "displayName": "Churn reasons", "queryLines": [
        "SELECT period, reason_category, competitor_named, account_name, lost_arr_usd ",
        "FROM fact_churn_reason WHERE reason_category <> 'Renewed' "]},
]

# ============ PAGE 1 — Executive Summary ============
p1 = [
    text("p1-title", ["# RevOps — Revenue Intelligence Cockpit\n", "\n",
                      "**Where to look:** one NRR line is diving (that's Mid-Market) while new business stays steady. "
                      "Watch plan variance and renewal exposure below."], 0, 0, 12, 2),
    counter("p1-kpi-arr", "ds_nrr", "sum(ending_arr_usd)", "SUM(`ending_arr_usd`)", "Total Ending ARR",
            0, 3, fmt=cur(2), period=("monthly(period)", "DATE_TRUNC(\"MONTH\", `period`)")),
    counter("p1-kpi-nrr", "ds_nrr", "avg(nrr_rolling_frac)", "AVG(`nrr_rolling_frac`)", "Blended NRR %", 3, 3, fmt=pct(1)),
    counter("p1-kpi-nnarr", "ds_forecast_plan", "sum(actual_nnarr_usd)", "SUM(`actual_nnarr_usd`)",
            "Net-New ARR", 6, 3, fmt=cur(2), period=("monthly(period)", "DATE_TRUNC(\"MONTH\", `period`)")),
    counter("p1-kpi-risk", "ds_health", "sum(at_risk_arr_usd)", "SUM(`at_risk_arr_usd`)", "At-Risk ARR", 9, 3, fmt=cur(2)),
    line("p1-nrr-line", "ds_nrr", "monthly(period)", "DATE_TRUNC(\"MONTH\", `period`)",
         "avg(nrr_rolling_frac)", "AVG(`nrr_rolling_frac`)", "Net revenue retention % by segment — trailing 12 months",
         0, 5, 12, 6, color="segment_name", yfmt=pct(1), mappings=seg_map()["mappings"]),
    bar("p1-ending-arr", "ds_nrr", "segment_name", "`segment_name`", "sum(ending_arr_usd)",
        "SUM(`ending_arr_usd`)", "Ending ARR by segment", 0, 11, 6, 5, horizontal=True,
        color="segment_name", mappings=seg_map()["mappings"], valfmt=cur(2)),
    bar("p1-nnarr-seg", "ds_forecast_plan", "segment_name", "`segment_name`", "sum(actual_nnarr_usd)",
        "SUM(`actual_nnarr_usd`)", "Net-new ARR by segment", 6, 11, 6, 5, horizontal=True,
        color="segment_name", mappings=seg_map()["mappings"], valfmt=cur(2)),
]

# ============ PAGE 2 — Retention & Attainment ============
ann = [{"type": "vertical-line", "encodings": {
    "x": {"dataValue": "2026-02-01T00:00:00.000", "dataType": "DATETIME"},
    "label": {"value": "Competitive losses begin"}, "color": {"value": {"hex": WARN}}}}]
p2 = [
    text("p2-alert", ["## ⚠️ ALERT: Mid-Market NRR compressed to 90%\n", "\n",
                     "Down 18 points from 108% four months ago. Churn + contraction surged ~6.5× while new business "
                     "stayed flat. Recommend immediate review. *(Scheduled Insight runs weekly against sem_nrr_retention.)*"],
         0, 0, 12, 2),
    combo("p2-mm-combo", "ds_nrr", "monthly(period)", "DATE_TRUNC(\"MONTH\", `period`)",
          [("sum(churn_contraction_usd)", "SUM(`churn_contraction_usd`)", "Churn + contraction ($)")],
          [("avg(nrr_rolling_pct)", "AVG(`nrr_rolling_pct`)", "NRR rolling %")],
          "Mid-Market NRR & churn — 12 months", 0, 2, 8, 6, annotations=ann),
    bar("p2-variance", "ds_forecast_plan", "segment_name", "`segment_name`", "avg(variance_frac)",
        "AVG(`variance_frac`)", "Actual vs plan net-new ARR variance % by segment — 2026 YTD", 8, 2, 4, 6,
        horizontal=True, color="plan_status", valfmt=pct(1),
        mappings=[{"value": "Below plan", "color": DANGER}, {"value": "Above plan", "color": HEALTHY}],
        filters=[{"expression": "year(`period`) = 2026"}]),
    bar("p2-sync", "ds_sync", "monthly(month)", "DATE_TRUNC(\"MONTH\", `month`)", "sum(mismatch_usd)",
        "SUM(`mismatch_usd`)", "CRM↔billing unmatched bookings (last 90 days)", 0, 8, 6, 5,
        cattype="temporal", valfmt=cur(2)),
    table("p2-attain", "ds_quota", [
        ("segment_name", "Segment"), ("team", "Team"),
        ("attainment_pct", "Attainment %", num(1)), ("pipeline_coverage_x", "Pipeline coverage (x)", num(2))],
        "Attainment detail by segment/team", 6, 8, 6, 5,
        styles={"attainment_pct": {"type": "basic", "rules": [
            {"condition": {"operand": {"type": "data-value", "value": "90"}, "operator": "<"},
             "backgroundColor": {"hex": DANGER}}]}}),
]

# ============ PAGE 3 — Net-New ARR & Scenario Modeling ============
p3 = [
    text("p3-title", ["# Net-New ARR & Scenario Modeling\n", "\n",
                     "Stress-test the outlook. Forecast tiles come from `predict_net_new_arr('Mid-Market')`; "
                     "the projection line compares a baseline vs worst-case ending-ARR path over 8 quarters."], 0, 0, 12, 2),
    counter("p3-m1", "ds_forecast_mm", "m1", "`m1`", "Forecast M1", 0, 2, fmt=cur(2)),
    counter("p3-m2", "ds_forecast_mm", "m2", "`m2`", "Forecast M2", 3, 2, fmt=cur(2)),
    counter("p3-m3", "ds_forecast_mm", "m3", "`m3`", "Forecast M3", 6, 2, fmt=cur(2)),
    counter("p3-qt", "ds_forecast_mm", "quarter_total", "`quarter_total`", "Quarter Total", 9, 2, fmt=cur(2)),
    line("p3-nnarr", "ds_nnarr", "period", "`period`", "actual_nnarr", "`actual_nnarr`",
         "Mid-Market net-new ARR — actual vs forecast", 0, 5, 12, 6, yfmt=cur(2)),
    line("p3-proj", "ds_arr_proj", "quarter", "`quarter`", "baseline_arr", "`baseline_arr`",
         "Mid-Market ending-ARR projection — baseline vs worst-case (8 quarters)", 0, 11, 12, 6,
         xtype="quantitative", yfmt=cur(2)),
]
# add second series to p3-nnarr (forecast) and p3-proj (worst-case) manually
p3[5]["widget"]["queries"][0]["query"]["fields"].append({"name": "forecast_nnarr", "expression": "`forecast_nnarr`"})
p3[5]["widget"]["spec"]["encodings"]["y"] = {"scale": {"type": "quantitative"}, "format": cur(2), "fields": [
    {"fieldName": "actual_nnarr", "displayName": "Actual"}, {"fieldName": "forecast_nnarr", "displayName": "Forecast"}]}
p3[5]["widget"]["queries"][0]["query"]["disaggregated"] = True
p3[6]["widget"]["queries"][0]["query"]["fields"].append({"name": "worst_case_arr", "expression": "`worst_case_arr`"})
p3[6]["widget"]["spec"]["encodings"]["y"] = {"scale": {"type": "quantitative"}, "format": cur(2), "fields": [
    {"fieldName": "baseline_arr", "displayName": "Baseline +2%/qtr"}, {"fieldName": "worst_case_arr", "displayName": "Worst case -3.5%/qtr"}]}
p3[6]["widget"]["queries"][0]["query"]["disaggregated"] = True

# ============ PAGE 4 — Renewal Risk ============
apac_map = [{"value": "APAC", "color": DANGER}, {"value": "EMEA", "color": "#FFDD4A"},
            {"value": "NA", "color": HEALTHY}]
p4 = [
    text("p4-title", ["# Renewal Risk — At-Risk Accounts\n", "\n",
                     "Three strategic Enterprise accounts hold $11.6M ARR with $5.4M at risk — low health, low usage."], 0, 0, 12, 2),
    table("p4-atrisk", "ds_atrisk", [
        ("account_name", "Account"), ("region", "Region"), ("segment_name", "Segment"),
        ("health_score", "Health", num(0)), ("product_usage_pct", "Usage %", num(0)),
        ("days_to_renewal", "Days to renewal", num(0)),
        ("at_risk_arr_usd", "At-risk ARR", cur(2)), ("arr_usd", "ARR", cur(2))],
        "At-risk accounts — renewals in the next 90 days", 0, 2, 12, 6,
        styles={"at_risk_arr_usd": {"type": "basic", "rules": [
            {"condition": {"operand": {"type": "data-value", "value": "0"}, "operator": ">"},
             "backgroundColor": {"hex": DANGER}}]}}),
    bar("p4-health", "ds_health_bottom", "account_name", "`account_name`", "min(health_score)",
        "MIN(`health_score`)", "Health score by account (bottom 15)", 0, 8, 6, 6, horizontal=True,
        color="region", mappings=apac_map, valfmt=num(0)),
    bar("p4-region", "ds_health", "region", "`region`", "sum(at_risk_arr_usd)",
        "SUM(`at_risk_arr_usd`)", "At-risk ARR by region", 6, 8, 6, 6, horizontal=True,
        color="region", mappings=apac_map, valfmt=cur(2)),
    bar("p4-atrisk-seg", "ds_health", "segment_name", "`segment_name`", "sum(at_risk_arr_usd)",
        "SUM(`at_risk_arr_usd`)", "At-risk ARR by segment", 0, 14, 6, 5, horizontal=True,
        color="segment_name", mappings=seg_map()["mappings"], valfmt=cur(2)),
    scatter("p4-scatter", "ds_health", "health_score", "arr_usd", "at_risk_arr_usd", "segment_name",
            "Health vs ARR (bubble = at-risk ARR)", 6, 14, 6, 5, mappings=seg_map()["mappings"], yfmt=cur(2)),
]
# p4-atrisk table: sort + top 10 via dataset filter — add ORDER BY through per-widget filter not possible; use dataset
# Instead: p4 at-risk table should show at-risk sorted desc. Add a dedicated ordered dataset.

# ============ PAGE 5 — GTM Efficiency & Quota ============
p5 = [
    text("p5-title", ["# GTM Efficiency & Quota\n", "\n",
                     "Q2 S&M ran ~+12% over the prior run-rate. CAC, magic number, and attainment by channel & segment."], 0, 0, 12, 2),
    bar("p5-spend", "ds_gtm_month", "monthly(month)", "DATE_TRUNC(\"MONTH\", `month`)", "sum(sm_spend)",
        "SUM(`sm_spend`)", "S&M spend by month (Q2 spike)", 0, 2, 12, 5, cattype="temporal",
        color="is_q2", valfmt=cur(2),
        mappings=[{"value": "Q2 2026", "color": DANGER}, {"value": "Other", "color": HEALTHY}]),
    bar("p5-cac", "ds_gtm", "channel_name", "`channel_name`", "avg(cac)", "AVG(`cac`)",
        "CAC by channel", 0, 7, 6, 5, horizontal=True, valfmt=cur(2)),
    pie("p5-pipe", "ds_gtm", "sum(attributed_pipeline)", "SUM(`attributed_pipeline`)", "channel_name",
        "Attributed pipeline % by channel", 6, 7, 6, 5),
    bar("p5-attain", "ds_quota", "team", "`team`", "avg(attainment_frac)", "AVG(`attainment_frac`)",
        "Attainment by segment/team", 0, 12, 6, 5, horizontal=True, color="segment_name",
        mappings=seg_map()["mappings"], valfmt=pct(1)),
    bar("p5-magic", "ds_gtm", "channel_name", "`channel_name`", "avg(magic_number)", "AVG(`magic_number`)",
        "Magic number by channel", 6, 12, 6, 5, horizontal=True, valfmt=num(2)),
]

# ============ FILTERS PAGE ============
filters = [
    filt("f-date", "filter-date-range-picker", "Date Range",
         [("ds_nrr", "period"), ("ds_forecast_plan", "period"), ("ds_quota", "period")], 0, 0),
    filt("f-segment", "filter-multi-select", "Segment",
         [("ds_nrr", "segment_name"), ("ds_health", "segment_name"),
          ("ds_forecast_plan", "segment_name"), ("ds_quota", "segment_name")], 4, 0),
    filt("f-region", "filter-multi-select", "Region", [("ds_health", "region")], 8, 0),
]

pages = [
    {"name": "exec", "displayName": "Executive Summary", "pageType": "PAGE_TYPE_CANVAS",
     "layoutVersion": "GRID_V1", "layout": p1},
    {"name": "retention", "displayName": "Retention & Attainment", "pageType": "PAGE_TYPE_CANVAS",
     "layoutVersion": "GRID_V1", "layout": p2},
    {"name": "nnarr", "displayName": "Net-New ARR & Scenario", "pageType": "PAGE_TYPE_CANVAS",
     "layoutVersion": "GRID_V1", "layout": p3},
    {"name": "risk", "displayName": "Renewal Risk", "pageType": "PAGE_TYPE_CANVAS",
     "layoutVersion": "GRID_V1", "layout": p4},
    {"name": "gtm", "displayName": "GTM Efficiency", "pageType": "PAGE_TYPE_CANVAS",
     "layoutVersion": "GRID_V1", "layout": p5},
    {"name": "filters", "displayName": "Filters", "pageType": "PAGE_TYPE_GLOBAL_FILTERS",
     "layoutVersion": "GRID_V1", "layout": filters},
]

theme = {
    "canvasBackgroundColor": {"light": "#F5F7FB", "dark": "#0F1419"},
    "widgetBackgroundColor": {"light": "#FFFFFF", "dark": "#161B22"},
    "widgetBorderColor": {"light": "#FFFFFF", "dark": "#161B22"},
    "fontColor": {"light": "#1F2530", "dark": "#E8ECF0"},
    "selectionColor": {"light": "#4F7CE3", "dark": "#8ACAFF"},
    "visualizationColors": ["#094074", "#3C6997", "#5ADBFF", "#FFDD4A", "#FE9000"],
    "widgetHeaderAlignment": "LEFT",
}

dashboard = {"datasets": datasets, "pages": pages,
             "uiSettings": {"theme": theme, "genieSpace": {
                 "isEnabled": True, "overrideId": "01f1ad62f147167eba19adef16388070", "enablementMode": "ENABLED"}}}

if __name__ == "__main__":
    with open("dashboard.json", "w") as f:
        json.dump(dashboard, f, indent=2)
    print("wrote dashboard.json")
