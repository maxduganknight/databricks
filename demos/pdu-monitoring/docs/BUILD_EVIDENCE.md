# PDU Monitoring — Build Execution Evidence

All output below was captured live on 2026-11-05 UTC from the running dev deployment
(`fevm-mdk-demo.cloud.databricks.com`, workspace `7474647295259694`).
Every table is the direct result of a SQL query or API call; no output has been edited.

---

## 1. Architecture

A single Declarative Automation Bundle (`pdu_monitoring`) that provisions:

```
bronze_pdu_telemetry (Delta, 100 units × ~604k rows/unit = 60.4M rows)
  └─ Lakeflow SDP pipeline (pdu_monitoring)
       ├─ pdu_thresholds  MV  — threshold CSV → scoped rules
       ├─ pdu_minute_stats MV — per-unit 1-min aggregates
       └─ pdu_latest_status MV — 1 row/PDU, status + severity
             ├─ Lakebase SNAPSHOT sync → pdu_latest_status_synced (Postgres)
             │    └─ Databricks App reads over psycopg (<10 ms)
             └─ Reverse-ETL job → ops_history.{technician_alerts, unit_notes} (UC Delta + CDF)
                  └─ SQL alert emails technician when alert triggered
```

Databricks App (Dash) serves these pages:
- `/` — monitoring grid, KPIs, worst-offenders (Lakebase only, no warehouse)
- `/unit/<id>` — second-level bronze charts + "Alert technician" button
- `/genie` — AI assistant chat over the PDU Genie space
- `/risk` — breach-risk ranking from the predictive-maintenance model (section 9, added 2026-11-06)

---

## 2. Deployed Resources

| Resource | ID | Status |
| --- | --- | --- |
| Catalog / schema | `mdk_demo_catalog.pdu_monitoring` | Unity Catalog |
| Bronze table | `mdk_demo_catalog.pdu_monitoring.bronze_pdu_telemetry` | Delta |
| SDP pipeline | `9927fd76-18d2-4b9b-8ebb-933a1cc71ccc` | RUNNING |
| Generator job | `976933271777932` | on-demand |
| Refresh job | `493670388364531` | UNPAUSED, every 5 min |
| Lakebase setup job | `5229467603065` | on-demand |
| Lakebase project | `pdu-monitoring-dev` | ACTIVE |
| Databricks App | `pdu-monitor-max-duganknight` | RUNNING |
| App URL | `https://pdu-monitor-max-duganknight-7474647295259694.aws.databricksapps.com` | |
| Breach alert | `2733671080397185` | UNPAUSED |
| Technician alert | `2548923072300097` | UNPAUSED |

---

## 3. Job Execution Log — `pdu-refresh` (job 493670388364531)

Schedule: `0 0/5 * * * ?` UTC (every 5 minutes), queue disabled.
Last 5 runs at time of capture:

| Run ID | Result | Start (UTC) | Duration |
| --- | --- | --- | --- |
| 1042465469345754 | RUNNING | 2026-11-05 22:10:01 | in progress |
| 649755172617157 | SUCCESS | 2026-11-05 22:05:01 | 4m 15s |
| 633696267954807 | SUCCESS | 2026-11-05 22:00:02 | 4m 21s |
| 841312779129727 | SUCCESS | 2026-11-05 21:55:01 | 4m 11s |
| 723967023032196 | SUCCESS | 2026-11-05 21:50:01 | 4m 20s |

### Task breakdown — run 649755172617157 (most recent complete run)

| Task | Result | Start (UTC) | End (UTC) | Duration |
| --- | --- | --- | --- | --- |
| generate_telemetry | SUCCESS | 22:05:01 | 22:05:57 | 56s |
| update_pipeline | SUCCESS | 22:05:57 | 22:07:30 | 93s |
| sync_lakebase | SUCCESS | 22:07:30 | 22:08:35 | 65s |
| sync_ops_lakehouse | SUCCESS | 22:08:35 | 22:09:15 | 40s |

All four tasks in the chain succeeded. `sync_ops_lakehouse` is the new reverse-ETL step
(Lakebase Postgres → UC Delta ops_history tables) that was debugged and fixed during this build.

---

## 4. SDP Pipeline — Latest Updates

Pipeline `pdu_monitoring` (ID `9927fd76-18d2-4b9b-8ebb-933a1cc71ccc`):

| Update ID | State | Created (UTC) |
| --- | --- | --- |
| f9b489b3-2662-4f27-90a2-c4e83ce9975b | WAITING_FOR_RESOURCES | 2026-11-05T22:11:02 |
| 7e7cf25a-89b0-40fa-92ac-d7542e266425 | COMPLETED | 2026-11-05T22:05:59 |
| 9a4c98b2-23cc-4d9c-af2e-a258c401300a | COMPLETED | 2026-11-05T22:01:00 |

Pipeline state at capture time: RUNNING (continuous triggered mode, update every 5 min).

---

## 5. Live Query Results

All queries run on `mdk_demo_catalog` at 2026-11-05 22:10:59 UTC.

### 5a. pdu_thresholds — threshold rules seeded from CSV

```
scope_type | scope_value | metric      | breach_min | warn_min | warn_max | breach_max | description
-----------+-------------+-------------+------------+----------+----------+------------+------------------------------------------------------------
GLOBAL     | (null)      | temperature | (null)     | (null)   | 45       | 55         | PDU inlet temperature: warn above 45 C; breach above 55 C
GLOBAL     | (null)      | voltage     | 220        | 228      | 252      | 260        | 240 V nominal: warn outside +/-5%; breach outside 220-260 V
MODEL      | PDU-HD-32A  | temperature | (null)     | (null)   | 50       | 60         | High-density PDUs are rated for higher inlet temperature
RACK       | R02         | voltage     | 222        | 230      | 250      | 258        | Example rack override: R02 feeder has tighter voltage tolerance
UNIT       | R03-S5-P4   | temperature | (null)     | (null)   | 43       | 46         | Demo hot unit runs ~48 C; lowered breach threshold so it reliably shows BREACH
```

5 rows. GLOBAL → MODEL → RACK → UNIT precedence chain working correctly.

### 5b. pdu_latest_status — fleet summary (100 units)

```
status | units | breached_unit_ids
-------+-------+---------------------------
BREACH | 2     | [R03-S5-P4, R04-S5-P3]
OK     | 96    | []
WARN   | 2     | []
```

Total: 100 units (4 racks × 5 shelves × 5 positions). Two units in active breach.

### 5c. pdu_latest_status — R03-S5-P4 detail (demo breach unit)

```
unit_id                   : R03-S5-P4
rack / shelf / position   : R03 / 5 / 4
model                     : PDU-STD-24A
status                    : BREACH
temperature_max (last min): 49.09 C
temperature_warn_max      : 43 C   (scope: UNIT:R03-S5-P4)
temperature_breach_max    : 46 C   (scope: UNIT:R03-S5-P4)
voltage_min / max         : 236.21 / 239.33 V
voltage_warn_min / max    : 228 / 252 V   (scope: GLOBAL)
breach_started_ts         : 2026-11-04T22:03:00 UTC
breach_minutes_lookback   : 1441 min  (~24 h continuous breach)
severity_score            : 2.03
last_event_ts             : 2026-11-05T22:03:59 UTC
updated_at                : 2026-11-05T22:07:22 UTC
is_stale                  : false
```

Unit exceeds the UNIT-scoped breach threshold (49.09 C > 46 C). Threshold scope resolution
confirmed: unit-level row in `pdu_thresholds` overrides the global 55 C limit.

### 5d. bronze_pdu_telemetry — raw telemetry scale

```
total_rows     : 60,444,000
distinct_units : 100
oldest_event   : 2026-10-29T22:10:22 UTC
newest_event   : 2026-11-05T22:10:21 UTC
query_ts       : 2026-11-05T22:10:59 UTC
```

60.4 M second-level readings, 7-day rolling window (7-day retention DELETE in each generator run),
100 units, newest reading 38 seconds before query — pipeline is current.

### 5e. ops_history.technician_alerts — operator actions synced to Lakehouse

```
alert_id | unit_id   | breach_started_ts            | alerted_by                           | alerted_at                   | note
---------+-----------+------------------------------+--------------------------------------+------------------------------+-------------------------------
2        | R03-S5-P4 | 2026-11-03T20:13:00 UTC      | max.duganknight@databricks.com       | 2026-11-04T20:21:17 UTC      | unit running way too hot. investigate
1        | R03-S5-P4 | 2026-11-03T16:53:00 UTC      | max.duganknight@databricks.com       | 2026-11-04T16:59:08 UTC      | persistent temp breach. investigate urgently
```

2 rows. Written by the app to Lakebase (`pdu_app.technician_alerts`), then synced to
`mdk_demo_catalog.ops_history.technician_alerts` (Delta + CDF) by the `sync_ops_lakehouse`
notebook task. Downstream SQL alert emails the technician on each new row.

### 5f. ops_history.unit_notes — troubleshooting notes synced to Lakehouse

```
note_id | unit_id   | author                         | created_at                   | note
--------+-----------+--------------------------------+------------------------------+---------------------------
2       | R01-S1-P4 | max.duganknight@databricks.com | 2026-11-04T15:59:28 UTC      | voltage drop issue. Monitoring
```

1 row. Written from the unit troubleshooting page in the app.

---

## 6. Databricks App Status

From `databricks apps get pdu-monitor-max-duganknight --output JSON`:

```json
{
  "name": "pdu-monitor-max-duganknight",
  "url": "https://pdu-monitor-max-duganknight-7474647295259694.aws.databricksapps.com",
  "app_status": { "state": "RUNNING", "message": "App has status: App is running" },
  "compute_status": { "state": "ACTIVE", "message": "App compute is running." },
  "active_deployment": {
    "deployment_id": "01f1d86a730c1b96ad6edeb89d2282db",
    "status": { "state": "SUCCEEDED", "message": "App started successfully" },
    "source_code_path": "/Workspace/Users/max.duganknight@databricks.com/databricks-demos-clone/demos/pdu-monitoring/src/app",
    "create_time": "2026-11-04T16:11:53Z",
    "update_time": "2026-11-04T16:12:00Z",
    "creator": "max.duganknight@databricks.com"
  },
  "resources": [
    { "name": "lakebase",     "postgres":      { "permission": "CAN_CONNECT_AND_CREATE" } },
    { "name": "sql-warehouse","sql_warehouse": { "id": "1f421abc4c14022f", "permission": "CAN_USE" } },
    { "name": "bronze-table", "uc_securable":  { "securable_full_name": "mdk_demo_catalog.pdu_monitoring.bronze_pdu_telemetry", "permission": "SELECT" } }
  ],
  "service_principal_client_id": "79ca3314-4072-4d3a-9629-2e96bbbcd487",
  "compute_size": "MEDIUM",
  "create_time": "2026-10-26T18:23:50Z"
}
```

App is source-linked to the Git folder. Three resource bindings: Lakebase (psycopg),
SQL warehouse (bronze drill-down), and the bronze Delta table (read-only).

---

## 7. Alert Configuration

| Alert | ID | State | Schedule | Recipient |
| --- | --- | --- | --- | --- |
| PDU breach | 2733671080397185 | UNPAUSED | `0 2/5 * * * ?` UTC | max.duganknight@databricks.com |
| PDU technician alert | 2548923072300097 | UNPAUSED | `0 2/5 * * * ?` UTC | max.duganknight@databricks.com |

Both alerts were received by the author during this build session, confirming end-to-end
delivery. Custom markdown email bodies include a direct link to the app.

---

## 8. End-to-End Demo Trace

The following sequence was executed live and produced the `ops_history.technician_alerts` rows above:

1. `pdu_thresholds_seed.csv` updated — added UNIT scope row for R03-S5-P4
   (breach_max lowered from 55 to 46 C to reliably trigger BREACH at the unit's ~48 C operating temperature)
2. Next `pdu-refresh` run picked up the new CSV → `pdu_thresholds` MV recomputed →
   `pdu_latest_status` MV recomputed → R03-S5-P4 status changed to BREACH
3. Lakebase SNAPSHOT sync pushed new status to `pdu_latest_status_synced` in Postgres
4. Databricks App auto-refreshed (30 s interval) → monitoring grid showed R03-S5-P4 as pulsing red tile
5. Breach alert evaluated → email received: subject "PDU breach detected — action required"
   with clickable link to the app
6. Operator navigated to `/unit/R03-S5-P4` in the app → clicked **Alert technician** →
   wrote note "persistent temp breach. investigate urgently" → submitted
7. App wrote row to `pdu_app.technician_alerts` in Lakebase (Postgres)
8. Next `sync_ops_lakehouse` notebook task ran → row appeared in
   `mdk_demo_catalog.ops_history.technician_alerts` (Delta + CDF)
9. Technician SQL alert evaluated → email received: subject
   "PDU technician alert — operator has flagged a breach for your attention"
   with clickable link back to the app

All query results in section 5 reflect the live state after this sequence completed.

---

## 9. Predictive Maintenance — Training and Batch Inference (2026-11-06)

Captured 2026-11-06 UTC on branch `predictive-maintenance`. Goal: rank PDUs by risk of a
*sustained* breach (at least 5 minute-average minutes outside the unit's breach limits) in the
next 12 hours, scored every 12 hours (00:00 and 12:00 UTC), so technicians can act before the breach.

```
pdu_minute_stats (21 days, wear model) ──► Feature Views features pm_* (UC, point-in-time)
   │                                              │
   └─► label spine (unit x 12 h) ──► predictive_maintenance_training ──► UC model pdu_breach_risk_model@champion
                                                                               │
                       score_breach_risk (latest 12 h boundary) ◄──────────────┘
                              └─► pdu_breach_risk_predictions (Delta + CDF) ──► App /risk page (SQL warehouse)
```

### 9a. Training history rebuild — `pdu-history-rebuild` (job 567654351682110)

| Run ID | Result | Start (UTC) | End (UTC) | Duration |
| --- | --- | --- | --- | --- |
| 441400920570845 | SUCCESS | 2026-11-06 16:21:15 | 16:27:27 | 6m 12s |

Tasks `rebuild_bronze`, `full_refresh_pipeline` and `sync_lakebase` all SUCCESS. Resulting data:

```
table                 | first_ts             | last_ts              | rows        | units
----------------------+----------------------+----------------------+-------------+------
bronze_pdu_telemetry  | 2026-10-16T16:23:57Z | 2026-11-06T16:23:56Z | 181,337,400 | 100
pdu_minute_stats      | 2026-10-16T16:23:00Z | 2026-11-06T16:21:00Z |   3,022,190 | 100
pdu_latest_status     | 2026-11-06T16:21:59Z | 2026-11-06T16:21:59Z |         100 | 100
```

Independent warehouse check of the wear signal (12 h windows, excluding the chronic hot unit
R03-S5-P4): 4,158 windows, 667 with a sustained breach (16%; 613 temperature-driven).
Units about to start a new breach had warmed by +1.27 C over the previous 12 h, versus -0.49 C for units that stayed healthy.

### 9b. Features — Feature Views in Unity Catalog

27 features registered as `mdk_demo_catalog.pdu_monitoring.pm_*` over `pdu_minute_stats`
(1 h / 6 h / 24 h / 72 h windows: temperature / current / voltage averages, max, min, population std dev,
sag / hot / sample minute counts). Sum / Avg / Count / StddevPop use `RollingWindow`; Min / Max
use a `SlidingWindow` that slides hourly. Not materialized: `create_training_set` recomputes them
point-in-time for both training and scoring.

Point-in-time spot check (unit R04-S2-P3, scoring time 2026-11-01 12:00 UTC):

```
feature       | create_training_set | direct SQL on pdu_minute_stats (window ending at scoring time)
--------------+---------------------+---------------------------------------------
temp_avg_1h   | 35.878              | 35.878
temp_max_6h   | 52.33               | 52.33
volt_min_6h   | 226.82              | 226.82
rows at/after scoring time used: 0
```

### 9c. Label spine and out-of-time split

42 scoring times x 100 units = 4,200 rows (41 with a complete 12 h label window); 17.2% positive.
254 rows already in a sustained breach at scoring time were excluded; the first 72 h are burn-in.

| Split | Scoring times (UTC) | Rows | Positives | Positive rate |
| --- | --- | --- | --- | --- |
| train | 2026-10-20 00:00 to 2026-10-29 00:00 | 1,764 | 241 | 13.7% |
| validation | 2026-10-29 12:00 to 2026-11-02 00:00 | 755 | 118 | 15.6% |
| holdout | 2026-11-02 12:00 to 2026-11-06 00:00 | 760 | 89 | 11.7% |

### 9d. Experiment grid — MLflow experiment `/Users/max.duganknight@databricks.com/pdu_predictive_maintenance` (3418253093978685)

Final grid (parent run `68e31598cdfe4b73948e484b7ca64988`, started 2026-11-06 16:44:45 UTC), validation metrics:

| Feature list | Model | Val PR-AUC | Val ROC-AUC | Val P@10 | Run ID |
| --- | --- | --- | --- | --- | --- |
| trend_volatility | logistic_regression | **0.536** | 0.820 | 0.56 | baf7a860ca49420ab4daef1de96b7d71 |
| trend | logistic_regression | 0.513 | 0.818 | 0.58 | 4fd111ae961746ec98c331000a1dbad2 |
| current_state | logistic_regression | 0.503 | 0.804 | 0.58 | a3ef96e780414004991bf798db55cb81 |
| rule baseline (temp headroom) | - | 0.488 | 0.789 | 0.56 | 4bf22274b07545bd9c81c1ef58857278 |
| trend_volatility | random_forest | 0.479 | 0.794 | 0.53 | 6c4bdb0acb2f43b4b5c076a52f08ebaf |
| trend | random_forest | 0.479 | 0.791 | 0.55 | 80b3dfd8f87743eaa8cfc6cc535c2b93 |
| trend_volatility | lightgbm | 0.459 | 0.784 | 0.49 | 2533c260a57748d98c93587a5e28c41c |
| trend | lightgbm | 0.458 | 0.788 | 0.48 | a635d8d245d045708ab775926096f26a |
| current_state | lightgbm | 0.447 | 0.791 | 0.49 | 562ab6f17e8d4a49867a970c2ec57476 |
| current_state | random_forest | 0.438 | 0.789 | 0.54 | 3cf5803000dc4f4899fafa25dff1dbee |

An earlier grid (parent `1325846e5868410ca815bb7472524a3e`) used deeper trees; random forest and
LightGBM scored below the rule baseline there (best 0.454), so they were regularized (validation-only tuning, holdout untouched).

Top drivers of the selected model (permutation importance, drop in validation PR-AUC):

```
temp_headroom_1h         0.2274
temp_warn_headroom_1h    0.2274
temp_avg_1h              0.1492
temp_trend_1h_vs_6h      0.1145
current_std_6h           0.0633
temp_max_1h              0.0424
current_std_24h          0.0405
sample_minutes_6h        0.0385
```

### 9e. Holdout evaluation and registration

Champion run `b89afe262c4f4d1488735cfe933390f0` (`champion__trend_volatility__logistic_regression`,
2026-11-06 16:47:24 UTC): refit on train + validation, evaluated once on holdout.

| Metric | Champion | Same config, train only | Rule baseline |
| --- | --- | --- | --- |
| PR-AUC | 0.373 | 0.369 | 0.341 |
| ROC-AUC | 0.780 | 0.773 | 0.769 |
| Precision@10 per shift | 0.41 | 0.44 | 0.43 |
| Brier | 0.181 | 0.177 | - |

Registered `mdk_demo_catalog.pdu_monitoring.pdu_breach_risk_model` **version 1**, status READY,
alias `champion` (verified via `GET /api/2.1/unity-catalog/models/.../aliases/champion`).

The model ranks units better than the rule overall, but at the top-10-per-shift cut-off it is on par with the rule.
Scores are not calibrated (class-balanced training), so the app shows them as a ranking.

### 9f. Batch inference — `src/notebooks/score_breach_risk`

Scoring time 2026-11-06 12:00 UTC, model v1 (`trend_volatility`), written 2026-11-06 17:19:52 UTC to
`mdk_demo_catalog.pdu_monitoring.pdu_breach_risk_predictions` (Delta + CDF, PK `unit_id, scoring_ts`,
idempotent per scoring time). 100 rows: 10 HIGH, 15 ELEVATED, 69 LOW, 6 IN_BREACH.

```
rank | unit_id   | band      | score | temp_1h C | headroom C | trend 1h vs 6h C
-----+-----------+-----------+-------+-----------+------------+-----------------
-    | R02-S3-P2 | IN_BREACH | 0.998 | 61.0      | -6.0       | +1.32
-    | R01-S5-P2 | IN_BREACH | 0.985 | 59.5      | -4.5       | -0.58
-    | R03-S5-P4 | IN_BREACH | 0.845 | 51.7      | -5.7       | +0.27
-    | R02-S5-P1 | IN_BREACH | 0.213 | 34.9      | 20.1       | -1.66
-    | R03-S3-P5 | IN_BREACH | 0.193 | 36.9      | 18.1       | -1.51
-    | R03-S2-P4 | IN_BREACH | 0.075 | 33.3      | 21.7       | -1.66
1    | R01-S1-P4 | HIGH      | 0.968 | 53.5      | 1.5        | -1.22
2    | R01-S3-P4 | HIGH      | 0.934 | 51.7      | 3.3        | -0.76
3    | R03-S2-P2 | HIGH      | 0.805 | 38.7      | 16.3       | -3.79
4    | R01-S3-P1 | HIGH      | 0.663 | 39.2      | 15.8       | -0.76
5    | R02-S2-P5 | HIGH      | 0.631 | 38.7      | 16.3       | -0.76
6    | R02-S3-P3 | HIGH      | 0.620 | 38.0      | 17.0       | -0.76
7    | R02-S3-P5 | HIGH      | 0.599 | 37.0      | 18.0       | -0.76
8    | R02-S3-P4 | HIGH      | 0.583 | 37.4      | 17.6       | -0.76
9    | R03-S5-P2 | HIGH      | 0.582 | 39.2      | 15.8       | -0.76
10   | R02-S2-P1 | HIGH      | 0.581 | 38.8      | 16.2       | -0.76
```

IN_BREACH units with positive temperature headroom are in a voltage breach. Feature check for
R01-S1-P4: scored `temp_avg_1h` 53.4548 / `temp_max_6h` 55.8 equal the direct SQL over
`pdu_minute_stats` for 11:00-12:00 / 06:00-12:00 UTC.

Outcome so far (telemetry observed to 2026-11-06 20:58 UTC, about 9 of the 12 h horizon; not final):

| Band | Units | Sustained breach so far | Rate |
| --- | --- | --- | --- |
| IN_BREACH | 6 | 3 | 0.50 |
| HIGH | 10 | 0 | 0.00 |
| ELEVATED | 15 | 3 | 0.20 |
| LOW | 69 | 4 | 0.06 |

So far this single batch has not shown the HIGH band catching breaches. One shift is a very small
sample (holdout precision@10 averaged 0.41 across 8 shifts), so it needs re-checking once the window closes at 2026-11-07 00:00 UTC.

### 9g. App — Breach risk page

Deployment `01f1da07bcc710abbe4522d15e3c852d` of `pdu-monitor-max-duganknight` (2026-11-06 17:30 UTC):
state SUCCEEDED, "App started successfully". Adds `/risk` (navbar "Breach risk"), which reads the
latest batch from the SQL warehouse (cached 5 min), filters by band and links each unit to its
troubleshooting page. App service principal `79ca3314-4072-4d3a-9629-2e96bbbcd487` holds SELECT on
`pdu_breach_risk_predictions` (verified in `information_schema.table_privileges`). The page's query
returns 100 rows on the warehouse.
