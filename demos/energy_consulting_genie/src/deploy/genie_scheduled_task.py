# Databricks notebook source
"""
Scheduled Genie task — the demo's monitoring beat (replaces the SQL alert).

On a schedule, this task asks the Scenario Strategy Genie space a
monitoring question via the Conversation API, reads Genie's answer + the SQL it
ran, and decides whether a scenario has swung materially (NPV move beyond the
guardrail). When it has, the consultant is pointed at Genie One to ask the
follow-ups — the demo's opening beat.

Why a Genie task (not a SQL alert): the watch itself runs THROUGH Genie, so the
monitoring question, the governed SQL, and the follow-up investigation are all
the same conversational surface. The task persists the run into
{catalog}.{schema}.genie_watch_log so the outcome is queryable + auditable.

The DAB runs this on a weekly schedule (see databricks.yml jobs schedule). It is
NOT gated by the setup job's other tasks — it reads the gold tables that already
exist after generate_data.

REQUIRES: databricks-sdk>=0.114.0 (environment_key: sdk_latest).

Parameters (base_parameters): catalog, schema, genie_space_id
                              (genie_space_id from the deploy_genie task value)
"""

# COMMAND ----------

# The monitoring question the scheduled task asks Genie every run. Phrased so
# Genie returns one row per scenario with the vintage-over-vintage NPV move —
# the same "which scenario changed the most and why" beat the consultant asks,
# run on a cadence.
WATCH_QUESTION = (
    "Which scenario projection changed the most since the earliest model vintage, "
    "and by what percent? Return the scenario name and the percent NPV change."
)
# Guardrail: flag when any scenario's NPV moved more than this (percent, signed).
THRESHOLD_PCT = -30.0

# COMMAND ----------

dbutils.widgets.text("catalog", "", "Catalog")
dbutils.widgets.text("schema", "", "Schema")
dbutils.widgets.text("genie_space_id", "", "Genie Space ID")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
genie_space_id = dbutils.widgets.get("genie_space_id")
assert catalog and schema and genie_space_id, "catalog + schema + genie_space_id are required"
if genie_space_id.startswith("{{") and genie_space_id.endswith("}}"):
    raise RuntimeError(f"genie_space_id={genie_space_id!r} — task value substitution didn't fire.")

print(f"Watching Genie space {genie_space_id} over {catalog}.{schema}")

# COMMAND ----------

import time
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# Ask the monitoring question, then poll the message to completion.
conv = w.genie.start_conversation(space_id=genie_space_id, content=WATCH_QUESTION)
conversation_id = conv.conversation_id
message_id = conv.message_id

TERMINAL = {"COMPLETED", "FAILED", "CANCELLED"}
deadline = time.time() + 300
status = None
while time.time() < deadline:
    msg = w.genie.get_message(space_id=genie_space_id, conversation_id=conversation_id, message_id=message_id)
    status = str(msg.status.value if hasattr(msg.status, "value") else msg.status)
    if status in TERMINAL:
        break
    time.sleep(5)

print(f"Genie message status: {status}")
if status != "COMPLETED":
    raise RuntimeError(f"Genie watch question did not complete (status={status}).")

# COMMAND ----------

# Pull Genie's answer text + the query result rows it produced.
answer_text = ""
executed_sql = ""
result_rows = []
for att in (msg.attachments or []):
    if getattr(att, "text", None) and att.text.content:
        answer_text = att.text.content
    if getattr(att, "query", None):
        executed_sql = att.query.query or ""
        res = w.genie.get_message_attachment_query_result(
            space_id=genie_space_id, conversation_id=conversation_id,
            message_id=message_id, attachment_id=att.attachment_id,
        )
        sr = res.statement_response
        if sr and sr.result and sr.result.data_array:
            result_rows = sr.result.data_array

print("Genie answer:\n", answer_text or "(no text)")
print("\nExecuted SQL:\n", executed_sql or "(none)")
print("\nResult rows:", result_rows)

# COMMAND ----------

# Decide whether a scenario swung beyond the guardrail. Parse the largest
# negative percent move out of the returned rows (defensive: the answer shape
# is Genie-generated, so scan every numeric cell for the min value).
def _to_float(x):
    try:
        return float(str(x).replace("%", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None

worst_pct = None
worst_scenario = None
for row in result_rows:
    nums = [(_to_float(c), c) for c in row]
    nums = [(v, c) for v, c in nums if v is not None]
    labels = [c for c in row if _to_float(c) is None]
    if not nums:
        continue
    row_min = min(nums, key=lambda t: t[0])[0]
    if worst_pct is None or row_min < worst_pct:
        worst_pct = row_min
        worst_scenario = labels[0] if labels else None

triggered = worst_pct is not None and worst_pct <= THRESHOLD_PCT
print(f"\nWorst move: {worst_scenario} = {worst_pct} (threshold {THRESHOLD_PCT}) -> triggered={triggered}")

# COMMAND ----------

# Persist the run to an auditable watch log — one row per scheduled run.
from pyspark.sql import functions as F

log_df = spark.createDataFrame(
    [(genie_space_id, WATCH_QUESTION, answer_text, executed_sql,
      worst_scenario, worst_pct, THRESHOLD_PCT, bool(triggered))],
    "genie_space_id string, question string, answer_text string, executed_sql string, "
    "worst_scenario string, worst_change_pct double, threshold_pct double, triggered boolean",
).withColumn("run_at", F.current_timestamp())

(log_df.write.mode("append").option("mergeSchema", "true")
   .saveAsTable(f"{catalog}.{schema}.genie_watch_log"))
spark.sql(
    f"COMMENT ON TABLE {catalog}.{schema}.genie_watch_log IS "
    f"'Scheduled Genie monitoring runs: the watch question, Genie''s answer + SQL, the worst scenario NPV move, and whether it breached the guardrail. One row per run.'"
)
print(f"Logged run to {catalog}.{schema}.genie_watch_log")

# COMMAND ----------

if triggered:
    print(
        f"\n*** SCENARIO SHIFT DETECTED *** {worst_scenario} moved {worst_pct}% "
        f"(guardrail {THRESHOLD_PCT}%). Open the 'Scenario Strategy' Genie space "
        f"and ask: Which scenario changed the most and why? Then: Summarize the analyst rationale "
        f"for the Accelerated Transition revision."
    )
else:
    print("\nNo scenario breached the guardrail this run.")
