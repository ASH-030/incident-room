"""Acceptance test of the real repair engine against isolated BigQuery table clones.

Uses real OpenAI, BigQuery, Git and workflow code. Test reviewers are explicitly
automated acceptance identities in a separate database, never production users.
The baseline invoice warehouse is read-only throughout this run.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from uuid import uuid4
from dotenv import load_dotenv
from google.cloud import bigquery
from incident_room.bigquery_project import BigQueryProject
from incident_room.live_service import LiveService
from incident_room.storage import Store
from incident_room.errors import Rejected

ROOT=Path(__file__).resolve().parents[1]


def main():
    load_dotenv(ROOT/'.env')
    os.environ.setdefault('OPENAI_REASONING_EFFORT','medium')
    original=BigQueryProject(os.environ['PROJECT_CONFIG'])
    baseline={name:original.client.get_table(name).etag for name in original.config.tables}
    run_id=uuid4().hex[:12]
    run=ROOT/'runtime'/'acceptance'/run_id
    repo=run/'sql-project';repo.mkdir(parents=True)
    dataset_id=original.config.billing_project+'.incident_room_accept_'+run_id
    client=original.client
    dataset=bigquery.Dataset(dataset_id);dataset.location=original.config.location;dataset.default_table_expiration_ms=3_600_000
    config=original.config.model_dump(mode='json')
    mapping={name:dataset_id+'.'+name.rsplit('.',1)[1] for name in original.config.tables}
    def rewrite_text(sql):
        for source,target in mapping.items():sql=sql.replace('`'+source+'`','`'+target+'`')
        return sql
    for name in config['transforms']:
        path=repo/name;path.parent.mkdir(parents=True,exist_ok=True)
        text=rewrite_text(original.read_transform(name)['content'])
        if name.endswith('retail_daily.sql'):
            if text.count('GROUP BY invoice_date, country')!=1:raise ValueError('Unexpected baseline transform; review the controlled fault')
            text=text.replace('GROUP BY invoice_date, country','WHERE NOT is_cancellation\nGROUP BY invoice_date, country')
        path.write_text(text,encoding='utf-8',newline='')
    (repo/'ACCEPTANCE.md').write_text('Controlled acceptance test. The daily transform deliberately excludes cancellations. Raw source records are unchanged. Automated finance and engineering identities below exercise workflow gates only; they are not independent human approvals.\n',encoding='utf-8')
    (repo/'.gitattributes').write_text('*.sql text eol=lf\n',encoding='utf-8')
    def git(*args):return subprocess.run(['git',*args],cwd=repo,check=True,capture_output=True,text=True).stdout.strip()
    git('init','-b','main');git('config','user.name','Incident Room Acceptance');git('config','user.email','acceptance@localhost');git('config','core.autocrlf','false');git('add','.');git('commit','-m','Acceptance baseline with documented cancellation fault')
    config.update(name='Isolated live repair acceptance '+run_id,project_root=repo.as_posix(),tables=list(mapping.values()),outputs={file:mapping[table] for file,table in config['outputs'].items()},publish_pr=False)
    for check in config['assertions']:check['sql']=rewrite_text(check['sql'])
    for metric in config['metrics']:metric['sql']=rewrite_text(metric['sql'])
    config_path=run/'project.json';config_path.write_text(json.dumps(config,indent=2),encoding='utf-8')
    result={'run_id':run_id,'dataset':dataset_id,'automated_acceptance_reviewers':True,'production_modified':False}
    created=False;service=None
    try:
        client.create_dataset(dataset);created=True
        for source,target in mapping.items():
            job=client.query(f'CREATE TABLE `{target}` CLONE `{source}` OPTIONS(expiration_timestamp=TIMESTAMP_ADD(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR))',location=original.config.location)
            try:job.result(timeout=120)
            except BaseException:job.cancel();raise
        project=BigQueryProject(config_path)
        faulty_file='models/retail_daily.sql'
        faulty=project.read_transform(faulty_file)['content']
        project.execute(project.rewrite(faulty,project.source_map),set(project.config.tables),destination=project.config.outputs[faulty_file])
        before=project.verify(project.source_map)
        if before['passed']:raise ValueError('The controlled fault did not violate the source contract')
        print('Controlled fault detected by:',[c['name'] for c in before['checks'] if not c['passed']],flush=True)
        result['before']=before
        service=LiveService(Store('sqlite:///'+(run/'state.db').as_posix()),run/'jobs')
        service.project=lambda:BigQueryProject(config_path)
        engineer={'id':'acceptance-engineer','name':'Automated acceptance engineering','role':'engineering'}
        finance={'id':'acceptance-finance','name':'Automated acceptance finance','role':'finance'}
        doc=service.create(engineer,'CONTROLLED ACCEPTANCE: daily signed invoice value differs from raw quantity times unit price. Investigate the SQL and propose the smallest justified correction; preserve all original records, including cancellations.')
        def action(doc,name,actor=engineer,**payload):return service.mutate(doc['id'],actor,doc['version'],name,payload)
        doc=action(doc,'definition',finance,definition='Signed invoice value is the exact NUMERIC sum of original quantity times GBP unit price across all source records, including C-prefixed cancellations, negative/zero adjustments and missing-customer rows. Daily grain is source invoice date and country across EVERY original row. Limit any correction to models/retail_daily.sql and preserve its selected columns and arithmetic. Daily totals must reconcile to raw inputs. These are isolated acceptance-test assets.')
        doc=action(doc,'investigate')
        print('Real investigation started:',doc['id'],flush=True)
        for clarification in range(3):
            service.jobs[doc['id']].result(timeout=900)
            doc=service.store.get(doc['id'])
            if doc['stage']!='NEEDS_INPUT' or clarification==2:break
            question=doc.get('question') or ''
            if not any(word in question.lower() for word in ['cancellation','grain','retail_daily.sql']):raise ValueError('Acceptance question needs operator input: '+question)
            answer='Confirmed acceptance policy: daily grain is source invoice date and country across EVERY original line, including cancellations. Limit the correction to models/retail_daily.sql; retain the existing selected columns and calculations, source precision and signed values. Do not change raw data, assertions, or metric definitions.'
            result.setdefault('clarifications',[]).append({'question':question,'acceptance_policy_answer':answer})
            print('Answering the model clarification with the predefined acceptance policy.',flush=True)
            doc=action(doc,'message',finance,text=answer)
            doc=action(doc,'investigate')
        if doc['stage']!='PROPOSAL_READY':raise ValueError('Expected a verified repair proposal; got '+doc['stage']+': '+str(doc.get('error') or doc.get('summary') or doc.get('question')))
        print('Real model proposed and BigQuery verified:',doc['proposal']['file'],flush=True)
        try:action(doc,'repair')
        except Rejected:result['unapproved_publication_rejected']=True
        else:raise ValueError('Publication was allowed without approvals')
        digest=doc['proposal']['digest']
        doc=action(doc,'approve',finance,digest=digest)
        try:action(doc,'repair')
        except Rejected:result['single_approval_publication_rejected']=True
        else:raise ValueError('Publication was allowed with only one role')
        doc=action(doc,'approve',engineer,digest=digest)
        doc=action(doc,'repair')
        service.jobs[doc['id']].result(timeout=900)
        doc=service.store.get(doc['id'])
        if doc['stage']!='VERIFIED_BRANCH':raise ValueError('Branch publication failed: '+str(doc.get('error')))
        proposal=doc['proposal'];artifact=doc['artifact']
        blob=subprocess.run(['git','cat-file','blob',artifact['commit']+':'+proposal['file']],cwd=repo,check=True,capture_output=True).stdout
        if blob!=proposal['content'].encode('utf-8'):raise ValueError('Published SQL differs from verified content')
        if project.read_transform(faulty_file)['content']!=faulty:raise ValueError('Main checkout changed during publication')
        # Apply only to the explicitly isolated acceptance output, then independently recheck.
        project.execute(project.rewrite(proposal['content'],project.source_map),set(project.config.tables),destination=project.config.outputs[proposal['file']])
        after=project.verify(project.source_map)
        if not after['passed']:raise ValueError('Isolated deployment did not restore the business contract')
        result.update(passed=True,incident_id=doc['id'],artifact=artifact,proposal_digest=digest,after=after,audit_events=len(service.store.history(doc['id'])),exact_commit_verified=True,main_checkout_preserved=True)
        print('Live repair acceptance PASSED: tested patch, two role gates, exact Git branch and isolated deployment.',flush=True)
    except BaseException as exc:
        result.update(passed=False,error=str(exc))
        raise
    finally:
        if service:service.pool.shutdown(wait=True)
        unchanged={name:client.get_table(name).etag for name in original.config.tables}==baseline
        result['baseline_table_versions_unchanged']=unchanged
        if created:
            if not dataset_id.startswith(original.config.billing_project+'.incident_room_accept_'):raise ValueError('Unexpected cleanup target')
            client.delete_dataset(dataset_id,delete_contents=True,not_found_ok=True)
            result['acceptance_dataset_cleaned']=True
        (run/'result.json').write_text(json.dumps(result,indent=2,default=str),encoding='utf-8')
        (ROOT/'runtime'/'live-repair-latest.json').write_text(json.dumps({'run_directory':str(run),**result},indent=2,default=str),encoding='utf-8')
        if not unchanged:raise ValueError('A baseline warehouse table changed during acceptance testing')
        print('Baseline table versions unchanged; acceptance datasets cleaned. Report:',run/'result.json',flush=True)


if __name__=='__main__':main()
