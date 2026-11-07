"""Prepare a persistent, clearly labelled fault in an isolated presentation project.

Run with the baseline project mounted and /srv/incident-room mounted writable.
This operator script never approves, publishes, or edits the baseline warehouse.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile

from google.cloud import bigquery
from incident_room.bigquery_project import BigQueryProject

original=BigQueryProject(os.environ['PROJECT_CONFIG'])
client=original.client
runtime=Path('/srv/incident-room/runtime')
repo=Path('/srv/incident-room/presentation-warehouse')
record=runtime/'presentation-evidence.json'
if record.exists():raise RuntimeError('Presentation already prepared. Inspect the recorded evidence before any reset.')
if repo.exists() and any(repo.iterdir()):raise RuntimeError('Presentation repository is not empty')
repo.mkdir(parents=True,exist_ok=True)
baseline={name:client.get_table(name).etag for name in original.config.tables}
dataset_id=original.config.billing_project+'.incident_room_presentation'
dataset=bigquery.Dataset(dataset_id)
dataset.location=original.config.location
dataset.description='Controlled Incident Room presentation assets. The daily SQL deliberately excludes cancellations. Original incident_data is unchanged.'
dataset.labels={'application':'incident-room','purpose':'presentation'}
client.create_dataset(dataset)
mapping={name:dataset_id+'.'+name.rsplit('.',1)[1] for name in original.config.tables}
for source,target in mapping.items():
    job=client.query(f'CREATE TABLE `{target}` CLONE `{source}`',location=original.config.location,job_config=bigquery.QueryJobConfig(maximum_bytes_billed=original.config.maximum_bytes_billed))
    try:job.result(timeout=120)
    except BaseException:job.cancel();raise

def rewrite(sql):
    for source,target in mapping.items():sql=sql.replace('`'+source+'`','`'+target+'`')
    return sql

fixed_daily=None
for name in original.config.transforms:
    content=rewrite(original.read_transform(name)['content'])
    if name=='models/retail_daily.sql':
        fixed_daily=content
        marker='GROUP BY invoice_date, country'
        if content.count(marker)!=1:raise RuntimeError('Baseline daily transform changed; review the intended fault')
        content=content.replace(marker,'WHERE NOT is_cancellation\n'+marker)
    target=repo/name;target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(content,encoding='utf-8',newline='')
if fixed_daily is None:raise RuntimeError('Daily transform is missing')
(repo/'.gitattributes').write_text('*.sql text eol=lf\n')
(repo/'README.md').write_text('# Controlled presentation project\n\nThis repository and incident_room_presentation dataset are isolated from the original retail warehouse. The initial daily transform deliberately excludes cancellation rows, creating a measurable reconciliation failure. The application must investigate the evidence and obtain real finance and engineering approval before publishing a tested repair branch. Publication does not deploy warehouse SQL.\n')
def git(*args):return subprocess.run(['git',*args],cwd=repo,check=True,capture_output=True,text=True).stdout.strip()
git('init','-b','main');git('config','user.name','Incident Room Presentation Setup');git('config','user.email','presentation@localhost');git('config','core.autocrlf','false')
git('add','.');git('commit','-m','Document controlled cancellation omission for live presentation')
config=original.config.model_dump(mode='json')
config.update(name='Retail reconciliation — controlled presentation dataset',project_root=repo.as_posix(),tables=list(mapping.values()),outputs={name:mapping[table] for name,table in config['outputs'].items()},publish_pr=False)
for check in config['assertions']:check['sql']=rewrite(check['sql'])
for metric in config['metrics']:metric['sql']=rewrite(metric['sql'])
check_config=runtime/'presentation-check.project.json'
check_config.write_text(json.dumps(config,indent=2)+'\n')
project=BigQueryProject(check_config)
faulty=project.read_transform('models/retail_daily.sql')['content']
project.execute(project.rewrite(faulty,project.source_map),set(project.config.tables),destination=project.config.outputs['models/retail_daily.sql'])
before=project.verify(project.source_map)
failed=[check['name'] for check in before['checks'] if not check['passed']]
assert failed==['Every daily amount and count reconciles directly to raw inputs'], 'Unexpected presentation contract failures'
with tempfile.TemporaryDirectory(prefix='incident-room-presentation-check-') as temporary:
    after=project.verify_patch('models/retail_daily.sql',fixed_daily,temporary)
assert after['passed'], 'The minimal correction did not pass independent checks'
for name,etag in baseline.items():
    if client.get_table(name).etag!=etag:raise RuntimeError('Baseline changed during presentation setup')
config['project_root']='/workspace/retail-warehouse'
(runtime/'presentation.project.json').write_text(json.dumps(config,indent=2)+'\n')
result={'dataset':dataset_id,'repository':repo.as_posix(),'fault':'models/retail_daily.sql filters out cancellation rows before aggregation','baseline_head':git('rev-parse','HEAD'),'original_tables_unchanged':True,'before':before,'isolated_correction':after,'human_approvals_created':False,'repair_branch_published':False,'presentation_fault_remains_active':True}
record.write_text(json.dumps(result,indent=2,default=str)+'\n')
print('Presentation dataset and SQL project prepared. Current contracts: 5/6. Isolated minimal correction: 6/6. Original tables unchanged.',flush=True)
