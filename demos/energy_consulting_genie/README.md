# Scenario Shift Alert

> A Genie-for-Consultants demo. An energy consultancy's consultant, prepping for a client strategy session on 10–20 year energy profitability, receives a **Genie alert in her inbox**: one strategic scenario swung from **attractive to marginal** three weeks ago. She clicks straight through to **Genie One** and asks her follow-up questions — Genie surfaces the changed assumptions across the projection data and quotes the source **assumptions PDF (in a Unity Catalog Volume)** to confirm. The **Scenario Landscape dashboard** gives her the broader context — all the scenarios in play, their NPV, risk band, and assumptions — before she drafts the updated recommendation for the meeting.

## The Story

| | |
|---|---|
| **Company** | Global energy consulting & advisory (reserves, valuations, energy transition strategy) |
| **Hero** | Dr. Amara Okonkwo, Senior Energy Strategy Consultant (advises operators & investors on long-range strategy) |
| **Problem** | Prepping for a client strategy session on 10–20 year profitability, a **Genie alert lands in Amara's inbox**: one modeled scenario ("Accelerated Transition") swung from **attractive to marginal** three weeks ago as new market + policy data landed — NPV fell ~38% |
| **Investigation** | Amara clicks the alert through to **Genie One** and asks *"Which scenario projections changed the most recently, and why?"* — Genie traces the swing to three assumption drivers: **carbon price, policy timing, and demand growth**, and reads the assumptions memo PDF from the Volume inline to confirm the analyst's rationale |
| **Root cause** | A revised **carbon-price floor** (policy pulled forward ~4 years) plus a **downgraded gas demand-growth curve** cut the Accelerated Transition scenario's 2035–2045 cash flows — captured in the latest assumptions revision |
| **Impact** | Scenario NPV moved **from ~$4.2B to ~$2.6B** (−38%); a $1.6B swing in the recommendation Amara takes into the client meeting, caught 3 weeks before the session instead of in the room |

---

## Overview

The week before a client session on long-range (10–20 year) energy profitability, a **Genie alert lands in Amara's inbox**: one of the five strategic scenarios she models — **Accelerated Transition** — dropped sharply in projected NPV three weeks ago, moving from the "attractive" band into "marginal." The alert summarizes what moved and by how much, and points her to the next step. The other four scenarios held steady.

She **clicks the alert straight through to Genie One** and asks one question: *"Which scenario changed the most recently, and why?"*

Genie walks the projection data: NPV-by-scenario over time → spots Accelerated Transition's 38% drop → traces it to three assumption drivers whose values were revised in the latest data load (carbon price floor, policy-effective year, gas demand-growth rate). Then Amara asks Genie to pull the reasoning: the same Genie space is grounded on the **assumptions memo PDF** sitting in a Unity Catalog Volume — parsed into a table with AI Functions — so Genie quotes the analyst's narrative directly: *"Carbon-price floor legislation advanced to 2028; long-run gas demand revised down 1.4%/yr on efficiency + electrification."*

For the broader context, Amara **opens the Scenario Landscape dashboard**: all five scenarios in play, ranked by projected NPV and colored by risk band, their cumulative-NPV outlook to 2045, and the key assumptions behind each. She drafts a discussion memo on the new strategy options, confirms the revised recommendation with the client, and uses it to steer the meeting — three weeks ahead of time.

**Duration:** 5–6 minutes.

---

## Key Numbers

| Metric | Value |
|--------|-------|
| Strategic scenarios modeled | 5 (Base Case, Accelerated Transition, Delayed Transition, High Demand, Carbon Constrained) |
| Projection horizon | 2025 → 2045 (20 years) |
| Scenario that swung | Accelerated Transition |
| Swing timing | ~3 weeks ago (latest data + assumptions revision) |
| NPV before revision | ~$4.2B |
| NPV after revision | ~$2.6B (−38%) |
| Recommendation swing | ~$1.6B |
| Assumption drivers behind the swing | Carbon-price floor, policy-effective year, gas demand-growth rate |
| Source document | Scenario assumptions memo (PDF in UC Volume, parsed to a table) |

---

## Demo Walkthrough

**Frame:** A week before Amara's client strategy session. She hasn't opened anything yet — the platform comes to her.

### Act 1 — The alert lands in the inbox (1 min)

**Open Amara's inbox / the Databricks alert notification.**

A **Genie alert** fired: *"Scenario alert: Accelerated Transition swung from Attractive to Marginal (NPV −38%)."* The body spells it out — ~$4.2B → ~$2.6B, a ~$1.6B swing in the client recommendation, the other four scenarios steady — and tells her the next step: open the Genie space and ask why. No dashboard hunting; the anomaly found *her*.

> *"This is a **Databricks SQL Alert** — it runs a governed query on a schedule, and when a guardrail breaks (here, a scenario NPV moving more than −30%) it drops a written summary in the inbox. The consultant doesn't monitor a dashboard all day; the platform watches the data and tells her when something moved."*

### Act 2 — Click through to Genie One, ask why (2–3 min)

**Click the alert through to Genie One** (the `Scenario Strategy` space).

**Amara types:** `Which scenario projection changed the most in the last month, and what drove it?`

Genie walks the data: NPV-by-scenario trend → isolates Accelerated Transition's drop → joins to the assumptions table → returns the three drivers whose values were revised (carbon-price floor, policy-effective year, gas demand growth) with old vs new values.

**Then Amara asks:** `Summarize the analyst rationale for the Accelerated Transition revision.`

The Genie space is also grounded on the **assumptions memo PDF** in a UC Volume — parsed into a text table with **AI Functions** — so Genie answers from the document itself, quoting the analyst's narrative and confirming what the numbers implied.

> *"This is **Genie One** over **Unity Catalog** — the business front door, natural language into governed SQL, no JOINs written by hand. And the same space answers from **unstructured data**: a PDF assumptions memo living in a **Volume**, parsed with **AI Functions** into a queryable table. Structured projections and the source document, one conversational surface."*

### Act 3 — See the whole landscape on the dashboard (1–2 min)

**Open the Scenario Landscape dashboard.**

Now that the conversation has surfaced the *what* and the *why*, Amara opens the dashboard for the broader picture — the overview of the landscape the energy consultancy's advisors work from. KPI tiles read how many scenarios sit in each risk band and the NPV spread between the best and worst outlook. The cumulative-NPV curves show every scenario's value building out to 2045; a ranked bar orders all five by NPV, colored by risk band; and the landscape table lays out each scenario's NPV, band, strategy theme, and the assumptions behind it.

> *"This is **AI/BI Dashboards** — the projection tables came in through **Lakeflow Connect** from the modeling platform and market-data feeds, governed end-to-end by **Unity Catalog**. In production these flow through **Spark Declarative Pipelines**; today we load the Gold tables directly so the story lands fast. Same governed data as the alert and Genie — the dashboard is the shared view of the whole scenario landscape any advisor can open."*

### Act 4 — Draft the recommendation with a Genie Code skill (1–2 min)

**Invoke the `draft-client-discussion-memo` Genie Code skill** (`genie_code_skills/draft_discussion_memo.md`).

Amara doesn't hand-write the memo. She runs a saved **Genie Code skill** that reads the governed data end-to-end — the scenario that moved (from `gold_scenario_npv_trend`), the assumption drivers (`gold_assumptions`), where the value moved across the horizon (`gold_projection_detail`), and the analyst rationale quoted straight from the parsed PDF (`gold_assumptions_doc.parsed_text`) — and drafts a one-page, decision-ready discussion memo: headline, what changed, where value moved, the rationale quote, the scenario landscape for context, and the strategy options to put to the client (hedge carbon exposure, re-time capex, revisit the transition pace). She reviews it, fills the client-specific brackets, confirms it with the client ahead of the session, and walks in with the updated recommendation.

> *"This is **Genie Code** — not just building pipelines and dashboards, but a reusable **skill** that turns the governed analysis into a client deliverable. Every figure is grounded in Unity Catalog tables and every rationale line is quoted from the source memo — no invented numbers. The alert finds the problem, the consultant asks, the data answers, the document confirms, the dashboard frames the landscape, and Genie Code drafts the memo."*

### Closing

> Amara caught a $1.6B swing in her client recommendation **three weeks before the meeting** — not by re-running a model by hand, but by asking. Governed structured projections and the unstructured assumptions memo behind them, answered in one place.
>
> **Ingest once. See the swing at a glance. Ask why in plain language. Confirm against the source document. Same Unity Catalog governance across all of it.**

---

## Products Showcased

| Product | Mode | What it does in this demo |
|---------|------|---------------------------|
| **Synthetic Data Generation** | Build (fast load) | Generates the scenario projection universe — 5 strategic scenarios × 20 annual projection points × several vintages, plus the assumption-driver revision history and a scenario-assumptions memo document — into raw tables, then `spark.sql` transforms to the Gold tables the alert, dashboard + Genie read. |
| **Databricks SQL Alert** | Build | Runs a scheduled governed query on the scenario-swing view; when a scenario NPV moves more than −30% it drops a written **Genie alert in the inbox** (summary + next step) — the demo's opening beat, replacing "open the dashboard." |
| **AI Functions** | Build | `ai_parse_document` turns the uploaded assumptions-memo **PDF in a UC Volume** into a queryable text table so Genie can answer from unstructured content. |
| **AI/BI Genie** | Build | The click-through target from the alert. Answers *"which scenario changed and why?"* over the projection + assumptions tables, and quotes the assumptions-memo PDF inline. |
| **AI/BI Dashboard** | Build | The **Scenario Landscape** overview for the energy consultancy's advisors — all five scenarios ranked by NPV and risk band, their cumulative-NPV outlook to 2045, and the assumptions behind each. The shared view of the landscape, not a swing-specific deep-dive. |
| **Metric Views** | Build | `mv_scenario_npv` — the governed **NPV** metric: `MEASURE(NPV ($B))` = the discounted sum of annual cash flows, defined once over `gold_projection_detail`. Same numbers as the dashboard, reused by Genie. |
| **Genie Ontology** | Talk track | The **NPV Ontology Page** — the business definition of NPV, its risk-band decision rules (Attractive ≥ $3.5B · Marginal $2.5–3.5B · Unattractive < $2.5B), synonyms, and related terms — pointing at the metric view so every Genie space, dashboard, and agent shares one meaning of "NPV." |
| **Lakeflow Connect** | Talk track | "In production, projection outputs and market/policy feeds arrive through managed connectors — no custom plumbing." |
| **Unity Catalog** | Talk track | One governance model across the projection tables, the Volume holding the PDF, the NPV metric view, and Genie's queries. |
| **Genie One** | Talk track | The consultant front door Amara **clicks into from the alert** — same governed answers on web + mobile, where she asks the follow-up questions. |
| **Genie Code** | Talk track + skill | The `draft-client-discussion-memo` skill (`genie_code_skills/draft_discussion_memo.md`) reads the governed scenario tables + the parsed assumptions PDF and drafts a one-page, decision-ready client memo — every figure grounded in Unity Catalog, every rationale line quoted from the source. Also the prompt-driven authoring of projections, dashboards, and queries. |
