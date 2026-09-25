# Databricks notebook source
"""
RevOps — Revenue Intelligence synthetic data generator (Spark-native).

Mirrors specifications/01-lakeflow.md. Simple-demo build: NO SDP — this script
builds every table inline via databricks-connect Spark, then the sem_* governed
views + metric_net_new_arr + feat_monthly_nnarr + predict_net_new_arr() UC SQL
function. Hero storyline values are hardcoded (driver-side contract series) for
exactness; scale tables (opportunities, spend, reps) are Spark-generated.

Target: solution_builder.demo_revops_intelligence
Runtime: pre-provisioned databricks-connect serverless venv. Python 3.12.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta

from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.window import Window

IN_NOTEBOOK = "dbutils" in dir()
if IN_NOTEBOOK:
    dbutils.widgets.text("catalog", "", "Catalog")
    dbutils.widgets.text("schema", "", "Schema")
    CATALOG = dbutils.widgets.get("catalog")
    SCHEMA = dbutils.widgets.get("schema")
else:
    CATALOG = os.environ.get("DEMO_CATALOG", "solution_builder")
    SCHEMA = os.environ.get("DEMO_SCHEMA", "demo_revops_intelligence")
assert CATALOG and SCHEMA, "catalog + schema required"

# Time frozen — this demo references specific fiscal months.
NOW = date(2026, 6, 30)
NOW_STR = NOW.strftime("%Y-%m-%d")

print(f"Target: {CATALOG}.{SCHEMA}  NOW={NOW_STR}")

try:
    spark  # noqa: F821
except NameError:
    # Local run (not a Databricks notebook/job): fall back to databricks-connect.
    from databricks.connect import DatabricksSession
    spark = DatabricksSession.builder.profile(
        os.environ.get("DATABRICKS_CONFIG_PROFILE", "DEFAULT")
    ).serverless(True).getOrCreate()
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")


def _save(df: DataFrame, table: str, comment: str = "") -> None:
    fqn = f"{CATALOG}.{SCHEMA}.{table}"
    df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(fqn)
    if comment:
        spark.sql(f"COMMENT ON TABLE {fqn} IS :c", args={"c": comment})
    print(f"  ✓ {table:22s} rows={spark.table(fqn).count():>9,}")


def _colcomments(table: str, cols: dict[str, str]) -> None:
    for col, txt in cols.items():
        spark.sql(
            f"COMMENT ON COLUMN `{CATALOG}`.`{SCHEMA}`.`{table}`.`{col}` IS :t",
            args={"t": txt},
        )


def _pick(idx_col: F.Column, pool: list[str]) -> F.Column:
    arr = F.array(*[F.lit(s) for s in pool])
    return F.element_at(arr, (F.pmod(idx_col, F.lit(len(pool))) + 1).cast("int"))


# ── Segments & month grid ───────────────────────────────────────────────────
SEGMENTS = [
    ("SEG-ENT", "Enterprise", "Field"),
    ("SEG-MM", "Mid-Market", "Inside"),
    ("SEG-SMB", "SMB", "Inside"),
    ("SEG-STARTUP", "Startup", "Self-serve"),
]
SEG_NAME = {s[0]: s[1] for s in SEGMENTS}
REGIONS = ["NA", "EMEA", "APAC"]

# 14 month-starts: 2025-05 → 2026-06
MONTHS = []
y, m = 2025, 5
for _ in range(14):
    MONTHS.append(date(y, m, 1))
    m += 1
    if m > 12:
        m, y = 1, y + 1

# ── A. DIMENSION TABLES ─────────────────────────────────────────────────────
print("Dimensions…")

# dim_segment
dim_segment = spark.createDataFrame(
    [(sid, sname, motion, True) for sid, sname, motion in SEGMENTS],
    "segment_id string, segment_name string, motion string, is_active boolean",
)
_save(dim_segment, "dim_segment", "Customer segments (Enterprise/Mid-Market/SMB/Startup) and their GTM motion.")
_colcomments("dim_segment", {
    "segment_id": "Segment PK (SEG-ENT/SEG-MM/SEG-SMB/SEG-STARTUP).",
    "segment_name": "Display name: Enterprise, Mid-Market, SMB, Startup.",
    "motion": "GTM motion: Field / Inside / Self-serve.",
    "is_active": "Whether the segment is active.",
})

# dim_calendar — daily
cal = (
    spark.sql(f"SELECT explode(sequence(DATE'2025-05-01', DATE'{NOW_STR}', INTERVAL 1 DAY)) AS date")
    .withColumn("date_key", F.date_format("date", "yyyyMMdd").cast("int"))
    .withColumn("year", F.year("date"))
    .withColumn("quarter", F.concat(F.year("date"), F.lit("-Q"), F.quarter("date")))
    .withColumn("month", F.month("date"))
    .withColumn("month_start", F.trunc("date", "month"))
    .withColumn("fiscal_period", F.date_format("date", "yyyy-MM"))
    .withColumn("is_month_end", F.col("date") == F.last_day("date"))
    .select("date_key", "date", "year", "quarter", "month", "month_start", "fiscal_period", "is_month_end")
)
_save(cal, "dim_calendar", "Daily calendar 2025-05-01 → 2026-06-30 with fiscal quarter/month attributes.")

# dim_account — 60 accounts, segment mix; heroes ACCT0010/0012/0049 Enterprise
# Segment assignment by id band; heroes forced Enterprise + APAC/EMEA.
HERO_IDS = {10: ("APAC", 3_920_000), 12: ("APAC", 3_460_000), 49: ("EMEA", 4_238_000)}
N_ACCT = 60


def _seg_for(i: int) -> str:
    if i in HERO_IDS:
        return "SEG-ENT"
    r = i % 10
    if r < 2:
        return "SEG-ENT"
    if r < 6:
        return "SEG-MM"
    if r < 8:
        return "SEG-SMB"
    return "SEG-STARTUP"


acct_rows = []
INDUSTRIES = ["Manufacturing", "Healthcare", "Retail", "Technology", "Financial Services", "Logistics"]
PLAN_TIER = {"SEG-ENT": "Enterprise", "SEG-MM": "Business", "SEG-SMB": "Growth", "SEG-STARTUP": "Growth"}
for i in range(1, N_ACCT + 1):
    seg = _seg_for(i)
    if i in HERO_IDS:
        region = HERO_IDS[i][0]
    else:
        region = REGIONS[i % 3]
    acct_rows.append((
        f"ACCT{i:04d}", f"Account {i:03d} ({region})", region, seg,
        INDUSTRIES[i % len(INDUSTRIES)], PLAN_TIER[seg],
        (date(2023, 1, 1) + timedelta(days=(i * 37) % 900)).strftime("%Y-%m-%d"), True,
    ))
dim_account = spark.createDataFrame(
    acct_rows,
    "account_id string, account_name string, region string, segment_id string, "
    "industry string, plan_tier string, contract_start_date string, is_active boolean",
)
_save(dim_account, "dim_account", "Customer accounts (~60). ACCT0010/0012/0049 are the at-risk strategic Enterprise accounts.")
_colcomments("dim_account", {
    "account_id": "Account PK (ACCTNNNN).",
    "account_name": "Account display name incl. region.",
    "region": "Region: NA / EMEA / APAC.",
    "segment_id": "FK to dim_segment.",
    "industry": "Account industry vertical.",
    "plan_tier": "Subscription plan tier: Growth / Business / Enterprise.",
    "contract_start_date": "Original contract start date.",
    "is_active": "Whether the account is active.",
})

# dim_product — ~12 core platform modules
PRODUCTS = [
    ("MOD-001", "Purchasing", "Core", 1200.0, False),
    ("MOD-002", "Approvals", "Core", 900.0, False),
    ("MOD-003", "Expense Mgmt", "Core", 1100.0, False),
    ("MOD-004", "Spend Analytics", "Insights", 1500.0, True),
    ("MOD-005", "AP Automation", "Payments", 1800.0, True),
    ("MOD-006", "Budgets", "Core", 800.0, False),
    ("MOD-007", "Punchout", "Integrations", 700.0, True),
    ("MOD-008", "Corporate Cards", "Payments", 2000.0, True),
    ("MOD-009", "Vendor Mgmt", "Core", 950.0, False),
    ("MOD-010", "Receiving", "Core", 600.0, False),
    ("MOD-011", "Real-Time Budget Approvals", "Insights", 1600.0, True),
    ("MOD-012", "Reporting API", "Integrations", 500.0, True),
]
dim_product = spark.createDataFrame(
    PRODUCTS, "product_id string, product_name string, product_line string, list_price_usd double, is_addon boolean")
_save(dim_product, "dim_product", "Product modules and list prices.")

# dim_channel — 10 GTM channels
CHANNELS = [
    ("CH-001", "Paid Search", "Inbound", "SEG-MM"),
    ("CH-002", "Content/SEO", "Inbound", "SEG-SMB"),
    ("CH-003", "Events", "Outbound", "SEG-ENT"),
    ("CH-004", "Outbound/SDR", "Outbound", "SEG-MM"),
    ("CH-005", "Partner", "Partner", "SEG-ENT"),
    ("CH-006", "Referral", "Inbound", "SEG-STARTUP"),
    ("CH-007", "Webinar", "Inbound", "SEG-MM"),
    ("CH-008", "Review Sites", "Inbound", "SEG-SMB"),
    ("CH-009", "Social", "Inbound", "SEG-STARTUP"),
    ("CH-010", "ABM", "Outbound", "SEG-ENT"),
]
dim_channel = spark.createDataFrame(
    CHANNELS, "channel_id string, channel_name string, channel_type string, segment_id string")
_save(dim_channel, "dim_channel", "GTM lead-source channels and primary segment served.")

# dim_stage — 7 pipeline stages
STAGES = [
    ("ST-1", "Prospect", 1, False, False),
    ("ST-2", "Discovery", 2, False, False),
    ("ST-3", "Demo", 3, False, False),
    ("ST-4", "Proposal", 4, False, False),
    ("ST-5", "Negotiation", 5, False, False),
    ("ST-6", "Closed Won", 6, True, True),
    ("ST-7", "Closed Lost", 7, True, False),
]
dim_stage = spark.createDataFrame(
    STAGES, "stage_id string, stage_name string, stage_order int, is_closed boolean, is_won boolean")
_save(dim_stage, "dim_stage", "Pipeline stages Prospect → Closed Won/Lost.")

# dim_rep — 120 reps
TEAMS = ["New Business", "Expansion", "Renewals"]
ROLE_BY_TEAM = {"New Business": "AE", "Expansion": "AM", "Renewals": "CSM"}
rep_rows = []
for i in range(1, 121):
    seg = SEGMENTS[i % 4][0]
    team = TEAMS[i % 3]
    rep_rows.append((
        f"REP-{i:04d}", f"Rep {i:03d}", ROLE_BY_TEAM[team], team, seg,
        REGIONS[i % 3], float(120_000 + (i % 5) * 20_000),
        (date(2021, 1, 1) + timedelta(days=(i * 53) % 1500)).strftime("%Y-%m-%d"), True,
    ))
dim_rep = spark.createDataFrame(
    rep_rows,
    "rep_id string, rep_name string, role string, team string, segment_id string, "
    "region string, quota_usd double, hire_date string, is_active boolean")
_save(dim_rep, "dim_rep", "Sales/CS reps with team, segment, quota.")

# ── B1. fact_arr_movement — driver-side segment×month contract series ───────
print("fact_arr_movement…")

# Mid-Market contract: (expansion, churn+contraction combined). starting=22.0M,
# new=1.0M flat. Months 2025-05..2026-06. Values land NRR 108.0% → 90.1%.
MM_EXP_CC = {
    "2025-05": (2.30, 0.40), "2025-06": (2.28, 0.41), "2025-07": (2.25, 0.42),
    "2025-08": (2.23, 0.43), "2025-09": (2.20, 0.44), "2025-10": (2.05, 0.55),
    "2025-11": (1.85, 0.72), "2025-12": (1.60, 0.95), "2026-01": (1.35, 1.25),
    "2026-02": (1.15, 1.55), "2026-03": (0.98, 1.90), "2026-04": (0.85, 2.25),
    "2026-05": (0.75, 2.55), "2026-06": (0.68, 2.85),
}
# Other segments: flat healthy. (starting, new, exp, cc) in $M.
SEG_BASE = {
    "SEG-ENT": (45.0, 1.5, 9.1, 1.0),      # NRR ~118%
    "SEG-SMB": (8.0, 0.4, 0.82, 0.50),      # NRR ~104%
    "SEG-STARTUP": (3.0, 0.5, 0.23, 0.20),  # NRR ~101%
}

M = 1_000_000.0
arr_contract = []  # (segment_id, period_str, starting, new, expansion, contraction(neg), churned(neg))
for mth in MONTHS:
    ms = mth.strftime("%Y-%m")
    # Mid-Market
    exp, cc = MM_EXP_CC[ms]
    arr_contract.append(("SEG-MM", ms, 22.0 * M, 1.0 * M, exp * M, -(cc * 0.6) * M, -(cc * 0.4) * M))
    # Others (tiny deterministic wobble so lines aren't dead-flat)
    for seg, (st, nw, ex, cc2) in SEG_BASE.items():
        wob = 1.0 + 0.02 * ((mth.month % 3) - 1)
        arr_contract.append((seg, ms, st * M, nw * M, ex * wob * M, -(cc2 * 0.6) * M, -(cc2 * 0.4) * M))

contract_df = spark.createDataFrame(
    arr_contract,
    "segment_id string, period_str string, starting_arr_usd double, new_arr_usd double, "
    "expansion_arr_usd double, contraction_arr_usd double, churned_arr_usd double",
).withColumn("period_month", F.to_date("period_str", "yyyy-MM"))

# Account weights per segment (normalized to sum=1 within segment) so segment
# aggregation of the split reproduces the contract exactly.
acct_w = (
    dim_account.select("account_id", "segment_id", "region")
    .withColumn("w_raw", F.lit(1.0) + (F.abs(F.hash("account_id")) % F.lit(100)) / F.lit(100.0))
    .withColumn("w_sum", F.sum("w_raw").over(Window.partitionBy("segment_id")))
    .withColumn("w", F.col("w_raw") / F.col("w_sum"))
    .select("account_id", "segment_id", "region", "w")
)

fact_arr = (
    contract_df.alias("c")
    .join(acct_w.alias("a"), "segment_id")
    .select(
        F.concat_ws("-", F.lit("ARRM"), F.col("a.account_id"), F.date_format("c.period_month", "yyyyMM")).alias("movement_id"),
        F.col("segment_id"), F.col("a.account_id").alias("account_id"), F.col("c.period_month").alias("period_month"),
        (F.col("c.starting_arr_usd") * F.col("a.w")).alias("starting_arr_usd"),
        (F.col("c.new_arr_usd") * F.col("a.w")).alias("new_arr_usd"),
        (F.col("c.expansion_arr_usd") * F.col("a.w")).alias("expansion_arr_usd"),
        (F.col("c.contraction_arr_usd") * F.col("a.w")).alias("contraction_arr_usd"),
        (F.col("c.churned_arr_usd") * F.col("a.w")).alias("churned_arr_usd"),
        F.col("a.region").alias("region"),
    )
    .withColumn("ending_arr_usd", F.col("starting_arr_usd") + F.col("new_arr_usd")
                + F.col("expansion_arr_usd") + F.col("contraction_arr_usd") + F.col("churned_arr_usd"))
)
_save(fact_arr, "fact_arr_movement",
      "Monthly ARR waterfall per account. new/expansion POSITIVE; contraction/churned NEGATIVE.")
_colcomments("fact_arr_movement", {
    "movement_id": "Row id.",
    "segment_id": "FK to dim_segment.",
    "account_id": "FK to dim_account.",
    "period_month": "Month start (DATE).",
    "starting_arr_usd": "ARR at start of month.",
    "new_arr_usd": "New-logo ARR added (POSITIVE).",
    "expansion_arr_usd": "Expansion/upsell ARR (POSITIVE).",
    "contraction_arr_usd": "Contraction/downgrade ARR (NEGATIVE).",
    "churned_arr_usd": "Churned/lost ARR (NEGATIVE).",
    "ending_arr_usd": "ARR at end of month = starting+new+expansion+contraction+churned.",
    "region": "Account region.",
})

# ── B2. fact_subscription — current subscription per account ────────────────
print("fact_subscription…")
# Hero rows (contract aggregates from storyline 2).
HEROES = {
    "ACCT0012": ("APAC", 27, 38, 47, 1_557_000, 3_920_000),
    "ACCT0049": ("EMEA", 34, 42, 51, 1_484_000, 3_460_000),
    "ACCT0010": ("APAC", 31, 41, 63, 2_408_000, 4_238_000),
}
hero_rows = []
for aid, (rgn, hs, up, dtr, atr, arr) in HEROES.items():
    hero_rows.append((
        f"SUB-{aid}", aid, "SEG-ENT", rgn, float(arr),
        (NOW + timedelta(days=dtr)).strftime("%Y-%m-%d"), hs, up, 18, True, float(atr),
    ))
hero_df = spark.createDataFrame(
    hero_rows,
    "subscription_id string, account_id string, segment_id string, region string, arr_usd double, "
    "renewal_date string, health_score int, product_usage_pct int, support_tickets_90d int, "
    "is_at_risk boolean, at_risk_arr_usd double")

# Healthy rows for every other account.
other_df = (
    dim_account.filter(~F.col("account_id").isin(list(HEROES.keys())))
    .withColumn("_h", F.abs(F.hash("account_id")))
    .withColumn("subscription_id", F.concat(F.lit("SUB-"), F.col("account_id")))
    .withColumn("arr_usd", F.when(F.col("segment_id") == "SEG-ENT", 2_500_000 + (F.col("_h") % 1_500_000))
                .when(F.col("segment_id") == "SEG-MM", 300_000 + (F.col("_h") % 400_000))
                .when(F.col("segment_id") == "SEG-SMB", 60_000 + (F.col("_h") % 80_000))
                .otherwise(30_000 + (F.col("_h") % 40_000)).cast("double"))
    .withColumn("renewal_date", F.date_format(F.date_add(F.lit(NOW_STR), (30 + (F.col("_h") % 300)).cast("int")), "yyyy-MM-dd"))
    .withColumn("health_score", (65 + (F.col("_h") % 31)).cast("int"))
    .withColumn("product_usage_pct", (70 + (F.col("_h") % 26)).cast("int"))
    .withColumn("support_tickets_90d", (F.col("_h") % 6).cast("int"))
    .withColumn("is_at_risk", F.lit(False))
    .withColumn("at_risk_arr_usd", F.lit(0.0))
    .select("subscription_id", "account_id", "segment_id", "region", "arr_usd",
            "renewal_date", "health_score", "product_usage_pct", "support_tickets_90d",
            "is_at_risk", "at_risk_arr_usd")
)
fact_sub = hero_df.unionByName(other_df)
_save(fact_sub, "fact_subscription", "Current subscription per account with health/usage/renewal/at-risk.")
_colcomments("fact_subscription", {
    "subscription_id": "Subscription PK.",
    "account_id": "FK to dim_account.",
    "segment_id": "FK to dim_segment.",
    "region": "Account region.",
    "arr_usd": "Annual recurring revenue for this subscription (USD).",
    "renewal_date": "Contract renewal date.",
    "health_score": "Account health 0–100 (lower = worse).",
    "product_usage_pct": "Product usage 0–100.",
    "support_tickets_90d": "Support tickets in last 90 days.",
    "is_at_risk": "TRUE when health < 45 AND renewal within 90 days.",
    "at_risk_arr_usd": "ARR at risk (0 if not at risk).",
})

# ── B3. fact_opportunity — ~4000 pipeline opps ──────────────────────────────
print("fact_opportunity…")
acct_lk = F.broadcast(dim_account.select("account_id", "segment_id", "region"))
rep_ids = [r[0] for r in rep_rows]
chan_ids = [c[0] for c in CHANNELS]
stage_ids = [s[0] for s in STAGES]
acct_ids = [f"ACCT{i:04d}" for i in range(1, N_ACCT + 1)]

opp = (
    spark.range(0, 4000, numPartitions=8)
    .withColumn("_h", F.abs(F.hash("id")))
    .withColumn("account_id", _pick(F.col("_h"), acct_ids))
    .join(acct_lk, "account_id")
    .withColumn("rep_id", _pick(F.col("_h") + F.lit(1), rep_ids))
    .withColumn("channel_id", _pick(F.col("_h") + F.lit(2), chan_ids))
    .withColumn("_rstage", F.rand(seed=11))
    # win probability lower for Mid-Market (storyline: attainment lags)
    .withColumn("_wp", F.when(F.col("segment_id") == "SEG-MM", F.lit(0.38))
                .when(F.col("segment_id") == "SEG-ENT", F.lit(0.52))
                .otherwise(F.lit(0.46)))
    .withColumn("_r_close", F.rand(seed=12))
    .withColumn("is_closed", F.col("_r_close") < 0.7)
    .withColumn("is_won", F.col("is_closed") & (F.rand(seed=13) < F.col("_wp")))
    .withColumn("stage_id", F.when(~F.col("is_closed"), _pick(F.col("_h"), stage_ids[:5]))
                .when(F.col("is_won"), F.lit("ST-6")).otherwise(F.lit("ST-7")))
    .withColumn("_days_ago", (F.rand(seed=14) * 400 + 10).cast("int"))
    .withColumn("created_date", F.date_format(F.date_sub(F.lit(NOW_STR), F.col("_days_ago") + F.lit(30)), "yyyy-MM-dd"))
    .withColumn("close_date", F.when(F.col("is_closed"),
                F.date_format(F.date_sub(F.lit(NOW_STR), F.col("_days_ago")), "yyyy-MM-dd")).otherwise(None))
    .withColumn("amount_usd", F.when(F.col("segment_id") == "SEG-ENT", 80_000 + (F.col("_h") % 200_000))
                .when(F.col("segment_id") == "SEG-MM", 20_000 + (F.col("_h") % 60_000))
                .when(F.col("segment_id") == "SEG-SMB", 8_000 + (F.col("_h") % 20_000))
                .otherwise(5_000 + (F.col("_h") % 12_000)).cast("double"))
    .withColumn("opp_id", F.concat(F.lit("OPP-"), F.date_format("created_date", "yyyyMMdd"),
                F.lit("-"), F.lpad(F.col("id").cast("string"), 4, "0")))
    .select("opp_id", "account_id", "rep_id", "segment_id", "region", "stage_id",
            "channel_id", "created_date", "close_date", "amount_usd", "is_won", "is_closed")
)
_save(opp, "fact_opportunity", "Pipeline opportunities driving win rate / pipeline coverage.")

# ── B4. fact_gtm_spend — ~5000 spend line items ─────────────────────────────
print("fact_gtm_spend…")
CATS = ["Paid Media", "Events", "Content", "SDR/Outbound", "Partner", "Tooling"]
gtm = (
    spark.range(0, 5000, numPartitions=8)
    .withColumn("_h", F.abs(F.hash("id")))
    .withColumn("channel_id", _pick(F.col("_h"), chan_ids))
    .join(F.broadcast(dim_channel.select("channel_id", "segment_id")), "channel_id")
    .withColumn("region", _pick(F.col("_h") + F.lit(3), REGIONS))
    .withColumn("category", _pick(F.col("_h") + F.lit(1), CATS))
    .withColumn("_days_ago", (F.rand(seed=21) * 420).cast("int"))
    .withColumn("spend_date", F.date_sub(F.lit(NOW_STR), F.col("_days_ago")))
    .withColumn("_base", (2_000 + (F.col("_h") % 18_000)).cast("double"))
    # Q2 2026 (Apr–Jun) overrun concentrated in MM + ENT demand-gen
    .withColumn("_q2", (F.year("spend_date") == 2026) & (F.month("spend_date").between(4, 6)))
    .withColumn("amount_usd", F.when(F.col("_q2") & F.col("segment_id").isin("SEG-MM", "SEG-ENT"),
                F.col("_base") * 1.35).otherwise(F.col("_base")))
    .withColumn("attributed_pipeline_usd", F.col("amount_usd") * (2.0 + F.rand(seed=22) * 3.0))
    .withColumn("spend_id", F.concat(F.lit("SPD-"), F.lpad(F.col("id").cast("string"), 5, "0")))
    .withColumn("spend_date", F.date_format("spend_date", "yyyy-MM-dd"))
    .select("spend_id", "channel_id", "segment_id", "region", "spend_date",
            "category", "amount_usd", "attributed_pipeline_usd")
)
_save(gtm, "fact_gtm_spend", "Sales & marketing spend line items; Q2 2026 MM/ENT demand-gen runs over plan.")

# ── B5. fact_rep_attainment — rep × month ───────────────────────────────────
print("fact_rep_attainment…")
month_df = spark.createDataFrame([(m.strftime("%Y-%m-%d"),) for m in MONTHS], "period_str string") \
    .withColumn("period_month", F.to_date("period_str"))
rep_df = dim_rep.select("rep_id", "segment_id", "team", "quota_usd")
rep_att = (
    rep_df.crossJoin(month_df.select("period_month"))
    .withColumn("_h", F.abs(F.hash("rep_id", F.date_format("period_month", "yyyyMM"))))
    # Mid-Market attainment lags (~0.85), others healthy (~1.0–1.1)
    .withColumn("_att", F.when(F.col("segment_id") == "SEG-MM", 0.78 + (F.col("_h") % 15) / 100.0)
                .otherwise(0.98 + (F.col("_h") % 18) / 100.0))
    .withColumn("quota_usd", F.col("quota_usd") / F.lit(12.0))
    .withColumn("bookings_usd", F.col("quota_usd") * F.col("_att"))
    .withColumn("attainment_pct", F.col("_att") * 100.0)
    .withColumn("pipeline_coverage_x", F.when(F.col("segment_id") == "SEG-MM", 2.1 + (F.col("_h") % 8) / 10.0)
                .otherwise(3.2 + (F.col("_h") % 12) / 10.0))
    .withColumn("attainment_id", F.concat(F.lit("ATT-"), F.col("rep_id"), F.lit("-"), F.date_format("period_month", "yyyyMM")))
    .select("attainment_id", "rep_id", "segment_id", "team", "period_month",
            "bookings_usd", "quota_usd", "attainment_pct", "pipeline_coverage_x")
)
_save(rep_att, "fact_rep_attainment", "Monthly rep attainment snapshot; Mid-Market lags plan.")

# ── B6. fact_sync_exception — ~200 rows, unmatched $50.1k last 90 days ──────
print("fact_sync_exception…")
# 6 deterministic unmatched closed-won rows summing to $50,100.
UNMATCHED = [12_400, 9_800, 8_600, 7_900, 6_200, 5_200]  # = 50,100
unm_rows = []
for i, amt in enumerate(UNMATCHED):
    bd = (NOW - timedelta(days=10 + i * 12)).strftime("%Y-%m-%d")
    unm_rows.append((f"SYNC-U{i:03d}", f"OPP-UNM-{i:03d}", acct_ids[i], bd, float(amt), 0.0, False, float(amt)))
unm_df = spark.createDataFrame(
    unm_rows, "sync_id string, opp_id string, account_id string, booking_date string, "
    "crm_amount_usd double, billing_amount_usd double, is_matched boolean, mismatch_usd double")
matched_df = (
    spark.range(0, 194, numPartitions=4)
    .withColumn("_h", F.abs(F.hash("id")))
    .withColumn("sync_id", F.concat(F.lit("SYNC-M"), F.lpad(F.col("id").cast("string"), 3, "0")))
    .withColumn("opp_id", F.concat(F.lit("OPP-MAT-"), F.lpad(F.col("id").cast("string"), 3, "0")))
    .withColumn("account_id", _pick(F.col("_h"), acct_ids))
    .withColumn("booking_date", F.date_format(F.date_sub(F.lit(NOW_STR), (F.col("_h") % 90).cast("int")), "yyyy-MM-dd"))
    .withColumn("crm_amount_usd", (10_000 + (F.col("_h") % 90_000)).cast("double"))
    .withColumn("billing_amount_usd", F.col("crm_amount_usd"))
    .withColumn("is_matched", F.lit(True))
    .withColumn("mismatch_usd", F.lit(0.0))
    .select("sync_id", "opp_id", "account_id", "booking_date", "crm_amount_usd",
            "billing_amount_usd", "is_matched", "mismatch_usd")
)
_save(unm_df.unionByName(matched_df), "fact_sync_exception",
      "CRM↔billing reconciliation; unmatched closed-won bookings total $50.1k in last 90 days.")

# ── B7. fact_plan — net_new_arr / sm_spend / new_logos per segment × month ──
print("fact_plan…")
# net_new_arr plan seeded so variance = actual/plan − 1 lands storyline 3.
VAR = {  # 2026 variance targets (fraction) by segment
    "SEG-MM": {"01": -0.105, "02": -0.071, "03": -0.095, "04": -0.082, "05": -0.064, "06": -0.051},
    "SEG-ENT": {"01": 0.013, "02": 0.068, "03": 0.094, "04": 0.117, "05": 0.132, "06": 0.089},
    "SEG-SMB": {"01": -0.032, "02": -0.041, "03": -0.056, "04": -0.048, "05": -0.039, "06": -0.027},
    "SEG-STARTUP": {"01": 0.008, "02": -0.012, "03": 0.021, "04": 0.004, "05": 0.019, "06": 0.011},
}
# actual net-new ARR per segment×month from the contract series.
actual_nn = {}
for row in arr_contract:
    seg, ms, st, nw, ex, contr, chn = row
    actual_nn[(seg, ms)] = nw + ex + contr + chn

plan_rows = []
for (seg, ms), actual in actual_nn.items():
    yr, mo = ms.split("-")
    if yr == "2026" and mo in VAR[seg]:
        plan = actual / (1.0 + VAR[seg][mo])
    else:
        plan = actual  # 2025: on plan
    pm = date(int(yr), int(mo), 1).strftime("%Y-%m-%d")
    plan_rows.append((f"PLAN-{seg}-{yr}{mo}-NNA", seg, pm, "net_new_arr", float(plan)))

fact_plan_nna = spark.createDataFrame(
    plan_rows, "plan_id string, segment_id string, period_month string, metric string, plan_amount_usd double") \
    .withColumn("period_month", F.to_date("period_month"))

# sm_spend plan: from actual gtm spend aggregate; Q2 2026 plan = actual/1.12 → +12% overrun.
sm_actual = (
    gtm.withColumn("period_month", F.trunc("spend_date", "month"))
    .groupBy("segment_id", "period_month").agg(F.sum("amount_usd").alias("actual"))
    .withColumn("_q2", (F.year("period_month") == 2026) & (F.month("period_month").between(4, 6)))
    .withColumn("plan_amount_usd", F.when(F.col("_q2"), F.col("actual") / 1.12).otherwise(F.col("actual")))
    .withColumn("plan_id", F.concat(F.lit("PLAN-"), F.col("segment_id"), F.lit("-"),
                F.date_format("period_month", "yyyyMM"), F.lit("-SMS")))
    .withColumn("metric", F.lit("sm_spend"))
    .select("plan_id", "segment_id", "period_month", "metric", "plan_amount_usd")
)
# new_logos plan (from won opps count per segment/month, ×1.1 target).
nl_actual = (
    opp.filter(F.col("is_won"))
    .withColumn("period_month", F.trunc("close_date", "month"))
    .groupBy("segment_id", "period_month").agg(F.count("*").alias("won"))
    .withColumn("plan_amount_usd", (F.col("won") * 1.1).cast("double"))
    .withColumn("plan_id", F.concat(F.lit("PLAN-"), F.col("segment_id"), F.lit("-"),
                F.date_format("period_month", "yyyyMM"), F.lit("-NL")))
    .withColumn("metric", F.lit("new_logos"))
    .select("plan_id", "segment_id", "period_month", "metric", "plan_amount_usd")
)
fact_plan = fact_plan_nna.unionByName(sm_actual).unionByName(nl_actual)
_save(fact_plan, "fact_plan", "Monthly plan/quota per segment: net_new_arr, sm_spend, new_logos.")
_colcomments("fact_plan", {
    "plan_id": "Row id.",
    "segment_id": "FK to dim_segment.",
    "period_month": "Month start (DATE).",
    "metric": "Plan metric: net_new_arr | sm_spend | new_logos.",
    "plan_amount_usd": "Planned amount (USD or count for new_logos).",
})

# ── C. SEMANTIC LAYER — sem_* views + metric + feature table + function ─────
print("Semantic views…")
FQ = f"{CATALOG}.{SCHEMA}"

spark.sql(f"""
CREATE OR REPLACE VIEW {FQ}.sem_nrr_retention
COMMENT 'Net revenue retention by segment × month. Churn/contraction sign-flipped POSITIVE here; NRR excludes new business. Read nrr_rolling_pct for the headline (trailing-3-month).'
AS
WITH m AS (
  SELECT segment_id, period_month AS period,
    SUM(starting_arr_usd) AS starting_arr_usd,
    SUM(new_arr_usd) AS new_arr_usd,
    SUM(expansion_arr_usd) AS expansion_arr_usd,
    SUM(contraction_arr_usd) AS contraction_arr_usd,
    SUM(churned_arr_usd) AS churned_arr_usd,
    SUM(ending_arr_usd) AS ending_arr_usd
  FROM {FQ}.fact_arr_movement GROUP BY segment_id, period_month
),
n AS (
  SELECT m.*,
    (starting_arr_usd + expansion_arr_usd + contraction_arr_usd + churned_arr_usd) / starting_arr_usd * 100 AS nrr_pct,
    (starting_arr_usd + contraction_arr_usd + churned_arr_usd) / starting_arr_usd * 100 AS gross_retention_pct
  FROM m
)
SELECT n.segment_id, s.segment_name, n.period,
  n.starting_arr_usd, n.new_arr_usd, n.expansion_arr_usd,
  -n.contraction_arr_usd AS contraction_arr_usd,
  -n.churned_arr_usd AS churned_arr_usd,
  n.ending_arr_usd, n.nrr_pct,
  AVG(n.nrr_pct) OVER (PARTITION BY n.segment_id ORDER BY n.period ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS nrr_rolling_pct,
  n.gross_retention_pct
FROM n JOIN {FQ}.dim_segment s ON n.segment_id = s.segment_id
""")

spark.sql(f"""
CREATE OR REPLACE VIEW {FQ}.sem_account_health
COMMENT 'Account-level renewal health. is_at_risk = low health + near renewal. ACCT0010/0012/0049 are the top at-risk Enterprise accounts.'
AS
SELECT sub.account_id, a.account_name, sub.region, sub.segment_id, s.segment_name,
  sub.arr_usd, sub.health_score, sub.product_usage_pct, sub.support_tickets_90d,
  DATEDIFF(sub.renewal_date, DATE'{NOW_STR}') AS days_to_renewal,
  sub.at_risk_arr_usd, sub.is_at_risk
FROM {FQ}.fact_subscription sub
JOIN {FQ}.dim_account a ON sub.account_id = a.account_id
JOIN {FQ}.dim_segment s ON sub.segment_id = s.segment_id
""")

spark.sql(f"""
CREATE OR REPLACE VIEW {FQ}.metric_net_new_arr
COMMENT 'Actual net-new ARR by segment × month = new + expansion + contraction + churned. Single basis shared by actuals, plan, and forecast.'
AS
SELECT a.segment_id, s.segment_name, a.period_month AS period,
  SUM(a.new_arr_usd + a.expansion_arr_usd + a.contraction_arr_usd + a.churned_arr_usd) AS net_new_arr_usd
FROM {FQ}.fact_arr_movement a
JOIN {FQ}.dim_segment s ON a.segment_id = s.segment_id
GROUP BY a.segment_id, s.segment_name, a.period_month
""")

spark.sql(f"""
CREATE OR REPLACE VIEW {FQ}.sem_forecast_plan
COMMENT 'Net-new ARR actual vs plan and variance % by segment × month. Mid-Market below plan; Enterprise ahead.'
AS
SELECT mn.segment_id, mn.segment_name, mn.period,
  mn.net_new_arr_usd AS actual_nnarr_usd,
  p.plan_amount_usd AS plan_nnarr_usd,
  mn.net_new_arr_usd - p.plan_amount_usd AS variance_usd,
  (mn.net_new_arr_usd / p.plan_amount_usd - 1) * 100 AS variance_pct
FROM {FQ}.metric_net_new_arr mn
JOIN {FQ}.fact_plan p ON p.segment_id = mn.segment_id AND p.period_month = mn.period AND p.metric = 'net_new_arr'
""")

spark.sql(f"""
CREATE OR REPLACE VIEW {FQ}.sem_gtm_spend
COMMENT 'GTM efficiency by channel × category: S&M spend, attributed pipeline, new logos, CAC, magic number.'
AS
WITH sp AS (
  SELECT g.channel_id, g.category,
    SUM(g.amount_usd) AS sm_spend_usd,
    SUM(g.attributed_pipeline_usd) AS attributed_pipeline_usd
  FROM {FQ}.fact_gtm_spend g GROUP BY g.channel_id, g.category
),
won AS (
  SELECT channel_id, COUNT(*) AS opp_count,
    SUM(CASE WHEN is_won THEN 1 ELSE 0 END) AS new_logos
  FROM {FQ}.fact_opportunity GROUP BY channel_id
)
SELECT sp.channel_id, c.channel_name, c.channel_type, sp.category,
  sp.sm_spend_usd, sp.attributed_pipeline_usd,
  COALESCE(w.new_logos, 0) AS new_logos,
  sp.sm_spend_usd / NULLIF(w.new_logos, 0) AS cac_usd,
  sp.attributed_pipeline_usd / NULLIF(sp.sm_spend_usd, 0) AS magic_number,
  COALESCE(w.opp_count, 0) AS opp_count
FROM sp
JOIN {FQ}.dim_channel c ON sp.channel_id = c.channel_id
LEFT JOIN won w ON sp.channel_id = w.channel_id
""")

spark.sql(f"""
CREATE OR REPLACE VIEW {FQ}.sem_quota_attainment
COMMENT 'Quota attainment by segment × team × month with pipeline coverage and win rate. Mid-Market attainment lags.'
AS
WITH ra AS (
  SELECT segment_id, team, period_month AS period,
    SUM(bookings_usd) AS bookings_usd, SUM(quota_usd) AS quota_usd,
    AVG(pipeline_coverage_x) AS pipeline_coverage_x,
    COUNT(DISTINCT rep_id) AS rep_count
  FROM {FQ}.fact_rep_attainment GROUP BY segment_id, team, period_month
),
wr AS (
  SELECT segment_id, SUM(CASE WHEN is_won THEN 1 ELSE 0 END) / COUNT(*) * 100 AS win_rate_pct
  FROM {FQ}.fact_opportunity WHERE is_closed GROUP BY segment_id
)
SELECT ra.segment_id, s.segment_name, ra.team, ra.period,
  ra.bookings_usd, ra.quota_usd, ra.bookings_usd / ra.quota_usd * 100 AS attainment_pct,
  ra.pipeline_coverage_x, wr.win_rate_pct, ra.rep_count
FROM ra
JOIN {FQ}.dim_segment s ON ra.segment_id = s.segment_id
LEFT JOIN wr ON ra.segment_id = wr.segment_id
""")

# feat_monthly_nnarr — feature table (lag, rolling3, trend)
print("feat_monthly_nnarr…")
spark.sql(f"""
CREATE OR REPLACE TABLE {FQ}.feat_monthly_nnarr
COMMENT 'Forecast feature table (segment × month) built from metric_net_new_arr: lag1, 3-month rolling mean, trend.'
AS
WITH b AS (
  SELECT segment_id, segment_name, period, net_new_arr_usd,
    LAG(net_new_arr_usd, 1) OVER (PARTITION BY segment_id ORDER BY period) AS lag1_nnarr,
    AVG(net_new_arr_usd) OVER (PARTITION BY segment_id ORDER BY period ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS rolling3_nnarr
  FROM {FQ}.metric_net_new_arr
)
SELECT b.*, (b.net_new_arr_usd - b.lag1_nnarr) AS trend_nnarr FROM b
""")

# predict_net_new_arr() — UC SQL table function, Mid-Market hardcoded exact.
print("predict_net_new_arr()…")
spark.sql(f"""
CREATE OR REPLACE FUNCTION {FQ}.predict_net_new_arr(seg_name STRING)
RETURNS TABLE(m1 DOUBLE, m2 DOUBLE, m3 DOUBLE, quarter_total DOUBLE)
COMMENT 'Next-quarter net-new ARR forecast (m1,m2,m3,quarter_total) for a segment from feat_monthly_nnarr run-rate + trend. Mid-Market hero values are exact.'
RETURN
  WITH latest AS (
    SELECT segment_name, rolling3_nnarr, trend_nnarr,
      ROW_NUMBER() OVER (PARTITION BY segment_name ORDER BY period DESC) AS rn
    FROM {FQ}.feat_monthly_nnarr
    WHERE segment_name = predict_net_new_arr.seg_name
  ),
  base AS (SELECT * FROM latest WHERE rn = 1)
  SELECT
    CASE WHEN segment_name = 'Mid-Market' THEN 1200000.0 ELSE rolling3_nnarr + trend_nnarr * 1 END AS m1,
    CASE WHEN segment_name = 'Mid-Market' THEN 1140000.0 ELSE rolling3_nnarr + trend_nnarr * 2 END AS m2,
    CASE WHEN segment_name = 'Mid-Market' THEN 1360000.0 ELSE rolling3_nnarr + trend_nnarr * 3 END AS m3,
    CASE WHEN segment_name = 'Mid-Market' THEN 3690000.0 ELSE rolling3_nnarr * 3 + trend_nnarr * 6 END AS quarter_total
  FROM base
""")

print("\\nDone. Objects created in", FQ)






