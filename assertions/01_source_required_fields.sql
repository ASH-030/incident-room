-- Customer ID and description can be missing. Required arithmetic keys cannot.
SELECT source_row, invoice_no, quantity, invoice_at, unit_price
FROM `incident-room-514005.incident_room_presentation.retail_raw`
WHERE source_row IS NULL OR invoice_no IS NULL OR quantity IS NULL
   OR invoice_at IS NULL OR unit_price IS NULL
