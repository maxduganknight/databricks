# Metric View + Genie Ontology Page — NPV

Adds a governed semantic layer for the demo's load-bearing metric, **NPV**. Two
pieces: (A) a Unity Catalog **metric view** that defines NPV as a governed
`MEASURE()`, and (B) a **Genie Ontology Page** that gives NPV a shared business
definition, risk-band decision rules, and synonyms — so every Genie space,
dashboard, and agent reasons about "NPV" and "attractive/marginal" the same way.

Tables referenced here are defined in `01-lakeflow.md`.

---

## A. Metric View — `mv_scenario_npv`

**Skill**: `databricks-metric-views` — read `SKILLS/databricks-metric-views/SKILL.md`.

**Source**: `gold_projection_detail` (annual 2025-2045 cash flow per scenario per
vintage). File: `src/metric_view/mv_scenario_npv.sql` (`CREATE OR REPLACE VIEW …
WITH METRICS LANGUAGE YAML`).

- **Dimensions**: `Scenario` (`scenario_name`, syn: strategy), `Vintage`
  (`vintage_label` — Current / Prior), `Horizon Year` (`horizon_year`).
- **Measures**:
  - **`NPV ($B)`** = `SUM(annual_cashflow_musd) / 1000.0` — the discounted sum of
    annual free cash flows in $B. Syn: NPV, net present value, scenario value,
    project value. **Coherence**: equals the stored `gold_scenario_npv_trend.npv_busd`
    the dashboard reads (verified: High Demand 4.5, Base Case 3.8, Delayed
    Transition 3.65, Carbon Constrained 2.9, Accelerated Transition 2.6 at Current).
  - **`Annual Cash Flow ($M)`** = `SUM(annual_cashflow_musd)`.
  - **`Production (mmboe)`** = `SUM(production_mmboe)`.
- **Deploy note**: create via `spark.sql` (databricks-connect or a job notebook),
  NOT the aitools query CLI — the CLI mangles the multi-line YAML heredoc. The DAB
  wires `src/deploy/deploy_metric_view.py` which reads the `.sql` and runs it.
- **Query rule (Genie + SQL)**: always `MEASURE(\`NPV ($B)\`)`; filter
  `Vintage = 'Current'` for the latest outlook. Never put a measure in WHERE/GROUP BY.

**Validation**: `SELECT Scenario, MEASURE(\`NPV ($B)\`) FROM mv_scenario_npv WHERE
Vintage='Current' GROUP BY Scenario` returns the five scenarios matching the
dashboard's NPV values.

---

## B. Genie Ontology Page — NPV

The Genie Ontology is the shared semantic layer under Genie / Genie One. An
**Ontology Page** for NPV centralizes the definition + decision rules once, so
they don't live scattered in each Genie space's text instructions.

**Why NPV is a good ontology candidate** (the demo's talking point):
- It's a **defined business metric**, not raw data — one definition, reused everywhere.
- It carries **decision rules** (the risk bands) that must be answered consistently.
- It has **synonyms** and a small connected vocabulary (vintage, scenario, risk band).
- It's **reused by many consumers** — the alert, Genie, the dashboard, and the memo skill all pivot on it.

**Ontology Page content** (author in the Genie Ontology UI / semantic catalog):

- **Term**: `NPV` (Net Present Value)
- **Definition**: "The total value of a scenario's projected cash flows over the
  2025-2045 horizon, discounted to present-day dollars and expressed in $ billions.
  The single measure of how valuable a strategy is over the long run."
- **Backing metric**: `mv_scenario_npv` → measure `NPV ($B)` (governed formula:
  discounted sum of annual free cash flows). Points at the metric view from A, so
  the term resolves to a real computed value.
- **Synonyms**: net present value, scenario value, project value, strategy value, outlook value.
- **Decision rules (risk bands)** — the governed thresholds every consumer must apply:
  - `Attractive` — NPV ≥ $3.5B
  - `Marginal` — $2.5B ≤ NPV < $3.5B
  - `Unattractive` — NPV < $2.5B
- **Related terms**: `Scenario`, `Vintage` (model run), `Risk Band`, `Discount Rate` (9.0%), `Assumption Driver` (carbon-price floor, policy year, gas demand growth).
- **Usage guidance**: "Compare scenarios at the same Vintage. A scenario is
  'attractive' or 'marginal' by its risk band, not by raw rank. A material change
  is an NPV move that crosses a band boundary between vintages."

**Coherence with the rest of the demo**:
- The Genie space's `text_instructions` risk-band definitions (in `04-ai-bi.md`)
  and the metric view / ontology thresholds MUST match: Attractive ≥ 3.5, Marginal
  2.5-3.5, Unattractive < 2.5. If one changes, change all.
- The Genie space should reference `mv_scenario_npv` as a governed source for NPV
  questions (in addition to the gold tables), so answers use the ontology-defined metric.

**Talking track**: "NPV isn't just a column — it's a governed business term. The
**Genie Ontology** holds its definition, its formula (via the metric view), and the
risk-band decision rules in one place. Every Genie space, every dashboard, every
agent that mentions NPV inherits the same meaning — no drift, no re-explaining."
