-- Silver: section-level chunks of every document (parsed PDFs/DOCX/images + markdown business rules).
-- A chunk = one section header plus the elements under it, prefixed with the document name for retrieval context.

CREATE OR REFRESH MATERIALIZED VIEW silver_doc_chunks (
  chunk_id STRING NOT NULL COMMENT 'Unique chunk id (<doc_id>#<section number>)',
  doc_id STRING COMMENT 'Document id (UC volume path)',
  doc_name STRING COMMENT 'Document file name',
  source STRING COMMENT 'SharePoint or HubSpot',
  folder STRING COMMENT 'SharePoint folder (Product Spec Sheets, Installation SOPs, Customer Service SOPs, HR, Business Rules, Pricing) or Ticket attachment',
  ticket_id BIGINT COMMENT 'HubSpot ticket id for ticket attachments',
  section STRING COMMENT 'Section heading the chunk belongs to (e.g. Warranty, Installation steps)',
  page INT COMMENT '1-based page number where the section starts',
  chunk_text STRING COMMENT 'Chunk text: document name, section heading and section content (tables as HTML)',
  CONSTRAINT pk_doc_chunks PRIMARY KEY (chunk_id)
)
COMMENT 'Section-level text chunks of SharePoint documents, HubSpot attachments and markdown business rules, ready for Genie / vector search.'
AS WITH el AS (
  SELECT d.doc_id, d.doc_name, d.source, d.folder, d.ticket_id, e.pos,
         e.col:type::STRING AS etype, coalesce(e.col:bbox[0].page_id::INT, 0) + 1 AS page, e.col:content::STRING AS txt
  FROM silver_doc_parsed d
  LATERAL VIEW posexplode(CAST(d.parsed:document.elements AS ARRAY<VARIANT>)) e AS pos, col
  WHERE is_variant_null(d.parsed:error_status)
), sec AS (
  SELECT *, sum(CASE WHEN etype IN ('title', 'section_header') THEN 1 ELSE 0 END) OVER (PARTITION BY doc_id ORDER BY pos) AS sec_no
  FROM el WHERE etype NOT IN ('page_header', 'page_footer', 'page_number') AND txt IS NOT NULL
), grouped AS (
  SELECT doc_id, doc_name, source, folder, ticket_id, sec_no, min(page) AS page,
         max_by(CASE WHEN etype IN ('title', 'section_header') THEN txt END, CASE WHEN etype IN ('title', 'section_header') THEN 1 ELSE 0 END) AS section,
         concat_ws('\n', transform(array_sort(collect_list(struct(pos, txt))), x -> x.txt)) AS body
  FROM sec GROUP BY ALL
), md AS (   -- markdown business rules: one chunk per file, no parsing needed
  SELECT path AS doc_id, file_name AS doc_name, 'SharePoint' AS source, folder, CAST(NULL AS BIGINT) AS ticket_id, 1 AS sec_no, 1 AS page,
         regexp_extract(CAST(content AS STRING), '^# *([^\n]+)', 1) AS section, CAST(content AS STRING) AS body
  FROM bronze_sharepoint_files WHERE lower(file_name) LIKE '%.md'
)
SELECT concat(doc_id, '#', sec_no) AS chunk_id, doc_id, doc_name, source, folder, ticket_id,
       coalesce(section, doc_name) AS section, page,
       concat('Document: ', regexp_replace(doc_name, '\\.[a-z]+$', ''), '\nSection: ', coalesce(section, ''), '\n', body) AS chunk_text
FROM (SELECT * FROM grouped UNION ALL SELECT * FROM md);
