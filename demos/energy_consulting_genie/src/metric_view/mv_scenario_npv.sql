CREATE OR REPLACE VIEW solution_builder.demo_scenario_shift_alert_015b3e.mv_scenario_npv
WITH METRICS
LANGUAGE YAML
AS $$
version: 1.1
source: solution_builder.demo_scenario_shift_alert_015b3e.gold_projection_detail
comment: "Governed NPV metric for strategic scenarios. NPV in $B is the discounted sum of annual free cash flows across the 2025-2045 horizon. Filter Vintage = Current for the latest outlook."
dimensions:
  - name: Scenario
    expr: scenario_name
    synonyms:
      - strategy
      - strategy scenario
  - name: Vintage
    expr: vintage_label
    comment: "Model run: Current (latest) or Prior (pre-revision)."
  - name: Horizon Year
    expr: horizon_year
measures:
  - name: NPV ($B)
    expr: SUM(annual_cashflow_musd) / 1000.0
    comment: "Net Present Value in $ billions - discounted sum of annual free cash flows over the horizon. Risk bands: Attractive >= 3.5, Marginal 2.5-3.5, Unattractive < 2.5."
    synonyms:
      - NPV
      - net present value
      - scenario value
      - project value
  - name: Annual Cash Flow ($M)
    expr: SUM(annual_cashflow_musd)
    comment: "Annual free cash flow in $ millions at the selected horizon year."
    synonyms:
      - cash flow
      - annual cashflow
  - name: Production (mmboe)
    expr: SUM(production_mmboe)
    synonyms:
      - production
      - volume
$$
