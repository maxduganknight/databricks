# Deploy — Scenario Shift Alert

Workflow-only demo (no App / Lakebase). The monitoring beat is a **scheduled Genie
task** (job `scenario_watch`), armed after the Genie space exists.

```bash
# 1. Create resource shells (schema, assumptions_docs volume, dashboard) + both jobs
databricks bundle deploy \
  --var catalog=mdk_demo_catalog \
  --var schema=demo_scenario_shift_alert_015b3e \
  --var warehouse_id=<your_sql_warehouse_id>

# 2. Run the setup job:
#    generate_data -> deploy_metric_view (governed NPV) + upload_pdfs -> parse_pdf (ai_parse_document)
#                  -> deploy_genie -> export_resources
databricks bundle run scenario_shift_setup \
  --var catalog=mdk_demo_catalog \
  --var schema=demo_scenario_shift_alert_015b3e \
  --var warehouse_id=<your_sql_warehouse_id>

# 3. Arm the scheduled Genie watch. The Genie space id only exists after step 2,
#    so grab it from the export_resources exit JSON, then re-deploy with it +
#    UNPAUSED. (Until then scenario_watch is deployed but PAUSED.)
databricks jobs get-run-output <run_id_from_step_2>   # -> notebook_output.result JSON has genie_space_id
databricks bundle deploy \
  --var catalog=mdk_demo_catalog \
  --var schema=demo_scenario_shift_alert_015b3e \
  --var warehouse_id=<your_sql_warehouse_id> \
  --var genie_space_id=<genie_space_id_from_step_3> \
  --var watch_pause_status=UNPAUSED
```

`export_resources` exits a JSON manifest of the resolved IDs (dashboard, genie_space_id,
volume, parsed-doc table) — retrieve it with `databricks jobs get-run-output <run_id>`.

## The scheduled Genie task

`scenario_watch` runs `src/deploy/genie_scheduled_task.py` on the schedule in `databricks.yml`
(weekly, Mon 07:00 UTC). Each run:
1. Asks the Genie space, via the Conversation API:
   *"Which scenario projection changed the most since the earliest model vintage, and by what percent?"*
2. Reads Genie's answer + the SQL it ran, finds the largest negative NPV move, and compares it to the
   `THRESHOLD_PCT` guardrail (−30%, editable at the top of the script).
3. Appends the run to `{catalog}.{schema}.genie_watch_log` (question, answer, SQL, worst scenario,
   percent move, `triggered` flag) — queryable + auditable.
4. When breached (the −38% Accelerated Transition swing trips it), prints the next step: open the
   *Scenario Strategy* Genie space and ask why, then summarize the analyst rationale.

Run it on demand (outside the schedule) with:
```bash
databricks bundle run scenario_watch \
  --var warehouse_id=<id> --var genie_space_id=<id>
```

## Notes
- Requires Databricks CLI **v0.283.0+** (dashboard `dataset_catalog`/`dataset_schema` rebinding).
- `dev` target (default) prefixes the schema with `dev_<user>_`; use `-t prod` for the unprefixed schema.
- `parse_pdf` uses `ai_parse_document` — needs a serverless notebook environment on **DBR 17.3+** (default).
- To use your own assumptions memo: drop the PDF into
  `/Volumes/<catalog>/<schema>/assumptions_docs/raw_data/pdf/` and re-run `bundle run scenario_shift_setup`.

## Teardown
```bash
databricks bundle destroy --auto-approve
```
Does not drop the UC tables/volume data, the Genie space, or the `genie_watch_log` (the log is a table written by the job task, not a declared resource).
