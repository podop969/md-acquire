[CmdletBinding()]
param([string]$TaskName = "md-acquire-daily")
$ErrorActionPreference = 'Stop'
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "removed '$TaskName'" -ForegroundColor Green
} else {
    Write-Host "'$TaskName' not registered"
}