#Requires -Version 5.1
$ErrorActionPreference = 'Stop'
$historyRoot = $PSScriptRoot
$pidFile = Join-Path (Split-Path -Parent $historyRoot) '.runtime/history.pid'
if (-not (Test-Path -LiteralPath $pidFile)) { Write-Host 'No history service PID is recorded.'; return }
$historyProcessId = [int](Get-Content -LiteralPath $pidFile)
$historyProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $historyProcessId"
if (-not $historyProcess) { Write-Host 'The recorded history process is no longer running.'; return }
$expectedPython = (Resolve-Path -LiteralPath (Join-Path $historyRoot '.venv/Scripts/python.exe')).ProviderPath
if ($historyProcess.ExecutablePath -ne $expectedPython -or $historyProcess.CommandLine -notmatch '-m\s+twin_history\s+serve') {
    throw 'The recorded PID belongs to a different process; it was left running.'
}
Stop-Process -Id $historyProcessId
Remove-Item -LiteralPath $pidFile
Write-Host 'Thing history stopped. Committed database records are preserved.'
