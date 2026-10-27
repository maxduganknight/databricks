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

## Configuration

**`config.yml` is the single place to edit settings.** Every tunable is a bundle variable there,
grouped and documented; the files in `resources/` only reference `${var.<name>}`. Main knobs:

| Variable | Default | Effect |
| --- | --- | --- |
| `catalog` / `schema` / `bronze_table` | `mdk_demo_catalog` / `pdu_monitoring` / `bronze_pdu_telemetry` | Where bronze and all pipeline outputs live |
| `warehouse_id` | lookup `Serverless Starter Warehouse` | Warehouse for app bronze queries and the alert |
| `refresh_cron` / `refresh_timezone` / `refresh_pause_status` | `0 0/5 * * * ?` / `UTC` / `UNPAUSED` | Schedule of `pdu-refresh` (generator -> pipeline -> Lakebase sync) |
| `refresh_duration_warning_seconds` / `refresh_timeout_seconds` | `480` / `1200` | Slow-run warning email / hard timeout |
| `bronze_retention_days` / `backfill_hours` | `7` / `6` | Synthetic generator retention and max backfill (demo only) |
| `num_racks` / `rack_shelves` / `rack_positions` | `4` / `5` / `5` | Generated layout; shelves/positions also size the app grid |
| `watermark` / `status_lookback_hours` / `pipeline_stale_after_minutes` | `1 minute` / `24` / `3` | Pipeline late-data tolerance, status lookback, stale rule |
| `alert_email` | deploying user | Job failure and breach notifications |
| `breach_alert_cron` / `breach_alert_pause_status` | `0 2/5 * * * ?` / `UNPAUSED` (`PAUSED` in dev) | Breach alert schedule |
| `app_refresh_seconds` / `app_breach_bronze_refresh_seconds` | `30` / `60` | App page refresh / bronze auto-refresh while in BREACH |
| `app_status_cache_seconds` / `app_bronze_cache_seconds` / `app_stale_after_minutes` | `10` / `60` / `15` | App query caches and app-side stale rule |
| `lakebase_min_cu` / `lakebase_max_cu` / `lakebase_suspend_timeout` | `0.5` / `2` / `300s` | Lakebase endpoint autoscaling and idle suspend |

* **Thresholds** are not in `config.yml`: edit `src/sql/pdu_thresholds_seed.csv` (see below).
* **Per-environment overrides** go in `databricks.yml` under `targets.<target>.variables` (dev already
  overrides `lakebase_project`, `app_name` and `breach_alert_pause_status`), or on the command line
  with `--var name=value`.
* Changes take effect on `databricks bundle deploy -t <target>`; for app settings also run
  `databricks bundle run pdu_app -t <target>` so the app restarts with the new environment.

## What's in the repo

| Path | Purpose |
| --- | --- |
| `config.yml` | All settings (bundle variables) - edit here |
| `databricks.yml` | Bundle, includes, `dev` / `prod` targets and per-target overrides |
| `resources/generator.job.yml` | On-demand synthetic bronze backfill (demo only) |
| `resources/pipeline.yml` | SDP pipeline `pdu-monitoring-pipeline` |
| `resources/lakebase.yml` | Lakebase project, branch, endpoint, database, synced table |
| `resources/lakebase_setup.job.yml` | Applies `src/sql/lakebase/*.sql` migrations, grants the app |
| `resources/app.yml` | Databricks App + its resources (Lakebase, warehouse, bronze `SELECT`) |
| `resources/refresh.job.yml` | `pdu-refresh`: generator -> pipeline -> Lakebase sync (default every 5 min) |
| `resources/breach.alert.yml` | SQL alert: email when any PDU is in BREACH |
| `src/notebooks/` | Synthetic generator, Lakebase migrations, Lakebase sync trigger |
| `src/pipeline/` | Pipeline transformations + shared rules (`utilities/pdu_rules.py`) |
| `src/sql/pdu_thresholds_seed.csv` | Threshold rules (source of truth) |
| `src/app/` | Dash app (`app.py` pages/callbacks, `data.py` data access, `components.py` UI) |
| `tests/` | pytest suite for the rules and UI helpers |
| `docs/CHECKLIST.md` | Deploy / verification checklist |

## Data model

* **Layout**: by default 4 racks x 5 shelves x 5 positions = 100 PDUs, `unit_id = Rxx-Sy-Pz`. The
  last rack holds `PDU-HD-32A` units, the rest are `PDU-STD-24A`. The app draws `rack_shelves` x
  `rack_positions` per rack and hides units outside that layout.
* **Bronze** `<catalog>.<schema>.bronze_pdu_telemetry`: voltage, current, power, temperature,
  humidity per second, clustered by `(unit_id, event_ts)`, `bronze_retention_days` retention. A real deployment
  points `var.bronze_table` at its existing table and removes the generator task.
* **`pdu_minute_stats`** (streaming table): 1-minute tumbling windows per PDU, `watermark` late-data tolerance,
  implausible readings (null, sensor faults such as -40 C) excluded via expectations.
* **`pdu_latest_status`** (materialized view): newest minute per PDU over a `status_lookback_hours` lookback with
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
  Refreshes from Lakebase every `app_refresh_seconds`; never queries bronze.
* **Troubleshooting (`/unit/<unit_id>`)**: unit facts and resolved thresholds, second-level voltage
  and temperature for the last 15/30/60/120 min with shaded threshold bands and breach points,
  acknowledge breach, notes. Bronze is queried on open / window change / Refresh and auto-refreshed
  every `app_breach_bronze_refresh_seconds` only while the unit is in BREACH (results cached
  `app_bronze_cache_seconds` across users).

App settings come from `config.yml` (`app_*`, `rack_shelves`, `rack_positions`) and reach the app as
environment variables via `resources/app.yml`.

## Deploy

Prerequisites: a recent Databricks CLI with Lakebase Autoscaling bundle resources (developed with
v1.22.1) authenticated to the workspace, a Unity Catalog catalog you
can create schemas in, a SQL warehouse (default lookup: `Serverless Starter Warehouse`), serverless
compute, Lakebase Autoscaling and Databricks Apps enabled.

```bash
databricks bundle validate --strict -t dev
databricks bundle deploy -t dev
databricks bundle run pdu_synthetic_generator -t dev   # backfill + creates the schema/bronze table
databricks bundle run pdu_refresh -t dev               # pipeline + first Lakebase sync
databricks bundle run pdu_lakebase_setup -t dev        # migrations + app grants
databricks bundle run pdu_app -t dev                   # deploy / start the app
```

On a brand-new workspace the synced table needs `pdu_latest_status` to exist. If the first deploy
fails on `postgres_synced_tables`, run the generator job and a pipeline update
(`databricks bundle run pdu_monitoring -t dev`), then deploy again.

Override settings per workspace in `config.yml`, per target in `databricks.yml`, or ad hoc with
`--var catalog=my_catalog --var alert_email=ops@example.com`.
For `prod`: `databricks bundle deploy -t prod`, then run the same jobs with `-t prod` (ideally from
CI as a service principal).

### Schedules and cost

* `pdu-refresh` runs on `refresh_cron` (default every 5 minutes, UTC) on serverless, takes ~3-4
  minutes, skips a tick rather than queueing if a run overruns, and emails on failure or if a run
  exceeds `refresh_duration_warning_seconds` (default 8 minutes).
  End-to-end freshness in the app is roughly 3-8 minutes behind bronze. Pause the job in the UI
  when not demoing.
* The breach alert evaluates on `breach_alert_cron` (default every 5 minutes) on the SQL warehouse, which keeps the warehouse from
  auto-stopping. It is **paused in `dev`**; enable with
  `databricks bundle deploy -t dev --var breach_alert_pause_status=UNPAUSED`.
* Lakebase endpoint autoscales `lakebase_min_cu`-`lakebase_max_cu` (default 0.5-2 CU) and suspends
  after `lakebase_suspend_timeout` (default 5 minutes) idle.

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
