-- Gold: one row per document with an AI summary (ai_summarize) and key fields (ai_extract): warranty terms, install steps, etc.

CREATE OR REFRESH MATERIALIZED VIEW gold_doc_summaries (
  doc_id STRING NOT NULL COMMENT 'Document id (UC volume path)',
  doc_name STRING COMMENT 'Document file name',
  source STRING COMMENT 'SharePoint or HubSpot',
  folder STRING COMMENT 'SharePoint folder or Ticket attachment',
  ticket_id BIGINT COMMENT 'HubSpot ticket id for ticket attachments',
  chunk_count INT COMMENT 'Number of chunks in silver_doc_chunks',
  summary STRING COMMENT 'AI summary of the document (ai_summarize, about 60 words)',
  document_type STRING COMMENT 'AI-extracted type: spec sheet, installation SOP, warranty policy, returns SOP, HR policy, business rule, pricing policy, quote, photo or screenshot',
  product_family STRING COMMENT 'AI-extracted product family the document covers (e.g. Door closers, Exit devices), if any',
  warranty_terms STRING COMMENT 'AI-extracted warranty periods / terms stated in the document, if any',
  install_steps ARRAY<STRING> COMMENT 'AI-extracted ordered installation steps, if the document is an installation procedure',
  key_policy_points ARRAY<STRING> COMMENT 'AI-extracted key rules or policy points (returns windows, fees, definitions, discount limits)',
  CONSTRAINT pk_doc_summaries PRIMARY KEY (doc_id)
)
COMMENT 'Document catalogue for TAI: AI summary plus extracted warranty terms, installation steps and policy points for every SharePoint document and HubSpot attachment.'
AS WITH docs AS (
  SELECT doc_id, any_value(doc_name) AS doc_name, any_value(source) AS source, any_value(folder) AS folder, any_value(ticket_id) AS ticket_id,
         CAST(count(*) AS INT) AS chunk_count,
         left(concat_ws('\n\n', transform(array_sort(collect_list(struct(chunk_id, chunk_text))), x -> x.chunk_text)), 20000) AS full_text
  FROM silver_doc_chunks GROUP BY doc_id
), ext AS (
  SELECT *, ai_summarize(full_text, 60) AS summary,
    ai_extract(full_text,
      '{"document_type": {"type": "enum", "labels": ["spec sheet", "installation SOP", "warranty policy", "returns SOP", "HR policy", "business rule", "pricing policy", "quote", "photo", "screenshot", "other"]},
        "product_family": {"type": "string", "description": "Product family covered, e.g. Door closers, Exit devices, Mortise locks, Lever sets, Faucets, Grab bars; null if general"},
        "warranty_terms": {"type": "string", "description": "All warranty periods and terms stated, concise; null if none"},
        "install_steps": {"type": "array", "description": "Ordered installation steps, only for installation procedures", "items": {"type": "string"}},
        "key_policy_points": {"type": "array", "description": "Up to 5 key rules, definitions, fees, limits or deadlines", "items": {"type": "string"}}}',
      map('version', '2.1', 'instructions', 'Documents from T Industries, a Canadian distributor of door hardware and bathroom fixtures.')) AS x
  FROM docs
)
SELECT doc_id, doc_name, source, folder, ticket_id, chunk_count, summary,
  x:response.document_type.value::STRING AS document_type,
  x:response.product_family.value::STRING AS product_family,
  x:response.warranty_terms.value::STRING AS warranty_terms,
  transform(CAST(x:response.install_steps AS ARRAY<VARIANT>), s -> s:value::STRING) AS install_steps,
  transform(CAST(x:response.key_policy_points AS ARRAY<VARIANT>), s -> s:value::STRING) AS key_policy_points
FROM ext;
