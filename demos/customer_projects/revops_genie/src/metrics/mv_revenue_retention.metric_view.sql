-- Unity Catalog metric view: governed Net Revenue Retention KPIs.
-- Deployed by the revops_setup job's deploy_metric_view sql_task (runs on a SQL
-- warehouse; metric views need DBR 17.2+ semantics). The :catalog / :schema
-- parameters are passed by the task so the view lands in the same target-prefixed
-- schema as the sem_* views it sources.
--
-- Why a metric view (demo talking point): NRR and GRR are ratios of aggregates.
-- Summing or averaging a per-row NRR % is wrong; the metric view encodes the
-- correct ratio ONCE so the dashboard, the 5 Genie spaces, and the CRO briefing
-- all get the same number at any grouping (segment, quarter, blended).

USE CATALOG IDENTIFIER(:catalog);
USE SCHEMA IDENTIFIER(:schema);

CREATE OR REPLACE VIEW mv_revenue_retention
WITH METRICS
LANGUAGE YAML
AS $$
version: 1.1
source: sem_nrr_retention
comment: "Governed Net Revenue Retention KPIs. One authoritative NRR / gross-retention definition shared by the dashboard, the Genie spaces, and the CRO briefing. Grain: GTM segment by month."
dimensions:
  - name: Segment
    expr: segment_name
    comment: "GTM segment: Enterprise, Mid-Market, SMB, Startup."
  - name: Period
    expr: period
    comment: "Month of the retention snapshot (first of month)."
measures:
  - name: Starting ARR
    expr: SUM(starting_arr_usd)
    comment: "Total ARR at the start of the period (USD)."
  - name: Ending ARR
    expr: SUM(ending_arr_usd)
    comment: "Total ARR at the end of the period (USD)."
  - name: Expansion ARR
    expr: SUM(expansion_arr_usd)
    comment: "ARR added from existing customers via upsell/cross-sell (USD)."
  - name: Contraction ARR
    expr: SUM(contraction_arr_usd)
    comment: "ARR lost to downgrades on retained customers (USD)."
  - name: Churned ARR
    expr: SUM(churned_arr_usd)
    comment: "ARR lost to full cancellations (USD)."
  - name: Net Revenue Retention
    expr: "MEASURE(`Ending ARR`) / NULLIF(MEASURE(`Starting ARR`), 0) * 100"
    comment: "NRR = ending ARR / starting ARR, as a percent. Ratio of aggregates so it recomputes correctly at ANY grouping (segment, quarter, blended). Never average the per-row NRR."
  - name: Gross Retention Rate
    expr: "(MEASURE(`Starting ARR`) - MEASURE(`Churned ARR`) - MEASURE(`Contraction ARR`)) / NULLIF(MEASURE(`Starting ARR`), 0) * 100"
    comment: "GRR = (starting - churn - contraction) / starting, as a percent. Excludes expansion, so it never exceeds 100 and isolates pure retention loss."
$$;
