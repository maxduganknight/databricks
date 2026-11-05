"""Genie API wrapper for the PDU monitoring app.

Sends questions to the 'PDU Monitoring and Telemetry Insights' Genie agent and
returns (conversation_id, answer_text, table_records_or_None, columns_or_None).

The space is read from DATABRICKS_GENIE_SPACE_ID, which is injected by the
bundle from the `genie-space` resource binding in resources/app.yml.
"""

import logging
import os
import time
from typing import Optional

import pandas as pd
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.dashboards import MessageStatus

log = logging.getLogger(__name__)

GENIE_SPACE_ID: str = os.getenv("DATABRICKS_GENIE_SPACE_ID", "")
_POLL_INTERVAL_S = 2
_TIMEOUT_S = 120
_MAX_TABLE_ROWS = 25


def _wait_for_message(w: WorkspaceClient, conversation_id: str, message_id: str):
    """Poll Genie until the message reaches a terminal state."""
    deadline = time.monotonic() + _TIMEOUT_S
    while time.monotonic() < deadline:
        msg = w.genie.get_message(
            space_id=GENIE_SPACE_ID,
            conversation_id=conversation_id,
            message_id=message_id,
        )
        if msg.status in (MessageStatus.COMPLETED, MessageStatus.FAILED, MessageStatus.CANCELLED):
            return msg
        time.sleep(_POLL_INTERVAL_S)
    raise TimeoutError(f"Genie did not respond within {_TIMEOUT_S}s")


def _fetch_query_result(
    w: WorkspaceClient, conversation_id: str, message_id: str, att
) -> Optional[pd.DataFrame]:
    """Fetch tabular results for a query attachment; returns None on failure."""
    try:
        qr = w.genie.get_message_attachment_query_result(
            space_id=GENIE_SPACE_ID,
            conversation_id=conversation_id,
            message_id=message_id,
            attachment_id=att.id,
        )
        stmt = getattr(qr, "statement_response", None)
        if not stmt:
            return None
        result = getattr(stmt, "result", None)
        manifest = getattr(stmt, "manifest", None)
        if not result or not manifest:
            return None
        cols = [c.name for c in manifest.schema.columns]
        rows = result.data_array or []
        return pd.DataFrame(rows, columns=cols)
    except Exception as exc:  # noqa: BLE001
        log.warning("Failed to fetch Genie query result: %s", exc)
        return None


def ask(
    question: str, conversation_id: Optional[str] = None
) -> tuple[str, str, Optional[list], Optional[list]]:
    """Send a natural-language question to the Genie agent.

    Args:
        question: Question about PDU telemetry.
        conversation_id: Continue an existing conversation, or None to start a new one.

    Returns:
        (conversation_id, answer_text, table_records_or_None, column_names_or_None)
        Table records are capped at _MAX_TABLE_ROWS rows with all values as strings
        so they are safe to store in dcc.Store.
    """
    if not GENIE_SPACE_ID:
        raise EnvironmentError(
            "DATABRICKS_GENIE_SPACE_ID is not set — check the genie-space resource binding."
        )

    w = WorkspaceClient()

    if conversation_id:
        msg_init = w.genie.create_message(
            space_id=GENIE_SPACE_ID,
            conversation_id=conversation_id,
            content=question,
        )
        message_id = msg_init.id
    else:
        resp = w.genie.start_conversation(
            space_id=GENIE_SPACE_ID,
            content=question,
        )
        conversation_id = resp.conversation_id
        message_id = resp.message.id

    msg = _wait_for_message(w, conversation_id, message_id)

    if msg.status == MessageStatus.FAILED:
        return conversation_id, "Genie could not answer that question. Try rephrasing.", None, None
    if msg.status == MessageStatus.CANCELLED:
        return conversation_id, "The request was cancelled.", None, None

    text = ""
    records = None
    columns = None

    for att in msg.attachments or []:
        text_att = getattr(att, "text", None)
        query_att = getattr(att, "query", None)

        if text_att and getattr(text_att, "content", ""):
            text = text_att.content
        elif query_att:
            # Use the description as the answer text if no separate text attachment
            if not text:
                text = getattr(query_att, "description", "") or ""
            # Fetch tabular results (first query attachment only)
            if records is None:
                df = _fetch_query_result(w, conversation_id, msg.id, att)
                if df is not None:
                    columns = list(df.columns)
                    records = df.head(_MAX_TABLE_ROWS).astype(str).to_dict("records")

    return conversation_id, text or "No answer returned.", records, columns
