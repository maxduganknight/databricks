# Ontology Page draft — "Net Revenue Retention (NRR)"

UC Semantics **Pages** are Beta and **UI-only** (no SQL/CLI/API/DABs). This file is
the source content to paste into the Page editor (or feed to Genie Code's
"generate from source"). Steps are in `ontology/README_ontology_page.md`.

---

## Page fields

- **Title:** Net Revenue Retention (NRR)
- **Domain:** Revenue Intelligence  *(create this domain first — see the guide)*
- **Owner:** RevOps  *(assign to yourself / the RevOps group)*
- **Synonyms:** NRR, net revenue retention, net dollar retention, NDR, net retention
- **Short description:** The authoritative definition of Net Revenue Retention for
  GTM reporting. NRR is the percent of recurring revenue retained from the existing
  customer base over a period, including expansion and net of contraction and churn.

---

## Body (rich text)

**Definition.** Net Revenue Retention (NRR) measures how recurring revenue from the
customers you already had at the start of a period evolves by the end of it —
expansion adds, contraction and churn subtract, and **new-logo ARR is excluded**.

**Formula.**

> NRR (%) = Ending ARR / Starting ARR × 100
>
> where Ending ARR = Starting ARR + Expansion − Contraction − Churn (existing customers only)

**The 100% control line.** NRR at 100% means the existing base is exactly flat.
- **Above 100%** — expansion is outrunning losses (healthy).
- **Below 100%** — the base is shrinking on its own; new logos are subsidizing
  retention. Treat sustained sub-100% NRR in a segment as a retention emergency.

**Gross Retention Rate (GRR)**, the sibling metric, excludes expansion:
GRR (%) = (Starting ARR − Churn − Contraction) / Starting ARR × 100. GRR never
exceeds 100% and isolates pure retention loss.

**How it is measured here (authoritative source).** NRR and GRR are computed only
by the governed metric view — do not hand-roll them in ad-hoc SQL:
- Metric view: `mv_revenue_retention` (measures `Net Revenue Retention`, `Gross Retention Rate`)
- Grain: GTM segment × month, sourced from `sem_nrr_retention`
- Because the measures are **ratios of aggregates**, they recompute correctly at any
  grouping (segment, quarter, blended). **Never average or sum a per-row NRR %.**

**Reporting rule.** Always report NRR **by segment**. The blended all-segment number
can sit comfortably above 100% while a single segment (currently **Mid-Market**) has
already fallen through the line — the blend hides the problem.

---

## Related assets (tag these in the editor)

- Metric view: `solution_builder.<schema>.mv_revenue_retention`
- View: `solution_builder.<schema>.sem_nrr_retention`
- Dashboard: "[dev] Revenue Intelligence" (NRR cliff page)

## Sources

- RevOps metric definitions (this demo's semantic layer)
- QBR / cancellation evidence: `fact_churn_reason`

---

## Optional follow-on Pages (one line each, same domain)

- **Net-New ARR** — new-logo annual recurring revenue booked in a period; excludes
  expansion. Source: `sem_forecast_plan.actual_nnarr_usd`; forecast `predict_net_new_arr()`.
- **At-Risk ARR** — ARR on accounts flagged `is_at_risk` (low health, low usage, near
  renewal). Source: `sem_account_health.at_risk_arr_usd`.
- **Competitive Displacement** — churn reason: customer left for a named competitor
  (e.g., ProcureIQ). Source: `fact_churn_reason.reason_category`.
- **Mid-Market (segment)** — GTM segment entity; the segment currently driving the
  NRR compression.
