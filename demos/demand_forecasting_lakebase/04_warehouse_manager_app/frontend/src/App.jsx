import React, { useState, useEffect, useCallback } from "react";

const API_BASE = "/api";

function StatusBadge({ status }) {
  const colors = {
    critical: "bg-red-100 text-red-800 border-red-200",
    low: "bg-yellow-100 text-yellow-800 border-yellow-200",
    healthy: "bg-green-100 text-green-800 border-green-200",
    URGENT: "bg-red-100 text-red-800 border-red-200",
    WARNING: "bg-yellow-100 text-yellow-800 border-yellow-200",
    OK: "bg-green-100 text-green-800 border-green-200",
  };
  return (
    <span
      className={`px-2 py-1 rounded-full text-xs font-medium border ${colors[status] || "bg-gray-100 text-gray-800"}`}
    >
      {status}
    </span>
  );
}

function DashboardTab({ data }) {
  const critical = data.filter((d) => d.stock_status === "critical");
  const low = data.filter((d) => d.stock_status === "low");
  const healthy = data.filter((d) => d.stock_status === "healthy");

  return (
    <div>
      <div className="grid grid-cols-3 gap-4 mb-6">
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-center">
          <div className="text-3xl font-bold text-red-700">{critical.length}</div>
          <div className="text-sm text-red-600">Critical Stock</div>
        </div>
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 text-center">
          <div className="text-3xl font-bold text-yellow-700">{low.length}</div>
          <div className="text-sm text-yellow-600">Low Stock</div>
        </div>
        <div className="bg-green-50 border border-green-200 rounded-lg p-4 text-center">
          <div className="text-3xl font-bold text-green-700">{healthy.length}</div>
          <div className="text-sm text-green-600">Healthy</div>
        </div>
      </div>

      <table className="w-full text-sm">
        <thead>
          <tr className="bg-gray-50 text-left">
            <th className="p-3">SKU</th>
            <th className="p-3">Product</th>
            <th className="p-3">Warehouse</th>
            <th className="p-3">Stock</th>
            <th className="p-3">Reorder Pt</th>
            <th className="p-3">Pending</th>
            <th className="p-3">Q Forecast</th>
            <th className="p-3">Status</th>
          </tr>
        </thead>
        <tbody>
          {data.map((row, i) => (
            <tr key={i} className="border-b hover:bg-gray-50">
              <td className="p-3 font-mono text-xs">{row.sku}</td>
              <td className="p-3">{row.product_name}</td>
              <td className="p-3">{row.warehouse}</td>
              <td className="p-3 font-medium">{row.current_stock}</td>
              <td className="p-3">{row.reorder_point}</td>
              <td className="p-3">{row.pending_qty}</td>
              <td className="p-3">{row.current_quarter_forecast?.toLocaleString()}</td>
              <td className="p-3">
                <StatusBadge status={row.stock_status} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ReorderQueueTab({ data, onAction }) {
  const [modifyState, setModifyState] = useState({});

  const handleAction = (queueId, action, modifiedQty, notes) => {
    onAction({ queue_id: queueId, action, modified_quantity: modifiedQty, notes });
  };

  return (
    <div>
      <h2 className="text-lg font-semibold mb-4">
        Model Recommendations ({data.length} pending)
      </h2>
      {data.length === 0 ? (
        <p className="text-gray-500">No pending recommendations.</p>
      ) : (
        <div className="space-y-4">
          {data.map((item) => (
            <div
              key={item.queue_id}
              className="border rounded-lg p-4 bg-white shadow-sm"
            >
              <div className="flex justify-between items-start mb-3">
                <div>
                  <h3 className="font-medium">
                    {item.product_name}{" "}
                    <span className="text-gray-500 text-sm">({item.sku})</span>
                  </h3>
                  <p className="text-sm text-gray-600">
                    {item.warehouse} | Current stock: {item.current_stock}
                  </p>
                </div>
                <div className="text-right">
                  <div className="text-2xl font-bold text-blue-700">
                    {item.recommended_quantity} units
                  </div>
                  <div className="text-sm text-gray-500">
                    Est. cost: ${Number(item.estimated_cost || 0).toFixed(2)}
                  </div>
                </div>
              </div>

              <p className="text-xs text-gray-500 bg-gray-50 p-2 rounded mb-3">
                {item.recommendation_reason}
              </p>

              <div className="flex gap-2 items-center">
                <button
                  onClick={() => handleAction(item.queue_id, "approved")}
                  className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 text-sm"
                >
                  Approve
                </button>

                <div className="flex items-center gap-1">
                  <input
                    type="number"
                    placeholder="Qty"
                    className="w-20 px-2 py-2 border rounded text-sm"
                    value={modifyState[item.queue_id]?.qty || ""}
                    onChange={(e) =>
                      setModifyState({
                        ...modifyState,
                        [item.queue_id]: {
                          ...modifyState[item.queue_id],
                          qty: e.target.value,
                        },
                      })
                    }
                  />
                  <button
                    onClick={() =>
                      handleAction(
                        item.queue_id,
                        "modified",
                        parseInt(modifyState[item.queue_id]?.qty),
                        modifyState[item.queue_id]?.notes
                      )
                    }
                    className="px-4 py-2 bg-yellow-500 text-white rounded hover:bg-yellow-600 text-sm"
                    disabled={!modifyState[item.queue_id]?.qty}
                  >
                    Modify
                  </button>
                </div>

                <button
                  onClick={() => handleAction(item.queue_id, "rejected", null, "Manager rejected")}
                  className="px-4 py-2 bg-red-500 text-white rounded hover:bg-red-600 text-sm"
                >
                  Reject
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function PredictionsTab({ data }) {
  return (
    <div>
      <h2 className="text-lg font-semibold mb-4">Demand Forecast by Category</h2>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {data.map((cat, i) => (
          <div key={i} className="border rounded-lg p-4 bg-white shadow-sm">
            <h3 className="font-medium text-lg mb-2">{cat.category}</h3>
            <p className="text-sm text-gray-500">{cat.sku_count} SKUs</p>
            <div className="mt-3 space-y-2">
              <div>
                <div className="text-xs text-gray-500">Current Quarter</div>
                <div className="text-xl font-bold">
                  {Number(cat.total_current_q_forecast).toLocaleString()} units
                </div>
                <div className="text-sm text-green-600">
                  ${Number(cat.current_q_revenue_est).toLocaleString(undefined, {
                    minimumFractionDigits: 0,
                    maximumFractionDigits: 0,
                  })}{" "}
                  est. revenue
                </div>
              </div>
              <div>
                <div className="text-xs text-gray-500">Next Quarter</div>
                <div className="text-xl font-bold">
                  {Number(cat.total_next_q_forecast).toLocaleString()} units
                </div>
                <div className="text-sm text-green-600">
                  ${Number(cat.next_q_revenue_est).toLocaleString(undefined, {
                    minimumFractionDigits: 0,
                    maximumFractionDigits: 0,
                  })}{" "}
                  est. revenue
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function StockoutRiskTab({ data }) {
  return (
    <div>
      <h2 className="text-lg font-semibold mb-4">
        Stockout Risk ({data.length} items at risk)
      </h2>
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-gray-50 text-left">
            <th className="p-3">Risk</th>
            <th className="p-3">Product</th>
            <th className="p-3">Warehouse</th>
            <th className="p-3">Stock</th>
            <th className="p-3">Daily Forecast</th>
            <th className="p-3">Days of Stock</th>
            <th className="p-3">Lead Time</th>
          </tr>
        </thead>
        <tbody>
          {data.map((row, i) => (
            <tr key={i} className="border-b hover:bg-gray-50">
              <td className="p-3">
                <StatusBadge status={row.risk_level} />
              </td>
              <td className="p-3">{row.product_name}</td>
              <td className="p-3">{row.warehouse}</td>
              <td className="p-3 font-medium">{row.current_stock}</td>
              <td className="p-3">{row.daily_forecast}</td>
              <td className="p-3 font-medium">{row.days_of_stock}</td>
              <td className="p-3">{row.lead_time_days} days</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function App() {
  const [tab, setTab] = useState("dashboard");
  const [dashboard, setDashboard] = useState([]);
  const [queue, setQueue] = useState([]);
  const [predictions, setPredictions] = useState([]);
  const [stockoutRisk, setStockoutRisk] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [dashRes, queueRes, predRes, riskRes] = await Promise.all([
        fetch(`${API_BASE}/dashboard`).then((r) => r.json()),
        fetch(`${API_BASE}/reorder-queue`).then((r) => r.json()),
        fetch(`${API_BASE}/predictions-summary`).then((r) => r.json()),
        fetch(`${API_BASE}/stockout-risk`).then((r) => r.json()),
      ]);
      setDashboard(dashRes.items || []);
      setQueue(queueRes.items || []);
      setPredictions(predRes.items || []);
      setStockoutRisk(riskRes.items || []);
    } catch (err) {
      console.error("Failed to fetch data:", err);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 60000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const handleAction = async (action) => {
    try {
      await fetch(`${API_BASE}/reorder-action`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(action),
      });
      fetchData();
    } catch (err) {
      console.error("Action failed:", err);
    }
  };

  const tabs = [
    { id: "dashboard", label: "Inventory Overview" },
    { id: "queue", label: `Reorder Queue (${queue.length})` },
    { id: "predictions", label: "Demand Forecast" },
    { id: "risk", label: "Stockout Risk" },
  ];

  return (
    <div className="min-h-screen bg-gray-100">
      <header className="bg-white border-b px-6 py-4">
        <h1 className="text-2xl font-bold text-gray-800">
          Warehouse Manager Dashboard
        </h1>
        <p className="text-sm text-gray-500">
          ML-powered demand forecasting + real-time inventory management
        </p>
      </header>

      <nav className="bg-white border-b px-6">
        <div className="flex gap-1">
          {tabs.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                tab === t.id
                  ? "border-blue-600 text-blue-600"
                  : "border-transparent text-gray-500 hover:text-gray-700"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </nav>

      <main className="p-6 max-w-7xl mx-auto">
        {loading ? (
          <div className="text-center py-12 text-gray-500">Loading...</div>
        ) : (
          <>
            {tab === "dashboard" && <DashboardTab data={dashboard} />}
            {tab === "queue" && (
              <ReorderQueueTab data={queue} onAction={handleAction} />
            )}
            {tab === "predictions" && <PredictionsTab data={predictions} />}
            {tab === "risk" && <StockoutRiskTab data={stockoutRisk} />}
          </>
        )}
      </main>
    </div>
  );
}
