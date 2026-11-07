$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$privateRoot=Join-Path (Split-Path -Parent (Split-Path -Parent $projectRoot)) 'private\gcp'
$release=Get-Content -LiteralPath (Join-Path $privateRoot 'cloud-release.json') -Raw | ConvertFrom-Json
$gcloud=Join-Path $env:LOCALAPPDATA 'Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd'
$env:PATH=(Split-Path -Parent $gcloud)+[IO.Path]::PathSeparator+$env:PATH
$env:DOCKER_CONFIG=Join-Path $privateRoot 'docker'
New-Item -ItemType Directory -Path $env:DOCKER_CONFIG -Force | Out-Null
& $gcloud auth configure-docker us-central1-docker.pkg.dev --quiet
if ($LASTEXITCODE -ne 0) {throw 'Docker registry authentication failed'}
Push-Location $projectRoot
try {
    docker tag incident-room-api:1.0.0 $release.api_image
    if ($LASTEXITCODE -ne 0) {throw 'Verified API image not found'}
    docker build --build-arg "ROOM_API_URL=http://$($release.internal_ip):8400" --tag $release.web_image --file frontend/Dockerfile frontend
    if ($LASTEXITCODE -ne 0) {throw 'Cloud dashboard image build failed'}
    docker build --tag $release.edge_image deploy/gcp/edge
    if ($LASTEXITCODE -ne 0) {throw 'Gateway image build failed'}
    docker run --rm -e BACKEND_HOST=127.0.0.1 -e BACKEND_PORT=8400 $release.edge_image nginx -t
    if ($LASTEXITCODE -ne 0) {throw 'Gateway configuration validation failed'}
    foreach ($image in @($release.api_image,$release.web_image,$release.edge_image)) {
        docker push $image
        if ($LASTEXITCODE -ne 0) {throw 'Release image publication failed'}
    }
    Write-Host 'Verified release images published to the private project repository.'
} finally {Pop-Location}
