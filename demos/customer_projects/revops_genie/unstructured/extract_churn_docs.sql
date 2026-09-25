-- RevOps — churn/QBR PDFs → fact_churn_reason
-- ai_parse_document reads each PDF's binary into text; ai_extract pulls typed
-- fields; the final table unpivots each doc into 3 reason lines. Materialized
-- once into Delta (per-row LLM calls), never re-run per query.
-- Objects: solution_builder.demo_revops_intelligence

-- Stage 1 — parse the PDF binaries into text.
CREATE OR REPLACE TABLE solution_builder.demo_revops_intelligence.raw_churn_parsed AS
SELECT
  path,
  regexp_extract(path, 'qbr_(ACCT[0-9]+)_', 1)          AS account_id,
  regexp_extract(path, 'qbr_ACCT[0-9]+_([0-9]{4})', 1)  AS month_tag,
  concat_ws('\n', transform(CAST(parsed:document:elements AS ARRAY<VARIANT>), e -> e:content::STRING)) AS text_blocks,
  parsed:error_status AS parse_error
FROM (
  SELECT path, content, ai_parse_document(content, map('version','2.0')) AS parsed
  FROM read_files('/Volumes/solution_builder/demo_revops_intelligence/raw_churn_docs/pdf/',
                  format => 'binaryFile')
)
WHERE parsed:error_status::STRING IS NULL;

-- Stage 2 — extract typed fields from the parsed text.
CREATE OR REPLACE TABLE solution_builder.demo_revops_intelligence.churn_extracted AS
SELECT
  path, account_id, month_tag,
  result:response:account_name::STRING          AS account_name,
  result:response:competitor_named::STRING      AS competitor_named,
  result:response:feature_requested::STRING     AS feature_requested,
  result:response:renewed_arr::DOUBLE           AS renewed_arr,
  result:response:competitive_loss_arr::DOUBLE  AS competitive_loss_arr,
  result:response:feature_gap_arr::DOUBLE       AS feature_gap_arr,
  result:error_message::STRING                  AS extract_error
FROM (
  SELECT *, ai_extract(text_blocks,
    '{"account_name":{"type":"string"},"competitor_named":{"type":"string"},'
    '"feature_requested":{"type":"string"},"renewed_arr":{"type":"number"},'
    '"competitive_loss_arr":{"type":"number"},"feature_gap_arr":{"type":"number"}}',
    map('version','2.0')) AS result
  FROM solution_builder.demo_revops_intelligence.raw_churn_parsed
  WHERE text_blocks IS NOT NULL
);

-- Stage 3 — unpivot to fact_churn_reason (document × reason_category).
CREATE OR REPLACE TABLE solution_builder.demo_revops_intelligence.fact_churn_reason
COMMENT 'Churn reasons extracted from 16 QBR/cancellation PDFs via ai_parse_document + ai_extract. Grain: document × reason_category. lost_arr_usd is 0 for Renewed.'
AS
WITH base AS (
  SELECT
    concat('QBR-', account_id, '-', month_tag) AS doc_id,
    account_id,
    account_name,
    to_date(concat('2026-', substr(month_tag,1,2), '-15')) AS doc_date,
    to_date(concat('2026-', substr(month_tag,1,2), '-01')) AS period,
    'SEG-MM' AS segment_id,
    competitor_named, feature_requested,
    coalesce(renewed_arr,0) renewed_arr,
    coalesce(competitive_loss_arr,0) competitive_loss_arr,
    coalesce(feature_gap_arr,0) feature_gap_arr
  FROM solution_builder.demo_revops_intelligence.churn_extracted
)
SELECT doc_id, account_id, account_name, doc_date, period, segment_id,
       'Renewed' AS reason_category, CAST(NULL AS STRING) AS competitor_named, renewed_arr AS lost_arr_usd
FROM base
UNION ALL
SELECT doc_id, account_id, account_name, doc_date, period, segment_id,
       'Competitive Displacement' AS reason_category, competitor_named, competitive_loss_arr AS lost_arr_usd
FROM base
UNION ALL
SELECT doc_id, account_id, account_name, doc_date, period, segment_id,
       'Missing-Feature Downgrade' AS reason_category, CAST(NULL AS STRING) AS competitor_named, feature_gap_arr AS lost_arr_usd
FROM base;
