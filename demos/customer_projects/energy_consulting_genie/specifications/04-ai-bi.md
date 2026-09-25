# AI/BI — Alert + Genie + Dashboard

Tables and columns referenced here are defined in `01-lakeflow.md`. Widgets read the `gold_*` tables directly; the analyst rationale is read from `gold_assumptions_doc.parsed_text` (the parsed PDF) via Genie.

**Demo flow (the opening beat is the alert, NOT the dashboard):** a scheduled **Databricks SQL Alert** fires a written summary into the consultant's inbox → she clicks through to **Genie One** and asks the follow-up questions (structured + the PDF) → she opens the **dashboard later** to go deeper on the topics the conversation surfaced. Build order still: Genie space → dashboard → alert (the alert's `custom_description` points at the Genie space, so the space must exist first).

---

## 0. Databricks SQL Alert (the opening beat)

**Skill**: `databricks-dbsql` for the source view; alert via `databricks alerts-v2 create-alert`.

- **Source view** `vw_scenario_alert` — one row from `gold_scenario_npv_trend` for SCEN-02: `scenario_name`, `npv_before`, `npv_now`, `npv_change_pct`, `band_before`, `band_now`.
- **Alert** `Scenario Shift Alert_015b3e` — evaluates `npv_change_pct LESS_THAN -30` (the −38% swing trips it), scheduled weekly (Mon 07:00 UTC). Delivered to the owner's **inbox** by default; no external destination needed for the demo.
- **`custom_summary`**: one-line "Accelerated Transition swung from Attractive to Marginal (NPV −38%)."
- **`custom_description`**: WHAT (~$4.2B → ~$2.6B, −38%, ~$1.6B swing) · WHERE (band Attractive → Marginal, other four steady) · WHY CARE (this was the recommendation for the client session) · NEXT STEP (open the Genie space and ask which scenario changed and why, then summarize the analyst rationale). Mirror the README walkthrough Act 1.
- Record `alert_id` + `alert_source_view` in `resources.json`.

> **Talking-track-only products in the README** — do NOT build resources for these:
> - **Genie One** — workspace surface; the Genie space shows up there once built. Nothing to provision.
> - **Genie Code** — AI authoring assist inside the editor. Narrative only.
> - **Unity Catalog** — global governance layer, already in place (the catalog/schema/Volume grants from `01-lakeflow.md` are what's in effect).
> - **Lakeflow Connect** — ingest narrative, talk track only.

---

## A. Genie Space

**Skill**: `databricks-genie` — read `SKILLS/databricks-genie/SKILL.md` before implementing.

Create `Scenario Strategy_015b3e` Genie Space.

### Tables

`gold_scenario_npv_trend` (swing trend + risk bands + `is_alerted`), `gold_projection_detail` (before/after annual cash flows), `gold_assumptions` (the three driver old/new/delta), `raw_scenarios` (scenario names + themes), **`gold_assumptions_doc`** (parsed PDF text — the unstructured beat).

The analyst rationale lives on `gold_assumptions_doc.parsed_text`. When Amara asks *"summarize the analyst rationale for the Accelerated Transition revision"*, Genie reads `SELECT parsed_text FROM gold_assumptions_doc WHERE scenario_id='SCEN-02'` and quotes the memo inline — the unstructured half of the demo. Structured question hits the projection/assumption tables; document question hits the parsed PDF; same Genie space.

### Self-sufficient room

Wire all three so anyone opening the room understands the story:

- **Space `description`** (via `PATCH /api/2.0/genie/spaces/<id>`): 1–3 sentences — Accelerated Transition swung from attractive (~$4.2B) to marginal (~$2.6B), −38%, ~3 weeks ago; drivers = carbon price, policy timing, gas demand; source memo is queryable. Point to the suggested questions in order. Lift from the README.
- **Story-context `text_instruction`** at the TOP of `instructions.text_instructions[]`: WHAT HAPPENED · WHAT TO HELP AMARA DO · TONE (see below).
- **`sample_questions`** chips + matching `example_question_sqls` walk the arc in order.

### Instructions

```
You analyze strategic scenario projections for Dr. Amara Okonkwo (Senior Energy Strategy Consultant, non-technical). She advises a client on 10-20 year energy profitability and is prepping for a strategy session.

CONTEXT: We model 5 strategic scenarios (Base Case, Accelerated Transition, Delayed Transition, High Demand, Carbon Constrained) over 2025-2045, re-run weekly (vintages). Each scenario has a projected NPV ($B) and a risk band: Attractive >= $3.5B, Marginal $2.5-3.5B, Unattractive < $2.5B.

THE ALERT: The Accelerated Transition scenario (SCEN-02) swung from ~$4.2B (Attractive) to ~$2.6B (Marginal), a -38% drop, about 3 weeks ago. The other four scenarios held steady.

INVESTIGATION FLOW for "which scenario changed and why?":
1. gold_scenario_npv_trend -> NPV by scenario over vintage_date -> SCEN-02 drops off a cliff ~3 weeks ago; others flat.
2. gold_scenario_npv_trend -> risk_band for SCEN-02 moved Attractive -> Marginal at the swing vintage.
3. gold_assumptions WHERE scenario_id='SCEN-02' -> the 3 drivers that changed with old vs new: carbon_price_floor 45->85 $/t, policy_effective_year 2032->2028, gas_demand_growth 0.8 -> -0.6 %/yr.
4. gold_projection_detail WHERE scenario_id='SCEN-02' -> Current vs Prior annual cash flow -> the gap opens in 2035-2045 (where the NPV was lost).
5. gold_assumptions_doc WHERE scenario_id='SCEN-02' -> SELECT parsed_text -> quote the analyst rationale from the memo PDF inline. THIS IS THE PUNCHLINE for the "why" — surface it explicitly.

TONE: Concise, advisory, decision-oriented. Amara needs talking points for a client meeting: what moved, why, by how much ($), and the strategy options (hedge carbon exposure, re-time capex, revisit transition pace).
```

### Sample Questions — story-arc walk

Ship the full arc as chips; curate the load-bearing ones as `example_question_sqls`.

Chips (arc order):
1. **Headline** — "Which scenario projection changed the most in the last month, and by how much?"
2. **Risk band** — "Did any scenario change risk band recently?"
3. **Drivers** — "What assumptions changed for the Accelerated Transition scenario? Show old vs new."
4. **Where the value went** — "For Accelerated Transition, how do the current annual cash flows compare to the prior projection?"
5. **The document** — "Summarize the analyst rationale for the Accelerated Transition revision." *(reads `gold_assumptions_doc.parsed_text` — the PDF beat)*
6. **Recommendation** — "What strategy options should I put to the client given this swing?"

Curated SQLs (the ones where Genie shouldn't guess the join/shape):
- **Headline** — NPV change per scenario between the earliest and latest vintage from `gold_scenario_npv_trend`, ordered by absolute drop → SCEN-02 first.
- **Drivers** — `gold_assumptions WHERE scenario_id='SCEN-02'` selecting the three `_old`/`_new` pairs.
- **The document** — `SELECT parsed_text FROM gold_assumptions_doc WHERE scenario_id='SCEN-02'` (cross-content beat — Genie would otherwise not know the PDF table holds the answer).

### Validation

- "Which scenario changed the most?" → SCEN-02 with ~−38% / ~$1.6B, others flat.
- "What assumptions changed?" → carbon 45→85, policy 2032→2028, gas 0.8→−0.6.
- "Summarize the analyst rationale" → quotes memo text incl. *"carbon-price floor"*, *"2028"*, *"1.4 percentage points"*, *"hedge carbon exposure"*.

Add `genie_space_id` to `resources.json`.

---

## B. Dashboard

**Skill**: `databricks-aibi-dashboards` — read `SKILLS/databricks-aibi-dashboards/SKILL.md` before implementing. The skill owns JSON shape, encoding, grid math; this spec is story-level (WHAT).

Create `Scenario Strategy_015b3e` dashboard. Save locally as `PROJECT/dashboard.json`. Link the Genie space from section A. Set `--dataset-catalog solution_builder` and `--dataset-schema demo_scenario_shift_alert_015b3e` on `lakeview create` AND `update`.

### Why this dashboard works

- **A landscape overview, not a swing deep-dive**: this is the shared view the energy consultancy's advisors open to see *all the scenarios in play* — NPV, risk band, strategy theme, and the assumptions behind each. It is not about any single scenario's move; the swing/why lives in the alert → Genie beats.
- **Landscape at a glance**: how many scenarios sit in each risk band, the NPV spread best-vs-worst, and every scenario's outlook to 2045 — an advisor gets the lay of the land in 5 seconds.
- **Datasets kept lean** (3): `ds_overview_kpi` (band counts + spread), `ds_landscape` (per-scenario snapshot joined to its current assumptions), `ds_horizon` (all-5 cumulative-NPV + production curves to 2045).

### Theme

```
canvasBackgroundColor: #F5F7FB / #0F1419
widgetBackgroundColor: #FFFFFF / #161B22
widgetBorderColor:     same as widgetBackgroundColor (no visible border)
fontColor:             #1F2530 / #E8ECF0
selectionColor:        #0B5D3B (energy green) / #7FD1AE
visualizationColors:   ["#0B5D3B","#2E8B57","#66B2A0","#F4B740","#C0392B"]
widgetHeaderAlignment: LEFT
```

5-stop palette: deep green → sea-green → teal → amber → alert-red. **Semantic pins (literal-hex, never `themeColorType: position N`):**
- **Scenario lines** — pinned by NPV rank so the landscape reads consistently (High Demand `#0B5D3B` → Base Case `#2E8B57` → Delayed Transition `#66B2A0` → Carbon Constrained `#F4B740` → Accelerated Transition `#C0392B`).
- **Risk band (on the NPV bar)** — `Attractive` → `#0B5D3B` green, `Marginal` → `#F4B740` amber, `Unattractive` → `#C0392B` red.

### Datasets (3)

| Name | Source | Powers |
|---|---|---|
| `ds_overview_kpi` | `gold_scenario_npv_trend` latest vintage: COUNT scenarios, COUNT by band, NPV spread | 4 KPI counters |
| `ds_landscape` | `gold_scenario_npv_trend` latest vintage JOIN `silver_assumptions` (current vintage): scenario_name, npv_busd, risk_band, strategy_theme + carbon floor / policy year / gas growth / oil / discount | NPV-by-scenario bar + landscape table + filters |
| `ds_horizon` | `gold_projection_detail WHERE vintage_label='Current'`: scenario_name, horizon_year, cumulative_npv_busd, production_mmboe | cumulative-NPV outlook line + production outlook line |

### Global filters (left panel)

| Filter | Column | Datasets | Default |
|---|---|---|---|
| Scenario | `scenario_name` | ds_landscape | All |
| Risk band | `risk_band` | ds_landscape | All |

### Page — Scenario Landscape

12-column grid; `(x, y, w, h)`:

| Row (y) | x | w | h | Widget |
|---|---|---|---|---|
| 0  | 0 | 12 | 4 | `title` (markdown) |
| 4  | 0 | 3 | 3 | `kpi_n_scenarios` |
| 4  | 3 | 3 | 3 | `kpi_attractive` |
| 4  | 6 | 3 | 3 | `kpi_marginal` |
| 4  | 9 | 3 | 3 | `kpi_npv_spread` |
| 7  | 0 | 12 | 6 | `horizon_chart` (cumulative NPV to 2045, all scenarios) |
| 13 | 0 | 6 | 6 | `npv_by_scenario_bar` (ranked, colored by risk band) |
| 13 | 6 | 6 | 6 | `production_chart` (production outlook to 2045) |
| 19 | 0 | 12 | 6 | `landscape_table` |

**`title` — markdown (12-wide)**. Self-sufficient header: what the dashboard is (the scenario landscape the energy consultancy's advisors work from), the risk-band definitions, and what to look at on the page. Lift substance from the README.

**4 × `counter`** — source `ds_overview_kpi`: scenarios modeled · # Attractive · # Marginal · NPV spread best-vs-worst ($B).

**`horizon_chart` — `line` "Cumulative NPV outlook to 2045, by scenario"** (12-wide). Source `ds_horizon`. x = `horizon_year`, y = `cumulative_npv_busd`, color = `scenario_name` (rank pins above). *The strategic landscape — how each scenario's value builds over the 20-year horizon.*

**`npv_by_scenario_bar` — horizontal `bar` "Projected NPV by scenario (current vintage)"** (6-wide). Source `ds_landscape`. y = `scenario_name` (sort by value), x = `npv_busd`, color = `risk_band` (band pins above). *Ranked best-to-worst, colored by band.*

**`production_chart` — `line` "Production outlook to 2045, by scenario"** (6-wide). Source `ds_horizon`. x = `horizon_year`, y = `production_mmboe`, color = `scenario_name`. *The volume view behind the value.*

**`landscape_table` — `table` "Scenario landscape — NPV, risk band, theme & key assumptions"** (12-wide). Source `ds_landscape`. Columns: scenario, NPV ($B), risk band, strategy theme, carbon floor ($/t), policy year, gas demand %/yr. Sort NPV desc. *The full picture per scenario.*

### Validation

Open the published dashboard: KPIs read 5 scenarios / 3 Attractive / 2 Marginal / spread ~1.8; the cumulative-NPV curves fan across all five to 2045; the bar ranks scenarios and colors them by band; the landscape table lists NPV + band + theme + assumptions for each. Filters (scenario, risk band) update every widget. Add `dashboard_id` to `resources.json`.
