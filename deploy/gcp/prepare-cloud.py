"""Prepare private cloud configuration; never prints credential values."""
import json
from pathlib import Path
import secrets
import shutil
import subprocess
from uuid import uuid4
from dotenv import dotenv_values,set_key

root=Path(__file__).resolve().parents[2]
state=json.loads((root/'runtime/gcp-server.json').read_text(encoding='utf-8-sig'))
private=root.parents[1]/'private/gcp'
private.mkdir(parents=True,exist_ok=True)
native=dotenv_values(root/'.env')
project=state['project'];region=state['region'];number='281482385461'
release_file=private/'cloud-release.json'
release=json.loads(release_file.read_text()) if release_file.exists() else {'release':'release-'+uuid4().hex[:10]}
release.update(project=project,region=region,internal_ip='10.44.0.2',registry=f'{region}-docker.pkg.dev/{project}/incident-room')
release['urls']={key:f'https://{service}-{number}.{region}.run.app' for key,service in {'app':'incident-room','switch':'incident-switch','gateway':'incident-switch-admin','chat':'incident-chat'}.items()}
for image in ['api','web','edge']:release[image+'_image']=release['registry']+'/'+image+':'+release['release']
app=private/'app.production.env';switch=private/'switch.production.env'
presentation=private/'project.presentation.cloud.json'
active_repo='/srv/incident-room/presentation-warehouse' if presentation.exists() else '/srv/incident-room/retail-warehouse'
if not app.exists():
    app.touch()
    for key,value in {'OPENAI_API_KEY':native['OPENAI_API_KEY'],'OPENAI_MODEL':native['OPENAI_MODEL'],'OPENAI_REASONING_EFFORT':native.get('OPENAI_REASONING_EFFORT') or 'medium','GOOGLE_CLIENT_ID':native['GOOGLE_CLIENT_ID'],'POSTGRES_PASSWORD':secrets.token_hex(24),'SWITCH_ADAPTER_TOKEN':secrets.token_urlsafe(48)}.items():set_key(app,key,value)
for key,value in {'APP_ENV':'production','ALLOW_REVIEWER_TOKENS':'false','AUTH_MEMBERS':'{}','ROOM_TOKENS':'{}','APP_ORIGINS':release['urls']['app'],'PROJECT_CONFIG':'/etc/incident-room/project.json','ROOM_DATA_DIR':'/app/runtime','DATABASE_URL':'postgresql+psycopg://incident:'+dotenv_values(app)['POSTGRES_PASSWORD']+'@db/incident','WAREHOUSE_REPO_PATH':'/srv/incident-room/retail-warehouse','VM_INTERNAL_IP':release['internal_ip'],'API_IMAGE':release['api_image'],'ROOM_API_URL':'http://api:8400','SWITCH_BASE_URL':'http://'+release['internal_ip']+':8000','SWITCH_MEMBERS':'{}'}.items():set_key(app,key,value)
set_key(app,'WAREHOUSE_REPO_PATH',active_repo)
if not switch.exists():
    shutil.copyfile(root.parents[1]/'src/switch-reference/.env.example',switch)
    for key in ['DB_PASSWORD','DB_OWNER_PASSWORD','AGENT_REGISTRATION_TOKEN','GATEWAY_ADMIN_PASSWORD','MATTERMOST_ADMIN_PASSWORD','MATTERMOST_USER_PASSWORD']:set_key(switch,key,secrets.token_hex(24))
    set_key(switch,'SECRET_KEYS','cloud:'+secrets.token_hex(32))
for key,value in {'SWITCH_VERSION':'0.31.0','COMPOSE_PROFILES':'collab,gateway','SWITCH_BIND_ADDR':release['internal_ip'],'GATEWAY_HOST_PORT':'3001','API_HOST_PORT':'8000','POSTGRES_HOST_PORT':'5433','GATEWAY_COOKIE_SECURE':'true','GATEWAY_ADMIN_EMAIL':'finance@example.com','MATTERMOST_USER':'finance','GATEWAY_PUBLIC_URL':release['urls']['switch'],'FRONTEND_BASE_URL':release['urls']['gateway'],'MESSAGING_PUBLIC_URL':release['urls']['chat']}.items():set_key(switch,key,value)
config=json.loads(Path(native['PROJECT_CONFIG']).read_text(encoding='utf-8-sig'))
repo=Path(config['project_root'])
config['project_root']='/workspace/retail-warehouse';config['publish_pr']=False
if presentation.exists():config=json.loads(presentation.read_text())
(private/'project.cloud.json').write_text(json.dumps(config,indent=2)+'\n',encoding='utf-8')
bundle=private/'retail-warehouse.bundle'
if not bundle.exists():subprocess.run(['git','bundle','create',str(bundle),'--all'],cwd=repo,check=True,capture_output=True)
release_file.write_text(json.dumps(release,indent=2)+'\n',encoding='utf-8')
print('Cloud release and private environment files prepared. No credentials printed.')
print(json.dumps({key:release[key] for key in ['release','urls']},indent=2))
