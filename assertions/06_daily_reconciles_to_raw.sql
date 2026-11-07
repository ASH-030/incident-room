-- Recompute controls from RAW, not from the transformed line values being tested.
WITH expected AS (
  SELECT
    DATE(invoice_at) AS invoice_date,
    country,
    COUNT(*) AS source_row_count,
    COUNTIF(STARTS_WITH(UPPER(invoice_no), 'C')) AS cancellation_row_count,
    COUNTIF(quantity < 0) AS negative_quantity_row_count,
    COUNTIF(customer_id IS NULL) AS missing_customer_row_count,
    SUM(IF(NOT STARTS_WITH(UPPER(invoice_no), 'C'), CAST(quantity AS NUMERIC) * unit_price, NUMERIC '0')) AS non_cancellation_value_gbp,
    SUM(IF(STARTS_WITH(UPPER(invoice_no), 'C'), CAST(quantity AS NUMERIC) * unit_price, NUMERIC '0')) AS cancellation_value_gbp,
    SUM(CAST(quantity AS NUMERIC) * unit_price) AS signed_invoice_value_gbp
  FROM `incident-room-514005.incident_room_presentation.retail_raw`
  GROUP BY invoice_date, country
), compared AS (
  SELECT 'expected' AS asset, * FROM expected
  UNION ALL
  SELECT 'actual' AS asset,
    invoice_date, country, source_row_count, cancellation_row_count,
    negative_quantity_row_count, missing_customer_row_count,
    non_cancellation_value_gbp, cancellation_value_gbp, signed_invoice_value_gbp
  FROM `incident-room-514005.incident_room_presentation.retail_daily`
)
-- GROUP BY preserves null keys and distinguishes them from empty strings.
-- Cardinality checks expose missing, extra and duplicate daily groups.
SELECT invoice_date, country,
  COUNTIF(asset = 'expected') AS expected_groups,
  COUNTIF(asset = 'actual') AS actual_groups,
  SUM(IF(asset = 'expected', signed_invoice_value_gbp, NULL)) AS expected_value_gbp,
  SUM(IF(asset = 'actual', signed_invoice_value_gbp, NULL)) AS actual_value_gbp
FROM compared
GROUP BY invoice_date, country
HAVING COUNTIF(asset = 'expected') != 1 OR COUNTIF(asset = 'actual') != 1
   OR SUM(IF(asset = 'expected', source_row_count, NULL)) IS DISTINCT FROM SUM(IF(asset = 'actual', source_row_count, NULL))
   OR SUM(IF(asset = 'expected', cancellation_row_count, NULL)) IS DISTINCT FROM SUM(IF(asset = 'actual', cancellation_row_count, NULL))
   OR SUM(IF(asset = 'expected', negative_quantity_row_count, NULL)) IS DISTINCT FROM SUM(IF(asset = 'actual', negative_quantity_row_count, NULL))
   OR SUM(IF(asset = 'expected', missing_customer_row_count, NULL)) IS DISTINCT FROM SUM(IF(asset = 'actual', missing_customer_row_count, NULL))
   OR SUM(IF(asset = 'expected', non_cancellation_value_gbp, NULL)) IS DISTINCT FROM SUM(IF(asset = 'actual', non_cancellation_value_gbp, NULL))
   OR SUM(IF(asset = 'expected', cancellation_value_gbp, NULL)) IS DISTINCT FROM SUM(IF(asset = 'actual', cancellation_value_gbp, NULL))
   OR SUM(IF(asset = 'expected', signed_invoice_value_gbp, NULL)) IS DISTINCT FROM SUM(IF(asset = 'actual', signed_invoice_value_gbp, NULL))
