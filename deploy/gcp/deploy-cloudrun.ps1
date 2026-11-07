param([switch]$App)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$privateRoot=Join-Path (Split-Path -Parent (Split-Path -Parent $projectRoot)) 'private\gcp'
$release=Get-Content -LiteralPath (Join-Path $privateRoot 'cloud-release.json') -Raw | ConvertFrom-Json
$gcloud=Join-Path $env:LOCALAPPDATA 'Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd'
$services=if ($App) {@{name='incident-room';image=$release.web_image;port='3000';health='/api/health';identity='incident-room-web';environment='ROOM_API_URL=http://10.44.0.2:8400'}} else {@{name='incident-switch';image=$release.edge_image;port='8080';health='/health';identity='incident-room-edge';environment='BACKEND_HOST=10.44.0.2,BACKEND_PORT=8000'},@{name='incident-switch-admin';image=$release.edge_image;port='8080';health='/';identity='incident-room-edge';environment='BACKEND_HOST=10.44.0.2,BACKEND_PORT=3001'},@{name='incident-chat';image=$release.edge_image;port='8080';health='/api/v4/system/ping';identity='incident-room-edge';environment='BACKEND_HOST=10.44.0.2,BACKEND_PORT=8065'}}
foreach ($service in $services) {
    $parameters=@('run','deploy',$service.name,"--image=$($service.image)","--region=$($release.region)","--project=$($release.project)",'--platform=managed','--no-invoker-iam-check','--ingress=all',"--port=$($service.port)","--service-account=$($service.identity)@$($release.project).iam.gserviceaccount.com",'--network=incident-room-net','--subnet=incident-room-cloudrun','--vpc-egress=private-ranges-only','--memory=512Mi','--cpu=1','--min-instances=0','--max-instances=2','--concurrency=80','--timeout=3600',"--set-env-vars=$($service.environment)","--startup-probe=httpGet.path=$($service.health),httpGet.port=$($service.port),timeoutSeconds=3,periodSeconds=5,failureThreshold=40",'--quiet')
    & $gcloud @parameters
    if ($LASTEXITCODE -ne 0) {throw ('Cloud Run deployment failed: '+$service.name)}
    & $gcloud run services describe $service.name "--region=$($release.region)" "--project=$($release.project)" --format='json(status.url,status.conditions)'
    if ($LASTEXITCODE -ne 0) {throw 'Could not verify the Cloud Run deployment'}
}
