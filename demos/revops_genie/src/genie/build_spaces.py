"""Build the 5 RevOps Genie spaces (spec 04-ai-bi.md §A)."""
import json, uuid, subprocess, os

WH = "a94beda3aab06fa4"
PARENT = "/Workspace/Users/2301685f-87d8-4a01-9f27-b105951ab400/genie_spaces"
CS = "solution_builder.demo_revops_intelligence"

def nid(): return uuid.uuid4().hex

SIGN = ("Sign convention: expansion & new ARR are POSITIVE, contraction & churned ARR are NEGATIVE — "
        "sem_nrr_retention already handles the sign flip and reports positive display values; "
        "always read NRR from sem_nrr_retention and use nrr_rolling_pct for the headline number.")

def space(title, desc, tables, story, chips, examples):
    sq = sorted([{"id": nid(), "question": [q]} for q in chips], key=lambda x: x["id"])
    ex = sorted([{"id": nid(), "question": [q], "sql": [s]} for q, s in examples], key=lambda x: x["id"])
    payload = {
        "version": 2,
        "config": {"sample_questions": sq},
        "data_sources": {"tables": sorted([{"identifier": f"{CS}.{t}"} for t in tables], key=lambda x: x["identifier"])},
        "instructions": {
            "text_instructions": [{"id": nid(), "content": [story]}],
            "example_question_sqls": ex,
        },
    }
    ss = json.dumps(payload)
    body = json.dumps({"warehouse_id": WH, "title": title, "description": desc,
                       "parent_path": PARENT, "serialized_space": ss})
    r = subprocess.run(["databricks", "genie", "create-space", "--json", body],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(f"FAIL {title}: {r.stderr[-800:]}")
        return None
    sid = json.loads(r.stdout)["space_id"]
    print(f"OK {title} -> {sid}")
    return sid

SPACES = [
    dict(
        title="Net Revenue Retention",
        desc="Mid-Market NRR compressed from 108% to 90% over 4 months — retention-driven, new business flat.",
        tables=["sem_nrr_retention", "dim_segment", "dim_calendar"],
        story=("## PURPOSE\n"
               "- WHAT HAPPENED: Mid-Market net revenue retention fell from ~108% to ~90% over the last four months; the erosion is retention-driven (churn + contraction surged ~6.5x) while new business stayed flat.\n"
               "- WHAT TO HELP MAYA DO: Maya Chen (Director of RevOps) needs to see NRR by segment, spot which segment is compressing, and break down the drivers of the Mid-Market decline.\n"
               "- TONE: concise, executive, evidence-first.\n"
               f"## DATA QUALITY NOTES\n- {SIGN}"),
        chips=[
            "Show me net revenue retention by segment for the last 12 months",
            "Which segment has the worst NRR trend this year?",
            "Why is Mid-Market NRR compressing? Break down the drivers.",
            "Ending ARR by segment, trailing 12 months",
        ],
        examples=[
            ("Why is Mid-Market NRR compressing? Break down the drivers.",
             f"SELECT period, new_arr_usd, expansion_arr_usd, contraction_arr_usd, churned_arr_usd, nrr_rolling_pct "
             f"FROM {CS}.sem_nrr_retention WHERE segment_name = 'Mid-Market' "
             f"AND period >= add_months((SELECT MAX(period) FROM {CS}.sem_nrr_retention), -11) ORDER BY period"),
            ("Show me net revenue retention by segment for the last 12 months",
             f"SELECT segment_name, period, nrr_rolling_pct FROM {CS}.sem_nrr_retention "
             f"WHERE period >= add_months((SELECT MAX(period) FROM {CS}.sem_nrr_retention), -11) ORDER BY segment_name, period"),
        ],
    ),
    dict(
        title="Net-New ARR & Renewal Risk",
        desc="3 strategic Enterprise accounts hold $11.6M ARR / $5.4M at risk; Mid-Market next-quarter net-new ARR forecast via predict_net_new_arr.",
        tables=["sem_account_health", "dim_account", "metric_net_new_arr"],
        story=("## PURPOSE\n"
               "- WHAT HAPPENED: Three strategic Enterprise accounts (ACCT0012, ACCT0049, ACCT0010) hold $11.6M ARR with $5.4M at risk; health scores 27-34 and product usage below 45% signal systemic risk.\n"
               "- WHAT TO HELP MAYA DO: surface at-risk accounts and exposure, compare high vs low usage, forecast Mid-Market net-new ARR, and recommend CRO next steps.\n"
               "- TONE: concise, executive, action-oriented.\n"
               "## DATA QUALITY NOTES\n"
               "- Forecasted net-new ARR comes from the UC table function predict_net_new_arr('<segment>'); call it as SELECT * FROM solution_builder.demo_revops_intelligence.predict_net_new_arr('Mid-Market').\n"
               "- is_at_risk flags accounts; at_risk_arr_usd is exposure.\n"
               "## Instructions you must follow when providing summaries\n"
               "- For the CRO synthesis: name the 3 Enterprise accounts, the $5.4M at-risk total, health 27-34, usage <45% as systemic; recommend save-plays, prioritize the feature gap, and exec sponsorship."),
        chips=[
            "Which strategic accounts are at risk in the next 90 days and what's the total exposure?",
            "What is the forecasted net-new ARR for Mid-Market for the next quarter?",
            "Show me health-score trends for our Enterprise accounts",
            "How does ARR compare between high-usage and low-usage accounts?",
            "Summarize the Enterprise renewal risk and recommend next steps for the CRO",
        ],
        examples=[
            ("Which strategic accounts are at risk in the next 90 days and what's the total exposure?",
             f"SELECT account_name, region, segment_name, health_score, product_usage_pct, days_to_renewal, at_risk_arr_usd, arr_usd "
             f"FROM {CS}.sem_account_health WHERE is_at_risk = TRUE OR days_to_renewal <= 90 ORDER BY at_risk_arr_usd DESC"),
            ("What is the forecasted net-new ARR for Mid-Market for the next quarter?",
             f"SELECT * FROM {CS}.predict_net_new_arr('Mid-Market')"),
        ],
    ),
    dict(
        title="Forecast Accuracy & Plan Attainment",
        desc="Mid-Market ran -9.5% (Mar) / -10.5% (Jan) below plan; Enterprise +1.3% to +13.2% ahead.",
        tables=["sem_forecast_plan", "dim_segment", "sem_quota_attainment", "fact_plan"],
        story=("## PURPOSE\n"
               "- WHAT HAPPENED: Mid-Market net-new ARR ran below plan (Jan -10.5%, Mar -9.5%) while Enterprise ran +1.3% to +13.2% ahead of plan for 2026 YTD.\n"
               "- WHAT TO HELP MAYA DO: compare actual vs plan by segment/month, identify teams below quota, and read pipeline coverage.\n"
               "- TONE: concise, executive.\n"
               "## DATA QUALITY NOTES\n"
               "- Read variance from sem_forecast_plan.variance_pct (positive = ahead of plan, negative = below plan)."),
        chips=[
            "What is each segment's actual vs plan net-new ARR and variance % for 2026 year to date?",
            "Which teams are most below quota this quarter?",
            "Show me pipeline coverage by segment for the current quarter",
        ],
        examples=[
            ("What is each segment's actual vs plan net-new ARR and variance % for 2026 year to date?",
             f"SELECT segment_name, period, actual_nnarr_usd, plan_nnarr_usd, variance_pct FROM {CS}.sem_forecast_plan "
             f"WHERE year(period) = 2026 ORDER BY segment_name, period"),
            ("Which teams are most below quota this quarter?",
             f"SELECT segment_name, team, attainment_pct, pipeline_coverage_x FROM {CS}.sem_quota_attainment "
             f"WHERE period = (SELECT MAX(period) FROM {CS}.sem_quota_attainment) ORDER BY attainment_pct ASC"),
        ],
    ),
    dict(
        title="Churn & Renewal Intelligence",
        desc="Churn reasons extracted from QBR/cancellation PDFs — competitive displacement + feature gap by month.",
        tables=["fact_churn_reason", "sem_account_health", "dim_account"],
        story=("## PURPOSE\n"
               "- WHAT HAPPENED: Churn reasons were extracted from 16 QBR/cancellation PDFs via ai_parse_document + ai_extract. Lost ARR escalates by month, split into Competitive Displacement (competitor ProcureIQ) and Missing-Feature Downgrade (Real-Time Budget Approvals).\n"
               "- WHAT TO HELP MAYA DO: break down lost ARR by month and reason, identify the dominant competitor, and find accounts lost to a missing feature.\n"
               "- TONE: concise, evidence-first.\n"
               "## DATA QUALITY NOTES\n"
               "- fact_churn_reason grain is document x reason_category. Exclude reason_category = 'Renewed' when measuring lost ARR (Renewed rows carry retained, not lost, ARR)."),
        chips=[
            "What is actually driving Mid-Market churn? Break down lost ARR by month and reason.",
            "Which competitor shows up most in our churn reasons?",
            "Show me the accounts we lost to a missing feature in the last quarter",
        ],
        examples=[
            ("What is actually driving Mid-Market churn? Break down lost ARR by month and reason.",
             f"SELECT period, reason_category, ROUND(SUM(lost_arr_usd)) AS lost_arr FROM {CS}.fact_churn_reason "
             f"WHERE reason_category <> 'Renewed' GROUP BY period, reason_category ORDER BY period, reason_category"),
            ("Which competitor shows up most in our churn reasons?",
             f"SELECT competitor_named, COUNT(*) AS mentions, ROUND(SUM(lost_arr_usd)) AS lost_arr FROM {CS}.fact_churn_reason "
             f"WHERE competitor_named IS NOT NULL GROUP BY competitor_named ORDER BY lost_arr DESC"),
        ],
    ),
    dict(
        title="GTM Efficiency & Quota",
        desc="Q2 S&M ran +12% over plan; CAC, magic number, and quota attainment by segment/channel.",
        tables=["sem_gtm_spend", "sem_quota_attainment", "dim_channel", "dim_rep"],
        story=("## PURPOSE\n"
               "- WHAT HAPPENED: Q2 sales & marketing spend ran ~+12% over plan. This space covers CAC, magic number, attributed pipeline, and quota attainment by segment and channel.\n"
               "- WHAT TO HELP MAYA DO: analyze CAC by channel, spend vs plan, and pipeline-to-spend efficiency.\n"
               "- TONE: concise, executive.\n"
               "## DATA QUALITY NOTES\n"
               "- cac_usd = S&M spend per new logo; magic_number = attributed pipeline / S&M spend."),
        chips=[
            "What is CAC by channel this year?",
            "Show me S&M spend vs plan by month — where did we overspend?",
            "Which channels have the best attributed-pipeline-to-spend ratio?",
        ],
        examples=[
            ("What is CAC by channel this year?",
             f"SELECT channel_name, cac_usd, new_logos, sm_spend_usd FROM {CS}.sem_gtm_spend ORDER BY cac_usd DESC"),
            ("Which channels have the best attributed-pipeline-to-spend ratio?",
             f"SELECT channel_name, magic_number, attributed_pipeline_usd, sm_spend_usd FROM {CS}.sem_gtm_spend ORDER BY magic_number DESC"),
        ],
    ),
]

if __name__ == "__main__":
    ids = {}
    for s in SPACES:
        sid = space(**s)
        if sid:
            ids[s["title"]] = sid
    print(json.dumps(ids, indent=2))
