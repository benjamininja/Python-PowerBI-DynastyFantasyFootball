<#
.SYNOPSIS
  Register (or remove) the weekly pipeline as a Windows scheduled task, so the
  schedule is reproducible from source instead of hand-built in Task Scheduler.

.DESCRIPTION
  One task, weekly Thursday 06:00 by default; phase logic (in-season vs
  offseason step selection) lives inside scripts\run_pipeline.py, not in the
  trigger. Moving to a daily reconciliation later = change -DaysOfWeek/-At
  here (the orchestrator already skips the commit when data is unchanged).

.EXAMPLE
  .\scripts\register_scheduled_task.ps1                 # register/update
.EXAMPLE
  .\scripts\register_scheduled_task.ps1 -At 05:30
.EXAMPLE
  .\scripts\register_scheduled_task.ps1 -Unregister
#>
param(
    [string]$TaskName = 'DynastyFF Weekly Pipeline',
    [string]$At = '06:00',
    [ValidateSet('Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday')]
    [string]$DayOfWeek = 'Thursday',
    [switch]$Unregister
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent

if ($Unregister) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "[ok] unregistered '$TaskName'"
    exit 0
}

$action = New-ScheduledTaskAction `
    -Execute 'powershell.exe' `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$repo\run_weekly.ps1`"" `
    -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $DayOfWeek -At $At
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Force | Out-Null
Write-Host "[ok] registered '$TaskName': $DayOfWeek $At -> run_weekly.ps1 (repo: $repo)"
