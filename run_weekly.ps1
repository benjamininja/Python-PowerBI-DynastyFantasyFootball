<#
.SYNOPSIS
  Task Scheduler entrypoint: run the weekly ETL pipeline against .venv,
  logging the console to data\outputs\pipeline_runs\console_<ts>.txt.

.DESCRIPTION
  Thin wrapper around scripts\run_pipeline.py (the phase-aware orchestrator).
  Same .venv pinning rationale as run.ps1. Extra args pass through, e.g.:
    .\run_weekly.ps1 --dry-run --phase OFFSEASON
    .\run_weekly.ps1 --profile dynasty

  Register the scheduled task with scripts\register_scheduled_task.ps1.
#>
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$py = Join-Path $root '.venv\Scripts\python.exe'

if (-not (Test-Path $py)) {
    Write-Error "No .venv interpreter at $py (see run.ps1 for setup)."
    exit 1
}

$logDir = Join-Path $root 'data\outputs\pipeline_runs'
New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path $logDir ("console_{0:yyyyMMdd_HHmmss}.txt" -f (Get-Date))

$env:PYTHONUTF8 = '1'
Set-Location $root
Write-Host "[run_weekly] logging to $log" -ForegroundColor DarkGray
& $py (Join-Path $root 'scripts\run_pipeline.py') @Rest 2>&1 | Tee-Object -FilePath $log
exit $LASTEXITCODE
