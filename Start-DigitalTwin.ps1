#Requires -Version 5.1
$ErrorActionPreference = 'Stop'
$twinRoot = $PSScriptRoot
$runtimePath = Join-Path $twinRoot '.runtime'
New-Item -ItemType Directory -Path $runtimePath -Force | Out-Null
& docker info --format '{{.ServerVersion}}' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Start Docker Desktop and wait until its engine is ready, then run this script again.' }
$dittoFolder = Join-Path $twinRoot 'ditto/deployment/docker'
& docker compose --project-directory $dittoFolder --env-file (Join-Path $dittoFolder '.env') -f (Join-Path $dittoFolder 'docker-compose.yml') start
if ($LASTEXITCODE -ne 0) { throw 'Could not start the installed Ditto containers.' }
$deadline = (Get-Date).AddMinutes(3)
$ready = $false
do {
    try { $health = Invoke-RestMethod 'http://127.0.0.1:8090/health' -TimeoutSec 5; $ready = $health.status -eq 'UP' } catch {}
    if (-not $ready) { Start-Sleep -Seconds 2 }
} while (-not $ready -and (Get-Date) -lt $deadline)
if (-not $ready) { throw 'Ditto is not healthy yet. Check its containers; existing data has been preserved.' }
& docker compose -f (Join-Path $twinRoot 'mqtt/compose.yml') up -d
if ($LASTEXITCODE -ne 0) { throw 'Could not start the native MQTT broker. Port 1884 must be free.' }
$node = (Get-Command node -ErrorAction Stop).Source
& $node (Join-Path $twinRoot 'mqtt/configure-ditto.mjs')
if ($LASTEXITCODE -ne 0) { throw 'Native MQTT configuration failed.' }
foreach ($service in @(@{ Name='dashboard'; Port=4321 }, @{ Name='simulator'; Port=4318 })) {
    $listener = Get-NetTCPConnection -State Listen -LocalPort $service.Port -ErrorAction SilentlyContinue
    if (-not $listener) {
        Start-Process -FilePath $node -ArgumentList 'server.mjs' -WorkingDirectory (Join-Path $twinRoot $service.Name) -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtimePath ($service.Name + '.out.log')) -RedirectStandardError (Join-Path $runtimePath ($service.Name + '.err.log'))
    }
}
Write-Host 'Dashboard: http://127.0.0.1:4321/'
Write-Host 'Simulator: http://127.0.0.1:4318/'
Write-Host 'Ditto:     http://localhost:8090/ui/'
Write-Host 'Native MQTT is configured. Connect the simulator broker and press Send reading to change a bin.'
