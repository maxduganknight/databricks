```json
[
  {
    "name": "RevOps — Revenue Intelligence",
    "story": "The company's Salesforce / billing / product-usage / support feeds land via Lakeflow Connect and customer churn/QBR PDFs land in a UC Volume (ai_parse_document + ai_extract → fact_churn_reason). All is shaped into a governed semantic layer (sem_* metric views + predict_net_new_arr) and surfaces through a 5-page AI/BI dashboard and 5 Genie spaces. A Genie One scheduled insight on the retention-control semantic views (sem_forecast_plan / sem_nrr_retention / sem_account_health) fires when Mid-Market NRR drops below the control line and at-risk Enterprise ARR breaches its limit, and finds Maya Chen, Director of RevOps, who investigates conversationally through Genie One — including the unstructured churn evidence — all on the governed Databricks Platform.",
    "aspect": "16:9",
    "direction": "horizontal",
    "columns": [
      "sources",
      "pipeline",
      "compute",
      "work",
      "entry"
    ],
    "nodes": [
      {
        "id": "aibi-dashboards",
        "type": "ai-bi-dashboard",
        "col": "work",
        "row": 1,
        "desc": "Revenue Intelligence — 5 pages: NRR cliff, attainment, net-new ARR, renewal risk, GTM efficiency"
      },
      {
        "id": "db-platform",
        "type": "db-platform",
        "pin": {
          "at": "top-left",
          "to": "platform-box"
        }
      },
      {
        "id": "genie",
        "type": "genie",
        "col": "work",
        "row": 2,
        "desc": "5 domain spaces — retention, ARR, forecast, churn, GTM"
      },
      {
        "id": "genie-one",
        "type": "genie-one",
        "col": "entry",
        "rot": 90,
        "desc": "Maya Chen, Director of RevOps — asks in plain language; the alert finds the executive"
      },
      {
        "id": "governance-block",
        "type": "governance-block",
        "pin": {
          "at": "top-right",
          "to": "platform-box"
        }
      },
      {
        "id": "lakeflow-genie-block",
        "type": "lakeflow-genie-block",
        "col": "pipeline",
        "desc": "Lakeflow Connect lands GTM feeds; SDP shapes bronze→silver→gold + the sem_* semantic layer"
      },
      {
        "id": "lakehouse",
        "type": "sql-lakehouse",
        "col": "compute",
        "desc": "Governed revenue model — sem_* metric views + predict_net_new_arr() + fact_churn_reason (extracted); a Genie One scheduled insight watches retention-control on sem_forecast_plan / sem_nrr_retention / sem_account_health"
      },
      {
        "id": "platform-box",
        "type": "box",
        "z": -1,
        "wraps": [
          "src-salesforce",
          "src-billing",
          "src-postgres",
          "src-docs",
          "lakeflow-genie-block",
          "lakehouse",
          "aibi-dashboards",
          "genie",
          "genie-one"
        ]
      },
      {
        "id": "src-billing",
        "type": "source",
        "col": "sources",
        "row": 2,
        "label": "Billing / Stripe",
        "icon": "file:vendor/stripe",
        "desc": "Subscriptions, ARR, renewals"
      },
      {
        "id": "src-docs",
        "type": "source",
        "col": "sources",
        "row": 4,
        "label": "Churn & QBR docs",
        "icon": "pdfLogo",
        "desc": "Cancellation/QBR PDFs → UC Volume → ai_parse_document + ai_extract → fact_churn_reason"
      },
      {
        "id": "src-postgres",
        "type": "source",
        "col": "sources",
        "row": 3,
        "label": "Product usage",
        "icon": "file:vendor/postgresql",
        "desc": "Usage events & health signals"
      },
      {
        "id": "src-salesforce",
        "type": "source",
        "col": "sources",
        "row": 1,
        "label": "Salesforce",
        "icon": "file:vendor/salesforce",
        "desc": "CRM — opportunities, pipeline, accounts"
      }
    ],
    "edges": [
      {
        "id": "e1",
        "from": "src-salesforce",
        "to": "lakeflow-genie-block@in-lakeflow-connect",
        "flow": true
      },
      {
        "id": "e2",
        "from": "src-billing",
        "to": "lakeflow-genie-block@in-lakeflow-connect",
        "flow": true
      },
      {
        "id": "e3",
        "from": "src-postgres",
        "to": "lakeflow-genie-block@in-lakeflow-connect",
        "flow": true
      },
      {
        "id": "e4",
        "from": "src-docs",
        "to": "lakeflow-genie-block@in-direct",
        "flow": true
      },
      {
        "id": "e5",
        "from": "lakeflow-genie-block",
        "to": "lakehouse",
        "flow": true
      },
      {
        "id": "e6",
        "from": "lakehouse",
        "to": "aibi-dashboards",
        "flow": true
      },
      {
        "id": "e7",
        "from": "lakehouse",
        "to": "genie",
        "flow": true
      },
      {
        "id": "e8",
        "from": "genie-one",
        "to": "aibi-dashboards"
      },
      {
        "id": "e9",
        "from": "genie-one",
        "to": "genie"
      }
    ]
  }
]
```
