SELECT invoice_date, country, COUNT(*) AS occurrences
FROM `incident-room-514005.incident_room_presentation.retail_daily`
GROUP BY invoice_date, country HAVING COUNT(*) != 1
