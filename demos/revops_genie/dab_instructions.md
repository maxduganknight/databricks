# Deploy — RevOps Revenue Intelligence

Workflow-only demo (no App / Lakebase). Prereqs: Databricks CLI **v0.283.0+**, a
configured profile (host + auth), and a running SQL warehouse.

Variables have defaults (`catalog=solution_builder`,
`schema=demo_revops_intelligence`, `warehouse_id=a94beda3aab06fa4`).
Override any with `--var` to deploy elsewhere.

```bash
# 1. Create the resource shells (schema, raw_churn_docs volume, dashboard, setup job)
databricks bundle deploy

#    …or to a different environment:
# databricks bundle deploy --var catalog=<cat> --var schema=<schema> --var warehouse_id=<id>

# 2. Run the setup job — builds everything:
#    generate_data (tables + sem_* views + predict_net_new_arr)
#    → upload_pdfs (churn/QBR PDFs to the volume)
#    → run_extract_churn (fact_churn_reason via ai_parse_document + ai_extract)
#    → deploy_genie (the 5 Genie spaces)  +  deploy_alert (Genie One scheduled insight)
databricks bundle run revops_setup
```

## Post-run: install the Genie Code skill

The "Revenue Retention Briefing" Genie Code skill is a workspace-level asset no
bundle resource type covers — install it once (Genie Code auto-loads it in fresh
chats):

```bash
USER_EMAIL=$(databricks current-user me | python3 -c 'import sys,json;print(json.load(sys.stdin)["userName"])')
databricks workspace mkdirs "/Workspace/Users/$USER_EMAIL/.assistant/skills"
databricks workspace import-dir .assistant/skills "/Workspace/Users/$USER_EMAIL/.assistant/skills" --overwrite
```

## Re-runs & teardown

- After a data/config change: re-run steps 1 + 2 — all tasks are idempotent
  (Genie spaces update in place by title). Re-running `deploy_alert` creates a
  new scheduled insight; delete the prior one if you don't want duplicates (see
  `specifications/06-unstructured-and-alert.md` for the delete command).
- `databricks bundle destroy` removes the schema, volume, dashboard, and job. It
  does NOT remove the Genie spaces, the scheduled insight, or the workspace skill
  — delete those manually.
