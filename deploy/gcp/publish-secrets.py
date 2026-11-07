"""Publish the two private environment files without putting secrets in arguments or output."""
import json
from pathlib import Path
import subprocess
import os

root=Path(__file__).resolve().parents[2]
private=root.parents[1]/'private/gcp'
release=json.loads((private/'cloud-release.json').read_text())
gcloud=str(Path(os.environ['LOCALAPPDATA'])/'Google/Cloud SDK/google-cloud-sdk/bin/gcloud.cmd')
project=release['project']
def cloud(*args):
    result=subprocess.run([gcloud,*args,'--project='+project,'--quiet'],capture_output=True,text=True)
    if result.returncode:raise RuntimeError('Cloud operation failed: '+' '.join(args[:3])+'\n'+result.stderr[-1500:])
    return result.stdout
existing=json.loads(cloud('secrets','list','--format=json(name,labels)'))
existing={row['name'].rsplit('/',1)[-1]:row for row in existing}
for name,filename in [('incident-room-app-env','app.production.env'),('incident-room-switch-env','switch.production.env')]:
    if name in existing and existing[name].get('labels',{}).get('app')!='incident-room':raise RuntimeError('Secret name is owned by another deployment')
    if name not in existing:cloud('secrets','create',name,'--replication-policy=user-managed','--locations='+release['region'],'--labels=app=incident-room')
    cloud('secrets','versions','add',name,'--data-file='+str(private/filename),'--format=none')
    cloud('secrets','add-iam-policy-binding',name,'--member=serviceAccount:incident-room-runtime@'+project+'.iam.gserviceaccount.com','--role=roles/secretmanager.secretAccessor','--format=none')
print('Both production environment secrets published; access restricted to the backend identity.')
