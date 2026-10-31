# scripts/ui.ps1 -- start the local trigger UI and open it in the browser.
[CmdletBinding()]
param(
    [int]$Port = 8619,
    [string]$Config = "config.yaml",
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

$venvPy = Join-Path $repo ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) { throw "run .\scripts\setup.ps1 first" }

$cliArgs = @("-m", "pipeline.webui", "--port", $Port, "--config", $Config)
if (-not $NoBrowser) { $cliArgs += "--open" }

Write-Host "md-acquire UI -> http://127.0.0.1:$Port   (Ctrl+C to stop)"
& $venvPy @cliArgs