"""Data access for the app.

* Lakebase (cheap, polled): synced pdu_latest_status + operator-state tables (acks, notes).
* SQL warehouse (on demand only): second-level bronze for ONE unit over a short window, cached.

All access uses the app's service principal. Identifiers come from env vars set by the bundle and are
validated; all values are bound as query parameters.
"""

import logging
import os
import re
import threading
import time
from typing import Callable, Optional

import pandas as pd
from psycopg import sql

import db

log = logging.getLogger(__name__)

BRONZE_TABLE = os.getenv("BRONZE_TABLE", "")
WAREHOUSE_ID = os.getenv("DATABRICKS_WAREHOUSE_ID", "")
STATUS_TTL_S = int(os.getenv("STATUS_CACHE_SECONDS", "10"))
BRONZE_TTL_S = int(os.getenv("BRONZE_CACHE_SECONDS", "60"))
# Pipeline runs every 5 min and lags ~2-3 min behind bronze, so anything older than this is stale.
STALE_AFTER_MIN = int(os.getenv("STALE_AFTER_MINUTES", "15"))
ALLOWED_WINDOWS_MIN = (15, 30, 60, 120)
# Physical rack layout shown on the monitoring page (shelves x positions per rack).
RACK_SHELVES = int(os.getenv("RACK_SHELVES", "5"))
RACK_POSITIONS = int(os.getenv("RACK_POSITIONS", "5"))
MAX_NOTE_CHARS = 4000

UNIT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_TABLE_RE = re.compile(r"^[A-Za-z0-9_]+\.[A-Za-z0-9_]+\.[A-Za-z0-9_]+$")
_IDENT_RE = re.compile(r"^[A-Za-z0-9_]+$")

for _name, _val in (("LB_SYNCED_SCHEMA", db.SYNCED_SCHEMA), ("LB_SYNCED_TABLE", db.SYNCED_TABLE), ("LB_APP_SCHEMA", db.APP_SCHEMA)):
    if not _IDENT_RE.match(_val):
        raise ValueError(f"Invalid identifier in {_name}: {_val!r}")


def valid_unit_id(unit_id: str) -> bool:
    return bool(unit_id) and bool(UNIT_ID_RE.match(unit_id))


# --------------------------------------------------------------------------- tiny TTL cache
class TTLCache:
    def __init__(self, max_items: int = 256):
        self._data: dict = {}
        self._lock = threading.Lock()
        self._max = max_items

    def get_or_load(self, key, ttl_s: float, loader: Callable):
        now = time.monotonic()
        with self._lock:
            hit = self._data.get(key)
            if hit and now - hit[0] < ttl_s:
                return hit[1], hit[0]
        value = loader()
        with self._lock:
            if len(self._data) >= self._max:
                self._data.pop(next(iter(self._data)))
            self._data[key] = (time.monotonic(), value)
        return value, time.monotonic()

    def clear(self):
        with self._lock:
            self._data.clear()


_cache = TTLCache()


# --------------------------------------------------------------------------- Lakebase reads
_STATUS_SQL = sql.SQL(
    """
    SELECT s.*,
           a.acknowledged_by AS ack_by, a.acknowledged_at AS ack_at, a.note AS ack_note,
           (s.status = 'BREACH' AND a.ack_id IS NULL) AS unacked_breach
    FROM {synced} s
    LEFT JOIN LATERAL (
        SELECT ack_id, acknowledged_by, acknowledged_at, note
        FROM {acks} x
        WHERE x.unit_id = s.unit_id
          AND x.breach_started_ts IS NOT DISTINCT FROM s.breach_started_ts
        ORDER BY x.acknowledged_at DESC
        LIMIT 1
    ) a ON s.status = 'BREACH'
    ORDER BY s.rack_id, s.shelf DESC, s.position
    """
).format(
    synced=sql.Identifier(db.SYNCED_SCHEMA, db.SYNCED_TABLE),
    acks=sql.Identifier(db.APP_SCHEMA, "incident_ack"),
)


def _load_status() -> pd.DataFrame:
    df = pd.DataFrame(db.fetch_all(_STATUS_SQL))
    if not df.empty:
        # The pipeline's is_stale is evaluated when the status was computed; also treat a unit as stale
        # when its newest reading is old *now* (e.g. the pipeline or the sync stopped running).
        cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(minutes=STALE_AFTER_MIN)
        last = pd.to_datetime(df["last_event_ts"], utc=True)
        df["is_stale"] = df["is_stale"].fillna(False).astype(bool) | last.isna() | (last < cutoff)
    return df


def latest_status() -> pd.DataFrame:
    """All units with status + current-breach acknowledgement (cached a few seconds across sessions)."""
    df, _ = _cache.get_or_load("status", STATUS_TTL_S, _load_status)
    return df


def split_by_layout(df: pd.DataFrame):
    """(units inside the configured rack layout, unit_ids outside it - e.g. slots retired by a layout change)."""
    inside = (df["shelf"] <= RACK_SHELVES) & (df["position"] <= RACK_POSITIONS)
    return df[inside], sorted(df.loc[~inside, "unit_id"].tolist())


def unit_status(unit_id: str) -> Optional[dict]:
    df = latest_status()
    if df.empty:
        return None
    row = df[df["unit_id"] == unit_id]
    return None if row.empty else row.iloc[0].to_dict()


def racks() -> list:
    df = latest_status()
    return sorted(df["rack_id"].dropna().unique().tolist()) if not df.empty else []


def acks(unit_id: str, limit: int = 10) -> list:
    q = sql.SQL(
        "SELECT acknowledged_by, acknowledged_at, breach_started_ts, note FROM {} "
        "WHERE unit_id = %s ORDER BY acknowledged_at DESC LIMIT %s"
    ).format(sql.Identifier(db.APP_SCHEMA, "incident_ack"))
    return db.fetch_all(q, (unit_id, limit))


def notes(unit_id: str, limit: int = 20) -> list:
    q = sql.SQL(
        "SELECT author, created_at, note FROM {} WHERE unit_id = %s ORDER BY created_at DESC LIMIT %s"
    ).format(sql.Identifier(db.APP_SCHEMA, "unit_notes"))
    return db.fetch_all(q, (unit_id, limit))


# --------------------------------------------------------------------------- Lakebase writes
def add_ack(unit_id: str, breach_started_ts, acknowledged_by: str, note: Optional[str]) -> None:
    if not valid_unit_id(unit_id):
        raise ValueError("invalid unit id")
    note = (note or "").strip()[:MAX_NOTE_CHARS] or None
    q = sql.SQL(
        "INSERT INTO {} (unit_id, breach_started_ts, acknowledged_by, note) VALUES (%s, %s, %s, %s)"
    ).format(sql.Identifier(db.APP_SCHEMA, "incident_ack"))
    db.execute(q, (unit_id, breach_started_ts, acknowledged_by, note))
    _cache.clear()  # status view shows the ack immediately


def add_note(unit_id: str, author: str, note: str) -> None:
    if not valid_unit_id(unit_id):
        raise ValueError("invalid unit id")
    note = (note or "").strip()[:MAX_NOTE_CHARS]
    if not note:
        raise ValueError("Note is empty")
    q = sql.SQL("INSERT INTO {} (unit_id, author, note) VALUES (%s, %s, %s)").format(
        sql.Identifier(db.APP_SCHEMA, "unit_notes")
    )
    db.execute(q, (unit_id, author, note))


# --------------------------------------------------------------------------- bronze via SQL warehouse
def _warehouse_connection():
    from databricks import sql as dbsql
    from databricks.sdk.core import Config

    cfg = Config()  # app service principal (DATABRICKS_CLIENT_ID / SECRET injected by the platform)
    return dbsql.connect(
        server_hostname=cfg.host.replace("https://", "").rstrip("/"),
        http_path=f"/sql/1.0/warehouses/{WAREHOUSE_ID}",
        credentials_provider=lambda: cfg.authenticate,
    )


def _query_bronze(unit_id: str, minutes: int) -> pd.DataFrame:
    if not _TABLE_RE.match(BRONZE_TABLE):
        raise ValueError(f"Invalid BRONZE_TABLE: {BRONZE_TABLE!r}")
    query = (
        "SELECT event_ts, voltage_v, temperature_c, current_a, power_kw "
        f"FROM {BRONZE_TABLE} "
        "WHERE unit_id = :unit_id "
        "AND event_ts >= timestampadd(MINUTE, -CAST(:minutes AS INT), current_timestamp()) "
        "ORDER BY event_ts"
    )
    t0 = time.monotonic()
    with _warehouse_connection() as conn, conn.cursor() as cur:
        cur.execute(query, {"unit_id": unit_id, "minutes": int(minutes)})
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
    log.info("bronze query unit=%s minutes=%s rows=%s %.1fs", unit_id, minutes, len(rows), time.monotonic() - t0)
    df = pd.DataFrame([tuple(r) for r in rows], columns=cols)
    if not df.empty:
        df["event_ts"] = pd.to_datetime(df["event_ts"], utc=True)
    return df


def bronze_window(unit_id: str, minutes: int):
    """Second-level telemetry for one unit. Returns (DataFrame, cache_age_seconds)."""
    if not valid_unit_id(unit_id):
        raise ValueError("invalid unit id")
    minutes = minutes if minutes in ALLOWED_WINDOWS_MIN else 30
    df, loaded_at = _cache.get_or_load(("bronze", unit_id, minutes), BRONZE_TTL_S, lambda: _query_bronze(unit_id, minutes))
    return df, time.monotonic() - loaded_at
