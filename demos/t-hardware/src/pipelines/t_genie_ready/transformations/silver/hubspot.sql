-- Silver: HubSpot CRM objects conformed to ERP keys. Tickets are linked to sales orders and classified into themes with ai_classify.

CREATE OR REFRESH MATERIALIZED VIEW silver_hubspot_companies (
  company_id BIGINT NOT NULL COMMENT 'HubSpot company id',
  company_name STRING COMMENT 'Company name',
  customer_id STRING COMMENT 'Linked ERP customer id (null for prospects)',
  industry STRING COMMENT 'Industry',
  city STRING COMMENT 'City',
  region STRING COMMENT 'Standardized region: BC, ON or US',
  lifecycle_stage STRING COMMENT 'HubSpot lifecycle stage (customer, lead, opportunity)',
  hubspot_owner STRING COMMENT 'Owner',
  created_at TIMESTAMP COMMENT 'Created timestamp',
  CONSTRAINT pk_hubspot_companies PRIMARY KEY (company_id)
)
COMMENT 'HubSpot companies with standardized regions and the ERP customer link.'
AS SELECT company_id, name AS company_name, erp_customer_id AS customer_id, industry, city,
  CASE WHEN upper(trim(state_region)) IN ('BC','B.C.','BRITISH COLUMBIA') THEN 'BC'
       WHEN upper(trim(state_region)) IN ('ON','ONT.','ONTARIO') THEN 'ON'
       WHEN upper(trim(state_region)) IN ('US','USA','UNITED STATES') THEN 'US' END AS region,
  lifecycle_stage, hubspot_owner, to_timestamp(createdate) AS created_at
FROM bronze_hubspot_companies;

CREATE OR REFRESH MATERIALIZED VIEW silver_hubspot_deals (
  deal_id BIGINT NOT NULL COMMENT 'HubSpot deal id',
  company_id BIGINT COMMENT 'HubSpot company id',
  customer_id STRING COMMENT 'ERP customer id via the company',
  deal_name STRING COMMENT 'Deal (project) name',
  deal_stage STRING COMMENT 'Deal stage',
  is_won BOOLEAN COMMENT 'Deal is closed-won',
  amount_cad DECIMAL(14,2) COMMENT 'Deal amount, CAD',
  close_date DATE COMMENT 'Close date (expected close for open deals)',
  order_id STRING COMMENT 'Linked ERP sales order (closed-won deals)',
  created_date DATE COMMENT 'Deal created date',
  CONSTRAINT pk_hubspot_deals PRIMARY KEY (deal_id)
)
COMMENT 'HubSpot project deals linked to ERP customers and (for closed-won) the resulting sales order.'
AS SELECT d.deal_id, d.company_id, c.erp_customer_id AS customer_id, d.dealname AS deal_name, d.dealstage AS deal_stage,
  d.dealstage = 'closedwon' AS is_won, CAST(d.amount AS DECIMAL(14,2)) AS amount_cad, to_date(d.closedate) AS close_date,
  d.erp_order_id AS order_id, to_date(d.createdate) AS created_date
FROM bronze_hubspot_deals d LEFT JOIN bronze_hubspot_companies c USING (company_id);

CREATE OR REFRESH MATERIALIZED VIEW silver_hubspot_tickets (
  ticket_id BIGINT NOT NULL COMMENT 'HubSpot ticket id',
  company_id BIGINT COMMENT 'HubSpot company id',
  customer_id STRING COMMENT 'ERP customer id (from the linked order, else the company)',
  order_id STRING COMMENT 'ERP sales order resolved from erp_order_number or the ticket text (SO-nnnnnn); null if not found in the ERP',
  order_link_method STRING COMMENT 'How the order was resolved: order_property, ticket_text or unlinked',
  warehouse STRING COMMENT 'Fulfilling warehouse of the linked order',
  sku STRING COMMENT 'SKU referenced on the ticket',
  subject STRING COMMENT 'Ticket subject',
  content STRING COMMENT 'Ticket description',
  theme STRING COMMENT 'AI-classified ticket theme (ai_classify): Finish defect, Backorder / late delivery, Wrong item shipped, Damaged in transit, Installation question, Warranty claim, Pricing / invoice dispute',
  status STRING COMMENT 'Ticket stage (New, Waiting on contact, Waiting on us, Closed)',
  is_open BOOLEAN COMMENT 'Ticket is not closed',
  priority STRING COMMENT 'LOW, MEDIUM or HIGH',
  created_at TIMESTAMP COMMENT 'Created timestamp',
  closed_at TIMESTAMP COMMENT 'Closed timestamp',
  days_to_close DOUBLE COMMENT 'Days from creation to close',
  CONSTRAINT pk_hubspot_tickets PRIMARY KEY (ticket_id)
)
COMMENT 'HubSpot service tickets joined to ERP sales orders and classified into themes with ai_classify.'
AS WITH t AS (
  SELECT *,
    CASE WHEN regexp_extract(erp_order_number, '([0-9]{6})', 1) <> '' THEN concat('SO-', regexp_extract(erp_order_number, '([0-9]{6})', 1)) END AS prop_order,
    CASE WHEN regexp_extract(concat_ws(' ', subject, content), 'SO-([0-9]{6})', 1) <> '' THEN concat('SO-', regexp_extract(concat_ws(' ', subject, content), 'SO-([0-9]{6})', 1)) END AS text_order
  FROM bronze_hubspot_tickets
), cls AS (
  SELECT *, ai_classify(concat(subject, '. ', content),
    '{"Finish defect": "Finish peeling, flaking, discolouring or corroding",
      "Backorder / late delivery": "Waiting on backordered or late units, ETA requests",
      "Wrong item shipped": "Received the wrong SKU or finish",
      "Damaged in transit": "Cartons or product damaged by the carrier",
      "Installation question": "How to install, templates, adjustments, SOP requests",
      "Warranty claim": "Product failed in service and a warranty replacement is requested",
      "Pricing / invoice dispute": "Invoice differs from quote, competitor price match requests"}',
    map('version', '2.1', 'instructions', 'These are customer service tickets for a door hardware and bathroom fixture distributor. Pick the single main issue.')) AS c
  FROM t
)
SELECT cls.ticket_id, cls.company_id,
  coalesce(o.customer_id, co.erp_customer_id) AS customer_id,
  o.order_id,
  CASE WHEN o.order_id IS NULL THEN 'unlinked' WHEN o.order_id = cls.prop_order THEN 'order_property' ELSE 'ticket_text' END AS order_link_method,
  o.warehouse, upper(cls.sku_mentioned) AS sku, cls.subject, cls.content,
  cls.c:response[0].value::STRING AS theme,
  cls.hs_pipeline_stage AS status, cls.hs_pipeline_stage <> 'Closed' AS is_open, cls.hs_ticket_priority AS priority,
  to_timestamp(cls.createdate) AS created_at, to_timestamp(cls.closed_date) AS closed_at,
  round((unix_timestamp(to_timestamp(cls.closed_date)) - unix_timestamp(to_timestamp(cls.createdate))) / 86400, 1) AS days_to_close
FROM cls
LEFT JOIN bronze_hubspot_companies co ON co.company_id = cls.company_id
LEFT JOIN silver_sales_orders o ON o.order_id = coalesce(cls.prop_order, cls.text_order);
