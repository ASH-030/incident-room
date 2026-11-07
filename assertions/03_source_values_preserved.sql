-- Compare directly with the independent raw source. Missing values stay missing.
SELECT r.source_row AS raw_source_row, l.source_row AS line_source_row
FROM `incident-room-514005.incident_room_presentation.retail_raw` AS r
FULL OUTER JOIN `incident-room-514005.incident_room_presentation.retail_lines` AS l
  ON r.source_row = l.source_row
WHERE r.source_row IS NULL OR l.source_row IS NULL
   OR r.invoice_no IS DISTINCT FROM l.invoice_no
   OR r.stock_code IS DISTINCT FROM l.stock_code
   OR r.description IS DISTINCT FROM l.description
   OR r.quantity IS DISTINCT FROM l.quantity
   OR r.invoice_at IS DISTINCT FROM l.invoice_at
   OR r.unit_price IS DISTINCT FROM l.unit_price
   OR r.customer_id IS DISTINCT FROM l.customer_id
   OR r.country IS DISTINCT FROM l.country
