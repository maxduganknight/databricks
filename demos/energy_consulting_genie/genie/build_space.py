import json, uuid

def nid(): return uuid.uuid4().hex

CAT = "solution_builder"
SCH = "demo_scenario_shift_alert_015b3e"

def t(name): return f"{CAT}.{SCH}.{name}"

sample_questions = [
    "Which scenario projection changed the most in the last month, and by how much?",
    "Did any scenario change risk band recently?",
    "What assumptions changed for the Accelerated Transition scenario? Show old vs new.",
    "For Accelerated Transition, how do the current annual cash flows compare to the prior projection?",
    "Summarize the analyst rationale for the Accelerated Transition revision.",
    "What strategy options should I put to the client given this swing?",
]

example_sqls = [
    ("Which scenario projection changed the most in the last month, and by how much?",
     f"WITH bounds AS (SELECT scenario_id, scenario_name, "
     f"FIRST_VALUE(npv_busd) OVER (PARTITION BY scenario_id ORDER BY vintage_date) AS first_npv, "
     f"FIRST_VALUE(npv_busd) OVER (PARTITION BY scenario_id ORDER BY vintage_date DESC) AS last_npv "
     f"FROM {t('gold_scenario_npv_trend')}) "
     f"SELECT DISTINCT scenario_name, ROUND(first_npv,2) AS npv_before, ROUND(last_npv,2) AS npv_now, "
     f"ROUND((last_npv-first_npv)/first_npv*100,1) AS pct_change, ABS(last_npv-first_npv) AS abs_change "
     f"FROM bounds ORDER BY abs_change DESC"),
    ("What assumptions changed for the Accelerated Transition scenario? Show old vs new.",
     f"SELECT scenario_name, carbon_price_floor_old, carbon_price_floor_new, "
     f"policy_effective_year_old, policy_effective_year_new, "
     f"gas_demand_growth_old, gas_demand_growth_new, driver_changed_count "
     f"FROM {t('gold_assumptions')} WHERE scenario_id = 'SCEN-02'"),
    ("Summarize the analyst rationale for the Accelerated Transition revision.",
     f"SELECT parsed_text FROM {t('gold_assumptions_doc')} WHERE scenario_id = 'SCEN-02'"),
]

text_instruction = "\n".join([
    "## PURPOSE",
    "- Answer questions about strategic scenario projections (5 scenarios, 2025-2045, re-run weekly as vintages) for a consultant advising a client on 10-20 year energy profitability.",
    "- Users are senior energy strategy consultants; assume advisory fluency but non-technical SQL.",
    "",
    "## DISAMBIGUATION",
    "- 'The alert' / 'the swing' / 'the scenario that changed' means the Accelerated Transition scenario (SCEN-02), which dropped from ~$4.2B (Attractive) to ~$2.6B (Marginal), about 3 weeks ago.",
    "- Risk bands: Attractive >= $3.5B, Marginal $2.5-3.5B, Unattractive < $2.5B (on npv_busd).",
    "- 'Latest' or 'now' means the most recent vintage_date; 'prior' means the pre-swing vintage.",
    "",
    "## DATA QUALITY NOTES",
    "- gold_scenario_npv_trend: NPV per (scenario, vintage) over time — the swing-trend fact.",
    "- gold_assumptions: the 3 headline drivers per scenario with old/new/delta (carbon_price_floor, policy_effective_year, gas_demand_growth). Only SCEN-02 has driver_changed_count = 3; others are 0.",
    "- gold_projection_detail: annual 2025-2045 cash flow at Current vs Prior vintage; the gap opens in 2035-2045 for SCEN-02.",
    "- gold_assumptions_doc.parsed_text: the analyst assumptions-memo PDF, parsed with AI Functions. For 'why', 'rationale', or 'what does the memo say' questions, read parsed_text WHERE scenario_id = 'SCEN-02' and quote it.",
    "",
    "## Instructions you must follow when providing summaries",
    "- State the scenario name, the NPV before and after (in $B), and the percent change.",
    "- When explaining the cause, name the three drivers (carbon-price floor 45->85 $/t, policy year 2032->2028, gas demand growth 0.8 -> -0.6 %/yr) and offer the client actions from the memo: hedge carbon exposure, re-time capex, revisit transition pace.",
])

col_cfg = {
    "gold_scenario_npv_trend": [
        {"column_name": "risk_band", "enable_format_assistance": True, "enable_entity_matching": True,
         "description": ["Risk band derived from NPV: Attractive (>=$3.5B), Marginal ($2.5-3.5B), Unattractive (<$2.5B)."]},
        {"column_name": "scenario_name", "enable_format_assistance": True, "enable_entity_matching": True,
         "synonyms": ["scenario", "strategy"]},
        {"column_name": "npv_busd", "description": ["Projected cumulative NPV in $ billions."], "synonyms": ["NPV", "value"]},
        {"column_name": "is_alerted", "description": ["TRUE only for the alerted scenario (Accelerated Transition) at the latest vintage."]},
    ],
    "gold_assumptions_doc": [
        {"column_name": "parsed_text", "description": ["Full text of the analyst assumptions-memo PDF (parsed via AI Functions). Quote from here for 'why' / 'rationale' questions."], "synonyms": ["memo", "analyst note", "rationale", "document"]},
    ],
}

tables = []
for name in ["gold_scenario_npv_trend", "gold_projection_detail", "gold_assumptions", "gold_assumptions_doc", "raw_scenarios"]:
    entry = {"identifier": t(name)}
    if name in col_cfg:
        entry["column_configs"] = sorted(col_cfg[name], key=lambda c: c["column_name"])
    tables.append(entry)
tables = sorted(tables, key=lambda x: x["identifier"])

payload = {
    "version": 2,
    "config": {"sample_questions": sorted([{"id": nid(), "question": [q]} for q in sample_questions], key=lambda x: x["id"])},
    "data_sources": {"tables": tables},
    "instructions": {
        "example_question_sqls": sorted([{"id": nid(), "question": [q], "sql": [s]} for q, s in example_sqls], key=lambda x: x["id"]),
        "text_instructions": [{"id": nid(), "content": [text_instruction]}],
    },
}
print(json.dumps(payload))
