-- Gold: service ticket fact (HubSpot tickets x ERP orders x products) for ticket-theme analysis.

CREATE OR REFRESH MATERIALIZED VIEW gold_ticket_insights (
  ticket_id BIGINT NOT NULL COMMENT 'HubSpot ticket id',
  created_date DATE COMMENT 'Ticket created date',
  theme STRING COMMENT 'AI-classified ticket theme (Finish defect, Backorder / late delivery, Wrong item shipped, Damaged in transit, Installation question, Warranty claim, Pricing / invoice dispute)',
  subject STRING COMMENT 'Ticket subject',
  status STRING COMMENT 'Ticket stage',
  is_open BOOLEAN COMMENT 'Ticket not closed',
  priority STRING COMMENT 'LOW, MEDIUM or HIGH',
  days_to_close DOUBLE COMMENT 'Days from creation to close',
  customer_id STRING COMMENT 'ERP customer id (FK dim_customer)',
  customer_name STRING COMMENT 'Customer name',
  region STRING COMMENT 'Customer region: BC, ON or US',
  order_id STRING COMMENT 'Linked ERP sales order (null if unlinked)',
  order_link_method STRING COMMENT 'order_property, ticket_text or unlinked',
  warehouse STRING COMMENT 'Warehouse of the linked order',
  sku STRING COMMENT 'SKU on the ticket (FK dim_product)',
  category STRING COMMENT 'Product category of the SKU',
  finish STRING COMMENT 'Finish of the SKU',
  attachment_count INT COMMENT 'Number of HubSpot attachments (quotes, photos, screenshots)',
  CONSTRAINT pk_ticket_insights PRIMARY KEY (ticket_id)
)
COMMENT 'One row per HubSpot ticket enriched with the linked ERP order, customer, product and AI theme.'
AS SELECT t.ticket_id, to_date(t.created_at) AS created_date, t.theme, t.subject, t.status, t.is_open, t.priority, t.days_to_close,
  t.customer_id, c.customer_name, c.region, t.order_id, t.order_link_method, t.warehouse, t.sku, p.category, p.finish,
  CAST(coalesce(a.n, 0) AS INT) AS attachment_count
FROM silver_hubspot_tickets t
LEFT JOIN silver_customers c ON c.customer_id = t.customer_id
LEFT JOIN silver_products p ON p.sku = t.sku
LEFT JOIN (SELECT ticket_id, count(*) AS n FROM bronze_hubspot_attachments GROUP BY ticket_id) a ON a.ticket_id = t.ticket_id;
