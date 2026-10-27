# AI/BI — Dashboard (5 pages) + Genie Spaces (5)

Tables, `sem_*` views, and `predict_net_new_arr()` are defined in `01-lakeflow.md`. Widgets read the `sem_*` views (and a few facts) directly. All objects live in `solution_builder.demo_revops_intelligence`.

> **Talking-track-only products** (do NOT build): **Unity Catalog** (global governance, already in place — just ensure grants from 01), **Lakeflow Connect** (ingest narrative). **Databricks One** surfaces the dashboard + spaces automatically once built. Genie One + Genie Code ARE built (scheduled insight in 06, skill in 07).

---

## A. Genie Spaces (5)

**Skill:** `databricks-genie-agents` — read `SKILLS/databricks-genie-agents/SKILL.md` before implementing. Each space is **self-sufficient**: set the space `description` (1–3 sentences naming the storyline + headline number), a story-context `text_instruction` at the top of `instructions.text_instructions[]` (WHAT HAPPENED · WHAT TO HELP MAYA DO · TONE · the sign-convention / metric ontology note), `sample_questions` chips = the recommended prompts for that space in arc order, and curated `example_question_sqls` for the load-bearing ones. Encode the **sign convention** ontology note in every space that touches `fact_arr_movement`/`sem_nrr_retention`: *"expansion & new ARR are POSITIVE, contraction & churned ARR are NEGATIVE — sem_nrr_retention handles the sign flip; always read NRR from sem_nrr_retention (use nrr_rolling_pct for the headline)."*

All spaces attach the relevant `sem_*` view(s) plus supporting dims. Add every space id to `resources.json` under `genie_spaces` (see § C).

### 1. Net Revenue Retention
Tables: `sem_nrr_retention`, `dim_segment`, `dim_calendar`. **Description:** Mid-Market NRR compressed from 108% to 90% over 4 months — retention-driven, new business flat. Chips (arc order):
- "Show me net revenue retention by segment for the last 12 months"
- "Which segment has the worst NRR trend this year?"
- **"Why is Mid-Market NRR compressing? Break down the drivers."** ← curated SQL: Mid-Market monthly new/expansion/churn+contraction/nrr_rolling_pct trailing 12 months from `sem_nrr_retention`, showing new business flat + churn/contraction surge. **This is the Step-2 punchline.**
- "Ending ARR by segment, trailing 12 months"

### 2. Net-New ARR & Renewal Risk
Tables: `sem_account_health`, `dim_account`, `metric_net_new_arr`, and access to `predict_net_new_arr()`. **Description:** 3 strategic Enterprise accounts hold $11.6M ARR / $5.4M at risk; Mid-Market next-quarter net-new ARR forecast via predict_net_new_arr. Chips:
- **"Which strategic accounts are at risk in the next 90 days and what's the total exposure?"** ← curated SQL: `sem_account_health WHERE is_at_risk = TRUE OR days_to_renewal <= 90` ORDER BY at_risk_arr_usd DESC → ACCT0012/0049/0010 with health, usage, days_to_renewal, at_risk, arr.
- **"What is the forecasted net-new ARR for Mid-Market for the next quarter?"** ← curated SQL: `SELECT * FROM predict_net_new_arr('Mid-Market')` → 1.20 / 1.14 / 1.36 / 3.69M.
- "Show me health-score trends for our Enterprise accounts"
- "How does ARR compare between high-usage and low-usage accounts?"
- "Summarize the Enterprise renewal risk and recommend next steps for the CRO" (Step-5 synthesis — text instruction primes: 3 Enterprise accounts, $5.4M at risk, health 27–34, usage <45% = systemic; recommend save-plays / prioritize feature gap / exec sponsorship).

### 3. Forecast Accuracy & Plan Attainment
Tables: `sem_forecast_plan`, `dim_segment`, `sem_quota_attainment`, `fact_plan`. **Description:** Mid-Market ran −9.5% (Mar) / −10.5% (Jan) below plan; Enterprise +1.3% to +13.2% ahead. Chips:
- **"What is each segment's actual vs plan net-new ARR and variance % for 2026 year to date?"** ← curated SQL from `sem_forecast_plan` 2026 YTD by segment/month. **Step-5 cross-space handoff punchline.**
- "Which teams are most below quota this quarter?"
- "Show me pipeline coverage by segment for the current quarter"

### 4. Churn & Renewal Intelligence
Tables: `fact_churn_reason`, `sem_account_health`, `dim_account`. **Description:** churn reasons extracted from QBR/cancellation PDFs — competitive displacement + feature gap by month. Chips (built out in `06-unstructured-and-alert.md`):
- **"What is actually driving Mid-Market churn? Break down lost ARR by month and reason."** ← curated SQL over `fact_churn_reason` (excluding `Renewed`) by period + reason_category.
- "Which competitor shows up most in our churn reasons?"
- "Show me the accounts we lost to a missing feature in the last quarter"

### 5. GTM Efficiency & Quota
Tables: `sem_gtm_spend`, `sem_quota_attainment`, `dim_channel`, `dim_rep`. **Description:** Q2 S&M ran +12% over plan; CAC, magic number, and quota attainment by segment/channel. Chips:
- "What is CAC by channel this year?"
- "Show me S&M spend vs plan by month — where did we overspend?"
- "Which channels have the best attributed-pipeline-to-spend ratio?"

**Validation:** each space answers its curated question grounded in its `sem_*` view; the Mid-Market NRR, at-risk ARR, YTD variance, and `predict_net_new_arr('Mid-Market')` answers exactly match the contract values in `01-lakeflow.md`.

---

## B. Dashboard — *Revenue Intelligence — Office of RevOps* (5 pages)

**Skill:** `databricks-aibi-dashboards` — read `SKILLS/databricks-aibi-dashboards/SKILL.md` before implementing (it owns JSON shape, encoding rules, grid math, color pinning, silent-failure pitfalls). This spec is story-level (WHAT). Save locally as `PROJECT/dashboard.json`. Set `--dataset-catalog` / `--dataset-schema` on `databricks lakeview create`. Link Genie space #1 (Net Revenue Retention) as the primary attached space.

### Theme (revenue-executive, cool→warm)
```
canvasBackgroundColor: #F5F7FB / #0F1419 (dark)
widgetBackgroundColor: #FFFFFF / #161B22
widgetBorderColor:     same as widgetBackgroundColor (no visible border)
fontColor:             #1F2530 / #E8ECF0
selectionColor:        #4F7CE3 / #8ACAFF
visualizationColors:   ["#094074","#3C6997","#5ADBFF","#FFDD4A","#FE9000"]
widgetHeaderAlignment: LEFT
```
**Semantic pins (literal-hex everywhere, never `themeColorType`):** danger / below-plan / NRR-cliff / at-risk → `#FE9000` (vivid orange) or `#FFDD4A` for annotations; healthy / above-plan → `#3C6997` steel blue. **Segment pins** (consistent across every widget colored by segment): Mid-Market → `#FE9000` (the protagonist, always warm), Enterprise → `#3C6997`, SMB → `#094074`, Startup → `#5ADBFF`.

### Datasets
| Name | Source | Powers |
|---|---|---|
| `ds_nrr` | `sem_nrr_retention` (segment × month) | Exec KPIs, NRR-by-segment line, ARR-by-segment, Mid-Market cliff, churn surge |
| `ds_health` | `sem_account_health` (account) | At-risk table, health by account/region, at-risk vs ARR, usage |
| `ds_forecast_plan` | `sem_forecast_plan` (segment × month) | Actual-vs-plan variance bars, net-new-ARR trend |
| `ds_nnarr` | `metric_net_new_arr` + a `predict_net_new_arr('Mid-Market')` lateral | Net-new-ARR actual vs forecast trend, forecast tiles |
| `ds_quota` | `sem_quota_attainment` (segment × team × month) | Attainment by team, pipeline coverage, win rate |
| `ds_gtm` | `sem_gtm_spend` | S&M spend mix, CAC, magic number |
| `ds_sync` | `fact_sync_exception` | CRM↔billing unmatched chart |
| `ds_churn` | `fact_churn_reason` | Churn lost-ARR by month & reason (built in 06) |

**No date clamps in datasets** — the global Date Range filter is the single windowing source.

### Global filters (left panel)
Date Range (`period`/`renewal_date`), Region, Segment — bound to `ds_nrr`, `ds_health`, `ds_forecast_plan`, `ds_quota`. Default All.

### Page 1 — Executive Summary (the glance)
- **`title`** markdown (12-wide): RevOps cockpit; what to look at (NRR by segment — one line diving, new business steady, plan variance, renewal exposure).
- **4 KPI counters** (`ds_nrr` / `ds_forecast_plan` / `ds_health`): Total Ending ARR (SUM ending_arr_usd, currency compact), Blended NRR % (rolling), Net-New ARR (SUM actual_nnarr), At-Risk ARR (SUM at_risk_arr_usd). Pin values `#094074`.
- **`line` "Net revenue retention % by segment — trailing 12 months"** (12-wide, `ds_nrr`): x=`period` monthly, y=`nrr_rolling_pct`, color=`segment_name` with segment pins. **Mid-Market (orange) is the one line collapsing from ~108% to ~90% while the others stay flat and high** — the 5-second hook. Frame description: *"One line dives. That's Mid-Market."*
- **`bar` "Ending ARR by segment"** (6-wide, `ds_nrr`): y=segment, x=SUM ending_arr_usd. + **`bar` "Net-new ARR by segment"** (6-wide, `ds_forecast_plan`): actual_nnarr by segment.

### Page 2 — Retention & Attainment (the alert surface — Step 1)
- **`text` ⚠️ alert widget** (12-wide, top): markdown styled as a Scheduled Insight notification — *"⚠️ ALERT: Mid-Market NRR compressed to 90% — down 18 points from 108% four months ago. Churn + contraction surged ~6.5× while new business stayed flat. Recommend immediate review."* This is the **notification surface** the demo opens on. Note it runs weekly against `sem_nrr_retention`.
- **`line`/`combo` "Mid-Market NRR & churn — 12 months"** (8-wide, `ds_nrr` filtered Mid-Market): dual encoding — nrr_rolling_pct line (orange) collapsing + churned+contraction bars rising + new_arr line flat. Vertical annotation ~2026-02 "Competitive losses begin". Frame: *"New business flat, churn surging — retention-driven erosion."*
- **`bar` "Actual vs plan net-new ARR variance % by segment — 2026 YTD"** (4-wide, `ds_forecast_plan`): y=segment_name, x=variance_pct, color by sign (Mid-Market negative orange, Enterprise positive steel). *Mid-Market & SMB below zero, Enterprise well above.*
- **`bar` "CRM↔billing unmatched bookings (last 90 days)"** (6-wide, `ds_sync`): SUM mismatch_usd where not matched → ~$50.1k data-hygiene callout. + **`table` "Attainment detail by segment/team"** (6-wide, `ds_quota`): segment, team, attainment_pct, pipeline_coverage_x (color low attainment).

### Page 3 — Net-New ARR & Scenario Modeling (Step 4)
- **`title`** markdown: stress-test the outlook; how to use the sliders.
- **3 KPI counters** for `predict_net_new_arr('Mid-Market')`: Forecast M1 $1.20M, M2 $1.14M, M3 $1.36M (from `ds_nnarr`). + a Quarter Total $3.69M tile.
- **`line` "Mid-Market net-new ARR — actual vs forecast"** (12-wide, `ds_nnarr`): actual_nnarr history + forecast band for the next 3 months (from predict_net_new_arr). Frame: *"Same metric basis as actuals + plan — no reconciliation gap."*
- **Parameterized 8-quarter ending-ARR projection** (`combo`/`line`, 12-wide): dashboard **parameters** `New-Logo Growth %/qtr` (default +2), `Churn Rate Δ pts` (default 0), `Expansion Δ %` (default 0), `Win-Rate Δ pts` (default 0). Parameterized SQL over `sem_nrr_retention` projects ending ARR forward 8 quarters from the latest closed actuals; toggling drivers compresses projected ARR. Frame: *"Live parameterized SQL against the metric view — not a spreadsheet."* (If dashboard parameter wiring is impractical, ship a static baseline+worst-case comparison line and note the parameters in the frame description.)

### Page 4 — Renewal Risk / At-Risk Accounts (Step 3)
- **`title`** markdown: Enterprise renewal risk.
- **`table` "At-risk accounts — renewals in the next 90 days"** (12-wide, `ds_health`, sort at_risk_arr DESC, top 10): columns account_name, region, segment, health_score, product_usage_pct, days_to_renewal, at_risk_arr_usd, arr_usd. **ACCT0012/0049/0010 on top** — the hero table. Color/badge at-risk.
- **`bar` "Health score by account (bottom 15)"** (6-wide, `ds_health`): y=account_name, x=health_score, color by region (APAC pin). + **`bar` "At-risk vs total ARR by region"** (6-wide): stacked at-risk vs ARR by region — APAC/EMEA tower.
- **`bar` "At-risk ARR by segment"** (6-wide) + **`scatter` "Health vs ARR"** (6-wide, bubble size = at_risk_arr) — the 3 Enterprise dots sit bottom-right (low health, high ARR), isolated.

### Page 5 — GTM Efficiency & Quota
- **`title`** markdown: Q2 S&M overrun +12%.
- **`bar` "S&M spend actual vs plan by month"** (12-wide, `ds_gtm`/`ds_forecast_plan`): grouped actual vs plan by month, Q2 spike visible. Color actual orange when over plan.
- **`bar` "CAC by channel"** (6-wide, `ds_gtm`) + **`pie` "Attributed pipeline % by channel"** (6-wide, `ds_gtm`).
- **`bar` "Attainment by segment/team"** (6-wide, `ds_quota`) + **`bar` "Magic number by segment"** (6-wide, `ds_gtm`).

### Validation
Publish and confirm at a glance: Page 1 Mid-Market NRR line visibly collapses while others stay flat; Page 2 alert widget + churn-surge chart read; Page 4 the 3 Enterprise accounts top the at-risk table with $11.6M / $5.4M; Page 5 Q2 S&M spike; global filters update every widget. Add `dashboard_id` to `resources.json`.
