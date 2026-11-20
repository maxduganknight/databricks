-- pdu_recent_readings: second-level readings per PDU for the last hour (silver view).
--
-- The app's unit troubleshooting charts read this view instead of bronze. It is a plain Unity
-- Catalog view: nothing is stored or refreshed, so it is as fresh as bronze, and the app needs
-- SELECT on this view only (bronze access is resolved through the view owner).
--
-- Transformations: keep only the columns the unit page charts, null implausible readings (sensor
-- faults) and limit to the last ${pdu.recent_readings_minutes} minutes. Bronze is already one row
-- per unit per second, so no aggregation. The plausible ranges below must match
-- PLAUSIBLE_RANGES in utilities/pdu_rules.py (used by pdu_minute_stats).

CREATE VIEW pdu_recent_readings
COMMENT 'Second-level PDU readings from the last ${pdu.recent_readings_minutes} minutes (silver view over bronze) for unit troubleshooting. Implausible voltage / temperature readings are nulled.'
AS SELECT
  unit_id,
  event_ts,
  CASE WHEN voltage_v BETWEEN 50.0 AND 400.0 THEN voltage_v END AS voltage_v,
  CASE WHEN temperature_c BETWEEN -20.0 AND 120.0 THEN temperature_c END AS temperature_c,
  current_a,
  power_kw
FROM ${pdu.bronze_table}
WHERE event_ts >= current_timestamp() - INTERVAL ${pdu.recent_readings_minutes} MINUTES;
