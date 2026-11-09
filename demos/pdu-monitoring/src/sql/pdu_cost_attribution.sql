-- PDU monitoring: daily usage and list-price cost by component, last 30 days.
-- Covers everything tagged project = pdu-monitoring:
--   * jobs (bundle tags + serverless usage policy), pipeline and app (usage policy),
--     Lakebase project (custom_tags in lakebase.yml).
-- Not covered: the shared Serverless Starter Warehouse (alerts, app bronze queries, Genie).
-- system.billing.usage lags a few hours; list_cost_usd is at list price, before discounts.
SELECT
  u.usage_date,
  u.billing_origin_product AS product,
  -- Jobs carry a component tag; pipeline, app and Lakebase are identified by product.
  coalesce(
    u.custom_tags['component'],
    CASE u.billing_origin_product
      WHEN 'DLT' THEN 'pipeline'
      WHEN 'APPS' THEN 'app'
      WHEN 'LAKEBASE' THEN 'lakebase'
    END,
    '(none)'
  ) AS component,
  coalesce(
    u.usage_metadata.job_id,
    u.usage_metadata.dlt_pipeline_id,
    u.usage_metadata.app_name,
    u.usage_metadata.app_id,
    u.usage_metadata.notebook_id
  ) AS resource_id,
  u.custom_tags['environment'] AS environment,
  u.sku_name,
  round(sum(u.usage_quantity), 3) AS usage_quantity,
  first(u.usage_unit) AS usage_unit,
  round(sum(u.usage_quantity * lp.pricing.default), 2) AS list_cost_usd
FROM system.billing.usage u
LEFT JOIN system.billing.list_prices lp
  ON u.sku_name = lp.sku_name
  AND u.cloud = lp.cloud
  AND lp.currency_code = 'USD'
  AND u.usage_start_time >= lp.price_start_time
  AND (lp.price_end_time IS NULL OR u.usage_start_time < lp.price_end_time)
WHERE u.custom_tags['project'] = 'pdu-monitoring'
  AND u.usage_date >= current_date() - INTERVAL 30 DAYS
GROUP BY ALL
ORDER BY u.usage_date DESC, list_cost_usd DESC
