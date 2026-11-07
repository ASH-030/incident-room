"""Upload private backups with the VM's short-lived service identity."""
import base64
import hashlib
import http.client
import json
from pathlib import Path
import re
import sys
import urllib.parse
import urllib.request

stamp=sys.argv[1]
if not re.fullmatch(r'\d{8}T\d{6}Z',stamp):raise ValueError('Invalid backup timestamp')
root=Path('/srv/incident-room/backups')
release=json.loads(Path('/opt/incident-room/deploy/gcp/release.json').read_text())
bucket=release['project']+'-private-backups'
request=urllib.request.Request('http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token',headers={'Metadata-Flavor':'Google'})
with urllib.request.urlopen(request,timeout=20) as response:token=json.load(response)['access_token']
for suffix in ['app.dump','switch.sql.gz','warehouse.bundle','project.json']:
    path=root/(stamp+'-'+suffix)
    size=path.stat().st_size
    checksum=hashlib.md5()
    with path.open('rb') as handle:
        for chunk in iter(lambda:handle.read(1024*1024),b''):checksum.update(chunk)
    md5=base64.b64encode(checksum.digest()).decode()
    metadata=json.dumps({'name':path.name,'md5Hash':md5}).encode()
    url='https://storage.googleapis.com/upload/storage/v1/b/'+bucket+'/o?uploadType=resumable&ifGenerationMatch=0'
    request=urllib.request.Request(url,data=metadata,method='POST',headers={'Authorization':'Bearer '+token,'Content-Type':'application/json','X-Upload-Content-Type':'application/octet-stream','X-Upload-Content-Length':str(size)})
    with urllib.request.urlopen(request,timeout=30) as response:session=response.headers['Location']
    endpoint=urllib.parse.urlsplit(session)
    if endpoint.scheme!='https' or endpoint.hostname!='storage.googleapis.com':raise RuntimeError('Unexpected upload destination')
    connection=http.client.HTTPSConnection(endpoint.hostname,timeout=180)
    try:
        connection.putrequest('PUT',endpoint.path+'?'+endpoint.query)
        connection.putheader('Content-Type','application/octet-stream')
        connection.putheader('Content-Length',str(size))
        connection.endheaders()
        with path.open('rb') as handle:
            for chunk in iter(lambda:handle.read(1024*1024),b''):connection.send(chunk)
        response=connection.getresponse()
        body=response.read()
        if response.status not in {200,201}:raise RuntimeError('Backup upload failed with HTTP '+str(response.status))
        committed=json.loads(body)
        if committed.get('md5Hash')!=md5 or int(committed['size'])!=size:raise RuntimeError('Backup integrity verification failed')
    finally:connection.close()
print('Four private off-VM backups uploaded and checksums verified.')
