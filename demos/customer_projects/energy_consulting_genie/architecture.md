```json
[
  {
    "name": "Scenario Shift Alert — End-to-End",
    "story": "Projection model runs, market data, and policy data enter a governed Databricks platform via Lakeflow; an assumptions-memo PDF lands in a UC Volume and is parsed with AI Functions (ai_parse_document). A scheduled SQL Alert on the scenario-swing view fires a Genie alert into the consultant's inbox; she clicks through to Genie One to ask why over the projection tables and the parsed memo, then opens the AI/BI dashboard to go deeper. Unity Catalog governs all of it.",
    "aspect": "16:9",
    "frame": {
      "title": "Scenario Shift Alert",
      "subtitle": "Alert → Genie One → dashboard, over governed projections + a parsed assumptions PDF"
    },
    "theme": "slide",
    "direction": "horizontal",
    "options": {
      "trademarkLogos": false
    },
    "columns": [
      "sources",
      "data",
      "serve",
      "work",
      "entry"
    ],
    "nodes": [
      {
        "id": "ai-bi-dashboard",
        "type": "ai-bi-dashboard",
        "col": "work",
        "row": 3,
        "label": "AI/BI Dashboard",
        "ai_reasoning": "the LATER deep-dive act — opened after the Genie conversation, not the entry point"
      },
      {
        "id": "alert",
        "type": "shape",
        "shape": "triangle",
        "col": "work",
        "row": 1,
        "size": [
          230,
          96
        ],
        "text": "SQL Alert → inbox",
        "ai_reasoning": "no alert tile in the catalog; the triangle is the alert/escalation marker. Scheduled SQL Alert on vw_scenario_alert (NPV move < -30%) — the OPENING beat, replacing 'open the dashboard'"
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
        "id": "doc-parse",
        "type": "document-parsing",
        "col": "data",
        "row": 4,
        "label": "AI Functions — parse PDF",
        "ai_reasoning": "ai_parse_document turns the memo into gold_assumptions_doc.parsed_text so Genie can quote it"
      },
      {
        "id": "genie",
        "type": "genie",
        "col": "work",
        "row": 4
      },
      {
        "id": "genie-one",
        "type": "genie-one",
        "col": "entry",
        "rot": 90,
        "ai_reasoning": "the consultant clicks the inbox alert through to Genie One, then asks the follow-ups; persona built in"
      },
      {
        "id": "governance-block",
        "type": "governance-block",
        "pin": {
          "at": "bottom",
          "to": "platform-box"
        }
      },
      {
        "id": "lakeflow-genie-block",
        "type": "lakeflow-genie-block",
        "col": "data",
        "row": 1,
        "ai_reasoning": "one data-layer block: managed ingest + bronze->silver->gold projection/assumption gold tables, built with Genie Code"
      },
      {
        "id": "note-inbox",
        "type": "note",
        "text": "Genie alert -> consultant's inbox",
        "below": "alert",
        "gap": 26
      },
      {
        "id": "platform-box",
        "type": "box",
        "z": -1,
        "pad": 40,
        "wraps": [
          "lakeflow-genie-block",
          "uc-volume",
          "doc-parse",
          "sql-lakehouse",
          "alert",
          "ai-bi-dashboard",
          "genie",
          "genie-one"
        ]
      },
      {
        "id": "sql-lakehouse",
        "type": "sql-lakehouse",
        "col": "serve",
        "row": 2,
        "ai_reasoning": "one governed serving copy the alert, dashboard, and Genie all read (structured gold tables + the parsed-memo table)"
      },
      {
        "id": "src-market",
        "type": "source",
        "col": "sources",
        "row": 2,
        "label": "Market Data Feed",
        "icon": "inputData"
      },
      {
        "id": "src-model",
        "type": "source",
        "col": "sources",
        "row": 1,
        "label": "Projection Model Runs",
        "icon": "inputData",
        "ai_reasoning": "weekly scenario model vintages (NPV + assumptions per scenario) — the structured projections; lands via managed connect"
      },
      {
        "id": "src-pdf",
        "type": "source",
        "col": "sources",
        "row": 4,
        "label": "Assumptions Memo (PDF)",
        "icon": "pdfLogo",
        "ai_reasoning": "the unstructured beat — routed through a UC Volume + AI Functions rather than the block's direct-file port so the parse is visible"
      },
      {
        "id": "src-policy",
        "type": "source",
        "col": "sources",
        "row": 3,
        "label": "Policy Data Feed",
        "icon": "inputData"
      },
      {
        "id": "uc-volume",
        "type": "uc-volume",
        "col": "data",
        "row": 3,
        "label": "Assumptions PDF (Volume)",
        "ai_reasoning": "the PDF lands here; the user can drop their own PDF into the same Volume to replace it"
      }
    ],
    "edges": [
      {
        "id": "e1",
        "from": "src-model",
        "to": "lakeflow-genie-block@in-lakeflow-connect",
        "flow": true
      },
      {
        "id": "e10",
        "from": "sql-lakehouse",
        "to": "genie",
        "flow": true
      },
      {
        "id": "e11",
        "from": "alert",
        "to": "genie-one",
        "label": "1 · Click through"
      },
      {
        "id": "e12",
        "from": "genie-one",
        "to": "genie",
        "label": "2 · Ask why"
      },
      {
        "id": "e13",
        "from": "genie-one",
        "to": "ai-bi-dashboard",
        "label": "3 · Go deeper"
      },
      {
        "id": "e2",
        "from": "src-market",
        "to": "lakeflow-genie-block@in-lakeflow-connect",
        "flow": true
      },
      {
        "id": "e3",
        "from": "src-policy",
        "to": "lakeflow-genie-block@in-lakeflow-connect",
        "flow": true
      },
      {
        "id": "e4",
        "from": "src-pdf",
        "to": "uc-volume",
        "flow": true
      },
      {
        "id": "e5",
        "from": "uc-volume",
        "to": "doc-parse",
        "flow": true,
        "label": "ai_parse_document"
      },
      {
        "id": "e6",
        "from": "lakeflow-genie-block",
        "to": "sql-lakehouse",
        "flow": true
      },
      {
        "id": "e7",
        "from": "doc-parse",
        "to": "sql-lakehouse",
        "flow": true,
        "label": "Parsed memo table"
      },
      {
        "id": "e8",
        "from": "sql-lakehouse",
        "to": "alert",
        "flow": true,
        "label": "Scheduled query"
      },
      {
        "id": "e9",
        "from": "sql-lakehouse",
        "to": "ai-bi-dashboard",
        "flow": true
      }
    ]
  }
]
```
