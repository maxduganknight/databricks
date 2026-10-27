"""
Scenario Shift Alert synthetic data generator (Spark-native).

Realizes specifications/01-lakeflow.md. No SDP in this simple build, so this
script does the full raw -> silver -> gold layering itself via spark.sql CTAS.

Story: five strategic scenarios modeled over 2025-2045, re-run weekly (vintages).
The Accelerated Transition scenario (SCEN-02) swings from ~$4.2B (Attractive)
to ~$2.6B (Marginal), -38%, ~3 weeks ago, driven by 3 assumption changes.
The other four scenarios hold steady.

Runtime: pre-provisioned databricks-connect venv. Python 3.12. Do NOT create a venv.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

from databricks.connect import DatabricksSession
from pyspark.sql import DataFrame
from pyspark.sql import functions as F

CATALOG = os.environ.get("DEMO_CATALOG", "solution_builder")
SCHEMA = os.environ.get("DEMO_SCHEMA", "demo_scenario_shift_alert_015b3e")

# Time anchors — rolling by default; pin for a recorded baseline.
STORY_PINNED_NOW = datetime(2026, 9, 15)
NOW = STORY_PINNED_NOW if os.environ.get("DEMO_PIN_TIME") == "1" else datetime.now()


def _friday_on_or_before(d: datetime) -> datetime:
    return d - timedelta(days=(d.weekday() - 4) % 7)


VINTAGE_LATEST = _friday_on_or_before(NOW)
SWING_VINTAGE = _friday_on_or_before(NOW - timedelta(weeks=3))
N_VINTAGES = 26  # ~6 months of weekly runs
VINTAGES = [VINTAGE_LATEST - timedelta(weeks=i) for i in range(N_VINTAGES)][::-1]  # oldest -> newest
PRIOR_VINTAGE = _friday_on_or_before(NOW - timedelta(weeks=4))  # a clearly pre-swing vintage
NOW_STR = NOW.strftime("%Y-%m-%d")

# Scenarios: (id, name, theme, description, base_npv_busd)
SCENARIOS = [
    ("SCEN-01", "Base Case", "Reference outlook",
     "Reference outlook on the current policy trajectory and consensus prices.", 3.8),
    ("SCEN-02", "Accelerated Transition", "Fast decarbonization",
     "Fast decarbonization with rapid electrification and forward carbon policy.", 4.2),
    ("SCEN-03", "Delayed Transition", "Policy + adoption lag",
     "Policy and adoption lag; hydrocarbons persist longer than consensus.", 3.65),
    ("SCEN-04", "High Demand", "Strong demand growth",
     "Strong global energy demand growth with tighter supply and firmer prices.", 4.5),
    ("SCEN-05", "Carbon Constrained", "Aggressive carbon pricing",
     "Aggressive carbon pricing constrains hydrocarbon capex and volumes.", 2.9),
]
BASE_NPV = {s[0]: s[4] for s in SCENARIOS}
NAME_OF = {s[0]: s[1] for s in SCENARIOS}
THEME_OF = {s[0]: s[2] for s in SCENARIOS}
SWING_ID = "SCEN-02"
SWING_NPV_POST = 2.6  # ~ -38% from 4.2

# Assumption drivers: (old, new_for_swing) — new applies to SCEN-02 from SWING_VINTAGE.
DRV_CARBON = (45.0, 85.0)          # $/t
DRV_POLICY = (2032, 2028)          # effective year
DRV_GASGROWTH = (0.8, -0.6)        # %/yr
OIL_BASE = 70.0
DISC_BASE = 9.0

HORIZON_YEARS = list(range(2025, 2046))  # 2025..2045

ASSUMPTIONS_PARAGRAPH = (
    "Scenario SCEN-02 Accelerated Transition - assumptions revision. "
    "The carbon-price floor legislation has advanced, with the effective year pulled forward "
    "from 2032 to 2028 and the floor raised from $45/t to $85/t. Long-run natural gas demand "
    "growth is revised down by 1.4 percentage points per year (from +0.8%/yr to -0.6%/yr) on "
    "accelerating efficiency gains and electrification. Combined, these cut projected 2035-2045 "
    "cash flows, moving the scenario from an attractive NPV of ~$4.2B to a marginal ~$2.6B. "
    "Recommended client actions: hedge carbon exposure, re-time capex to the revised policy "
    "schedule, and revisit the assumed transition pace."
)

print(f"Target:          {CATALOG}.{SCHEMA}")
print(f"NOW:             {NOW.date()}")
print(f"VINTAGE_LATEST:  {VINTAGE_LATEST.date()}")
print(f"SWING_VINTAGE:   {SWING_VINTAGE.date()}")
print(f"PRIOR_VINTAGE:   {PRIOR_VINTAGE.date()}")

try:
    spark  # noqa: F821
except NameError:
    spark = (DatabricksSession.builder
             .profile(os.environ.get("DATABRICKS_CONFIG_PROFILE", "DEFAULT"))
             .serverless(True).getOrCreate())
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")


def _save(df: DataFrame, table: str, comment: str) -> None:
    fqn = f"{CATALOG}.{SCHEMA}.{table}"
    df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(fqn)
    spark.sql(f"COMMENT ON TABLE {fqn} IS :c", args={"c": comment})
    print(f"  ✓ {table:26s} rows={spark.table(fqn).count():>7,}")


def _npv_for(scen_id: str, vintage: datetime) -> float:
    """Deterministic NPV: flat baseline, with SCEN-02 stepping down at SWING_VINTAGE."""
    if scen_id == SWING_ID and vintage >= SWING_VINTAGE:
        return SWING_NPV_POST
    return BASE_NPV[scen_id]


def _band(npv: float) -> str:
    if npv >= 3.5:
        return "Attractive"
    if npv >= 2.5:
        return "Marginal"
    return "Unattractive"


# ── Phase 1 — RAW ───────────────────────────────────────────────────────────

# 1a. scenarios (5 rows, hand-curated)
scen_df = spark.createDataFrame(
    [(s[0], s[1], s[3], s[2]) for s in SCENARIOS],
    "scenario_id string, scenario_name string, scenario_description string, strategy_theme string",
)
_save(scen_df, "raw_scenarios", "The 5 strategic scenarios modeled for the client's 10-20 year profitability outlook.")

# 1b. raw_assumptions — 5 scenarios x 26 vintages (driver values per vintage).
assum_rows = []
for scen_id, name, _theme, _desc, _npv in SCENARIOS:
    for v in VINTAGES:
        swing_now = (scen_id == SWING_ID and v >= SWING_VINTAGE)
        carbon = DRV_CARBON[1] if swing_now else DRV_CARBON[0]
        policy = DRV_POLICY[1] if swing_now else DRV_POLICY[0]
        gas = DRV_GASGROWTH[1] if swing_now else DRV_GASGROWTH[0]
        assum_rows.append((
            scen_id, name, v.strftime("%Y-%m-%d"),
            float(carbon), int(policy), float(gas), OIL_BASE, DISC_BASE,
        ))
assum_df = spark.createDataFrame(
    assum_rows,
    "scenario_id string, scenario_name string, vintage_date string, "
    "carbon_price_floor_usd_t double, policy_effective_year int, gas_demand_growth_pct double, "
    "oil_price_usd_bbl double, discount_rate_pct double",
).withColumn("vintage_date", F.to_date("vintage_date"))
_save(assum_df, "raw_assumptions",
      "Per-scenario per-vintage assumption drivers. SCEN-02 flips carbon floor, policy year, and gas demand growth at the swing vintage; all others hold.")

# 1c. raw_projections — NPV summary point per (scenario, vintage) + full 21-yr
# annual curve at PRIOR_VINTAGE and VINTAGE_LATEST for the before/after chart.
proj_rows = []
# Summary points (all scenarios, all vintages) — horizon_year = NULL marks the summary grain.
for scen_id, name, _theme, _desc, _npv in SCENARIOS:
    for vi, v in enumerate(VINTAGES):
        npv = _npv_for(scen_id, v)
        # deterministic +/-1.5% wobble on non-swing points so lines look like model runs
        wob = 1.0 + 0.015 * ((vi % 5) - 2) / 2.0 if not (scen_id == SWING_ID) else 1.0
        proj_rows.append((
            f"PRJ-{scen_id}-{v.strftime('%Y%m%d')}-SUM", scen_id, name,
            v.strftime("%Y-%m-%d"), None,
            None, round(npv * wob, 3), None, None, None,
        ))

# Annual curves at PRIOR and LATEST vintages for the swing scenario + others.
def _annual_curve(scen_id: str, vintage: datetime):
    """Yield (year, annual_cashflow_musd, cumulative_npv_busd, production_mmboe,
    realized_price_boe, carbon_cost_musd) for a scenario at a vintage."""
    npv_target = _npv_for(scen_id, vintage)
    swing_post = (scen_id == SWING_ID and vintage >= SWING_VINTAGE)
    cum = 0.0
    cfs = []
    for y in HORIZON_YEARS:
        t = y - 2025
        prod = 42.0 * (0.985 ** t)  # mmboe, slow decline
        price = 62.0 + 0.6 * t
        # carbon cost climbs; heavier post-swing (higher floor + earlier policy)
        floor = (DRV_CARBON[1] if swing_post else DRV_CARBON[0]) if scen_id == SWING_ID else 50.0
        pol_year = (DRV_POLICY[1] if swing_post else DRV_POLICY[0]) if scen_id == SWING_ID else 2032
        carbon_intensity = 0.35
        active = 1.0 if y >= pol_year else 0.25
        carbon_cost = prod * carbon_intensity * floor * active / 10.0  # $M-ish
        # gas volume effect post-swing: demand-down erodes back-half cashflow
        gas_pen = (1.0 - 0.02 * max(0, y - 2034)) if swing_post else 1.0
        gross = prod * price * 0.42 * gas_pen  # $M annual free cash flow proxy
        cf = gross - carbon_cost
        cfs.append((y, cf, prod, price, carbon_cost))
        cum += cf
    # scale the curve so discounted NPV roughly matches the target band
    scale = (npv_target * 1000.0) / cum if cum else 1.0
    running = 0.0
    for (y, cf, prod, price, carbon_cost) in cfs:
        cf_s = cf * scale
        cc_s = carbon_cost * scale
        running += cf_s
        yield (y, round(cf_s, 1), round(running / 1000.0, 3),
               round(prod, 2), round(price, 2), round(cc_s, 1))


for scen_id, name, _theme, _desc, _npv in SCENARIOS:
    for label, vintage in [("Prior", PRIOR_VINTAGE), ("Current", VINTAGE_LATEST)]:
        for (y, cf, cum, prod, price, cc) in _annual_curve(scen_id, vintage):
            proj_rows.append((
                f"PRJ-{scen_id}-{label}-{y}", scen_id, name,
                vintage.strftime("%Y-%m-%d"), y,
                cf, cum, prod, price, cc,
            ))

proj_df = spark.createDataFrame(
    proj_rows,
    "projection_id string, scenario_id string, scenario_name string, vintage_date string, "
    "horizon_year int, annual_cashflow_musd double, cumulative_npv_busd double, "
    "production_mmboe double, realized_price_usd_boe double, carbon_cost_musd double",
).withColumn("vintage_date", F.to_date("vintage_date"))
_save(proj_df, "raw_projections",
      "Scenario projections: NPV summary point per (scenario, vintage) plus the full 2025-2045 annual cashflow curve at the prior and current vintages.")

# ── Phase 2 — SILVER ─────────────────────────────────────────────────────────

print("Building silver_scenario_npv …")
spark.sql(f"""
    CREATE OR REPLACE TABLE {CATALOG}.{SCHEMA}.silver_scenario_npv
    COMMENT 'One row per (scenario, vintage): NPV and derived risk band — the swing-trend fact.'
    AS SELECT
      p.scenario_id, p.scenario_name, p.vintage_date,
      CAST(p.cumulative_npv_busd AS DOUBLE) AS npv_busd,
      CASE WHEN p.cumulative_npv_busd >= 3.5 THEN 'Attractive'
           WHEN p.cumulative_npv_busd >= 2.5 THEN 'Marginal'
           ELSE 'Unattractive' END AS risk_band,
      s.strategy_theme
    FROM {CATALOG}.{SCHEMA}.raw_projections p
    JOIN {CATALOG}.{SCHEMA}.raw_scenarios s ON p.scenario_id = s.scenario_id
    WHERE p.horizon_year IS NULL
""")

print("Building silver_assumptions …")
spark.sql(f"""
    CREATE OR REPLACE TABLE {CATALOG}.{SCHEMA}.silver_assumptions
    COMMENT 'Assumption drivers per (scenario, vintage) with a current-vintage flag.'
    AS SELECT
      a.*,
      CASE WHEN a.vintage_date = (SELECT MAX(vintage_date) FROM {CATALOG}.{SCHEMA}.raw_assumptions)
           THEN TRUE ELSE FALSE END AS is_current_vintage
    FROM {CATALOG}.{SCHEMA}.raw_assumptions a
""")

# ── Phase 3 — GOLD ───────────────────────────────────────────────────────────

print("Building gold_scenario_npv_trend …")
spark.sql(f"""
    CREATE OR REPLACE TABLE {CATALOG}.{SCHEMA}.gold_scenario_npv_trend
    COMMENT 'Per (scenario, vintage) NPV + risk band. Drives the swing trend line and risk-band KPIs. is_alerted TRUE only for the alerted scenario at the latest vintage.'
    AS SELECT
      scenario_id, scenario_name, vintage_date, npv_busd, risk_band, strategy_theme,
      CASE WHEN scenario_id = '{SWING_ID}'
             AND vintage_date = (SELECT MAX(vintage_date) FROM {CATALOG}.{SCHEMA}.silver_scenario_npv)
           THEN TRUE ELSE FALSE END AS is_alerted
    FROM {CATALOG}.{SCHEMA}.silver_scenario_npv
""")

print("Building gold_projection_detail …")
spark.sql(f"""
    CREATE OR REPLACE TABLE {CATALOG}.{SCHEMA}.gold_projection_detail
    COMMENT 'Annual 2025-2045 cashflow curve per (scenario, horizon_year) at Current vs Prior vintage. Drives the before/after cashflow chart for the alerted scenario.'
    AS SELECT
      scenario_id, scenario_name, horizon_year,
      CASE WHEN vintage_date = DATE'{VINTAGE_LATEST.strftime('%Y-%m-%d')}' THEN 'Current'
           WHEN vintage_date = DATE'{PRIOR_VINTAGE.strftime('%Y-%m-%d')}'  THEN 'Prior'
           ELSE 'Other' END AS vintage_label,
      annual_cashflow_musd, cumulative_npv_busd, carbon_cost_musd, production_mmboe
    FROM {CATALOG}.{SCHEMA}.raw_projections
    WHERE horizon_year IS NOT NULL
      AND vintage_date IN (DATE'{VINTAGE_LATEST.strftime('%Y-%m-%d')}', DATE'{PRIOR_VINTAGE.strftime('%Y-%m-%d')}')
""")

print("Building gold_assumptions …")
spark.sql(f"""
    CREATE OR REPLACE TABLE {CATALOG}.{SCHEMA}.gold_assumptions
    COMMENT 'Per scenario, the headline assumption drivers at Current vs Prior vintage (old/new/delta) and a count of drivers that changed. Drives the assumption-change table and Genie''s why answer.'
    AS WITH cur AS (
      SELECT scenario_id, scenario_name, carbon_price_floor_usd_t, policy_effective_year, gas_demand_growth_pct
      FROM {CATALOG}.{SCHEMA}.raw_assumptions
      WHERE vintage_date = DATE'{VINTAGE_LATEST.strftime('%Y-%m-%d')}'
    ), pri AS (
      SELECT scenario_id, carbon_price_floor_usd_t AS carbon_old, policy_effective_year AS policy_old,
             gas_demand_growth_pct AS gas_old
      FROM {CATALOG}.{SCHEMA}.raw_assumptions
      WHERE vintage_date = DATE'{PRIOR_VINTAGE.strftime('%Y-%m-%d')}'
    )
    SELECT
      cur.scenario_id, cur.scenario_name,
      pri.carbon_old AS carbon_price_floor_old, cur.carbon_price_floor_usd_t AS carbon_price_floor_new,
      cur.carbon_price_floor_usd_t - pri.carbon_old AS carbon_price_floor_delta,
      pri.policy_old AS policy_effective_year_old, cur.policy_effective_year AS policy_effective_year_new,
      cur.policy_effective_year - pri.policy_old AS policy_effective_year_delta,
      pri.gas_old AS gas_demand_growth_old, cur.gas_demand_growth_pct AS gas_demand_growth_new,
      ROUND(cur.gas_demand_growth_pct - pri.gas_old, 2) AS gas_demand_growth_delta,
      (CASE WHEN cur.carbon_price_floor_usd_t <> pri.carbon_old THEN 1 ELSE 0 END
       + CASE WHEN cur.policy_effective_year <> pri.policy_old THEN 1 ELSE 0 END
       + CASE WHEN cur.gas_demand_growth_pct <> pri.gas_old THEN 1 ELSE 0 END) AS driver_changed_count
    FROM cur JOIN pri ON cur.scenario_id = pri.scenario_id
""")

print(f"\nDone. Tables in {CATALOG}.{SCHEMA}:")
for row in spark.sql(f"SHOW TABLES IN {CATALOG}.{SCHEMA}").collect():
    print(f"  - {row['tableName']}")
print(f"\nVINTAGE_LATEST={VINTAGE_LATEST.date()}  SWING_VINTAGE={SWING_VINTAGE.date()}  PRIOR_VINTAGE={PRIOR_VINTAGE.date()}")
