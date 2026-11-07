#!/usr/bin/env bash
set -euo pipefail
python3 /opt/incident-room/deploy/gcp/fetch-secrets.py
python3 - <<'PY'
import json,subprocess,urllib.request
request=urllib.request.Request('http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token',headers={'Metadata-Flavor':'Google'})
with urllib.request.urlopen(request,timeout=15) as response:token=json.load(response)['access_token']
subprocess.run(['docker','login','-u','oauth2accesstoken','--password-stdin','us-central1-docker.pkg.dev'],input=token,text=True,check=True)
PY
cd /opt/incident-room/switch
docker compose -p incident-switch -f compose.yaml -f cloud.yaml up -d --no-build postgres mattermost switch gateway
cd /opt/incident-room
docker compose -p incident-room -f compose.yaml -f compose.cloud.yaml --profile switch up -d --no-build db api adapter
