-- 002: replace incident_ack with action-oriented technician_alerts.
-- Applied once by src/notebooks/lakebase_migrate (tracked in pdu_app.schema_migrations).
-- incident_ack is kept but no longer written to; it can be dropped once its history is no longer needed.

-- One row per "Alert Technician" action. breach_started_ts ties the alert to a specific breach
-- episode so a new breach on the same unit is again shown as unalerted.
CREATE TABLE IF NOT EXISTS pdu_app.technician_alerts (
    alert_id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    unit_id           TEXT        NOT NULL,
    breach_started_ts TIMESTAMPTZ,
    alerted_by        TEXT        NOT NULL,
    alerted_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    note              TEXT        CHECK (note IS NULL OR length(note) <= 4000)
);
CREATE INDEX IF NOT EXISTS technician_alerts_unit_idx
    ON pdu_app.technician_alerts (unit_id, alerted_at DESC);
