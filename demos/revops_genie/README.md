# Genie for RevOps — Revenue Intelligence

> **What this is.** An end-to-end Databricks demo for the Office of Revenue Operations at a SaaS company (an AI-native procurement & spend-management platform): subscription/GTM data + **customer churn & QBR documents** → a governed semantic layer (`sem_*` views) + a UC-registered net-new-ARR forecast function → a 5-page AI/BI dashboard → 5 domain Genie spaces. The story runs on an **alert-initiated, exception-based** flow: a **Genie One scheduled insight** evaluates the semantic layer, surfaces a **revenue-retention control breach** (Mid-Market NRR below target + at-risk Enterprise ARR), and notifies the Director of RevOps, who then investigates conversationally in **Genie / Databricks One** — across net revenue retention, net-new ARR, renewals risk, GTM efficiency, and the **unstructured churn evidence** behind the retention slide.

## The Story

| | |
|---|---|
| **Company** | An AI-native procurement & spend-management SaaS company, selling to Enterprise, Mid-Market, SMB and Startup segments across NA / EMEA / APAC |
| **Hero** | Maya Chen, Director of Revenue Operations — owns net revenue retention, net-new ARR, forecast accuracy, and GTM efficiency |
| **Problem** | Mid-Market net revenue retention collapsed from **108% → 90%** over four months (new business flat, churned + contracted ARR surging) while three strategic **Enterprise** accounts drifted to red health with renewals inside 90 days, holding **$11.6M** ARR under management (**$5.4M** at risk) |
| **Investigation** | Maya opens the RevOps dashboard, sees the NRR alert, and asks Genie *"why is Mid-Market NRR compressing?"* — churn/contraction, not slowing new business. She pivots to net-new ARR vs plan, forecasts Mid-Market next quarter via `predict_net_new_arr()`, and drills into the 3 strategic Enterprise accounts behind the at-risk balance |
| **Root cause** | Mid-Market ending ARR fell (churned + contracted ARR $0.44M → $2.85M/mo, expansion decaying) with new business flat → pure retention erosion. The *why* is in the **churn & QBR documents**: a new **AI-native competitor undercutting on price + a missing real-time budget-approval feature** (absent from prior renewals) driving losses ~$13K → ~$81K/mo Mar→Jun, extracted from PDFs via `ai_parse_document` + `ai_extract`. Enterprise renewals stall: health scores 25–40, usage <45% = systemic, not one-off |
| **Impact** | ~**$2.8M** annual ARR at risk in Mid-Market · **$5.4M** at-risk Enterprise renewals in APAC/EMEA · Mid-Market net-new ARR **−9.5%** below plan in Q1 |

---

## Overview

Every SaaS company runs a revenue engine: new business in, expansion up, churn and contraction dragging down, and RevOps keeps net retention healthy and predictable. When CRM, billing, product-usage, and support data are siloed, three silent multi-million-dollar drains hide inside consolidated board decks: **net revenue retention (NRR) compression**, **renewal risk (health-score decay)**, and **net-new ARR variance vs plan**.

Maya Chen doesn't browse dashboards looking for problems. A **Genie One scheduled insight** (a scheduled task in Databricks One, runs every Monday 06:00) runs a **revenue-retention control** check — is Mid-Market NRR more than 5 points below the 100% control line, or does at-risk Enterprise ARR exceed $5M? Both thresholds just broke (Mid-Market NRR **90%**, at-risk ARR **$5.4M**). The insight lands in Genie One and points her straight into the investigation.

The insight found the executive. From that alert Maya investigates conversationally in Genie One — no SQL, no login barriers — grounded in trusted metric definitions (the `sem_*` semantic layer), business permissions (Unity Catalog), and organizational context (Genie ontology per space). When she asks *why* retention slipped, Genie reads the **churn reasons extracted from QBR/cancellation PDFs** and names the competitor and the feature gap directly.

**Duration:** 5–10 min (AE pitch path) / 15–20 min (SA discovery).

---

## Key Numbers

| Metric | Value |
|--------|-------|
| Mid-Market NRR (peak → trough) | 108% → **90%** over 4 months |
| Mid-Market churned + contracted ARR surge | $0.44M → **$2.85M**/mo (~6.5×) |
| Churn losses (extracted from PDFs) | Competitive + feature-gap losses escalate **~$13K → ~$81K/mo** Mar→Jun (16 docs, `fact_churn_reason`) |
| Mid-Market annual ARR at risk | ~**$2.8M** |
| At-risk strategic accounts (3 Enterprise) | **$11.6M** ARR under management (ACCT0010, ACCT0012, ACCT0049) |
| At-risk ARR (red health, renewal < 90d) | **$5.4M** at 25–40 health scores, <45% usage |
| `predict_net_new_arr('Mid-Market')` next quarter | $1.20M / $1.14M / $1.36M = **$3.69M** |
| Mid-Market net-new ARR vs plan | **−9.5%** (Mar), **−10.5%** (Jan) |
| Enterprise net-new ARR vs plan | **+1.3% to +13.2%** (consistently ahead) |
| Q2 S&M spend overrun (CAC pressure) | **+12%** |
| CRM↔billing unmatched bookings | **$50.1k** (last 90 days) |

---

## Demo Walkthrough

**Frame:** Monday morning, before the revenue leadership meeting. The Genie One scheduled insight ran overnight; Maya opens Databricks One and sees it waiting.

### Step 1 — The Scheduled Alert (the trigger)

The **Genie One scheduled insight** `Mid-Market Retention Control Alert — Office of RevOps` ran on its weekly schedule and crossed its control limits: Mid-Market NRR **90% (−10 pts vs the 100% control line)** and at-risk Enterprise ARR **$5.4M** (> $5M). Show the scheduled task in Databricks One → *Scheduled tasks* — a plain-language prompt against the same `sem_forecast_plan` / `sem_nrr_retention` / `sem_account_health` semantic views the dashboard and Genie use, one metric definition, authored right where Maya investigates. The insight surfaces directly inside **Genie / Databricks One**. *The insight found the executive — no login, no SQL, no dashboard hunt.* This is the shift from analytics **pulls** to intelligence **pushes**.

> *"The alert told us what broke. Let's ask Genie why — right here in Databricks One."*

### Step 2 — Conversational Investigation in Genie One (root cause)

From the alert, Maya lands in **Genie One** and opens the **Net Revenue Retention** space:
`Why is Mid-Market NRR compressing? Break down the drivers.`
Genie queries `sem_nrr_retention`, filters Mid-Market over trailing 12 months, and shows new business flat while churned + contracted ARR climbs $0.44M → $2.85M/mo. **Retention-driven, not a top-of-funnel problem.**

Then the unstructured payoff — pivot to **Churn & Renewal Intelligence**:
`What is actually driving Mid-Market churn? Break down lost ARR by month and reason.`
Genie reads `fact_churn_reason` — **reasons extracted from 16 QBR/cancellation PDFs** via `ai_parse_document` + `ai_extract` — and names it: **competitive displacement (a new AI-native procurement rival undercutting on price) + a missing real-time budget-approval feature**, escalating ~$13K → ~$81K/mo since March, absent from prior renewals. The documentary root cause, surfaced conversationally. No table names, no SQL, no opening 16 PDFs by hand.

> *"Churn is the driver, and now we know exactly why. But is this bleeding into next quarter's number?"*

### Step 3 — Cascading Impact (net-new ARR exposure)

Open **Net-New ARR & Renewal Risk** Genie space:
`What is the forecasted net-new ARR for Mid-Market for the next quarter?`
→ `predict_net_new_arr('Mid-Market')` returns $1.20M / $1.14M / $1.36M = **$3.69M**. Same source (`metric_net_new_arr`) as actuals + plan — no reconciliation gap.
`Which strategic accounts are at risk in the next 90 days and what's the total exposure?`
→ `sem_account_health` surfaces ACCT0010/012/049 — $11.6M ARR under management, $5.4M at risk, health 25–40. **Dual-front revenue exposure.**

> *"We know the exposure. How bad could it get?"*

### Step 4 — Scenario Modeling (stress test)

Dashboard **Net-New ARR & Scenario Modeling** page. Parameter-driven 8-quarter projection: baseline New-Logo Growth +2%/qtr → toggle Churn Rate Δ +2 pts, Expansion Δ −5%, Win-Rate Δ −3 pts → watch ending ARR compress. Parameterized SQL live against the same metric views — not a spreadsheet.

> *"Now RevOps has the full picture. Time to act."*

### Step 5 — Actionable Differentiator (operational handoff)

In **Net-New ARR & Renewal Risk**: `Summarize the Enterprise renewal risk and recommend next steps for the CRO.` → escalate to the strategic-account team, launch save-plays, prioritize the feature gap. Then cross-space handoff to **Forecast Accuracy & Plan Attainment**: `What is each segment's actual vs plan net-new ARR and variance % for 2026 YTD?` → Mid-Market −9.5% (Mar) / −10.5% (Jan), Enterprise +1.3% to +13.2%. The retention story flows through to the number.

**Then the Director of RevOps institutionalizes it — in Genie Code.** Maya opens Genie Code and types *"prepare the weekly revenue retention briefing for the CRO."* The **`revenue-retention-briefing` skill** (a standing directive from the Office of RevOps, auto-loaded by the workspace) assembles the governed figures — NRR vs the 100% control line, net-new ARR vs plan, at-risk ARR exposure, the churn root cause, and the `predict_net_new_arr('Mid-Market')` forecast — into a **consistent, one-page, email-ready brief** with a first-person *"Directed actions — for the CRO"* section. The conversational investigation becomes a repeatable, governed deliverable the team produces every week and at QBR — no re-formatting, every number traceable to `sem_*`. *This is the operating-model change: exception intelligence → a standard the whole revenue team runs on.*

### Step 6 — Governance & Trust (architecture)

Unity Catalog governs every table, `sem_*` view, the `predict_net_new_arr()` function, and the `raw_churn_docs` Volume of source PDFs. Semantic metric views enforce consistent definitions (NRR is always NRR; the ARR-movement waterfall is netted once). Genie ontology per space encodes institutional knowledge. The Genie One scheduled insight — running a natural-language prompt against that same governed semantic view — is what started it all.

> **Exception-based revenue management by design: the insight finds the executive, the semantic layer keeps every answer consistent, and Unity Catalog keeps it all governed.**

---

## Products Showcased

| Product | Mode | What it does in this demo |
|---------|------|---------------------------|
| **Synthetic Data Generation** | Build (fast load) | Generates SaaS revenue data (ARR movement, subscriptions/renewals, opportunities/pipeline, plan/quota, GTM spend, rep attainment, CRM↔billing sync) + 7 dimensions, then builds the 6 `sem_*` semantic views and the `predict_net_new_arr()` UC SQL function that back every dashboard tile and Genie answer. |
| **AI/BI Dashboard** | Build | *Revenue Intelligence — Office of RevOps*: 5 pages (Executive Summary, Retention & Attainment with the ⚠️ alert widget, Net-New ARR & Scenario Modeling, Renewal Risk / At-Risk Accounts, GTM Efficiency & Quota). The NRR cliff and Enterprise exposure read at a glance. |
| **AI/BI Genie** | Build | 5 domain spaces — Net Revenue Retention, Net-New ARR & Renewal Risk, Forecast Accuracy & Plan Attainment, Churn & Renewal Intelligence, GTM Efficiency & Quota — each grounded in its `sem_*` view + ontology. |
| **Semantic Metric Views** | Build (as `sem_*` SQL views) | `sem_nrr_retention`, `sem_account_health`, `sem_gtm_spend`, `sem_forecast_plan`, `sem_quota_attainment` — consistent metric definitions across every space and dashboard tile. |
| **ML Net-New-ARR Forecast** | Build (as `predict_net_new_arr()` UC function) | Returns next-quarter net-new ARR (m1, m2, m3, quarter_total) by segment from the same `metric_net_new_arr` basis as actuals + plan. |
| **AI Functions** | Build | `ai_parse_document` + `ai_extract` read 16 churn/QBR PDFs from a UC Volume into `fact_churn_reason` — the unstructured → structured pipeline that exposes the competitive displacement + feature gap behind the NRR slide. |
| **Genie One Scheduled Insight** | Build | A scheduled task authored in Databricks One (`insight_type: ALERT`, weekly Mon 06:00) — a natural-language **retention-control** prompt that watches Mid-Market NRR vs the 100% control line and at-risk Enterprise ARR (`sem_forecast_plan` / `sem_nrr_retention` / `sem_account_health`), alerting the Director of RevOps inside Genie One when either breaches its limit. The scheduled task that initiates the story, native to the demo's primary vehicle. |
| **Genie One / Databricks One** | Primary vehicle | The business-user front door and the demo's spine — the alert lands here, Maya investigates conversationally across all 5 spaces, no SQL or login barriers. |
| **Unity Catalog** | Talk track | One permission model across tables, semantic views, the forecast function, and the `raw_churn_docs` Volume — RevOps sees only what they're entitled to. |
| **Lakeflow Connect** | Talk track | "In production this is how Salesforce / billing / product-usage / support data arrives — 200+ connectors, no custom plumbing." |
| **Genie Code** | Build | Ships the `revenue-retention-briefing` skill — a RevOps-issued standing directive the workspace auto-loads. In Genie Code, "prepare the weekly revenue retention briefing" renders a fixed-format, one-page CRO brief from the governed `sem_*` layer. Turns the conversational investigation into a repeatable, governed deliverable. |
