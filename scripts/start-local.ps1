$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimePath = Join-Path $projectRoot 'runtime'
New-Item -ItemType Directory -Path $runtimePath -Force | Out-Null
if (!(Test-Path -LiteralPath (Join-Path $projectRoot '.env'))) { throw 'Configure the app first: uv run python -m incident_room.configure' }
foreach ($port in @(8400,3000)) {
    if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) { throw "Port $port is already in use. Stop the existing process before starting another instance." }
}
Push-Location $projectRoot
try {
    uv sync --frozen
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed' }
    Push-Location (Join-Path $projectRoot 'frontend')
    try {
        $lockHash=(Get-FileHash -LiteralPath 'package-lock.json' -Algorithm SHA256).Hash
        $dependencyStamp=Join-Path $runtimePath 'frontend-lock.sha256'
        $previousHash=if (Test-Path -LiteralPath $dependencyStamp) {(Get-Content -LiteralPath $dependencyStamp -Raw).Trim()} else {''}
        if (!(Test-Path -LiteralPath 'node_modules\next\dist\bin\next') -or $previousHash -ne $lockHash) {
            npm ci
            if ($LASTEXITCODE -ne 0) { throw 'Dashboard dependency installation failed' }
            Set-Content -LiteralPath $dependencyStamp -Value $lockHash
        }
        npm run build
        if ($LASTEXITCODE -ne 0) { throw 'Dashboard build failed' }
    } finally { Pop-Location }
    $pythonExecutable = Join-Path $projectRoot '.venv\Scripts\python.exe'
    $apiProcess = Start-Process -PassThru -FilePath $pythonExecutable -WorkingDirectory $projectRoot -ArgumentList @('-m','uvicorn','incident_room.app:app','--host','127.0.0.1','--port','8400','--workers','1') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtimePath 'api.stdout.log') -RedirectStandardError (Join-Path $runtimePath 'api.stderr.log')
    @{api=$apiProcess.Id} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtimePath 'owned-processes.json')
    $nodeExecutable = (Get-Command node).Source
    $nextScript = Join-Path $projectRoot 'frontend\node_modules\next\dist\bin\next'
    $webProcess = Start-Process -PassThru -FilePath $nodeExecutable -WorkingDirectory (Join-Path $projectRoot 'frontend') -ArgumentList @(('"'+$nextScript+'"'),'start','--hostname','127.0.0.1','--port','3000') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtimePath 'web.stdout.log') -RedirectStandardError (Join-Path $runtimePath 'web.stderr.log')
    @{api=$apiProcess.Id;web=$webProcess.Id} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtimePath 'owned-processes.json')
    $ready=$false
    for ($attempt=0;$attempt -lt 20;$attempt++) {
        try {
            $health=Invoke-RestMethod -Uri 'http://127.0.0.1:8400/api/health' -TimeoutSec 2
            $page=Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:3000' -TimeoutSec 2
            if ($page.StatusCode -eq 200) {$ready=$true;break}
        } catch { Start-Sleep -Milliseconds 500 }
    }
    if (!$ready) { throw 'A service did not become ready. Inspect runtime logs and run scripts\stop-local.ps1 before retrying.' }
    Write-Host 'Dashboard: http://127.0.0.1:3000'
    Write-Host ('Configuration: '+$health.status)
    if ($health.switch_configured) { & (Join-Path $PSScriptRoot 'start-switch.ps1') }
    Write-Host 'Logs and process IDs are in runtime.'
} finally { Pop-Location }
