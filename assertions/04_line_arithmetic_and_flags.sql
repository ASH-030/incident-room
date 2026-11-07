SELECT l.source_row
FROM `incident-room-514005.incident_room_presentation.retail_lines` AS l
JOIN `incident-room-514005.incident_room_presentation.retail_raw` AS r ON l.source_row = r.source_row
WHERE l.signed_line_value_gbp IS DISTINCT FROM (CAST(r.quantity AS NUMERIC) * r.unit_price)
   OR l.invoice_date IS DISTINCT FROM DATE(r.invoice_at)
   OR l.is_cancellation IS DISTINCT FROM STARTS_WITH(UPPER(r.invoice_no), 'C')
   OR l.has_negative_quantity IS DISTINCT FROM (r.quantity < 0)
   OR l.has_nonpositive_price IS DISTINCT FROM (r.unit_price <= 0)
   OR l.has_missing_customer IS DISTINCT FROM (r.customer_id IS NULL)
