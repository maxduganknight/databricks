# Creating the Ontology Page (UI-only, Beta)

An "Ontology Page" is a **Page** in **Unity Catalog semantics** (part of Genie
Ontology). Pages are a **Beta** feature and can only be created in the **UI** —
there is no SQL, CLI, API, or DABs path, so this step is manual and is *not*
reproduced by `bundle deploy`.

Content to use: `ontology/scenario_npv.page.md`.

## Prerequisites (do these first)

1. **Enable the Beta.** Pages require an **account admin** to turn on the
   Unity Catalog semantics / Pages Beta for the workspace. If you don't see
   "Pages" under Catalog → Discover, this is why.
2. **Create a domain.** A Page must attach to a domain. Create a domain named
   **Energy Scenario Intelligence** (Catalog → Discover → Domains → Create).
   Pages inherit access permissions from their domain.

## Create the Page

1. Go to **Catalog → Discover** (left nav) and open the **Energy Scenario Intelligence** domain.
2. **Create → Page** (or **Pages → New Page**).
3. Fill the fields from `scenario_npv.page.md`:
   - **Title:** Scenario NPV
   - **Synonyms:** NPV, net present value, scenario valuation, full-life NPV
   - **Description / body:** paste the Definition → Measurement → Vintage → Risk band →
     Scenario Shift alert sections (the editor supports rich text, tables, links, and
     asset tagging).
4. **Tag related assets:** attach `mv_scenario_economics`, `gold_scenario_npv_trend`,
   `gold_projection_detail`, `gold_assumptions`, and the dashboard.
5. **Add sources** and **publish**.

   *Shortcut:* the Page editor can **generate a draft from source material** — paste
   `scenario_npv.page.md` in and let it draft, then edit.

## Verify it works in Genie One

Open Genie One (or the demo's Genie space) and ask: **"What is scenario NPV?"** or
**"How is full-life NPV calculated?"** Genie One should answer from the Page and **cite
it** as the authoritative source. That citation is the demo payoff — the same governed
definition the `mv_scenario_economics` metric view computes.

## Caveats

- **Beta / availability:** Genie Ontology is Public Preview and Pages is Beta. I have
  **not** confirmed availability in Canadian regions (AWS `ca-central-1`, Azure Canada
  Central) — **confirm regional availability before presenting Pages as something they can use.**
- **No sensitive data:** Pages store text in plain text and don't support
  customer-managed keys — keep PII out (fine for this synthetic demo).
- The Scenario NPV Page is the one to build for the walkthrough; the four follow-on
  Pages are optional.
