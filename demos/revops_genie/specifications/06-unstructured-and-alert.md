# 06 — Unstructured Evidence & the Scheduled Alert

This spec adds two beats to the demo: the **documentary root cause** behind the Mid-Market NRR compression (unstructured churn/QBR PDFs → governed table) and the **scheduled task** that initiates the whole story (a **Genie One scheduled insight** whose notification launches Genie / Databricks One). Together they make "the insight finds the executive" a real, running mechanism rather than a narrated one.

## A. Unstructured — churn / QBR PDFs → `fact_churn_reason`

**Business purpose.** The number story says Mid-Market churn + contraction rose $0.55M → $1.10M/mo with flat new business. The *why* was never visible in the structured data. It lives in the churn & QBR documents: a **new AI-native procurement competitor undercutting on price** and a **missing real-time budget-approval feature**, absent from prior renewals, appearing in March 2026 and escalating each month.

**Inputs.** 16 churn/QBR PDFs (4 Mid-Market accounts × 4 months, Mar–Jun 2026), generated from HTML by `unstructured/generate_churn_docs.py`. Filenames encode the `account_id` (e.g. `qbr_ACCT0031_0326.pdf`) so the extracted rows join back to `dim_account`. Each document breaks the account's ARR change into three reason lines: **Renewed/Retained** (flat), **Competitive Displacement** (escalating), **Missing-Feature Downgrade** (escalating).

**Landing.** Unity Catalog Volume `solution_builder.demo_revops_intelligence.raw_churn_docs`.

**Extraction (see `unstructured/extract_churn_docs.sql`).** `ai_parse_document` reads each PDF's binary into text, then `ai_extract` pulls typed fields (account_name, doc_date, competitor_named, renewed_arr, competitive_loss_arr, feature_gap_arr, feature_requested). Both are per-row LLM calls — materialized once into Delta, never re-run per query.

**Output — `fact_churn_reason`** (grain: document × reason_category):

| column | type | notes |
|---|---|---|
| doc_id | STRING | e.g. `QBR-ACCT0031-0326` |
| account_id | STRING | joins `dim_account` |
| account_name | STRING | extracted account name |
| doc_date | DATE | 15th of month |
| period | DATE | month truncation |
| segment_id | STRING | `SEG-MM` |
| reason_category | STRING | `Renewed` \| `Competitive Displacement` \| `Missing-Feature Downgrade` |
| competitor_named | STRING | competitor when reason is competitive (else NULL) |
| lost_arr_usd | DOUBLE | ARR lost on this line (0 for `Renewed`) |

**Contract (validated).** `Renewed` flat at ~$449K/mo; loss total (competitive + feature-gap) escalates **~$13K (Mar) → ~$40K (Apr) → ~$61K (May) → ~$81K (Jun)** — a ~6× ramp. Competitive Displacement dominates and names the same rival across accounts. 48 rows, 16 documents.

**Consumption.**
- **Genie** — added to the *Churn & Renewal Intelligence* space with an example question ("What is actually driving Mid-Market churn?") and ontology in the text instruction.
- **Dashboard** — *Retention & Attainment* page: a stacked bar (`ds_churn`) of lost ARR by month & reason, plus a callout naming the `ai_parse_document` + `ai_extract` mechanism.

## B. Scheduled Insight — the trigger (Genie One Scheduled Task)

**Business purpose.** Maya doesn't hunt dashboards. A scheduled **retention-control** check — the core use case of this demo — authored natively in **Genie One**, finds her.

**Definition (see `alert/scheduled_insight.json`).**
- **Type** — a Genie One *Scheduled Insight* of `insight_type: ALERT`, created via `POST /api/2.0/alerts-internal/scheduled-insights` and owned by the user. It surfaces in Databricks One → *Scheduled tasks*.
- **Prompt (natural language, not SQL)** — Genie One monitors **Mid-Market revenue retention control**: latest trailing NRR vs the 100% control line (from `sem_nrr_retention`), net-new-ARR actual vs plan variance % (from `sem_forecast_plan` / `metric_net_new_arr`), and at-risk Enterprise renewal exposure (health-red accounts renewing within 90 days from `sem_account_health`). It alerts if **Mid-Market NRR is >5 points below the 100% control line OR at-risk Enterprise ARR exceeds $5M** — reporting the NRR, the plan variance %, the at-risk exposure, and a recommendation to investigate in Genie One, where the drain traces to churn/contraction (competitive displacement + feature gap in `fact_churn_reason`) and stalled Enterprise renewals. Both thresholds are currently breached (Mid-Market NRR 90%, at-risk ARR $5.4M), so it fires.
- **Schedule** — weekly, Mondays 06:00 America/New_York (`0 0 6 ? * MON`).
- **Notification** — Genie One delivers the generated insight to the owning user; the prompt itself frames the next step (open Genie One, drill into NRR, renewal risk, and `fact_churn_reason`).

**Why this shape (vs. legacy DBSQL `alerts-v2`).** The trigger is authored in the *same surface the Director of RevOps investigates in* — Genie One — with a plain-language prompt rather than a SQL query + numeric threshold. It still resolves against the *same governed semantic views* (`sem_nrr_retention`, `sem_forecast_plan`, `metric_net_new_arr`, `sem_account_health`) the dashboard and Genie spaces use, so there's one metric definition and no reconciliation gap. The scheduled insight is the entry point; **Genie One is the investigation surface**; `fact_churn_reason` is the evidence.

**Portability.** `alert/scheduled_insight.json` is a **portable template** — it hardcodes no environment. It carries three substitution tokens resolved at deploy time:
- `${USER_ID}` — the numeric id of the insight owner (`databricks current-user me`).
- `${CATALOG}` / `${SCHEMA}` — where the semantic layer lives.

The prompt names the semantic views by their **unqualified, portable names** (`sem_nrr_retention`, `sem_forecast_plan`, `metric_net_new_arr`, `sem_account_health`, `fact_churn_reason`) and describes each in business terms, so it moves to any environment by substituting only catalog/schema/owner — no table paths to rewrite.

**Management (token-resolving deploy).** Uses only `python3` (portable — no `gettext`/`envsubst` dependency):
```bash
export USER_ID=$(databricks current-user me | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')
export CATALOG=solution_builder
export SCHEMA=demo_revops_intelligence
python3 -c 'import os,sys; sys.stdout.write(os.path.expandvars(open("alert/scheduled_insight.json").read()))' \
  | databricks api post /api/2.0/alerts-internal/scheduled-insights --json @/dev/stdin
```
- Delete: `databricks api delete /api/2.0/alerts-internal/scheduled-insights/<id> --json '{"name":"alert/users/<user-id>/scheduled_insights/<id>"}'`

The currently-deployed insight in this environment (`resources.json.created_resources.scheduled_insight`) is the token-resolved instantiation of this template.
