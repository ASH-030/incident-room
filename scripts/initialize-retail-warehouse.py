"""Create the two configured retail outputs once, then run independent controls.

Existing output data is never replaced. This helper is for initial warehouse setup,
not for deploying repairs. Every query has a dry run and the configured byte cap.
"""
import argparse
import hashlib
import json
from pathlib import Path
from google.cloud import bigquery
from google.api_core.exceptions import NotFound,Conflict
from sqlglot import parse_one,exp
from incident_room.bigquery_project import BigQueryProject

ROOT=Path(__file__).resolve().parents[1]
DESCRIPTIONS={
    'retail_lines':'UCI Online Retail, Chen (2015), DOI 10.24432/C5BW33, CC BY 4.0. Complete original invoice lines; signed_line_value_gbp = quantity * unit_price at source precision. Cancellation means invoice identifier begins with C. Negative/zero prices and quantities and missing customer IDs remain present. invoice_date uses source wall-clock DATETIME. Invoice arithmetic does not establish settlement or recognized revenue.',
    'retail_daily':'UCI Online Retail daily invoice arithmetic grouped by source invoice date and country. Includes every source row. Non-cancellation and C-prefixed cancellation values sum to signed invoice value. Negative non-cancellation adjustments are included. GBP NUMERIC at original source precision. Counts track source rows, cancellations, negative quantities and missing customer IDs. No payment settlement or revenue-recognition claim.',
}


def wait(job,seconds):
    try:return job.result(timeout=seconds,max_results=1,job_retry=None)
    except BaseException:
        job.cancel()
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-only',action='store_true',help='Validate local configuration and dry-run only queries whose dependencies already exist; do not create output tables')
    args=parser.parse_args()
    project=BigQueryProject(ROOT/'config'/'project.local.json')
    source=project.client.get_table('incident-room-514005.incident_data.retail_raw',timeout=20,retry=None)
    if source.table_type!='TABLE' or not source.num_rows:raise ValueError('Load the attributed raw transaction table first')
    report={'project':project.config.name,'source_rows':source.num_rows,'outputs':[],'mode':'check-only' if args.check_only else 'initialize'}
    pending=set()
    for file in project.config.transforms:
        target=project.config.outputs[file]
        content=project.read_transform(file)['content']
        sql=project.rewrite(content,project.source_map)
        stamp=hashlib.sha256(content.encode('utf-8')).hexdigest()
        marker='Bootstrap transform SHA256: '+stamp
        try:existing=project.client.get_table(target,timeout=20,retry=None)
        except NotFound:existing=None
        if existing and marker not in (existing.description or ''):
            raise ValueError('Existing output has no matching bootstrap provenance: '+target+'. No overwrite was attempted; inspect it before proceeding.')
        dependencies={'.'.join(p.name for p in t.parts) for t in parse_one(sql,read='bigquery').find_all(exp.Table)}
        if args.check_only and dependencies & pending:
            pending.add(target)
            print('Deferred dry run until upstream output exists:',file,flush=True)
            continue
        dry=project.client.query(sql,job_config=bigquery.QueryJobConfig(dry_run=True,use_query_cache=False),location=project.config.location,timeout=20)
        allowed=set(project.config.tables)
        if dry.statement_type!='SELECT' or any(f'{t.project}.{t.dataset_id}.{t.table_id}' not in allowed for t in dry.referenced_tables or []):raise ValueError('Unexpected transform statement or table dependency')
        estimate=dry.total_bytes_processed or 0
        if estimate>project.config.maximum_bytes_billed:raise ValueError('Dry-run estimate exceeds the configured query ceiling')
        print('Dry run:',file,'estimated bytes:',estimate,flush=True)
        if args.check_only:
            if not existing:pending.add(target)
            report['outputs'].append({'table':target,'estimated_bytes':estimate,'exists':existing is not None})
            continue
        if not existing:
            config=bigquery.QueryJobConfig(destination=target,write_disposition=bigquery.WriteDisposition.WRITE_EMPTY,maximum_bytes_billed=project.config.maximum_bytes_billed,use_query_cache=False,labels={'app':'incident-room','purpose':'initial-warehouse'})
            job_id='incident_room_init_'+target.rsplit('.',1)[1]+'_'+stamp[:24]
            print('Creating:',target,'job:',job_id,flush=True)
            try:job=project.client.query(sql,job_config=config,job_id=job_id,job_retry=None,location=project.config.location,timeout=30)
            except Conflict:
                job=project.client.get_job(job_id,location=project.config.location,timeout=20)
                if str(job.destination)!=target:raise ValueError('The existing job destination does not match this transform')
            wait(job,project.config.query_timeout_seconds)
            existing=project.client.get_table(target,timeout=20,retry=None)
            existing.description=DESCRIPTIONS[target.rsplit('.',1)[1]]+' '+marker
            project.client.update_table(existing,['description'],timeout=20)
        print('Output ready:',target,'rows:',existing.num_rows,flush=True)
        report['outputs'].append({'table':target,'rows':existing.num_rows,'bootstrap_sql_sha256':stamp})
    if args.check_only:
        print('Local configuration and available dry runs passed. No output tables were created.')
        return
    print('Running six independent assertions and configured metric queries...',flush=True)
    verification=project.verify(project.source_map)
    report['verification']=verification
    runtime=ROOT/'runtime';runtime.mkdir(exist_ok=True)
    (runtime/'retail-initialization.json').write_text(json.dumps(report,indent=2,default=str),encoding='utf-8')
    passed=sum(c['passed'] for c in verification['checks'])
    print(f'Assertions passed: {passed}/{len(verification["checks"])}',flush=True)
    if not verification['passed']:
        print(json.dumps(verification,indent=2,default=str))
        raise SystemExit('Warehouse checks failed. Inspect runtime/retail-initialization.json before continuing.')
    for metric in verification['metrics']:print(metric['name']+': '+str(metric['value']))
    print('Warehouse ready for investigation.')


if __name__=='__main__':main()
