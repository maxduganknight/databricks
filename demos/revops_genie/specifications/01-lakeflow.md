# Lakeflow — RevOps Data Generation + Semantic Layer + Forecast Function

> **Simple-demo contract.** One self-contained, idempotent data-generation script (databricks-connect / Spark) produces the full revenue model: 7 dimension tables, 7 fact tables, then the 5 `sem_*` semantic views, the `metric_net_new_arr` source view, the `feat_monthly_nnarr` feature table, and the `predict_net_new_arr(segment)` UC SQL function. **No SDP** in the simple build — the script builds raw→curated inline with `spark.sql` CTAS. **No UC metric-views object and no trained ML model** — the "semantic metric views" are delivered as governed SQL views (`sem_*`), and `predict_net_new_arr()` is a UC SQL function. Talking track: *"in production this is where Lakeflow Connect drops Salesforce/billing/product-usage feeds and SDP shapes them; here the data-gen does the layering inline so the demo lands in minutes."*

**Catalog / schema:** `solution_builder.demo_revops_intelligence`. All objects (tables, `sem_*` views, `predict_net_new_arr`) live here. Every table and column carries a COMMENT so Genie reads them as semantics.

**Skill:** `databricks-synthetic-data-gen` — read `SKILLS/databricks-synthetic-data-gen/SKILL.md` first. Runtime: databricks-connect serverless (Python 3.12 already provisioned). Do NOT create a new venv.

---

## Shared Context (defined once — every downstream spec references these)

**Company:** the company (an AI-native procurement & spend-management SaaS). **Persona:** Maya Chen, Director of Revenue Operations.

**Segments** (`dim_segment`, exact IDs + names — used by every widget and space):
- `SEG-ENT` — "Enterprise" — the healthy, ahead-of-plan segment (but hosts the 3 at-risk strategic accounts)
- `SEG-MM` — "Mid-Market" — **the NRR-compression protagonist**
- `SEG-SMB` — "SMB" — small, stable
- `SEG-STARTUP` — "Startup" — small, high-velocity, stable

**Regions:** `NA`, `EMEA`, `APAC` (attribute on accounts/reps; the 3 at-risk accounts split APAC/EMEA).

**Time anchors:** `NOW` pinned to **2026-06-30** (this demo references specific fiscal months, so time is frozen). Monthly grain spans **2025-05 → 2026-06** (14 months) so trailing-12 and "2026 YTD" both resolve. Set an env flag to freeze; do not use `datetime.now()`.

**Storyline 1 — Mid-Market NRR Compression (load-bearing).** `sem_nrr_retention` for `SEG-MM` must reproduce this trajectory (new business flat, churn + contraction surging → NRR cliff). Starting ARR is flat at ~$22.0M; new-logo ARR flat ~$1.0M/mo. These are the **contract values** (single-month NRR = (starting + expansion − churn_contraction) / starting):

| Month | Expansion $M | Churn+Contraction $M | NRR % |
|---|---|---|---|
| 2025-09 | 2.20 | 0.44 | 108.0% |
| 2025-10 | 2.05 | 0.55 | 106.8% |
| 2025-11 | 1.85 | 0.72 | 105.1% |
| 2025-12 | 1.60 | 0.95 | 102.9% |
| 2026-01 | 1.35 | 1.25 | 100.5% |
| 2026-02 | 1.15 | 1.55 | 98.2% |
| 2026-03 | 0.98 | 1.90 | 95.8% |
| 2026-04 | 0.85 | 2.25 | 93.6% |
| 2026-05 | 0.75 | 2.55 | 91.8% |
| 2026-06 | 0.68 | 2.85 | 90.1% |

**Headline NRR: 108% (peak, 2025-09) → 90% (trough, 2026-06).** `nrr_pct` is the single-month value above; also emit `nrr_rolling_pct` (trailing-3-month mean) for a smoothed line. New business (new-logo ARR) stays roughly flat; **churn + contraction is the driver, not slowing acquisition.** Other segments have healthy stable NRR (Enterprise ~118% on ~$45M base, SMB ~104% on ~$8M, Startup ~101% on ~$3M) so Mid-Market's cliff dominates any by-segment view.

**Metric convention (must be encoded in COMMENTS + handled by the view):** in `fact_arr_movement`, `expansion_arr_usd` and `new_arr_usd` are stored **POSITIVE**, `contraction_arr_usd` and `churned_arr_usd` as **NEGATIVE**. `sem_nrr_retention` flips the sign on churn/contraction so `nrr_pct = (starting_arr + expansion + contraction + churned) / starting_arr` and `ending_arr = starting + new + expansion + contraction + churned`. This is exactly the ontology note Genie relies on.

**Storyline 2 — Enterprise Renewal Risk (load-bearing).** Three strategic Enterprise accounts dominate `sem_account_health`. Generate their subscription/health rows to reproduce these **contract aggregates** (±3% ok):

| account_id | account_name | region | segment | health_score | usage_pct | days_to_renewal | at_risk_arr_usd | arr_usd |
|---|---|---|---|---|---|---|---|---|
| `ACCT0012` | Account 012 (APAC) | APAC | Enterprise | 27 | 38% | 47 | 1,557,000 | 3,920,000 |
| `ACCT0049` | Account 049 (EMEA) | EMEA | Enterprise | 34 | 42% | 51 | 1,484,000 | 3,460,000 |
| `ACCT0010` | Account 010 (APAC) | APAC | Enterprise | 31 | 41% | 63 | 2,408,000 | 4,238,000 |

Totals: **$11.6M ARR under management, $5.4M at-risk ARR.** All other ~50 accounts have healthy scores (65–95), high usage (>70%), renewals spread out, and small at-risk balances so these 3 top every renewal-risk ranking. Generate per-account subscription rows with explicit `arr_usd`, `renewal_date`, `health_score`, `product_usage_pct`, `support_tickets_90d`, `is_at_risk` so `sem_account_health` aggregates to the contract; override the hero aggregates directly if generation drifts.

**Storyline 3 — Actual vs Plan Net-New ARR variance (load-bearing for Step 5).** `sem_forecast_plan` for 2026 YTD must show Mid-Market below plan and Enterprise ahead:

| Segment | Jan | Feb | Mar | Apr | May | Jun |
|---|---|---|---|---|---|---|
| Mid-Market | **−10.5%** | −7.1% | **−9.5%** | −8.2% | −6.4% | −5.1% |
| Enterprise | **+1.3%** | +6.8% | +9.4% | +11.7% | **+13.2%** | +8.9% |
| SMB | −3.2% | −4.1% | −5.6% | −4.8% | −3.9% | −2.7% |
| Startup | +0.8% | −1.2% | +2.1% | +0.4% | +1.9% | +1.1% |

Seed `fact_plan` (plan net-new ARR) and `metric_net_new_arr` (actual net-new ARR) per segment/month to land these variances (`variance_pct = actual/plan − 1`).

**Storyline 4 — Q2 S&M Overrun / CAC pressure.** Q2 2026 (esp. April) Sales & Marketing spend runs **+12%** over plan (surfaces in `sem_gtm_spend` + GTM dashboard page + GTM Genie space). Concentrate the overrun in Mid-Market + Enterprise demand-gen channels; CAC for Mid-Market rises.

**Storyline 5 — CRM↔Billing Mismatch.** `fact_sync_exception` (closed-won in CRM not synced to billing) has **$50.1k** unmatched in the last 90 days (a handful of bookings where `is_matched = FALSE`). Surfaces on the Retention & Attainment dashboard page as a data-hygiene / revenue-leakage callout.

**Storyline 6 — ML Net-New-ARR Forecast.** `predict_net_new_arr('Mid-Market')` returns next-quarter net-new ARR: **m1 $1.20M, m2 $1.14M, m3 $1.36M, quarter_total $3.69M.** Other segments return values derived from their `feat_monthly_nnarr` run-rate. Same `metric_net_new_arr` basis as actuals + plan — no reconciliation gap.

---

## A. Dimension Tables (7)

Curated, hand-controlled where the story needs fixed values. COMMENT every table + column.

- **`dim_segment`** — 4 rows (above): `segment_id` (PK), `segment_name`, `motion` (`Field`/`Inside`/`Self-serve`), `is_active`.
- **`dim_calendar`** — daily 2025-05-01 → 2026-06-30: `date_key` (PK), `date`, `year`, `quarter` (`2026-Q1`…), `month`, `month_start`, `fiscal_period`, `is_month_end`.
- **`dim_account`** — ~50 rows: `account_id` (PK, `ACCTNNNN`), `account_name`, `region`, `segment_id` (FK), `industry`, `plan_tier` (`Growth`/`Business`/`Enterprise`), `contract_start_date`, `is_active`. **Must include ACCT0010/0012/0049 as at-risk Enterprise** (storyline 2), plus a couple of expansion-tier accounts for the "top expansion accounts" prompt.
- **`dim_rep`** — ~120 rows: `rep_id` (PK), `rep_name`, `role` (`AE`/`AM`/`SDR`/`CSM`), `team` (`New Business`/`Expansion`/`Renewals`), `segment_id` (FK), `region`, `quota_usd`, `hire_date`, `is_active`.
- **`dim_product`** — ~12 rows (core platform modules): `product_id` (PK, `MOD-NNN`), `product_name` (e.g. Purchasing, Approvals, Expense Mgmt, Spend Analytics, AP Automation, Budgets, Punchout, Cards), `product_line`, `list_price_usd`, `is_addon`.
- **`dim_channel`** — ~10 rows (GTM/lead sources): `channel_id` (PK, `CH-NNN`), `channel_name` (`Paid Search`, `Content/SEO`, `Events`, `Outbound/SDR`, `Partner`, `Referral`, `Webinar`, `Review Sites`, `Social`, `ABM`), `channel_type` (`Inbound`/`Outbound`/`Partner`), `segment_id` (FK, primary segment served).
- **`dim_stage`** — ~7 rows (pipeline stages): `stage_id` (PK), `stage_name` (`Prospect`→`Discovery`→`Demo`→`Proposal`→`Negotiation`→`Closed Won`/`Closed Lost`), `stage_order`, `is_closed`, `is_won`.

## B. Fact Tables (7)

- **`fact_arr_movement`** — monthly ARR waterfall, grain `(segment_id, account_id, period_month)`, ~14 months × 4 segments × accounts. Cols: `movement_id`, `segment_id`, `account_id`, `period_month` (month_start DATE), `starting_arr_usd`, `new_arr_usd` (+), `expansion_arr_usd` (+), `contraction_arr_usd` (−), `churned_arr_usd` (−), `ending_arr_usd`, `region`. Mid-Market follows storyline 1 exactly; other segments generated with ±5% monthly noise around baseline.
- **`fact_subscription`** — current subscription per account, grain per account (+ small history). ~50+ rows. Cols: `subscription_id` (PK), `account_id` (FK), `segment_id`, `region`, `arr_usd`, `contract_start_date`, `renewal_date`, `health_score` (0–100), `product_usage_pct` (0–100), `support_tickets_90d`, `is_at_risk` (health < 45 AND renewal < 90 days), `at_risk_arr_usd` (arr × risk factor, 0 if not at risk). Hero accounts (storyline 2) seeded to hit contract aggregates.
- **`fact_opportunity`** — pipeline opportunities, ~4,000 rows. Cols: `opp_id` (PK, `OPP-YYYYMMDD-NNNN`), `account_id` (FK), `rep_id` (FK), `segment_id`, `region`, `stage_id` (FK), `channel_id` (FK), `created_date`, `close_date`, `amount_usd`, `is_won` (BOOLEAN), `is_closed`. Drives win rate / pipeline coverage for `sem_quota_attainment`.
- **`fact_plan`** — monthly plan/quota, grain `(segment_id, period_month, metric)`. Cols: `plan_id`, `segment_id`, `period_month`, `metric` (`net_new_arr` | `sm_spend` | `new_logos`), `plan_amount_usd`. Net-new-ARR plan seeded so storyline 3 variances land; S&M plan seeded so Q2 shows +12%.
- **`fact_gtm_spend`** — sales & marketing spend line items, ~5,000 rows. Cols: `spend_id`, `channel_id` (FK), `segment_id`, `region`, `spend_date`, `category` (`Paid Media`, `Events`, `Content`, `SDR/Outbound`, `Partner`, `Tooling`), `amount_usd`, `attributed_pipeline_usd`. Enough Q2 spend so "S&M spend vs plan" shows the +12% overrun; supports CAC computation.
- **`fact_rep_attainment`** — monthly rep attainment snapshot, grain `(rep_id, period_month)`. Cols: `attainment_id`, `rep_id` (FK), `segment_id`, `team`, `period_month`, `bookings_usd`, `quota_usd`, `attainment_pct`, `pipeline_coverage_x`. Drives attainment by segment/team + pipeline coverage.
- **`fact_sync_exception`** — CRM↔billing reconciliation, ~200 rows over 90 days. Cols: `sync_id`, `opp_id`, `account_id`, `booking_date`, `crm_amount_usd`, `billing_amount_usd`, `is_matched` (BOOLEAN), `mismatch_usd`. Seed unmatched closed-won totalling **$50.1k** (storyline 5).

## C. Semantic Layer — 5 `sem_*` views + source + feature table

Governed SQL views (the demo's "semantic metric views"). COMMENT the view + every column. These enforce consistent metric definitions — NRR is always NRR, computed the same way — regardless of who asks or which Genie space.

1. **`sem_nrr_retention`** — grain `segment × month`. Cols: `segment_id`, `segment_name`, `period` (month_start), `starting_arr_usd`, `new_arr_usd`, `expansion_arr_usd`, `contraction_arr_usd` (sign-flipped positive), `churned_arr_usd` (sign-flipped positive), `ending_arr_usd`, `nrr_pct` (single-month), `nrr_rolling_pct` (trailing-4-month rolling — the headline that lands 112%→89% for Mid-Market), `gross_retention_pct`. Source `fact_arr_movement` + `dim_segment`. **Handles the sign flip.**
2. **`sem_account_health`** — grain `account`. Cols: `account_id`, `account_name`, `region`, `segment_id`, `segment_name`, `arr_usd`, `health_score`, `product_usage_pct`, `support_tickets_90d`, `days_to_renewal`, `at_risk_arr_usd`, `is_at_risk`. Source `fact_subscription` + `dim_account`.
3. **`sem_gtm_spend`** — grain `channel / category`. Cols: `channel_id`, `channel_name`, `channel_type`, `category`, `sm_spend_usd`, `attributed_pipeline_usd`, `new_logos`, `cac_usd`, `magic_number`, `opp_count`. Source `fact_gtm_spend` + `fact_opportunity` + `dim_channel`. CAC = spend / new_logos; magic_number ≈ net-new ARR / prior-period S&M spend.
4. **`metric_net_new_arr`** (source view) — grain `segment × month`. Cols: `segment_id`, `segment_name`, `period`, `net_new_arr_usd` (actual = new + expansion + contraction + churned). Derived from `fact_arr_movement` so forecast/actual/plan share one basis.
5. **`sem_forecast_plan`** — grain `segment × month`. Cols: `segment_id`, `segment_name`, `period`, `actual_nnarr_usd`, `plan_nnarr_usd`, `variance_usd`, `variance_pct`. Source `metric_net_new_arr` + `fact_plan` (metric=`net_new_arr`). Reproduces storyline 3.
6. **`sem_quota_attainment`** — grain `segment × team × month`. Cols: `segment_id`, `segment_name`, `team`, `period`, `bookings_usd`, `quota_usd`, `attainment_pct`, `pipeline_coverage_x`, `win_rate_pct`, `rep_count`. Source `fact_rep_attainment` + `fact_opportunity` + `dim_rep`. Reproduces storyline 4 pressure (Mid-Market attainment lags).

**`feat_monthly_nnarr`** — feature table for the forecast, grain `segment × month`, built from `metric_net_new_arr` (lagged net-new ARR, 3-month rolling mean, trend). Same source as actuals + plan.

**`predict_net_new_arr(segment_name STRING)`** — UC SQL **table function** (`RETURNS TABLE(m1 DOUBLE, m2 DOUBLE, m3 DOUBLE, quarter_total DOUBLE)`). Reads `feat_monthly_nnarr` for the segment and projects the next 3 months from run-rate + trend. **Mid-Market must return m1=1_200_000, m2=1_140_000, m3=1_360_000, quarter_total=3_690_000** (storyline 6) — implement a per-segment CASE override so the hero values are exact; other segments use the run-rate formula. COMMENT the function.

---

## D. Validation (LLM writes one-line checks; fix synth before Stage 2 build proceeds)

**Load-bearing (gate the story):**
- **Mid-Market NRR cliff** — `sem_nrr_retention WHERE segment_id='SEG-MM'` monthly: `nrr_rolling_pct` ≈ 112% (2025-09) → 89% (2026-06); new-logo ARR flat; churn+contraction $0.55M → $1.10M. Mid-Market is the worst by-segment NRR trend.
- **Enterprise renewal risk** — `sem_account_health` ORDER BY arr_usd DESC → ACCT0010/0012/0049 top 3, combined ARR ≈ $11.6M, at-risk ≈ $5.4M, health 27–34, usage 38–42%. Every other account far healthier.
- **Variance** — `sem_forecast_plan` 2026 YTD: Mid-Market Jan ≈ −10.5%, Mar ≈ −9.5%; Enterprise positive +1.3% to +13.2%.
- **Q2 S&M** — `sem_gtm_spend` / `fact_plan` Q2 2026 S&M `variance` ≈ +12%.
- **CRM↔billing** — `fact_sync_exception` `SUM(mismatch_usd) WHERE NOT is_matched` last 90 days ≈ $50.1k.
- **Forecast fn** — `SELECT * FROM predict_net_new_arr('Mid-Market')` → (1.20M, 1.14M, 1.36M, 3.69M). Runs without error for every segment.

**Smoke checks:** all `sem_*` views + `metric_net_new_arr` return rows; every fact row FK-resolves to a dim; `dim_calendar` covers the full window; sign convention correct (fact_arr_movement expansion/new > 0, churn/contraction < 0; sem view churned_arr_usd > 0).

Surface resolved catalog/schema + confirmation of contract values in `resources.json` / notebook exit so `04-ai-bi.md` can reference them.
