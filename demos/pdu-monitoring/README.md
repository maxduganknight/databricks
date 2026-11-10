# PDU Monitoring (prototype)

Rack PDU monitoring as one Declarative Automation Bundle: second-level telemetry in Delta, a Lakeflow
Spark Declarative Pipeline that classifies every PDU against configurable thresholds, a Lakebase
(Postgres) serving layer, a Dash Databricks App for operators, SQL alerts, a Genie agent and a
predictive-maintenance model that ranks units by breach risk.

```
bronze_pdu_telemetry (1 row / PDU / second)
   |  SDP pipeline (triggered by pdu-refresh every 5 min)
   v
pdu_minute_stats (1-min windows) + pdu_thresholds
   |                       |
   v                       +--> Feature Views (pm_*) --> breach-risk model --> pdu_breach_risk_predictions
pdu_latest_status (1 row / PDU) --SNAPSHOT sync--> Lakebase pdu_latest_status_synced
   +--> breach SQL alert                           Lakebase pdu_app.technician_alerts / unit_notes
                                                      | ops history sync (every 5 min)
                                                      v
                                     UC ops_history.* (Delta + CDF) --> technician SQL alert

App: monitor (Lakebase) | unit troubleshooting (bronze via warehouse) | breach risk | Ask Genie
```

## Configuration

All settings are bundle variables in **`config.yml`**, grouped and documented there; `resources/`
only references `${var.<name>}`. The ones you are most likely to change:

| Variable | Default | Effect |
| --- | --- | --- |
| `catalog` / `schema` / `bronze_table` | `mdk_demo_catalog` / `pdu_monitoring` / `bronze_pdu_telemetry` | Where bronze and all outputs live |
| `warehouse_id` | lookup `Serverless Starter Warehouse` | App bronze queries and both alerts |
| `refresh_cron` / `refresh_pause_status` | every 5 min UTC / `UNPAUSED` | `pdu-refresh` schedule |
| `bronze_retention_days` | `21` | Synthetic bronze retention (enough history for model training) |
| `num_racks` / `rack_shelves` / `rack_positions` | `4` / `5` / `5` | Generated layout; also sizes the app grid |
| `alert_email` / `technician_email` | deploying user | Job-failure and breach mail / "Alert technician" mail |
| `breach_alert_pause_status` | `UNPAUSED` (`PAUSED` in dev) | Schedule state of both SQL alerts |
| `app_url` / `genie_space_id` | set in dev | Link in alert emails / Genie agent for the Ask Genie page |
| `cost_tag_project` / `usage_policy_id` | `pdu-monitoring` / set in dev | Cost attribution (see Schedules and cost) |

Thresholds live in `src/sql/pdu_thresholds_seed.csv`, not `config.yml`. Override per target in
`databricks.yml` (`targets.<target>.variables`) or ad hoc with `--var name=value`. Changes apply on
`databricks bundle deploy`; app settings also need `databricks bundle run pdu_app`.

## What's in the repo

| Path | Purpose |
| --- | --- |
| `config.yml` / `databricks.yml` | Settings / bundle, `dev` and `prod` targets |
| `resources/refresh.job.yml` | `pdu-refresh`: generator -> pipeline -> Lakebase sync -> ops history sync |
| `resources/generator.job.yml` | On-demand synthetic bronze backfill (demo only) |
| `resources/history_rebuild.job.yml` | On-demand rebuild of synthetic history with the wear model + full pipeline refresh (demo only) |
| `resources/pipeline.yml` | SDP pipeline `pdu-monitoring-pipeline` |
| `resources/lakebase.yml` / `lakebase_setup.job.yml` | Lakebase project, branch, endpoint, database, synced table / migrations and app grants |
| `resources/app.yml` | Databricks App and its resource bindings |
| `resources/breach.alert.yml` / `technician_alert.alert.yml` | SQL alerts: any PDU in BREACH / "Alert technician" triggered |
| `src/pipeline/` | Pipeline transformations + shared rules (`utilities/pdu_rules.py`) |
| `src/notebooks/` | Generator, Lakebase migrations and sync, ops history sync, model training and scoring |
| `src/ml/pdu_pm_features.py` | Feature definitions, labels and scoring helpers shared by training and scoring |
| `src/app/` | Dash app (`app.py` pages, `data.py` data access, `components.py` UI, `genie_chat.py`) |
| `src/sql/` | Threshold rules CSV, Lakebase migrations, cost attribution query |
| `tests/` | pytest suite for the rules and UI helpers |
| `docs/` | `CHECKLIST.md` (deploy checks), `BUILD_EVIDENCE.md` (captured run outputs) |

## Data model

* **`bronze_pdu_telemetry`**: per-second voltage, current, power, temperature and humidity, clustered
  by `(unit_id, event_ts)`. Not bundle-managed, so `bundle destroy` never drops it.
* **`pdu_minute_stats`** (streaming table): 1-minute windows per PDU.
* **`pdu_latest_status`** (materialized view): one row per PDU with `status` (OK / WARN / BREACH),
  breached / warned metrics, `severity_score`, `breach_started_ts`, `is_stale` and resolved thresholds.
* **Lakebase `pdu_app`**: `technician_alerts` and `unit_notes`, written by the app as the signed-in
  user; copied to UC `ops_history` (Delta + CDF) after each pipeline cycle.
* **`pdu_breach_risk_predictions`**: one row per unit per scoring time with `risk_score`, `risk_rank`,
  `risk_band` (HIGH / ELEVATED / LOW / IN_BREACH) and the key features behind it.

### Thresholds

Edit `src/sql/pdu_thresholds_seed.csv`, then `databricks bundle deploy`; the next pipeline update
republishes `pdu_thresholds`. Rules are per metric (`voltage`, `temperature`) with optional
`breach_min <= warn_min <= warn_max <= breach_max`. Most specific scope wins:
`UNIT > RACK > MODEL > GLOBAL`.

| Scope | Metric | Breach < | Warn < | Warn > | Breach > |
| --- | --- | --- | --- | --- | --- |
| GLOBAL | voltage | 220 | 228 | 252 | 260 |
| GLOBAL | temperature | | | 45 | 55 |
| MODEL `PDU-HD-32A` | temperature | | | 50 | 60 |
| RACK `R02` | voltage | 222 | 230 | 250 | 258 |
| UNIT `R03-S5-P4` | temperature | | | 43 | 46 |

## The app

* **Monitor (`/`)**: KPIs, one tile per PDU by rack (OK / WARN / BREACH, alerted, stale), worst
  offenders. Reads Lakebase only, refreshed every `app_refresh_seconds`.
* **Unit (`/unit/<unit_id>`)**: second-level voltage and temperature with threshold bands, "Alert
  technician" and notes. Queries bronze via the warehouse on demand (auto-refresh only while in BREACH).
* **Breach risk (`/risk`)**: latest model ranking, filterable by band, linking to each unit page.
* **Ask Genie (`/genie`)**: natural-language questions over the PDU tables, as the signed-in user.

## Predictive maintenance

Ranks healthy units by the chance of a sustained breach (at least 5 minutes) in the next 12 hours, so
technicians can visit them first. Features are Feature Views over `pdu_minute_stats` (`pm_*` in the
schema, computed point-in-time, not materialized).

* **Train**: `src/notebooks/predictive_maintenance_training` compares feature sets and models against
  a simple temperature-headroom rule on an out-of-time split, then registers
  `pdu_breach_risk_model` with alias `champion`.
* **Score**: `src/notebooks/score_breach_risk` scores every unit at the latest 00:00 / 12:00 UTC
  boundary and writes `pdu_breach_risk_predictions`. Run on demand; not yet scheduled.

Results are in `docs/BUILD_EVIDENCE.md` section 9: the model beats the rule on PR-AUC but matches it at
the top 10 per shift, and scores are a ranking, not calibrated probabilities.

## Deploy

Prerequisites: a recent Databricks CLI (with Lakebase Autoscaling bundle resources), a UC catalog
you can create schemas in, a SQL warehouse, serverless compute, Lakebase Autoscaling and Databricks
Apps. Optional: a Genie space over the PDU tables and a serverless usage policy (set their IDs per
target).

```bash
databricks bundle validate --strict -t dev
databricks bundle deploy -t dev
databricks bundle run pdu_synthetic_generator -t dev   # backfill + creates the schema/bronze table
databricks bundle run pdu_refresh -t dev               # pipeline + first Lakebase sync
databricks bundle run pdu_lakebase_setup -t dev        # migrations + app grants
databricks bundle run pdu_app -t dev                   # deploy / start the app
```

First deploy on a new workspace: the synced table needs `pdu_latest_status`, and the app binds to
`pdu_breach_risk_predictions`. If deploy fails on either, run the generator and a pipeline update
(`databricks bundle run pdu_monitoring -t dev`), and the training and scoring notebooks, then deploy
again. For `prod`, deploy and run with `-t prod`, ideally from CI as a service principal.

### Schedules and cost

* **`pdu-refresh`** runs every 5 minutes on serverless (about 3-4 minutes per run), skips a tick
  rather than queueing, and emails on failure or slow runs. The app lags bronze by about 3-8 minutes.
  It is the largest cost: about $35-45 a day at list price in dev.
* **Both SQL alerts** evaluate every 5 minutes on the warehouse and are paused in dev; enable with
  `--var breach_alert_pause_status=UNPAUSED`.
* **Lakebase** autoscales 0.5-2 CU and suspends after 5 idle minutes.
* **Cost attribution**: jobs and the pipeline get `project`, `environment` and `component` tags from
  the bundle, the Lakebase project gets the same as `custom_tags`, and the pipeline, app and jobs use
  the serverless usage policy in `usage_policy_id` (tag `project`). Query
  `src/sql/pdu_cost_attribution.sql` for daily cost by component. Not attributed: the shared SQL
  warehouse, and notebooks run interactively unless the usage policy is your default.

### Teardown

`databricks bundle destroy -t dev` removes the jobs, pipeline, app, alerts and Lakebase project.
The schema, bronze table, ops history, model and predictions are not bundle-managed and are kept.

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

Spark tests use an active Databricks session, Databricks Connect, or local PySpark (in that order).
UI helper tests are skipped if Dash is not installed.

## Known limitations (prototype)

* Telemetry is synthetic, with a simulated wear model. `R03-S5-P4` runs hot (its breach threshold
  is lowered to 46 C so it always shows BREACH) and `R02-S3-P2` drops out to exercise stale states.
* Status is minute-level and recomputed every 5 minutes; it is not a real-time alarm system.
* Alerts have no per-unit routing, and a technician alert does not suppress the breach alert.
* The breach-risk model is trained on synthetic data, scoring is not scheduled, and no maintenance
  actions are recorded yet, so the model cannot learn from repairs.
* The app runs on Dash's built-in server; use gunicorn for heavier use.
