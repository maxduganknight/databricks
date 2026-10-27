-- 001: operator state owned by the app (written from the UI, never synced from the lakehouse).
-- Applied once by src/notebooks/lakebase_migrate (tracked in pdu_app.schema_migrations).

CREATE SCHEMA IF NOT EXISTS pdu_app;

-- One row per acknowledgement. breach_started_ts ties the ack to a specific breach episode,
-- so a NEW breach on the same unit is shown as unacknowledged again.
CREATE TABLE IF NOT EXISTS pdu_app.incident_ack (
    ack_id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    unit_id           TEXT        NOT NULL,
    breach_started_ts TIMESTAMPTZ,
    acknowledged_by   TEXT        NOT NULL,
    acknowledged_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    note              TEXT        CHECK (note IS NULL OR length(note) <= 4000)
);
CREATE INDEX IF NOT EXISTS incident_ack_unit_idx
    ON pdu_app.incident_ack (unit_id, acknowledged_at DESC);

-- Free-form troubleshooting notes per unit.
CREATE TABLE IF NOT EXISTS pdu_app.unit_notes (
    note_id    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    unit_id    TEXT        NOT NULL,
    author     TEXT        NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    note       TEXT        NOT NULL CHECK (length(note) BETWEEN 1 AND 4000)
);
CREATE INDEX IF NOT EXISTS unit_notes_unit_idx
    ON pdu_app.unit_notes (unit_id, created_at DESC);
