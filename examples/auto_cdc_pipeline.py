from pyspark import pipelines as dp

# ─── Configuration ───────────────────────────────────────────────
# Each pipeline notebook defines its own subset of tables.
# Group by size: small tables in one pipeline, large in another.

TABLES = [
    {"source": "dbo.orders", "target": "orders", "keys": ["order_id"]},
    {"source": "dbo.customers", "target": "customers", "keys": ["customer_id"]},
    {"source": "dbo.positions", "target": "positions", "keys": ["position_id"]},
    {"source": "dbo.trades", "target": "trades", "keys": ["trade_id"]},
    # ... add remaining tables for this pipeline
]

JDBC_URL = spark.conf.get("jdbc_url")
JDBC_PROPS = {
    "user": dbutils.secrets.get("scope", "sql_user"),
    "password": dbutils.secrets.get("scope", "sql_password"),
    "driver": "com.microsoft.sqlserver.jdbc.SQLServerDriver",
}

# ─── Dynamic Pipeline Generation ────────────────────────────────

for table_config in TABLES:
    source_table = table_config["source"]
    target_name = table_config["target"]
    keys = table_config["keys"]

    # 1. Declare the target streaming table
    dp.create_streaming_table(target_name)

    # 2. Create a view that reads the current JDBC snapshot
    #    Note: closure capture with default arg (src=source_table)
    @dp.view(name=f"{target_name}_snapshot")
    def snapshot_view(src=source_table):
        return spark.read.jdbc(JDBC_URL, src, properties=JDBC_PROPS)

    # 3. Apply Auto CDC from Snapshot (SCD Type 1)
    dp.create_auto_cdc_from_snapshot_flow(
        target=target_name,
        source=f"{target_name}_snapshot",
        keys=keys,
        stored_as_scd_type=1,
    )
