#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$PythonPath,
    [ValidateRange(1024, 65535)][int]$Port = 4322,
    [ValidateRange(1, 3600)][int]$SampleSeconds = 30
)
$ErrorActionPreference = 'Stop'
$historyRoot = $PSScriptRoot
$twinRoot = Split-Path -Parent $historyRoot
$python = Join-Path $historyRoot '.venv/Scripts/python.exe'
$runtime = Join-Path $twinRoot '.runtime'
New-Item -ItemType Directory -Path $runtime -Force | Out-Null
if (-not (Test-Path -LiteralPath $python)) {
    if ($PythonPath) {
        & $PythonPath -m venv (Join-Path $historyRoot '.venv')
    } elseif (Get-Command uv -ErrorAction SilentlyContinue) {
        & uv venv --python 3.12 --cache-dir (Join-Path $historyRoot '.cache') (Join-Path $historyRoot '.venv')
    } else {
        & python -m venv (Join-Path $historyRoot '.venv')
    }
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $python)) {
        throw 'Install Python 3.11+ or uv, or pass -PythonPath pointing to an installed python.exe.'
    }
}
& $python -c 'import sys, sqlite3; assert sys.version_info >= (3,11), "Python 3.11 or newer is required"'
if ($LASTEXITCODE -ne 0) { throw 'The history Python runtime is not ready.' }
$listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
if ($listener) {
    try { $health = Invoke-RestMethod "http://127.0.0.1:$Port/health" -TimeoutSec 5 } catch { $health = $null }
    if (-not $health -or $health.service -ne 'smartbin-thing-history') { throw "Port $Port is already used by another application." }
    Write-Host "Thing history is already running: http://127.0.0.1:$Port/api/metrics"
    return
}
$process = Start-Process -FilePath $python -ArgumentList @('-m', 'twin_history', 'serve', '--port', "$Port", '--sample-seconds', "$SampleSeconds") -WorkingDirectory $historyRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtime 'history.out.log') -RedirectStandardError (Join-Path $runtime 'history.err.log')
Set-Content -LiteralPath (Join-Path $runtime 'history.pid') -Value $process.Id
$ready = $false
for ($attempt = 0; $attempt -lt 20; $attempt++) {
    try { $health = Invoke-RestMethod "http://127.0.0.1:$Port/health" -TimeoutSec 2; $ready = $health.service -eq 'smartbin-thing-history' } catch {}
    if ($ready) { break }
    Start-Sleep -Milliseconds 500
}
if (-not $ready) { throw 'History service did not become ready. Check .runtime/history.err.log.' }
Write-Host "Thing history: http://127.0.0.1:$Port/api/latest"
Write-Host "Database metrics: http://127.0.0.1:$Port/api/metrics"
Write-Host 'Data source: Ditto Thing notifications and HTTP snapshots, not the MQTT broker.'
Write-Host 'The API is ready; /health reports whether the Ditto collector has connected.'
