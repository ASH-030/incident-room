-- Arithmetic invoice values, including cancellations and other adjustments.
-- These measures do not establish payment settlement or revenue recognition.
SELECT
  invoice_date,
  country,
  COUNT(*) AS source_row_count,
  COUNTIF(is_cancellation) AS cancellation_row_count,
  COUNTIF(has_negative_quantity) AS negative_quantity_row_count,
  COUNTIF(has_missing_customer) AS missing_customer_row_count,
  SUM(IF(NOT is_cancellation, signed_line_value_gbp, NUMERIC '0')) AS non_cancellation_value_gbp,
  SUM(IF(is_cancellation, signed_line_value_gbp, NUMERIC '0')) AS cancellation_value_gbp,
  SUM(signed_line_value_gbp) AS signed_invoice_value_gbp
FROM `incident-room-514005.incident_room_presentation.retail_lines`
WHERE NOT is_cancellation
GROUP BY invoice_date, country
