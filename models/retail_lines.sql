-- Preserve the complete invoice-line ledger; add arithmetic and diagnostic flags.
-- Source invoice times are wall-clock DATETIME, not an asserted UTC timestamp.
SELECT
  source_row,
  invoice_no,
  stock_code,
  description,
  quantity,
  invoice_at,
  unit_price,
  customer_id,
  country,
  DATE(invoice_at) AS invoice_date,
  CAST(quantity AS NUMERIC) * unit_price AS signed_line_value_gbp,
  STARTS_WITH(UPPER(invoice_no), 'C') AS is_cancellation,
  quantity < 0 AS has_negative_quantity,
  unit_price <= 0 AS has_nonpositive_price,
  customer_id IS NULL AS has_missing_customer
FROM `incident-room-514005.incident_room_presentation.retail_raw`
