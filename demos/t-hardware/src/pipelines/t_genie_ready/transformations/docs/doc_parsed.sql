-- Docs: ai_parse_document over the binary files landed by the (simulated) SharePoint and HubSpot connectors.
-- Markdown business rules are plain text and skip parsing (handled in silver_doc_chunks).

CREATE OR REFRESH MATERIALIZED VIEW silver_doc_parsed (
  doc_id STRING NOT NULL COMMENT 'Unique document id (UC volume path)',
  doc_name STRING COMMENT 'File name',
  source STRING COMMENT 'Source system: SharePoint or HubSpot',
  folder STRING COMMENT 'SharePoint folder, or Ticket attachment for HubSpot',
  ticket_id BIGINT COMMENT 'HubSpot ticket id (HubSpot attachments only)',
  modified_time TIMESTAMP COMMENT 'Last modified / uploaded time',
  parsed VARIANT COMMENT 'ai_parse_document v2.0 output (document.elements, pages, metadata, error_status)',
  CONSTRAINT pk_doc_parsed PRIMARY KEY (doc_id)
)
COMMENT 'Parsed SharePoint documents (PDF/DOCX) and HubSpot attachments (PDF quotes, JPG/PNG photos and screenshots) via ai_parse_document.'
AS WITH files AS (
  SELECT path AS doc_id, file_name AS doc_name, 'SharePoint' AS source, folder, CAST(NULL AS BIGINT) AS ticket_id, modified_time, content
  FROM bronze_sharepoint_files WHERE lower(file_name) NOT LIKE '%.md'
  UNION ALL
  SELECT path, file_name, 'HubSpot', 'Ticket attachment', ticket_id, uploaded_at, content
  FROM bronze_hubspot_attachments
)
SELECT doc_id, doc_name, source, folder, ticket_id, modified_time,
  ai_parse_document(content, map('version', '2.0')) AS parsed
FROM files;
