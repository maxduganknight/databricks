"""Genie API wrapper for the PDU monitoring app.

Uses the app service principal (injected via DATABRICKS_CLIENT_ID /
DATABRICKS_CLIENT_SECRET env vars) to query the Genie space.  The SP must have
CAN_RUN on the space, which is granted by the genie_space resource binding in
resources/app.yml.

All calls are synchronous and poll until the message reaches a terminal state.
The caller bears the thread cost, which is fine for Dash's threaded server model.
"""

import logging
import os
import time
from typing import Optional

from databricks.sdk import WorkspaceClient

log = logging.getLogger(__name__)

SPACE_ID: str = os.getenv("DATABRICKS_GENIE_SPACE_ID", "")
_POLL_INTERVAL_S = 1.5
_TIMEOUT_S = 120  # 2-minute hard cap per message
_TERMINAL = {"COMPLETED", "FAILED", "CANCELLED", "QUERY_RESULT_EXPIRED"}


def _status(msg) -> str:
    st = msg.status
    return st.value if hasattr(st, "value") else str(st)


def _poll(space_id: str, conversation_id: str, message_id: str):
    """Poll get_message until terminal or timeout; returns GenieMessage or None."""
    w = WorkspaceClient()
    deadline = time.monotonic() + _TIMEOUT_S
    while time.monotonic() < deadline:
        msg = w.genie.get_message(
            space_id=space_id,
            conversation_id=conversation_id,
            message_id=message_id,
        )
        if _status(msg) in _TERMINAL:
            return msg
        time.sleep(_POLL_INTERVAL_S)
    return None


def _extract(msg, conversation_id: str) -> dict:
    """Turn a completed GenieMessage into a plain dict the UI can render."""
    if msg is None:
        return {"error": "Request timed out after 2 minutes.", "conversation_id": conversation_id}

    st = _status(msg)
    if st != "COMPLETED":
        err = None
        if hasattr(msg, "error") and msg.error:
            err = getattr(msg.error, "message", str(msg.error))
        return {"error": err or f"Genie returned status: {st}", "conversation_id": conversation_id}

    texts, sql_blocks = [], []
    for att in msg.attachments or []:
        if getattr(att, "text", None) and getattr(att.text, "content", None):
            texts.append(att.text.content)
        if getattr(att, "query", None) and getattr(att.query, "query", None):
            sql_blocks.append(att.query.query)

    return {
        "text": "\n\n".join(texts) or "(no explanation provided)",
        "sql": sql_blocks,
        "conversation_id": conversation_id,
    }


def ask(question: str) -> dict:
    """Start a new Genie conversation with *question*.

    Returns a dict with keys: text, sql (list), conversation_id, error (optional).
    """
    if not SPACE_ID:
        return {
            "error": "DATABRICKS_GENIE_SPACE_ID is not configured. "
                     "Deploy the app via the bundle to inject the resource binding.",
            "conversation_id": None,
        }
    try:
        w = WorkspaceClient()
        resp = w.genie.start_conversation(space_id=SPACE_ID, content=question)
        msg = _poll(SPACE_ID, resp.conversation_id, resp.message_id)
        return _extract(msg, resp.conversation_id)
    except Exception as exc:  # noqa: BLE001
        log.exception("genie.ask failed")
        return {"error": f"{type(exc).__name__}: {exc}", "conversation_id": None}


def follow_up(conversation_id: str, question: str) -> dict:
    """Send a follow-up message in an existing Genie conversation.

    Returns the same shape as ask().
    """
    if not SPACE_ID:
        return {"error": "DATABRICKS_GENIE_SPACE_ID is not configured.", "conversation_id": conversation_id}
    try:
        w = WorkspaceClient()
        sent = w.genie.create_message(
            space_id=SPACE_ID,
            conversation_id=conversation_id,
            content=question,
        )
        msg = _poll(SPACE_ID, conversation_id, sent.id)
        return _extract(msg, conversation_id)
    except Exception as exc:  # noqa: BLE001
        log.exception("genie.follow_up failed")
        return {"error": f"{type(exc).__name__}: {exc}", "conversation_id": conversation_id}
