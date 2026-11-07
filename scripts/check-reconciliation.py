"""Run the real reconciliation assertion against targeted BigQuery regression inputs.

No warehouse table is changed. Null and empty-string keys, missing/extra/duplicate
groups, incorrect values and missing amounts must preserve their distinct meanings.
Run using Incident Room's Python environment, which supplies google-cloud-bigquery.
"""
from pathlib import Path
from google.cloud import bigquery

ROOT=Path(__file__).resolve().parents[1]
RAW='''SELECT '100' AS invoice_no, 1 AS quantity, DATETIME '2011-01-01 09:00:00' AS invoice_at,
  NUMERIC '10' AS unit_price, '123' AS customer_id, CAST(NULL AS STRING) AS country
UNION ALL SELECT 'C101', -1, DATETIME '2011-01-01 10:00:00', NUMERIC '2.5', CAST(NULL AS STRING), '' '''
DAILY='''SELECT DATE '2011-01-01' AS invoice_date, CAST(NULL AS STRING) AS country,
  1 AS source_row_count, 0 AS cancellation_row_count, 0 AS negative_quantity_row_count,
  0 AS missing_customer_row_count, NUMERIC '10' AS non_cancellation_value_gbp,
  NUMERIC '0' AS cancellation_value_gbp, NUMERIC '10' AS signed_invoice_value_gbp
UNION ALL SELECT DATE '2011-01-01', '', 1, 1, 1, 1, NUMERIC '0', NUMERIC '-2.5', NUMERIC '-2.5' '''


def main():
    assertion=(ROOT/'assertions/06_daily_reconciles_to_raw.sql').read_text(encoding='utf-8')
    assertion=assertion.replace('`incident-room-514005.incident_room_presentation.retail_raw`','raw_input')
    assertion=assertion.replace('`incident-room-514005.incident_room_presentation.retail_daily`','daily_input')
    scenarios=[
        ('null_and_empty_keys_match',DAILY,0),
        ('wrong_signed_value','SELECT * REPLACE(IF(country IS NULL, NUMERIC \'11\', signed_invoice_value_gbp) AS signed_invoice_value_gbp) FROM baseline',1),
        ('missing_null_group','SELECT * FROM baseline WHERE country IS NOT NULL',1),
        ('extra_group',"SELECT * FROM baseline UNION ALL SELECT DATE '2011-01-02', 'France', 1, 0, 0, 0, NUMERIC '1', NUMERIC '0', NUMERIC '1'",1),
        ('duplicate_null_group','SELECT * FROM baseline UNION ALL SELECT * FROM baseline WHERE country IS NULL',1),
        ('wrong_cancellation_sign',"SELECT * REPLACE(IF(country = '', NUMERIC '2.5', cancellation_value_gbp) AS cancellation_value_gbp) FROM baseline",1),
        ('null_is_not_a_valid_amount','SELECT * REPLACE(IF(country IS NULL, CAST(NULL AS NUMERIC), signed_invoice_value_gbp) AS signed_invoice_value_gbp) FROM baseline',1),
    ]
    cases=[]
    for name,actual,wanted in scenarios:
        body=assertion.replace('WITH expected AS (',f'WITH raw_input AS ({RAW}), baseline AS ({DAILY}), daily_input AS ({actual}), expected AS (',1)
        cases.append(f"SELECT '{name}' AS case_name, COUNT(*) AS actual_violations, {wanted} AS expected_violations FROM ({body})")
    sql='\nUNION ALL\n'.join(cases)
    client=bigquery.Client(project='incident-room-514005',location='US')
    dry=client.query(sql,job_config=bigquery.QueryJobConfig(dry_run=True,use_query_cache=False),timeout=20)
    if dry.referenced_tables:raise ValueError('Regression inputs unexpectedly reference a warehouse table')
    job=client.query(sql,job_config=bigquery.QueryJobConfig(maximum_bytes_billed=10_485_760,use_query_cache=False),timeout=20)
    try:results=list(job.result(timeout=60))
    except BaseException:
        job.cancel()
        raise
    for row in results:
        if row.actual_violations!=row.expected_violations:raise AssertionError(dict(row))
        print('PASS:',row.case_name)
    print(f'BigQuery reconciliation regression cases passed: {len(results)}/{len(scenarios)}')


if __name__=='__main__':main()
