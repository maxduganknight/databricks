# Creating the Ontology Page (UI-only, Beta)

An "Ontology Page" is a **Page** in **Unity Catalog semantics** (part of Genie
Ontology). Pages are a **Beta** feature and can only be created in the **UI** —
there is no SQL, CLI, API, or DABs path, so this step is manual and is *not*
reproduced by `bundle deploy`.

Content to use: `ontology/net_revenue_retention.page.md`.

## Prerequisites (do these first)

1. **Enable the Beta.** Pages require an **account admin** to turn on the
   Unity Catalog semantics / Pages Beta for the workspace. If you don't see
   "Pages" under Catalog → Discover, this is why.
2. **Create a domain.** A Page must attach to a domain. Create a domain named
   **Revenue Intelligence** (Catalog → Discover → Domains → Create). Pages inherit
   access permissions from their domain.

## Create the Page

1. Go to **Catalog → Discover** (left nav) and open the **Revenue Intelligence** domain.
2. **Create → Page** (or **Pages → New Page**).
3. Fill the fields from `net_revenue_retention.page.md`:
   - **Title:** Net Revenue Retention (NRR)
   - **Synonyms:** NRR, net dollar retention, NDR, net retention
   - **Description / body:** paste the Definition → Formula → Control line →
     Measurement → Reporting rule sections (the editor supports rich text, tables,
     links, and asset tagging).
4. **Tag related assets:** attach `mv_revenue_retention`, `sem_nrr_retention`, and the
   dashboard so the Page links to the governed objects.
5. **Add sources** and **publish**.

   *Shortcut:* the Page editor can **generate a draft from source material** — paste
   `net_revenue_retention.page.md` in and let it draft, then edit.

## Verify it works in Genie One

Open Genie One and ask: **"What is NRR / net revenue retention?"** Genie One should
answer from the Page and **cite it** as the authoritative source, rather than
inferring a definition. That citation is the demo payoff — the same governed
definition the `mv_revenue_retention` metric view computes.

## Caveats

- **Beta / availability:** Genie Ontology is Public Preview and Pages is Beta. I have
  **not** confirmed availability in Canadian regions (AWS `ca-central-1`, Azure Canada
  Central). Do not tell a Canadian customer this is available to them without checking.
- **No sensitive data:** Pages store text in plain text and don't support
  customer-managed keys — keep PII out (fine for this synthetic demo).
- Only the four listed follow-on Pages are optional; the NRR Page is the one to build
  for the walkthrough.
