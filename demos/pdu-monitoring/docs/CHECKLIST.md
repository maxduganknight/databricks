# Deploy and verification checklist

Tick each item after a fresh deploy (or after changes to the relevant part). Commands assume `-t dev`.

## Bundle

- [ ] `databricks bundle validate --strict -t dev` and `-t prod` both pass
- [ ] `databricks bundle deploy -t dev` succeeds
- [ ] Settings changed only in `config.yml` (or `databricks.yml` target overrides / `--var`), not in `resources/*.yml`; `bundle validate -o json` shows the expected resolved values
- [ ] No customer names, hosts, tokens or personal IDs committed (`git grep -i` for them before pushing)

## Bronze

- [ ] `pdu_synthetic_generator` run succeeds; bronze has 100 distinct `unit_id`s and rows up to ~now
- [ ] Bronze is clustered by `(unit_id, event_ts)` (`DESCRIBE DETAIL`)

## Pipeline

- [ ] `pdu-monitoring-pipeline` update completes; `pdu_minute_stats`, `pdu_latest_status`, `pdu_thresholds` exist
- [ ] `pdu_latest_status` has exactly one row per unit; `pdu_thresholds` has one row per CSV line
- [ ] Expectation metrics in the event log: `plausible_voltage` / `plausible_temperature` show failures
      (the generator injects faults), `has_unit_id` / `has_event_ts` show none
- [ ] Spot check: one unit's minute in `pdu_minute_stats` matches min/max/count from bronze
- [ ] R02 units resolve `RACK:R02` voltage thresholds; R04 units resolve `MODEL:PDU-HD-32A` temperature

## Lakebase

- [ ] Synced table state is `ONLINE`; row count matches `pdu_latest_status`
- [ ] `pdu_lakebase_setup` run succeeds; `pdu_app.incident_ack`, `pdu_app.unit_notes` exist
- [ ] App service principal can `SELECT` the synced table and `SELECT, INSERT` the `pdu_app` tables

## Refresh job and alert

- [ ] `pdu_refresh` run succeeds (generator -> pipeline -> sync) in under 5 minutes
- [ ] Schedule shows every 5 minutes, UNPAUSED (pause when idle to save cost)
- [ ] After a run, Lakebase `max(updated_at)` is within a few minutes of now
- [ ] Breach alert query returns `breached_units`; alert is PAUSED in dev unless deliberately enabled
- [ ] Failure email arrives (e.g. temporarily break a job parameter) - optional

## App

- [ ] App deployment `SUCCEEDED` and the app is `RUNNING`
- [ ] App service principal has `USE CATALOG`, `USE SCHEMA` and `SELECT` on the bronze table
- [ ] Monitoring page: 4 rack cards stacked vertically, 5 x 5 landscape tiles each, KPIs add up to 100
- [ ] Rack filter limits grid, KPIs and offenders to the selected racks
- [ ] Clicking a tile opens `/unit/<unit_id>` with voltage and temperature charts and threshold bands
- [ ] Breach markers on the chart match a bronze count of readings beyond the breach bound
- [ ] Healthy unit: charts do not auto-refresh; breached unit: "auto-refreshing while in breach" shown
- [ ] Acknowledge a breach: tile turns dark red / ACK, unacknowledged count drops, ack shows your email
- [ ] A new breach episode on the same unit shows as unacknowledged again
- [ ] Add a note: appears in history with your email; empty note rejected
- [ ] Stop the refresh job for > 15 minutes: tiles turn hatched / STALE

## Tests

- [ ] `pytest -q` passes
