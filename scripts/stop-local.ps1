$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent $PSScriptRoot
$record=Join-Path $projectRoot 'runtime\owned-processes.json'
if (!(Test-Path -LiteralPath $record)) { Write-Host 'No owned process record.';exit }
$owned=Get-Content -LiteralPath $record -Raw | ConvertFrom-Json
foreach ($property in $owned.PSObject.Properties) {
    $process=Get-CimInstance Win32_Process -Filter "ProcessId = $($property.Value)"
    if (!$process) { continue }
    if ($property.Name -in @('api','adapter')) {
        $expectedPython=Join-Path $projectRoot '.venv\Scripts\python.exe'
        $entryPoint=if ($property.Name -eq 'api') {'incident_room.app:app'} else {'incident_room.switch_adapter'}
        if ($process.ExecutablePath -ne $expectedPython -or !$process.CommandLine.Contains($entryPoint)) { throw 'Saved Python PID now belongs to another process. Refusing to stop it.' }
    } elseif ($property.Name -eq 'web') {
        $expectedNext=Join-Path $projectRoot 'frontend\node_modules\next\dist\bin\next'
        if (!$process.CommandLine.Contains($expectedNext)) { throw 'Saved dashboard PID now belongs to another process. Refusing to stop it.' }
    } else { throw 'Unknown process record' }
    # The Windows venv launcher runs a child interpreter which owns the socket.
    # Stop only children of our validated launcher with the same uvicorn entry point.
    if ($property.Name -in @('api','adapter')) {
        $children=@(Get-CimInstance Win32_Process -Filter "ParentProcessId = $($property.Value)")
        foreach ($child in $children) {
            if ($child.Name -eq 'conhost.exe' -and $child.ExecutablePath -eq (Join-Path $env:SystemRoot 'System32\conhost.exe')) { continue }
            if ($child.Name -notlike 'python*.exe' -or !$child.CommandLine.Contains($entryPoint)) { throw 'Unexpected Python child process. Refusing to stop it.' }
            Stop-Process -Id $child.ProcessId -ErrorAction SilentlyContinue
        }
    }
    Stop-Process -Id $property.Value -ErrorAction SilentlyContinue
}
Remove-Item -LiteralPath $record
Write-Host 'Stopped the owned API and dashboard processes.'
