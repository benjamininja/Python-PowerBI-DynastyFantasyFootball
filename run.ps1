<#
.SYNOPSIS
  Run any project Python script against the .venv interpreter.

.DESCRIPTION
  "Run Python File" in VS Code (or a bare `python x.py`) resolves to whatever
  interpreter is selected -- usually anaconda base, which lacks playwright and
  ships a broken pyarrow ("Repetition level histogram size mismatch"). This
  launcher always uses .venv\Scripts\python.exe, so scrapers (04a/04w) and the
  ledger builders (02d/02e) run against the full env. See the ENV note in
  PLAN.md and Environment Gotchas in ~/.claude/memory/preferences.md.

  The repo has two venv folders (venv\ and .venv\); this pins the correct one.

.EXAMPLE
  .\run.ps1 notebooks\04w_fantrax_draft_results.py
.EXAMPLE
  .\run.ps1 notebooks\02d_fact_roster_transactions.py --some-flag value
#>
param(
    [Parameter(Position = 0)]
    [string]$Script,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$py = Join-Path $root '.venv\Scripts\python.exe'

if (-not $Script) {
    Write-Host "Usage: .\run.ps1 <script.py> [args...]   (runs against .venv)"
    Write-Host "Example: .\run.ps1 notebooks\04w_fantrax_draft_results.py"
    exit 2
}

if (-not (Test-Path $py)) {
    Write-Error "No .venv interpreter at $py. Create it:`n  python -m venv .venv`n  .\.venv\Scripts\python.exe -m pip install -r requirements.txt`n  .\.venv\Scripts\python.exe -m playwright install chromium"
    exit 1
}

# Resolve the script relative to repo root if the given path doesn't exist as-is.
if (-not (Test-Path $Script)) {
    $alt = Join-Path $root $Script
    if (Test-Path $alt) { $Script = $alt }
    else { Write-Error "Script not found: $Script"; exit 1 }
}

$env:PYTHONUTF8 = '1'   # consistent UTF-8 I/O for the scrapers' unicode prints
Write-Host "[run.ps1] $py $Script $Rest" -ForegroundColor DarkGray
& $py $Script @Rest
exit $LASTEXITCODE
