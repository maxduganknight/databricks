# Lakeflow — Data Generation + PDF-in-Volume + Small Transformation Chain

> **Simple-demo contract.** One self-contained data-generation script produces the full **raw → silver → gold** layering for the scenario-strategy universe: the `raw_*` source tables, the `silver_*` cleaned facts, and the `gold_*` tables the dashboard + Genie read. There is **no SDP** here — the script does the layering inline with `spark.sql`. A **PDF assumptions memo lands in a Unity Catalog Volume**, and **AI Functions** (`ai_parse_document`) turns it into a queryable text table so Genie can answer from unstructured content. Talking track: *"in production this is Lakeflow Connect pulling projection outputs + market/policy feeds, and SDP shaping them — here the data-gen does the equivalent layering inline so the demo lands in minutes."*

---

## Shared Context (defined once here; later specs reference "from 01")

**Company / persona**: Energy consultancy. Persona: **Dr. Amara Okonkwo**, Senior Energy Strategy Consultant, advising a client on 10–20 year energy profitability ahead of a strategy session.

**The five strategic scenarios** (verbatim — `raw_scenarios`):
- `SCEN-01` **Base Case** — reference outlook, current policy trajectory. Risk band steady ~`Attractive`.
- `SCEN-02` **Accelerated Transition** — fast decarbonization + rapid electrification. **THIS is the scenario that swings.**
- `SCEN-03` **Delayed Transition** — policy + adoption lag; hydrocarbons persist longer.
- `SCEN-04` **High Demand** — strong global energy demand growth, tighter supply.
- `SCEN-05` **Carbon Constrained** — aggressive carbon pricing, constrained hydrocarbon capex.

**Projection horizon**: annual points **2025 → 2045** (21 years) per scenario per model vintage.

**Model vintages (as-of dates)**: weekly model runs over the trailing ~6 months. `VINTAGE_LATEST = NOW` (most recent load), and every prior Friday back to `NOW − 26 weeks`. Each vintage carries a full set of projections + assumption values per scenario. **`NOW = datetime.now()` by default** (rolling time → the trend's right edge is always this week); set `DEMO_PIN_TIME=1` to freeze `NOW` to `2026-09-15` for reproducible runs (stable vintage dates/IDs for a recorded video).

**The catalyst — the swing** (load-bearing):
- **Accelerated Transition (`SCEN-02`)** scenario NPV holds ~**$4.2B** across all vintages until **`SWING_VINTAGE = NOW − 3 weeks`**, then **drops to ~$2.6B (−38%)** and stays there through `VINTAGE_LATEST`. Build-up is a single step-down at `SWING_VINTAGE` (a new data + assumptions revision landed that week), NOT a gradual drift — the eye must catch one line falling off a cliff ~3 weeks ago while the other four hold flat.
- **The other four scenarios hold steady** across all vintages (± small noise only): Base Case ~$3.8B, Delayed Transition ~$3.5B, High Demand ~$4.5B, Carbon Constrained ~$2.9B.
- **Risk bands** (derived from NPV): `Attractive` ≥ $3.5B · `Marginal` $2.5B–$3.5B · `Unattractive` < $2.5B. Accelerated Transition moves **Attractive → Marginal** at the swing. This band change is the "attractive to marginal" beat.

**The three assumption drivers that changed** (Accelerated Transition, at `SWING_VINTAGE`; `raw_assumptions` old→new). Every other scenario's drivers and every prior vintage of `SCEN-02` keep the "old" values:

| Driver (column) | Old value (pre-swing) | New value (SWING_VINTAGE →) | Narrative |
|---|---|---|---|
| `carbon_price_floor_usd_t` | 45 | 85 | Carbon-price floor legislation advanced; higher carbon cost on remaining hydrocarbons |
| `policy_effective_year` | 2032 | 2028 | Policy pulled forward ~4 years |
| `gas_demand_growth_pct` | 0.8 | -0.6 | Long-run gas demand revised **down 1.4 pts/yr** on efficiency + electrification |

Other assumption columns (unchanged, carried for context): `oil_price_usd_bbl` (~70), `discount_rate_pct` (~9.0).

**Assumptions memo PDF** (the unstructured beat). A scenario-assumptions memo PDF sits in a UC Volume. Its narrative body MUST contain — verbatim, so Genie can quote it — the analyst rationale:
> *"Scenario SCEN-02 Accelerated Transition — assumptions revision. The carbon-price floor legislation has advanced, with the effective year pulled forward from 2032 to 2028 and the floor raised from $45/t to $85/t. Long-run natural gas demand growth is revised down by 1.4 percentage points per year (from +0.8%/yr to −0.6%/yr) on accelerating efficiency gains and electrification. Combined, these cut projected 2035–2045 cash flows, moving the scenario from an attractive NPV of ~$4.2B to a marginal ~$2.6B. Recommended client actions: hedge carbon exposure, re-time capex to the revised policy schedule, and revisit the assumed transition pace."*

Keywords Genie searches the parsed doc for: *"carbon-price floor"*, *"2028"*, *"1.4 percentage points"*, *"attractive"*, *"marginal"*, *"hedge carbon exposure"*.

**`is_alerted` flag** — denormalized onto `gold_scenario_npv_trend` (TRUE iff `scenario_id = 'SCEN-02'` at `VINTAGE_LATEST`). Dashboard KPI + Genie use it to isolate the alerted scenario.

---

## A. Data Generation Script

**Skill**: `databricks-synthetic-data-gen` — read `SKILLS/databricks-synthetic-data-gen/SKILL.md` first. For the PDF, read `SKILLS/databricks-unstructured-pdf-generation/SKILL.md`.

**Runtime**: pre-provisioned databricks-connect venv (path in system prompt). Do NOT create a new venv. Target `solution_builder.demo_scenario_shift_alert_015b3e`.

One self-contained, idempotent script produces all three layers plus the PDF + parsed doc table:

### Raw tables

- **`raw_scenarios`** 5 rows — `scenario_id` (PK, `SCEN-0N`), `scenario_name`, `scenario_description`, `strategy_theme`. Hand-curated verbatim from Shared Context (fixed IDs so downstream validates by name).
- **`raw_projections`** ~2,200 rows (5 scenarios × 21 years × ~26 vintages, but only the changed scenario needs all vintages at annual grain — see note) — `projection_id` (PK), `scenario_id` (FK), `scenario_name`, `vintage_date` (DATE, as-of model run), `horizon_year` (INT 2025–2045), `annual_cashflow_musd` (annual free cash flow, $M), `cumulative_npv_busd` (running discounted NPV to that year, $B), `production_mmboe`, `realized_price_usd_boe`, `carbon_cost_musd`. *Cash-flow curve: Accelerated Transition's post-swing curve is visibly lower in years 2035–2045 (the carbon cost + demand-down effect), matching the −38% NPV.*
  - *Grain note:* to keep the file lean, generate the **full 21-year annual curve for all 5 scenarios at `VINTAGE_LATEST` and at the pre-swing vintage `NOW − 4 weeks`** (for the before/after cash-flow chart), and the **NPV summary point for every scenario at every weekly vintage** (drives the trend). You do not need the full annual curve at every one of the 26 vintages.
- **`raw_assumptions`** ~130 rows (5 scenarios × ~26 vintages) — `scenario_id` (FK), `scenario_name`, `vintage_date`, `carbon_price_floor_usd_t`, `policy_effective_year`, `gas_demand_growth_pct`, `oil_price_usd_bbl`, `discount_rate_pct`. SCEN-02 flips the three drivers at `SWING_VINTAGE` per the table above; everything else holds.

### Silver tables (cleaned + enriched — gold reads these)

- **`silver_scenario_npv`** — one row per (scenario, vintage): `scenario_id/name`, `vintage_date`, `npv_busd`, `risk_band` (derived from NPV thresholds), joined `strategy_theme`. This is the trend fact.
- **`silver_assumptions`** — `raw_assumptions` enriched with a `is_current_vintage` flag and, for each driver, a `*_changed` boolean comparing this vintage to the scenario's immediately prior vintage.

### Gold tables (what the dashboard + Genie read — COMMENT every table + column so Genie reads them as semantics)

- **`gold_scenario_npv_trend`** ~130 rows — per (scenario, vintage): `scenario_id`, `scenario_name`, `vintage_date`, `npv_busd`, `risk_band`, `strategy_theme`, `is_alerted`. **Drives the swing trend line + risk-band KPIs.**
- **`gold_projection_detail`** ~210 rows — per (scenario, horizon_year, vintage_label ∈ {`Current`, `Prior`}): `scenario_id`, `scenario_name`, `horizon_year`, `vintage_label`, `annual_cashflow_musd`, `cumulative_npv_busd`, `carbon_cost_musd`, `production_mmboe`. **Drives the before/after cash-flow curve for the alerted scenario.**
- **`gold_assumptions`** ~10 rows — per scenario at Current vs Prior vintage, pivoted so each of the three headline drivers has an `_old` and `_new` column plus a `_delta`: `scenario_id`, `scenario_name`, `carbon_price_floor_old/new`, `policy_effective_year_old/new`, `gas_demand_growth_old/new`, `driver_changed_count`. **Drives the assumption-change table + Genie's "what drove it" answer.**
- **`gold_assumptions_doc`** (from AI Functions — see § B) — parsed text of the assumptions-memo PDF: `doc_path`, `scenario_id`, `parsed_text` (full memo body), `page_count`. **Genie reads `parsed_text` to quote the analyst rationale.**

---

## B. Unstructured Data — PDF in a Volume + AI Functions parse

1. **Volume**: create managed Volume `assumptions_docs` in the schema. Its Volume path is `/Volumes/solution_builder/demo_scenario_shift_alert_015b3e/assumptions_docs/`.
2. **PDF**: the user has an example PDF to upload. Generate a **synthetic fallback** assumptions-memo PDF (`scen02_accelerated_transition_assumptions.pdf`) using the `databricks-unstructured-pdf-generation` skill so the demo is self-contained — its body MUST contain the verbatim analyst-rationale paragraph + keywords from Shared Context. Upload it to the Volume. **Note in `resources.json` that the user can drop their own PDF into the same Volume to replace it** (the parse step re-runs over whatever PDFs are in the Volume).
3. **Parse with AI Functions**: use `ai_parse_document` (read `SKILLS/databricks-ai-functions/SKILL.md`) over the PDF(s) in the Volume to produce `gold_assumptions_doc.parsed_text`. Tag each parsed row with `scenario_id = 'SCEN-02'` (the memo is the Accelerated Transition revision). This is the only AI Function in the build — keep it to a single parse step feeding one table.

---

## C. Data Shaping Rules

- **NPV noise**: ±1.5% gaussian on each non-swing NPV point per vintage so the flat lines look like real model runs, not ruled lines — but small enough that SCEN-02's −38% cliff is unmistakably the only real move.
- **The swing is one step, in the past**: SCEN-02 NPV = ~$4.2B for every vintage `< SWING_VINTAGE`, ~$2.6B for every vintage `≥ SWING_VINTAGE` (`SWING_VINTAGE = NOW − 3 weeks`). Peak/plateau of the drop sits ~3 weeks back with 3 weeks of "new normal" tail to its right — never pinned at the chart's rightmost edge.
- **Cash-flow curve coherence**: Prior-vintage SCEN-02 annual cash flow and Current-vintage differ mainly in **2035–2045** (carbon cost rises, gas volumes fall) so the two curves fan apart in the back half — visually explaining where the $1.6B went.
- **Risk-band coherence**: with the thresholds above, only SCEN-02 crosses a band boundary (Attractive→Marginal) at the swing. High Demand stays Attractive, Base Case stays Attractive, Delayed Transition sits at the Attractive/Marginal edge (~$3.5B → keep it just above so it doesn't flicker), Carbon Constrained stays Marginal throughout.
- **Assumption coherence**: the three `_new` values in `gold_assumptions` for SCEN-02 MUST equal the "new" column of the Shared Context table AND match the numbers quoted in the PDF body. Data ↔ document must agree.

---

## D. Validation

The LLM writes one-line checks. Fix the synth before `04-ai-bi.md` if any fail.

**Load-bearing (gate the story):**
- **The swing** — `gold_scenario_npv_trend WHERE scenario_id='SCEN-02'` ordered by `vintage_date`: NPV ~$4.2B up to `NOW−3w`, ~$2.6B after; the drop is ≥35%. No other scenario moves more than ~3% across its vintages.
- **Band change** — SCEN-02 `risk_band` = `Attractive` at the pre-swing vintage, `Marginal` at `VINTAGE_LATEST`. No other scenario changes band.
- **Drivers** — `gold_assumptions WHERE scenario_id='SCEN-02'`: `carbon_price_floor_old/new` = 45/85, `policy_effective_year_old/new` = 2032/2028, `gas_demand_growth_old/new` = 0.8/−0.6, `driver_changed_count` = 3. All other scenarios `driver_changed_count` = 0.
- **Cash-flow fan** — `gold_projection_detail WHERE scenario_id='SCEN-02'`: Current vintage annual cash flow < Prior in every year ≥ 2035; roughly equal before 2033.
- **PDF parsed** — `gold_assumptions_doc`: ≥1 row, `parsed_text` contains *"carbon-price floor"*, *"2028"*, *"1.4 percentage points"*, *"attractive"*, *"marginal"*, *"hedge carbon exposure"*.

**Smoke checks:** `is_alerted` TRUE only for SCEN-02 at `VINTAGE_LATEST` · every table has table + column COMMENTs · vintage dates cover the full 26-week window · Volume exists and holds the PDF.

Surface the resolved `SWING_VINTAGE`, `VINTAGE_LATEST`, and Volume path (notebook exit JSON / `resources.json`) so `04-ai-bi.md` and Genie can reference them.
