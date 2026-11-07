$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent $PSScriptRoot
$record=Join-Path $projectRoot 'runtime\owned-processes.json'
if (!(Test-Path -LiteralPath $record)) {throw 'Start Incident Room before its adapter.'}
$owned=Get-Content -LiteralPath $record -Raw | ConvertFrom-Json
if ($owned.PSObject.Properties.Name -contains 'adapter' -and (Get-Process -Id $owned.adapter -ErrorAction SilentlyContinue)) {throw 'The recorded adapter process is already running.'}
$python=Join-Path $projectRoot '.venv\Scripts\python.exe'
$adapterProcess=Start-Process -PassThru -FilePath $python -WorkingDirectory $projectRoot -ArgumentList @('-m','incident_room.switch_adapter') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $projectRoot 'runtime\switch.stdout.log') -RedirectStandardError (Join-Path $projectRoot 'runtime\switch.stderr.log')
$owned | Add-Member -NotePropertyName adapter -NotePropertyValue $adapterProcess.Id -Force
$owned | ConvertTo-Json | Set-Content -LiteralPath $record
Start-Sleep -Milliseconds 1500
if ($adapterProcess.HasExited) {throw 'Adapter stopped. Inspect runtime\switch.stderr.log.'}
Write-Host 'Switch adapter started. Logs are in runtime.'
