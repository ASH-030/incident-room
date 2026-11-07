SELECT 'raw' AS asset, source_row, COUNT(*) AS occurrences
FROM `incident-room-514005.incident_room_presentation.retail_raw`
GROUP BY source_row HAVING COUNT(*) != 1
UNION ALL
SELECT 'lines' AS asset, source_row, COUNT(*) AS occurrences
FROM `incident-room-514005.incident_room_presentation.retail_lines`
GROUP BY source_row HAVING COUNT(*) != 1
