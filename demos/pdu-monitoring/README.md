# PDU Monitoring (prototype)

Rack PDU monitoring for a data center on Databricks, packaged as one Declarative Automation Bundle:
second-level telemetry in Delta, a Lakeflow Spark Declarative Pipeline that classifies every PDU
against configurable thresholds, a Lakebase (Postgres) serving layer, and a Dash Databricks App for
operators.

```
bronze_pdu_telemetry (Delta, 1 row / PDU / second)
        |  SDP pipeline (triggered every 5 min)
        v
pdu_minute_stats (ST, 1-min windows)  +  pdu_thresholds (MV, from CSV)
        v
pdu_latest_status (MV, 1 row / PDU)  --SNAPSHOT sync-->  Lakebase: pdu_latest_status_synced
        |                                                    Lakebase: pdu_app.incident_ack / unit_notes
        +--> SQL alert (breach email)                                 ^
                                                                      |
                     Databricks App (Dash)  -- monitoring page reads Lakebase only
                                            -- unit page reads bronze for ONE unit via SQL warehouse
```

## What's in the repo

| Path | Purpose |
| --- | --- |
| `databricks.yml` | Bundle, variables, `dev` / `prod` targets |
| `resources/generator.job.yml` | On-demand synthetic bronze backfill (demo only) |
| `resources/pipeline.yml` | SDP pipeline `pdu-monitoring-pipeline` |
| `resources/lakebase.yml` | Lakebase project, branch, endpoint, database, synced table |
| `resources/lakebase_setup.job.yml` | Applies `src/sql/lakebase/*.sql` migrations, grants the app |
| `resources/app.yml` | Databricks App + its resources (Lakebase, warehouse, bronze `SELECT`) |
| `resources/refresh.job.yml` | `pdu-refresh`: generator -> pipeline -> Lakebase sync, every 5 min |
| `resources/breach.alert.yml` | SQL alert: email when any PDU is in BREACH |
| `src/notebooks/` | Synthetic generator, Lakebase migrations, Lakebase sync trigger |
| `src/pipeline/` | Pipeline transformations + shared rules (`utilities/pdu_rules.py`) |
| `src/sql/pdu_thresholds_seed.csv` | Threshold rules (source of truth) |
| `src/app/` | Dash app (`app.py` pages/callbacks, `data.py` data access, `components.py` UI) |
| `tests/` | pytest suite for the rules and UI helpers |
| `docs/CHECKLIST.md` | Deploy / verification checklist |

## Data model

* **Layout**: 4 racks x 5 shelves x 5 positions = 100 PDUs, `unit_id = Rxx-Sy-Pz`. Rack `R04` holds
  `PDU-HD-32A` units, the rest are `PDU-STD-24A`. The app draws `RACK_SHELVES` x `RACK_POSITIONS`
  (default 5 x 5) per rack and hides units outside that layout.
* **Bronze** `<catalog>.<schema>.bronze_pdu_telemetry`: voltage, current, power, temperature,
  humidity per second, clustered by `(unit_id, event_ts)`, 7-day retention. A real deployment
  points `var.bronze_table` at its existing table and removes the generator task.
* **`pdu_minute_stats`** (streaming table): 1-minute tumbling windows per PDU, 1-minute watermark,
  implausible readings (null, sensor faults such as -40 C) excluded via expectations.
* **`pdu_latest_status`** (materialized view): newest minute per PDU over a 24 h lookback with
  `status` (OK / WARN / BREACH), `breached_metrics`, `warn_metrics`, `severity_score`,
  `breach_started_ts`, `breach_minutes_lookback`, `is_stale` and the resolved thresholds.
* **Lakebase** `pdu_app.incident_ack` (ack tied to a breach episode via `breach_started_ts`) and
  `pdu_app.unit_notes`, written by the app as the signed-in user's email.

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

## The app

* **Monitoring (`/`)**: KPIs (breach / warning / OK / stale counts, unacknowledged breaches, data
  age), racks stacked vertically with one landscape tile per PDU (green OK, amber WARN, pulsing red
  unacknowledged BREACH, dark red acknowledged, hatched stale), rack filter, worst-offenders list.
  Refreshes from Lakebase every 30 s; never queries bronze.
* **Troubleshooting (`/unit/<unit_id>`)**: unit facts and resolved thresholds, second-level voltage
  and temperature for the last 15/30/60/120 min with shaded threshold bands and breach points,
  acknowledge breach, notes. Bronze is queried on open / window change / Refresh and auto-refreshed
  every 60 s only while the unit is in BREACH (results cached 60 s across users).

App settings (env vars, all optional): `REFRESH_SECONDS` (30), `BREACH_BRONZE_REFRESH_SECONDS` (60),
`STATUS_CACHE_SECONDS` (10), `BRONZE_CACHE_SECONDS` (60), `STALE_AFTER_MINUTES` (15),
`RACK_SHELVES` / `RACK_POSITIONS` (5 / 5).

## Deploy

Prerequisites: a recent Databricks CLI with Lakebase Autoscaling bundle resources (developed with
v1.22.1) authenticated to the workspace, a Unity Catalog catalog you
can create schemas in, a SQL warehouse (default lookup: `Serverless Starter Warehouse`), serverless
compute, Lakebase Autoscaling and Databricks Apps enabled.

```bash
databricks bundle validate --strict -t dev
databricks bundle deploy -t dev
databricks bundle run pdu_synthetic_generator -t dev   # 6 h backfill + creates the schema/bronze table
databricks bundle run pdu_refresh -t dev               # pipeline + first Lakebase sync
databricks bundle run pdu_lakebase_setup -t dev        # migrations + app grants
databricks bundle run pdu_app -t dev                   # deploy / start the app
```

On a brand-new workspace the synced table needs `pdu_latest_status` to exist. If the first deploy
fails on `postgres_synced_tables`, run the generator job and a pipeline update
(`databricks bundle run pdu_monitoring -t dev`), then deploy again.

Override variables per workspace, e.g. `--var catalog=my_catalog --var alert_email=ops@example.com`.
For `prod`: `databricks bundle deploy -t prod`, then run the same jobs with `-t prod` (ideally from
CI as a service principal).

### Schedules and cost

* `pdu-refresh` runs every 5 minutes (UTC) on serverless, takes ~3-4 minutes, skips a tick rather
  than queueing if a run overruns, and emails on failure or if a run exceeds 8 minutes.
  End-to-end freshness in the app is roughly 3-8 minutes behind bronze. Pause the job in the UI
  when not demoing.
* The breach alert evaluates every 5 minutes on the SQL warehouse, which keeps the warehouse from
  auto-stopping. It is **paused in `dev`**; enable with
  `databricks bundle deploy -t dev --var breach_alert_pause_status=UNPAUSED`.
* Lakebase endpoint autoscales 0.5-2 CU and suspends after 5 idle minutes.

### Teardown

`databricks bundle destroy -t dev` removes the jobs, pipeline, app, alert and Lakebase project.
The schema and bronze table are deliberately not bundle-managed and are kept.

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

Spark tests use an active Databricks session, Databricks Connect, or local PySpark (in that order).
UI helper tests are skipped if Dash is not installed.

## Known limitations (prototype)

* Telemetry is synthetic; one unit runs hot (`R03-S5-P4`) and one drops out periodically
  (`R02-S3-P2`) to exercise WARN and stale states.
* Status is minute-level and recomputed every 5 minutes; it is not a real-time alarm system.
* Acknowledgements do not suppress the email alert, and the alert has no per-unit routing.
* The app uses Flask's threaded server; use gunicorn for heavier use.
* Units removed from the layout disappear from status after the 24 h lookback, or immediately
  after deleting their bronze rows and fully refreshing the pipeline.
