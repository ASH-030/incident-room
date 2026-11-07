"""Check the real images, PostgreSQL persistence and BigQuery ADC in an owned test stack."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
from uuid import uuid4
import httpx

root=Path(__file__).resolve().parents[1]
project='incident-room-check'
token=secrets.token_urlsafe(40)
env={**os.environ,'ROOM_WEB_PORT':'3002','ACCEPTANCE_ROOM_TOKENS':json.dumps({token:{'id':'acceptance:runtime-engineer','name':'Automated runtime engineer','role':'engineering'}})}
adc=Path(os.getenv('GOOGLE_ADC_PATH') or (Path(os.environ['APPDATA'])/'gcloud'/'application_default_credentials.json'))
if not adc.is_file():raise SystemExit('Local ADC JSON not found; set GOOGLE_ADC_PATH')
env['GOOGLE_ADC_PATH']=adc.as_posix()
compose=['docker','compose','--project-name',project,'-f','compose.yaml','-f','compose.credentials.yaml','-f','compose.validation.yaml']
def run(args):
    result=subprocess.run(args,cwd=root,env=env,capture_output=True,text=True,timeout=120)
    if result.returncode:raise RuntimeError('Container operation failed: '+result.stderr[-1600:])
    return result.stdout.strip()
for resource in ('container','volume'):
    existing=run(['docker',resource,'ls','--filter','label=com.docker.compose.project='+project,'--format','{{.ID}}' if resource=='container' else '{{.Name}}'])
    if existing:raise SystemExit('The validation project already owns resources. Inspect them before a new run; refusing to overwrite or remove existing state.')
result={'run_id':uuid4().hex[:12],'passed':False,'project':project,'automated_acceptance_identity':True,'warehouse_mutations':False}
started=False
try:
    print('Starting the owned container acceptance stack...',flush=True)
    started=True;run(compose+['up','-d','--no-build'])
    with httpx.Client(base_url='http://127.0.0.1:3002',headers={'Authorization':'Bearer '+token},timeout=90) as client:
        for attempt in range(30):
            try:
                health=client.get('/api/health');health.raise_for_status()
                if health.json()['storage']=='postgresql':break
            except httpx.HTTPError:pass
            time.sleep(.5)
        else:raise RuntimeError('PostgreSQL API did not become ready')
        assert httpx.get('http://127.0.0.1:3002/api/incidents').status_code==401
        original=client.get('/api/incidents');original.raise_for_status()
        assert original.json()==[], 'Expected an isolated empty acceptance database'
        warehouse=client.get('/api/project');warehouse.raise_for_status()
        result.update(postgresql=True,anonymous_denied=True,bigquery_adc_verified=True,metric_queries=len(warehouse.json()['metrics']))
        created=client.post('/api/incidents',json={'report':'Container persistence acceptance: verify durable incident storage, without running an investigation.'})
        created.raise_for_status();doc=created.json()
        before_restart=client.get('/api/incidents/'+doc['id']);before_restart.raise_for_status()
        expected=before_restart.json()
        assert run(compose+['exec','-T','api','id','-u'])=='10001'
        assert run(compose+['exec','-T','api','python','-c',"from pathlib import Path; print(Path('/app/.env').exists())"])=='False'
        print('Real BigQuery reads and unprivileged API verified; restarting API...',flush=True)
        run(compose+['restart','api'])
        for attempt in range(40):
            try:
                restored=client.get('/api/incidents/'+doc['id'])
                if restored.status_code==200:
                    assert restored.json()==expected
                    break
            except httpx.HTTPError:pass
            time.sleep(.5)
        else:raise RuntimeError('Incident did not survive the API restart')
        result.update(persistence_after_restart=True,api_uid=10001,no_env_file_in_image=True,passed=True)
finally:
    if started:
        # Exact fixed project label, checked empty before creating this disposable stack.
        run(compose+['down','--volumes'])
        result['owned_test_resources_removed']=True
    (root/'runtime'/'container-validation.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
if result['passed']:print('PASS: dashboard proxy, PostgreSQL restart persistence, real BigQuery ADC, API isolation and image secret exclusion.')
