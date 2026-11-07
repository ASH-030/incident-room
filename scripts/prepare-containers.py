"""Prepare private container paths without copying credentials into images."""
import json
from pathlib import Path
import secrets
from dotenv import dotenv_values,set_key

root=Path(__file__).resolve().parents[1]
path=root/'.env'
values=dotenv_values(path)
if not values.get('PROJECT_CONFIG'):raise SystemExit('Configure the real BigQuery project first')
config=json.loads(Path(values['PROJECT_CONFIG']).read_text(encoding='utf-8-sig'))
repository=config['project_root']
config['project_root']='/workspace/retail-warehouse'
(root/'config'/'project.container.json').write_text(json.dumps(config,indent=2)+'\n',encoding='utf-8')
for key,value in {'POSTGRES_PASSWORD':secrets.token_hex(24),'SWITCH_ADAPTER_TOKEN':secrets.token_urlsafe(48),'WAREHOUSE_REPO_PATH':str(Path(repository).resolve()).replace('\\','/')}.items():
    if not values.get(key):set_key(path,key,value)
print('Container configuration prepared. PostgreSQL and adapter secrets saved locally, not printed.')
