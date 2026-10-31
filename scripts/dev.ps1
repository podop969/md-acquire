# scripts/dev.ps1 -- daily loop: pytest, then a dry-run of the bulk pass.
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

$venvPy = Join-Path $repo ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) { throw "run .\scripts\setup.ps1 first" }

Write-Host "==> pytest" -ForegroundColor Cyan
& $venvPy -m pytest
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "`n==> dry-run" -ForegroundColor Cyan
& $venvPy -m pipeline.bulk --dry-run