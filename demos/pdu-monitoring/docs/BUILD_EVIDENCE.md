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

Databricks App (Dash) serves two pages:
- `/` — monitoring grid, KPIs, worst-offenders (Lakebase only, no warehouse)
- `/unit/<id>` — second-level bronze charts + "Alert technician" button

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
