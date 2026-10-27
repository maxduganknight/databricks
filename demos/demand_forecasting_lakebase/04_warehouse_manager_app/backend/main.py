"""
Warehouse Manager Dashboard - FastAPI Backend

Reads from Lakebase (PostgreSQL) for:
- Inventory levels
- ML demand predictions
- Reorder recommendations

Writes manager decisions back to Lakebase.
"""

import os
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState

app = FastAPI(title="Warehouse Manager Dashboard")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

LAKEBASE = os.getenv("LAKEBASE_DATABASE", "demand_forecast_ops")
CATALOG = os.getenv("CATALOG", "demand_forecast_demo_catalog")
SCHEMA = os.getenv("SCHEMA", "demand_forecasting")


def get_workspace_client():
    return WorkspaceClient()


def execute_sql(statement: str, catalog: str = None, schema: str = None):
    """Execute SQL via Databricks SQL Statement API."""
    w = get_workspace_client()

    # Find a warehouse
    warehouses = list(w.warehouses.list())
    if not warehouses:
        raise HTTPException(status_code=500, detail="No SQL warehouse available")
    warehouse_id = warehouses[0].id

    response = w.statement_execution.execute_statement(
        statement=statement,
        warehouse_id=warehouse_id,
        catalog=catalog,
        schema=schema,
        wait_timeout="30s",
    )

    if response.status.state != StatementState.SUCCEEDED:
        raise HTTPException(
            status_code=500,
            detail=f"SQL execution failed: {response.status.error}",
        )

    columns = [col.name for col in response.manifest.schema.columns]
    rows = []
    if response.result and response.result.data_array:
        for row in response.result.data_array:
            rows.append(dict(zip(columns, row)))
    return rows


# ---------- API Endpoints ----------


@app.get("/api/dashboard")
def get_dashboard():
    """Main dashboard: inventory + predictions + reorder recommendations."""
    rows = execute_sql(f"""
        SELECT
            i.sku,
            p.name AS product_name,
            p.category,
            p.unit_price,
            i.warehouse,
            i.current_stock,
            rt.reorder_point,
            rt.reorder_quantity,
            rt.lead_time_days,
            sp.current_quarter_forecast,
            sp.next_quarter_forecast,
            sp.current_quarter_lower,
            sp.current_quarter_upper,
            COALESCE(po.pending_qty, 0) AS pending_qty,
            CASE
                WHEN i.current_stock + COALESCE(po.pending_qty, 0) < rt.reorder_point THEN 'critical'
                WHEN i.current_stock + COALESCE(po.pending_qty, 0) < rt.reorder_point * 1.5 THEN 'low'
                ELSE 'healthy'
            END AS stock_status
        FROM {LAKEBASE}.inventory i
        JOIN {CATALOG}.{SCHEMA}.products p ON i.sku = p.sku
        JOIN {LAKEBASE}.reorder_thresholds rt ON i.sku = rt.sku
        LEFT JOIN {LAKEBASE}.sales_predictions sp ON i.sku = sp.sku
        LEFT JOIN (
            SELECT sku, warehouse, SUM(quantity) AS pending_qty
            FROM {LAKEBASE}.pending_orders
            WHERE status = 'pending'
            GROUP BY sku, warehouse
        ) po ON i.sku = po.sku AND i.warehouse = po.warehouse
        ORDER BY
            CASE
                WHEN i.current_stock + COALESCE(po.pending_qty, 0) < rt.reorder_point THEN 1
                WHEN i.current_stock + COALESCE(po.pending_qty, 0) < rt.reorder_point * 1.5 THEN 2
                ELSE 3
            END,
            i.sku, i.warehouse
    """)
    return {"items": rows}


@app.get("/api/reorder-queue")
def get_reorder_queue():
    """Pending reorder recommendations for manager review."""
    rows = execute_sql(f"""
        SELECT
            q.queue_id,
            q.sku,
            p.name AS product_name,
            p.category,
            q.warehouse,
            q.recommended_quantity,
            q.recommendation_reason,
            q.created_at,
            i.current_stock,
            p.unit_cost,
            q.recommended_quantity * p.unit_cost AS estimated_cost
        FROM {LAKEBASE}.reorder_queue q
        JOIN {CATALOG}.{SCHEMA}.products p ON q.sku = p.sku
        JOIN {LAKEBASE}.inventory i ON q.sku = i.sku AND q.warehouse = i.warehouse
        WHERE q.manager_action IS NULL
        ORDER BY q.created_at DESC
    """)
    return {"items": rows}


class ReorderAction(BaseModel):
    queue_id: int
    action: str  # 'approved', 'modified', 'rejected'
    modified_quantity: Optional[int] = None
    notes: Optional[str] = None


@app.post("/api/reorder-action")
def submit_reorder_action(action: ReorderAction):
    """Manager approves, modifies, or rejects a reorder recommendation."""
    if action.action not in ("approved", "modified", "rejected"):
        raise HTTPException(status_code=400, detail="Invalid action")

    if action.action == "modified" and action.modified_quantity is None:
        raise HTTPException(
            status_code=400,
            detail="modified_quantity required for 'modified' action",
        )

    mod_qty = action.modified_quantity if action.modified_quantity else "NULL"
    notes = action.notes.replace("'", "''") if action.notes else ""

    execute_sql(f"""
        UPDATE {LAKEBASE}.reorder_queue
        SET manager_action = '{action.action}',
            modified_quantity = {mod_qty},
            manager_notes = '{notes}',
            actioned_at = CURRENT_TIMESTAMP
        WHERE queue_id = {action.queue_id}
    """)

    # If approved or modified, create a pending order
    if action.action in ("approved", "modified"):
        qty = action.modified_quantity if action.action == "modified" else None
        execute_sql(f"""
            INSERT INTO {LAKEBASE}.pending_orders (sku, warehouse, quantity, supplier, expected_delivery, status)
            SELECT
                sku,
                warehouse,
                COALESCE({mod_qty}, recommended_quantity),
                'Auto-ordered via Dashboard',
                CURRENT_DATE + INTERVAL '7 days',
                'pending'
            FROM {LAKEBASE}.reorder_queue
            WHERE queue_id = {action.queue_id}
        """)

    return {"status": "ok", "message": f"Reorder {action.queue_id} {action.action}"}


@app.get("/api/predictions-summary")
def get_predictions_summary():
    """Aggregated prediction summary by category."""
    rows = execute_sql(f"""
        SELECT
            p.category,
            COUNT(DISTINCT sp.sku) AS sku_count,
            SUM(sp.current_quarter_forecast) AS total_current_q_forecast,
            SUM(sp.next_quarter_forecast) AS total_next_q_forecast,
            SUM(sp.current_quarter_forecast * p.unit_price) AS current_q_revenue_est,
            SUM(sp.next_quarter_forecast * p.unit_price) AS next_q_revenue_est
        FROM {LAKEBASE}.sales_predictions sp
        JOIN {CATALOG}.{SCHEMA}.products p ON sp.sku = p.sku
        GROUP BY p.category
        ORDER BY current_q_revenue_est DESC
    """)
    return {"items": rows}


@app.get("/api/stockout-risk")
def get_stockout_risk():
    """SKUs at risk of stockout based on current inventory vs forecast."""
    rows = execute_sql(f"""
        SELECT
            i.sku,
            p.name AS product_name,
            i.warehouse,
            i.current_stock,
            sp.current_quarter_forecast,
            rt.lead_time_days,
            ROUND(sp.current_quarter_forecast / 90.0, 1) AS daily_forecast,
            ROUND(i.current_stock / NULLIF(sp.current_quarter_forecast / 90.0, 0), 0) AS days_of_stock,
            CASE
                WHEN i.current_stock / NULLIF(sp.current_quarter_forecast / 90.0, 0) < rt.lead_time_days THEN 'URGENT'
                WHEN i.current_stock / NULLIF(sp.current_quarter_forecast / 90.0, 0) < rt.lead_time_days * 2 THEN 'WARNING'
                ELSE 'OK'
            END AS risk_level
        FROM {LAKEBASE}.inventory i
        JOIN {CATALOG}.{SCHEMA}.products p ON i.sku = p.sku
        JOIN {LAKEBASE}.sales_predictions sp ON i.sku = sp.sku
        JOIN {LAKEBASE}.reorder_thresholds rt ON i.sku = rt.sku
        WHERE i.current_stock / NULLIF(sp.current_quarter_forecast / 90.0, 0) < rt.lead_time_days * 2
        ORDER BY
            CASE
                WHEN i.current_stock / NULLIF(sp.current_quarter_forecast / 90.0, 0) < rt.lead_time_days THEN 1
                ELSE 2
            END,
            i.current_stock ASC
    """)
    return {"items": rows}


# Serve frontend static files
frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "build")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")
