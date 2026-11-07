"""Bind the actual preconfigured Mattermost transport IDs to invited members."""
import json
import subprocess

query="SELECT row_to_json(c) FROM (SELECT display_name,matrix_user_id,type FROM clients) c;"
result=subprocess.run(['docker','exec','incident-switch-postgres-1','psql','-U','postgres','-d','switch','-At','-c',query],check=True,text=True,capture_output=True)
clients=[json.loads(line) for line in result.stdout.splitlines() if line.strip()]
compose=['docker','compose','--project-directory','/opt/incident-room','-p','incident-room','-f','/opt/incident-room/compose.yaml','-f','/opt/incident-room/compose.cloud.yaml']
for name,email in [('finance','finance@example.com'),('engineering','engineering@example.com')]:
    matches=[row for row in clients if row['display_name']==name and row['type']=='user']
    if len(matches)!=1:raise RuntimeError('Expected exactly one configured '+name+' chat participant')
    subprocess.run(compose+['exec','-T','api','python','-m','incident_room.manage_users','bind-switch',matches[0]['matrix_user_id'],email],check=True)
