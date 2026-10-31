# scripts/schedule.ps1 -- nightly Task Scheduler entry wrapping run.ps1.
[CmdletBinding()]
param(
    [string]$TaskName = "md-acquire-daily",
    [string]$Time     = "03:00",
    [switch]$WhatIf
)

$ErrorActionPreference = 'Stop'
$repo        = Split-Path -Parent $PSScriptRoot
$runScript   = Join-Path $PSScriptRoot "run.ps1"
$pwsh        = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"

$action = New-ScheduledTaskAction `
    -Execute $pwsh `
    -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$runScript`"" `
    -WorkingDirectory $repo

$trigger   = New-ScheduledTaskTrigger -Daily -At $Time

# S4U = "run whether user is logged on or not", no stored password.
# It does NOT inherit your interactive env vars -> that's why contact_email must be
# in config.yaml, not only $env:ACQUIRE_EMAIL.
$principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType S4U `
    -RunLevel Limited

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopIfGoingOnBatteries `
    -AllowStartIfOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 4) `
    -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 10)

if ($WhatIf) {
    Write-Host "would register '$TaskName' daily at $Time"
    exit 0
}

Register-ScheduledTask `
    -TaskName  $TaskName `
    -Action    $action `
    -Trigger   $trigger `
    -Principal $principal `
    -Settings  $settings `
    -Force | Out-Null

Write-Host "registered '$TaskName' -> daily at $Time" -ForegroundColor Green
Write-Host "test now : Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "inspect  : Get-ScheduledTaskInfo -TaskName '$TaskName'"
Write-Host "remove   : .\scripts\unschedule.ps1"