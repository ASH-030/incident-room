"""Fetch only this VM's two environment secrets through its attached identity."""
import base64
import json
import os
from pathlib import Path
import urllib.request

metadata='http://metadata.google.internal/computeMetadata/v1/'
def get_metadata(path):
    request=urllib.request.Request(metadata+path,headers={'Metadata-Flavor':'Google'})
    with urllib.request.urlopen(request,timeout=15) as response:return response.read().decode()
project=get_metadata('project/project-id')
token=json.loads(get_metadata('instance/service-accounts/default/token'))['access_token']
for name,path in [('incident-room-app-env','/opt/incident-room/.env'),('incident-room-switch-env','/opt/incident-room/switch/.env')]:
    request=urllib.request.Request(f'https://secretmanager.googleapis.com/v1/projects/{project}/secrets/{name}/versions/latest:access',headers={'Authorization':'Bearer '+token})
    with urllib.request.urlopen(request,timeout=20) as response:payload=json.load(response)
    data=base64.b64decode(payload['payload']['data'])
    destination=Path(path);destination.parent.mkdir(parents=True,exist_ok=True)
    temporary=destination.with_suffix('.incoming')
    descriptor=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(descriptor,'wb') as handle:handle.write(data)
    os.replace(temporary,destination)
print('Deployment secrets loaded from Secret Manager. Values were not printed.')
