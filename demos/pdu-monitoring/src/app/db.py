"""Lakebase (Postgres) access for the app, authenticated as the app's service principal.

The platform injects PGHOST / PGDATABASE / PGUSER / PGPORT / PGSSLMODE for the app's Lakebase
resource; LAKEBASE_ENDPOINT is declared via valueFrom. A fresh OAuth credential is minted for every
new physical connection, and connections are recycled before the 1-hour token expiry.
"""

import logging
import os
from functools import lru_cache

import psycopg
from databricks.sdk import WorkspaceClient
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

log = logging.getLogger(__name__)

SYNCED_SCHEMA = os.getenv("LB_SYNCED_SCHEMA", "pdu_monitoring")
SYNCED_TABLE = os.getenv("LB_SYNCED_TABLE", "pdu_latest_status_synced")
APP_SCHEMA = os.getenv("LB_APP_SCHEMA", "pdu_app")


@lru_cache(maxsize=1)
def workspace() -> WorkspaceClient:
    return WorkspaceClient()


class _TokenConnection(psycopg.Connection):
    """psycopg connection that injects a freshly minted Lakebase credential at connect time."""

    @classmethod
    def connect(cls, conninfo: str = "", **kwargs):
        kwargs["password"] = workspace().postgres.generate_database_credential(
            endpoint=os.environ["LAKEBASE_ENDPOINT"]
        ).token
        return super().connect(conninfo, **kwargs)


@lru_cache(maxsize=1)
def pool() -> ConnectionPool:
    p = ConnectionPool(
        conninfo="",
        connection_class=_TokenConnection,
        kwargs={
            "host": os.environ["PGHOST"],
            "port": int(os.getenv("PGPORT", "5432")),
            "dbname": os.environ["PGDATABASE"],
            "user": os.environ["PGUSER"],
            "sslmode": os.getenv("PGSSLMODE", "require"),
            "application_name": os.getenv("PGAPPNAME", "pdu-monitor"),
            "row_factory": dict_row,
        },
        min_size=1,
        max_size=5,
        max_lifetime=2700,  # recycle 15 min before the 1 h token expiry
        max_idle=600,
        check=ConnectionPool.check_connection,  # survive scale-to-zero restarts
        open=False,
    )
    p.open(wait=False)
    return p


def fetch_all(query, params=None) -> list:
    with pool().connection() as conn:
        return conn.execute(query, params).fetchall()


def execute(query, params=None) -> None:
    with pool().connection() as conn:
        conn.execute(query, params)
