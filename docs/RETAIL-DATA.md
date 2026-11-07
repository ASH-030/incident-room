# Retail invoice warehouse

Real historical UCI Online Retail records, loaded into `incident-room-514005.incident_data` for Incident Room investigations.

## Lineage

`retail_raw` -> `models/retail_lines.sql` -> `retail_lines` -> `models/retail_daily.sql` -> `retail_daily`

The ordered SQL files are standalone GoogleSQL SELECTs. Bootstrap runs them once with WRITE_EMPTY destinations. The Incident Room app reads these assets and tests proposed changes by cloning all three tables into an isolated validation dataset.

## Metric definitions

- Source grain: one original workbook row. `source_row` identifies that row; invoice/product combinations are not assumed unique.
- `signed_line_value_gbp` is the original signed quantity multiplied by the source unit price, using NUMERIC arithmetic at source precision. Negative and zero prices/quantities are retained and flagged. No exclusions, deduplication, currency conversion or per-line rounding are applied.
- A cancellation flag means the invoice identifier begins with C, case-insensitively, following the source documentation. Negative quantity alone does not establish the reason for an adjustment.
- Non-cancellation value includes every row without the C prefix, including negative adjustments. Cancellation value includes every C-prefixed row. Their sum equals signed invoice value.
- Daily grouping uses the source invoice date and country, including missing grouping values. Source DATETIME is a wall-clock value with no inferred timezone.
- Missing customer identifiers and descriptions remain missing. No customer payment, settlement, tax, cost, margin or recognition data is available. Invoice arithmetic must not be presented as verified recognized revenue or cash collections.

These are explicit initial technical contracts. Finance still confirms the desired business metric and reporting window inside the app. The agent can conclude that a difference is a definition issue rather than inventing a repair.

## Independent checks

Six SQL assertions return violating records: required source fields, unique source-row keys, complete preservation of original values, exact line arithmetic/flags, unique daily groups, and a daily reconciliation calculated directly from raw inputs. A missing customer is a diagnostic, not automatically an invalid transaction. All check SQL is copied into the application's local project configuration.

## Source and reproducibility

Chen, D. (2015). Online Retail [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C5BW33.

Source: https://archive.ics.uci.edu/dataset/352/online+retail. License: CC BY 4.0, https://creativecommons.org/licenses/by/4.0/.

The unmodified workbook, archive, converted CSV, schema, conversion script and SHA256 provenance manifest are stored in `D:/SwitchHackathon/data/uci-online-retail`. All 541,909 source rows were retained during conversion.

## Publication

Initial SQL and future agent-produced commits use the repository-local Incident Room automation identity. Independent human reviewers are recorded separately in the application's audit history. A tested repair branch remains separate from the main checkout; applying it to live output tables requires the normal reviewed deployment step. The bootstrap helper never overwrites existing output tables.
