# Ontology Page draft — "Scenario NPV"

UC Semantics **Pages** are Beta and **UI-only** (no SQL/CLI/API/DABs). This file is
the source content to paste into the Page editor (or feed to Genie Code's
"generate from source"). Steps are in `ontology/README_ontology_page.md`.

---

## Page fields

- **Title:** Scenario NPV
- **Domain:** Energy Scenario Intelligence  *(create this domain first — see the guide)*
- **Owner:** Reserves / Advisory  *(assign to yourself / the practice group)*
- **Synonyms:** NPV, net present value, scenario valuation, scenario NPV, project NPV, full-life NPV
- **Short description:** The authoritative definition of the net present value reported
  for a reserves projection scenario — the discounted, full-life value of
  a scenario's forecast cashflows, net of carbon compliance cost.

---

## Body (rich text)

**Definition.** Scenario NPV is the net present value of a projection scenario's
annual cashflows across the full 10-20 year horizon, net of carbon compliance cost,
discounted to today. It is the headline number an advisor takes to a client when
comparing strategic options.

**Reported in:** billions of USD (B USD).

**How it is measured here (authoritative source).** Scenario NPV and its efficiency
ratios are computed only by the governed metric view — do not hand-roll them:
- Metric view: `mv_scenario_economics` (measure `Full-Life NPV (B USD)`)
- Grain: scenario x vintage x horizon year, sourced from `gold_projection_detail`
- **Full-life NPV = the cumulative NPV at the final horizon year** (`MAX(cumulative_npv_busd)`),
  viewed per Scenario x Vintage. Do not sum NPV across scenarios — scenarios are
  alternative futures, not additive line items.
- Companion efficiency measures (also ratios of aggregates, correct at any grouping):
  `Cashflow per BOE (USD)`, `Carbon Intensity (USD/BOE)`, `Carbon Cost % of Cashflow`.

**Vintage.** Each scenario is re-run on a cadence; every run is a **vintage**
(`Prior` vs `Current`). A scenario's NPV is only comparable across vintages — that
comparison is what surfaces a shift.

**Risk band.** Every scenario NPV carries a qualitative band (e.g., **Attractive**,
and lower bands) that translates the number into advisory language for the client.

**Scenario Shift alert.** When a scenario's `Current` NPV moves materially from its
`Prior` vintage, the scenario-shift alert fires (`is_alerted = true`). This is the
signal for the advisor to revisit the client's strategy. Example in the current data:
**Accelerated Transition** fell from **$4.2B (Prior) to $2.6B (Current)** as the carbon
price floor rose and gas-demand growth turned negative — carbon cost jumped from 4.2%
to 10.8% of cashflow.

---

## Related assets (tag these in the editor)

- Metric view: `solution_builder.<schema>.mv_scenario_economics`
- Table: `solution_builder.<schema>.gold_scenario_npv_trend` (NPV by vintage, risk band, is_alerted)
- Table: `solution_builder.<schema>.gold_projection_detail` (per-year cashflow / carbon / production)
- Table: `solution_builder.<schema>.gold_assumptions` (driver deltas behind a shift)
- Dashboard: "[dev] Scenario Strategy"

## Sources

- Scenario methodology (this demo's semantic layer)
- Scenario assumptions memo: `gold_assumptions_doc` (parsed from the PDF via ai_parse_document)

---

## Optional follow-on Pages (one line each, same domain)

- **MMBOE** — millions of barrels of oil equivalent; the common production/reserves unit
  that normalizes oil and gas volumes. Source: `gold_projection_detail.production_mmboe`.
- **Carbon Price Floor** — the assumed minimum carbon price (USD/tonne) driving carbon
  compliance cost; a key scenario driver. Source: `gold_assumptions.carbon_price_floor_*`.
- **Carbon Intensity** — carbon cost per BOE (USD/BOE); how carbon-exposed a scenario's
  production is. Source: metric view measure `Carbon Intensity (USD/BOE)`.
- **Risk Band** — the qualitative rating attached to a scenario NPV for client advice.
  Source: `gold_scenario_npv_trend.risk_band`.
