#!/usr/bin/env bash
set -euo pipefail
umask 077
install -d -m 0755 /opt/incident-room
tar -xzf "$1" -C /opt/incident-room --no-same-owner
python3 /opt/incident-room/deploy/gcp/fetch-secrets.py
python3 - <<'PY'
import json,subprocess,urllib.request
request=urllib.request.Request('http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token',headers={'Metadata-Flavor':'Google'})
with urllib.request.urlopen(request,timeout=15) as response:token=json.load(response)['access_token']
subprocess.run(['docker','login','-u','oauth2accesstoken','--password-stdin','us-central1-docker.pkg.dev'],input=token,text=True,check=True)
PY
active_repo=$(python3 - <<'PY'
from pathlib import Path
value=next(line.split('=',1)[1].strip().strip("'\"") for line in Path('/opt/incident-room/.env').read_text().splitlines() if line.startswith('WAREHOUSE_REPO_PATH='))
if value not in {'/srv/incident-room/retail-warehouse','/srv/incident-room/presentation-warehouse'}:raise ValueError('Unexpected SQL repository target')
print(value)
PY
)
if [ ! -d "$active_repo/.git" ]; then
    git clone /opt/incident-room/migration/retail.bundle "$active_repo"
fi
chown -R 10001:10001 "$active_repo"
runuser -u incident-room -- git -C "$active_repo" config user.name 'Incident Room Automation'
runuser -u incident-room -- git -C "$active_repo" config user.email 'incident-room@localhost'
runuser -u incident-room -- git -C "$active_repo" config core.autocrlf false
if [ ! -e /opt/incident-room/runtime ]; then
    ln -s /srv/incident-room/runtime /opt/incident-room/runtime
fi
cd /opt/incident-room
docker compose -p incident-room -f compose.yaml -f compose.cloud.yaml pull api
docker compose -p incident-room -f compose.yaml -f compose.cloud.yaml up -d --no-build db
cd /opt/incident-room/switch
docker compose -p incident-switch -f compose.yaml -f cloud.yaml up -d --no-build
echo 'Persistent databases and Switch stack installed. Application import and startup follow.'
