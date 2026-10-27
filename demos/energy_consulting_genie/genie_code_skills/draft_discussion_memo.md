---
name: draft-client-discussion-memo
description: >-
  Draft a client discussion memo for an energy-strategy session on
  10-20 year profitability. Reads the governed scenario projections, the
  assumption drivers, and the parsed analyst assumptions memo, then writes a
  concise, decision-ready memo the consultant confirms with the client. Use when
  a consultant asks to "draft the memo", "write up the recommendation", or
  "prepare the client discussion" after reviewing a scenario shift in Genie.
---

# Draft Client Discussion Memo

You are drafting a **client discussion memo** for a consultant
(persona: Dr. Amara Okonkwo, Senior Energy Strategy Consultant) preparing for a
client strategy session on 10-20 year energy profitability. This is Act 4 of the
demo: after the scheduled Genie watch flagged a scenario shift, the consultant
investigated in Genie One and reviewed the Scenario Landscape dashboard. Now she
asks Genie Code to turn that analysis into a memo she can confirm with the client
and use to steer the meeting.

**The memo is grounded in governed data — never invented.** Every number comes
from the tables below; every rationale claim comes from the parsed assumptions
memo. If a value isn't in the data, say so rather than guessing.

## Data sources (Unity Catalog)

Catalog / schema: `solution_builder.demo_scenario_shift_alert_015b3e`
(if these differ in the target workspace, substitute the deployed catalog.schema.)

| Table | What it gives the memo |
|-------|------------------------|
| `gold_scenario_npv_trend` | Per (scenario, vintage) NPV ($B), `risk_band` (Attractive ≥ $3.5B · Marginal $2.5-3.5B · Unattractive < $2.5B), `strategy_theme`, `is_alerted`. Source of the swing (before vs latest vintage) and the current landscape. |
| `gold_assumptions` | Per scenario, the three headline drivers with `_old`/`_new`/`_delta`: `carbon_price_floor`, `policy_effective_year`, `gas_demand_growth`, and `driver_changed_count`. The "what changed". |
| `gold_projection_detail` | Annual 2025-2045 cash flow at `Current` vs `Prior` vintage — where the value moved across the horizon. |
| `gold_assumptions_doc` | `parsed_text` — the analyst assumptions-memo PDF, parsed with AI Functions. The narrative rationale to quote. |

## Steps

1. **Identify the scenario that moved.** From `gold_scenario_npv_trend`, find the
   scenario whose NPV changed most between its earliest and latest vintage (the
   alerted scenario — `is_alerted = TRUE` at the latest vintage). Capture: scenario
   name, NPV before, NPV now, % change, and the risk-band move (e.g. Attractive → Marginal).
2. **Pull the drivers.** From `gold_assumptions` for that scenario, read the three
   `_old`/`_new` pairs (carbon-price floor, policy-effective year, gas demand growth).
3. **Locate where the value moved.** From `gold_projection_detail` for that scenario,
   compare `Current` vs `Prior` annual cash flow and note the horizon window where the
   gap opens (expected: 2035-2045).
4. **Ground the rationale.** From `gold_assumptions_doc.parsed_text`, quote the
   analyst's explanation for the revision — do not paraphrase beyond the source.
5. **Frame the landscape.** From `gold_scenario_npv_trend` at the latest vintage, list
   the other scenarios with their NPV and risk band so the client sees the shift in context.
6. **Write the memo** using the structure below. Keep it to one page, advisory tone,
   decision-oriented — talking points for a meeting, not a research report.

## Memo structure (output)

```markdown
# Client Strategy Discussion Memo — [Client] energy portfolio, 10-20 year outlook
**Prepared by:** Dr. Amara Okonkwo  ·  **Date:** [today]  ·  **For:** [client strategy session]

## 1. Headline
[Scenario] moved from **[band before] (~$[NPV before]B)** to **[band now] (~$[NPV now]B)** —
a **[% change]** shift ([$ swing]B in the recommendation) since [prior vintage]. The other
scenarios held broadly steady.

## 2. What changed (assumptions)
| Driver | Prior | Revised |
|--------|-------|---------|
| Carbon-price floor ($/t) | [old] | [new] |
| Policy effective year | [old] | [new] |
| Gas demand growth (%/yr) | [old] | [new] |

## 3. Where the value moved
The revised assumptions cut projected cash flows in **[horizon window]** — [one line on
the volume/carbon-cost mechanism from the analyst memo].

## 4. Analyst rationale (source memo)
> "[direct quote from gold_assumptions_doc.parsed_text]"

## 5. Scenario landscape (for context)
| Scenario | NPV ($B) | Risk band |
|----------|----------|-----------|
| [rows, ranked by NPV] | | |

## 6. Recommended discussion options
1. [option — e.g. hedge carbon exposure]
2. [option — e.g. re-time capex to the revised policy schedule]
3. [option — e.g. revisit the assumed transition pace]
Draw these from the "Recommended client actions" in the analyst memo; adapt to the client's portfolio.

## 7. Ask of the client
[One or two questions to confirm direction in the session.]
```

## Guardrails

- **No invented figures.** Only numbers present in the tables. Round NPV to one decimal ($B);
  express changes as signed percentages.
- **Quote, don't embellish.** Section 4 is a direct quote from `parsed_text`; keep client-action
  recommendations anchored to what the memo actually says.
- **Advisory, concise, one page.** This is a discussion aid for a meeting — bullets over prose,
  no filler.
- **Leave brackets the consultant must fill** (`[Client]`, `[today]`) as visible placeholders.
