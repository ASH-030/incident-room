"""Prepare Switch's official version-pinned local stack with random credentials."""
import json
from pathlib import Path
import secrets
import shutil
from dotenv import dotenv_values,set_key

root=Path(__file__).resolve().parents[1]
hackathon=root.parents[1]
reference=hackathon/'src'/'switch-reference'
target=hackathon/'deploy'/'switch'
target.mkdir(parents=True,exist_ok=True)
compose=target/'compose.yaml'
if not compose.exists():
    shutil.copyfile(reference/'console/apps/switch-console-desktop/src/main/core/managed-switch-server/resources/standalone-docker-compose.pinned.yml',compose)
    shutil.copyfile(reference/'LICENSE',target/'SWITCH-LICENSE')
env=target/'.env'
if not env.exists():shutil.copyfile(reference/'.env.example',env)
values=dotenv_values(env)
for key in ['DB_PASSWORD','DB_OWNER_PASSWORD','AGENT_REGISTRATION_TOKEN','GATEWAY_ADMIN_PASSWORD','MATTERMOST_ADMIN_PASSWORD','MATTERMOST_USER_PASSWORD']:
    if not values.get(key):set_key(env,key,secrets.token_hex(24))
if not values.get('SECRET_KEYS'):set_key(env,'SECRET_KEYS','incident-room:'+secrets.token_hex(32))
for key,value in {'SWITCH_VERSION':'0.31.0','COMPOSE_PROFILES':'collab,gateway','GATEWAY_HOST_PORT':'3001','API_HOST_PORT':'8000','POSTGRES_HOST_PORT':'5433','SWITCH_BIND_ADDR':'127.0.0.1','FRONTEND_BASE_URL':'http://localhost:3001','GATEWAY_PUBLIC_URL':'http://localhost:8000'}.items():set_key(env,key,value)
credentials={key:dotenv_values(env).get(key) for key in ['GATEWAY_ADMIN_EMAIL','GATEWAY_ADMIN_PASSWORD','MATTERMOST_USER','MATTERMOST_USER_PASSWORD']}
(target/'operator-credentials.json').write_text(json.dumps(credentials,indent=2)+'\n',encoding='utf-8')
(target/'.gitignore').write_text('.env\noperator-credentials.json\n',encoding='utf-8')
print('Official Switch 0.31.0 stack prepared at '+str(target))
print('Credentials remain in operator-credentials.json. No secrets printed.')
