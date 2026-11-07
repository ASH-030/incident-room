"""Load the prepared, attributed UCI transactions into this project's new raw table.

No rows are filtered or invented. WRITE_EMPTY prevents accidental duplicate appends
or overwrites. A deterministic job ID allows uncertain uploads to be reconciled.
"""
import argparse
import hashlib
import json
from pathlib import Path
from google.cloud import bigquery
from google.api_core.exceptions import NotFound,Conflict

PROJECT='incident-room-514005'
TABLE=PROJECT+'.incident_data.retail_raw'
DATA=Path(__file__).resolve().parents[3]/'data'/'uci-online-retail'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-only',action='store_true',help='Verify local source files and SDK load configuration without contacting Google Cloud')
    args=parser.parse_args()
    manifest=json.loads((DATA/'manifest.json').read_text(encoding='utf-8'))
    csv_path=DATA/'online-retail.csv'
    checksum=hashlib.sha256()
    with csv_path.open('rb') as f:
        for chunk in iter(lambda:f.read(1048576),b''):checksum.update(chunk)
    if checksum.hexdigest()!=manifest['csv_sha256']:raise ValueError('Prepared CSV changed. Review its provenance before uploading.')
    fields=json.loads((DATA/'online-retail.schema.json').read_text(encoding='utf-8'))
    config=bigquery.LoadJobConfig(
        schema=[bigquery.SchemaField.from_api_repr(field) for field in fields],
        source_format=bigquery.SourceFormat.CSV,
        skip_leading_rows=1,
        allow_quoted_newlines=True,
        allow_jagged_rows=False,
        ignore_unknown_values=False,
        max_bad_records=0,
        encoding='UTF-8',
        write_disposition=bigquery.WriteDisposition.WRITE_EMPTY,
        destination_table_description='Public historical UCI Online Retail transactions. Chen, D. (2015), DOI 10.24432/C5BW33, CC BY 4.0. All source rows retained. Prices in GBP; invoice dates are source wall-clock DATETIME. CSV SHA256: '+checksum.hexdigest(),
        labels={'app':'incident-room','source':'uci-online-retail','source_hash':checksum.hexdigest()[:32]},
    )
    if config.to_api_repr()['load']['writeDisposition']!='WRITE_EMPTY':raise ValueError('Invalid write policy')
    if args.check_only:
        print('Local CSV checksum and import schema verified.')
        print('Prepared rows:',manifest['source_rows'])
        print('Destination:',TABLE)
        print('No Google Cloud request was made.')
        return
    client=bigquery.Client(project=PROJECT,location='US')
    dataset=client.get_dataset(PROJECT+'.incident_data',timeout=20,retry=None)
    if dataset.location!='US':raise ValueError('Dataset location must match the configured US location')
    try:
        existing=client.get_table(TABLE,timeout=20,retry=None)
    except NotFound:existing=None
    if existing:
        if checksum.hexdigest() in (existing.description or '') and existing.num_rows==manifest['source_rows']:
            print('The same attributed source is already loaded. No data was appended or changed.')
            print('Verified rows:',existing.num_rows)
            print('Table:',TABLE)
            return
        raise ValueError('The destination table already exists with different or unverified content. No overwrite or append was attempted.')
    job_id='uci_retail_load_'+checksum.hexdigest()[:24]
    print('Uploading the prepared source to:',TABLE,flush=True)
    print('Load job ID:',job_id,flush=True)
    try:
        with csv_path.open('rb') as f:
            job=client.load_table_from_file(f,TABLE,job_config=config,job_id=job_id,location='US',timeout=60,num_retries=3)
    except Conflict:
        job=client.get_job(job_id,location='US',timeout=20)
        if str(job.destination)!=TABLE:raise ValueError('Existing load job has an unexpected destination; inspect it before retrying')
        print('Resuming the existing load job; no duplicate job was submitted.',flush=True)
    job.result(timeout=180)
    table=client.get_table(TABLE,timeout=20,retry=None)
    if table.num_rows!=manifest['source_rows']:raise ValueError('Loaded row count differs from the verified source; inspect the load job')
    print('Verified rows:',table.num_rows)
    print('Table:',TABLE)
    print('Next: configure the SQL transforms and business assertions for investigation.')


if __name__=='__main__':main()
