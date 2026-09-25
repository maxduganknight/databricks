# 07 — Genie Code Skill: Revenue Retention Briefing

This spec adds a **Genie Code skill** as a first-class demo asset. It elevates *Genie Code* from a talking-track line to a **buildable** capability: a skill the workspace auto-loads so that, mid-demo, the Director of RevOps (or her analyst) produces a consistently-formatted **Revenue Retention Briefing for the CRO** on demand.

## Business purpose

The demo's Step 5 (operational handoff) is where conversational investigation becomes action. Today that beat is a one-off Genie prompt. This skill formalizes it: Maya Chen, Director of RevOps, institutionalizes a **standing operating practice** — a standardized retention briefing the team produces on a fixed cadence (weekly Monday AM + QBR) and shares with the **Chief Revenue Officer**. The skill embodies the RevOps directive: same report shape every time, drawn from the governed semantic layer, with a first-person, directive **"Directed actions — for the CRO"** section that changes how the team operates (stand up the briefing, launch Enterprise save-plays, escalate the competitive/feature-gap loss to product, re-baseline the Mid-Market forecast).

The point for the audience: **Genie Code skills turn a great conversation into a repeatable, governed deliverable** — no analyst re-formatting each week, one consistent document, all numbers traceable to `sem_*`.

## Placement

- **Repo:** `.assistant/skills/revenue-retention-briefing/SKILL.md`.
- **Workspace:** installed to `/Workspace/Users/<user>/.assistant/skills/revenue-retention-briefing/` — the canonical path Genie Code auto-loads skills from (fresh chats only). Install snippet:
  ```bash
  USER_EMAIL=$(databricks current-user me | python3 -c 'import sys,json;print(json.load(sys.stdin)["userName"])')
  databricks workspace mkdirs "/Workspace/Users/$USER_EMAIL/.assistant/skills"
  databricks workspace import-dir .assistant/skills "/Workspace/Users/$USER_EMAIL/.assistant/skills" --overwrite
  ```

## Behavior

- **Triggers** on "prepare the revenue retention briefing", "draft the CRO report", "weekly retention report", "format this for the CRO", etc. (see the skill's `description` frontmatter).
- **Gathers** governed figures via six queries against `sem_nrr_retention`, `sem_forecast_plan`, `sem_account_health`, `fact_churn_reason`, and `predict_net_new_arr('Mid-Market')` — latest period unless the user names one.
- **Renders** a fixed 7-section, one-page markdown brief (executive summary → NRR vs 100% control line → net-new ARR vs plan → renewal risk exposure → documentary root cause → next-quarter forecast → **directed actions for the CRO**), in the RevOps first-person voice, with ⚠️ flags on breached controls.
- **Formatting-and-sharing only:** the skill assembles and formats governed numbers; it does not invent metrics. Empty/errored query → "no data for this period" in that section.

## Demo positioning

- **Walkthrough Step 5** — after the Genie investigation, the Director of RevOps invokes the skill in Genie Code to generate the standardized brief and share it with the CRO.
- **Products table** — *Genie Code* moves to a **Build** row (skill shipped), keeping its "AI authoring assist inside Genie/SQL" framing but now demonstrated live.
- **Consistency guarantee** — the brief uses the same `sem_*` metric definitions as the dashboard and the 5 Genie spaces, so the CRO's document never diverges from the executive dashboard.
