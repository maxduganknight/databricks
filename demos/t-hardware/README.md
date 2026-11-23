# T Industries - Databricks as the backend for TAI

T Industries is a Canadian distributor of door hardware (locks, levers, door closers, hinges, exit devices) and bathroom fixtures (faucets, grab bars, accessories). Its Teams chatbot **TAI** runs on Copilot Studio. This demo shows Databricks as TAI's governed backend: ERP, HubSpot and SharePoint data are combined in one pipeline, then queried through Genie Agents and an AI/BI dashboard.

All data is synthetic and seeded, so it is the same on every run. It is small (about 14K orders and 36 documents) and runs entirely on serverless.

## What gets built

Everything lives in **one schema, `mdk_demo_catalog.t_hardware`**. The layer is the table-name prefix (`bronze_`, `silver_`, `gold_`, `gov_`), and every `bronze_` / `silver_` / `gold_` object also carries the governed Unity Catalog tag `layer` (bronze / silver / gold).

| Layer | Objects (schema `mdk_demo_catalog.t_hardware`) |
| --- | --- |
| Landing | Volume `landing` with `product_images/` (64 PNGs), `sharepoint/` (14 PDF/DOCX + 2 markdown business rules), `hubspot_attachments/` (20 quotes, photos, screenshots), `photo_uploads/` (9 real customer-style product photos of other brands' knobs, handlesets and a digital deadbolt, to upload to Genie One during the demo). Volume `knowledge`: the SharePoint library as raw files (16 PDF / DOCX / Markdown), synced from `landing/sharepoint` on every job run and read directly by the T Docs & SOPs agent |
| Bronze (`bronze_*`) | `bronze_products` (285 SKUs), `bronze_customers` (500), `bronze_sales_orders` / `bronze_order_lines` (24 months, seasonality), `bronze_inventory` (Delta BC, Toronto), `bronze_competitor_prices` (NorthBuild Supply, Pacific Hardware Co, DoorPro Direct), `bronze_hubspot_companies` / `_deals` / `_tickets`, `bronze_hubspot_attachments`, `bronze_sharepoint_files` (Lakeflow Connect shape: file_name, path, modified_time, content BINARY) |
| Silver (`silver_*`) | Typed, deduplicated tables with standardized SKUs and regions (`silver_products`, `silver_order_lines`, ...), HubSpot tickets joined to ERP orders and themed with `ai_classify` (`silver_hubspot_tickets`), `silver_doc_parsed` (`ai_parse_document` output for every SharePoint and HubSpot binary) and `silver_doc_chunks` (doc_name, source, section, chunk_text, page) |
| Gold (`gold_*`) | `gold_sales_daily`, `gold_product_margin`, `gold_inventory_position` (row filter), `gold_price_benchmark` (+ `_by_competitor`), `gold_ticket_insights`, `gold_dim_product`, `gold_dim_customer`, `gold_doc_summaries` (`ai_summarize` + `ai_extract`: warranty terms, install steps, policy points) |
| Semantic layer | Metric view `t_sales_metrics` (net sales, gross margin %, units, ASP, backorder rate, with synonyms) |
| Governance (`gov_*`) | Comments on every table and column, PK constraints, pipeline expectations, `layer` tags, and the row filter `gov_warehouse_row_filter` driven by the `gov_warehouse_access` table |
| Genie | **T Sales & Ops** (gold tables + metric view; matches a product described by Genie One to our closest SKUs; 8 example SQLs, 7 benchmarks) and **T Docs & SOPs** (raw files in the `knowledge` volume + `gold_ticket_insights` + `gold_dim_product`, the Knowledge Assistant replacement) |
| Dashboard | **T Commercial Overview**: KPIs, sales trend, margin by category, inventory by warehouse, backorder heatmap, competitor price-gap heatmap, ticket themes, overpriced SKUs. Ask Genie is linked to T Sales & Ops |

## Repo layout

```
databricks.yml                          bundle (vars: catalog, warehouse_id)
resources/
  t_genie_ready.pipeline.yml            SDP pipeline (serverless)
  t_daily_refresh.job.yml               daily job, 06:00 America/Vancouver
  t_commercial_overview.dashboard.yml   AI/BI dashboard
src/notebooks/
  01_generate_synthetic_data            Faker + reportlab + python-docx; idempotent (regenerate=true to rebuild)
  02_setup_governance                   gov_warehouse_row_filter + gov_warehouse_access (presenter_scope widget)
  03_semantic_layer                     metric view + identify_product_photo + layer tags
  04_setup_genie                        create/update both Genie Agents via REST, link the dashboard
src/pipelines/t_genie_ready/transformations/
  silver/erp.sql, silver/hubspot.sql, docs/doc_parsed.sql (silver_doc_parsed), silver/doc_chunks.sql
  gold/sales.sql, gold/pricing.sql, gold/inventory_position.sql, gold/service.sql, gold/doc_summaries.sql
src/dashboards/t_commercial_overview.lvdash.json
```

## Deploy and run

```
databricks bundle deploy -t dev
databricks bundle run t_daily_refresh -t dev          # first run: about 15 minutes
```

The job runs `land_sources` -> `governance` -> `t_genie_ready` (pipeline) -> `semantic_layer` -> `genie_agents`. To rebuild the synthetic data from scratch, pass `--params regenerate=true`. In `dev` mode the bundle pauses the schedule; deploy with `-t prod` to schedule it. To use another catalog or warehouse, override `catalog` / `warehouse_id`, then update the catalog name in the `.lvdash.json` datasets.

## Demo script

1. **Lineage and run history**: open job `t_daily_refresh`, then the pipeline graph (bronze -> silver -> gold, plus the docs branch through `ai_parse_document`). In Catalog Explorer, open schema `t_hardware` (filter by the `layer` tag) and follow `gold_price_benchmark` lineage back to `bronze_competitor_prices`.
2. **Governed metrics**: open `t_sales_metrics` and point out that net sales follows the Finance rule in `/Volumes/mdk_demo_catalog/t_hardware/landing/sharepoint/Business Rules/net_sales_definition.md`.
3. **Row-level security**: `SELECT warehouse, count(*) FROM mdk_demo_catalog.t_hardware.gold_inventory_position GROUP BY 1` returns both warehouses. Set `presenter_scope = Delta BC` in `02_setup_governance` and run it again (or `UPDATE` your row in `t_hardware.gov_warehouse_access`). The same query now returns only Delta BC. Set it back to `ALL` afterwards.
4. **T Sales & Ops Genie**:
   * Which SKUs are priced more than 10% above competitors? (Exit devices stand out: about 70% of exit device SKUs are more than 10% above the cheapest competitor.)
   * Top customers by margin in BC last quarter.
   * Why are Toronto door closer backorders so high? (The backorder rate has been about 28% since August, against a 5% target.)
   * **Photo question (in Genie One)**: upload a product photo (e.g. one from `photo_uploads/`, or a Schlage keypad lever photo) and ask "What's our equivalent of this product?". Genie One describes the photo and asks T Sales & Ops in text; the agent maps the description to a subcategory and finish and returns our top 3 SKUs with competitor prices. Example: a satin chrome / nickel keypad entry lever lock maps to TH-LK-1034 Cambie Electronic Keypad Lock - Satin Stainless at $508.73 vs $505.81 at NorthBuild Supply (0.6% above). We have no Satin Chrome keypad lock, so the agent says the finish is the closest match. Knobs map to Passage Lever Sets, and the agent says we sell levers, not knobs or handlesets.
5. **T Docs & SOPs Genie** (Agent mode; this is the Knowledge Assistant replacement and reads the raw files in the `knowledge` volume):
   * "What is the restocking fee for returns?": 20%, waived for T Industries shipping errors (CS-04, DOCX).
   * "Who can approve a 35% discount off list?": a Regional Sales Manager, who can approve up to 38% (Pricing and Discount Authority Matrix, DOCX).
   * "What's the warranty on commercial door closers, and how many warranty-claim tickets did we get on closers in the last 12 months?": 10 years on the body and 3 years on finish (WP-01, PDF), plus the ticket count from `gold_ticket_insights`. Documents and data come back in one answer with citations.
   * "Summarize the DC-Series commercial door closer spec sheet" and "How many vacation days do employees in BC get after one year?" (both PDF).
   * After new files are added to the volume, Genie needs a few minutes to index them.
6. **Dashboard**: open *T Commercial Overview*, filter Region = BC, then click **Ask Genie** for follow-up questions.

## Planted stories

* Exit devices are priced well above competitors (DoorPro Direct and NorthBuild Supply undercut T most often). Eight HubSpot invoice-dispute tickets on exit devices have quote PDFs attached.
* Toronto has a door closer backorder problem in recent months.
* About 1% of order lines are duplicates, SKU formats are inconsistent (`th-dc-1101`, `TH DC 1082`, `THDC1088`), and region spellings vary. Silver cleans all three.
* Some HubSpot tickets reference orders only in free text. Silver resolves them (`order_link_method`).

## Mapping to production

| Demo | Production |
| --- | --- |
| `01_generate_synthetic_data` | Lakeflow Connect connectors for SharePoint and HubSpot, plus ERP ingestion (Lakeflow Connect or federation) |
| Photo question via Genie One | TAI (Copilot Studio) describes the user's photo with its own vision model, or forwards it to Genie One, and asks T Sales & Ops through the Genie Conversation API |
| `knowledge` volume synced from `landing/sharepoint` | The Lakeflow Connect SharePoint connector lands files directly in the volume the T Docs & SOPs agent reads; this replaces the Knowledge Assistant index |
| Genie Agents | Exposed to Teams through the Genie Conversation API or the Copilot Studio Genie connector |
