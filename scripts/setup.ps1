# scripts/setup.ps1 -- one-time setup (idempotent).
[CmdletBinding()]
param(
    [string]$PythonVersion = "3.11"
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

Write-Host "==> md-acquire setup" -ForegroundColor Cyan

# 1) locate python launcher
if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "py.exe (Python launcher) not found. Install Python 3.11+ from https://python.org/ (check 'py launcher')."
}
# Probe via cmd so py.exe's stderr never hits PS 5.1's error stream (EAP Stop
# would otherwise abort). Falls back to the launcher's default Python 3.
$ver = cmd /c "py -$PythonVersion -c ""import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"" 2>nul"
if (-not $ver) {
    Write-Host "Python $PythonVersion not found; falling back to the launcher default" -ForegroundColor Yellow
    $ver = cmd /c "py -3 -c ""import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"" 2>nul"
    if (-not $ver) {
        Write-Host "No Python 3 found by the launcher. Installed:" -ForegroundColor Yellow
        cmd /c "py -0"
        throw "Install Python $PythonVersion or pass -PythonVersion with an installed one."
    }
    $PythonVersion = "3"
    Write-Host "    using Python $ver" -ForegroundColor Yellow
}

# 2) venv (reuse an existing one -- e.g. one created by uv, any 3.10+ works)
if (-not (Test-Path .venv)) {
    Write-Host "    creating .venv"
    & py -$PythonVersion -m venv .venv
}
$venvPy = Join-Path $repo ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) { throw "venv python missing at $venvPy" }

# 3) deps (uv-created venvs ship without pip -> prefer uv, else bootstrap pip)
Write-Host "    installing deps"
$ErrorActionPreference = 'Continue'   # native tools write progress to stderr
if (Get-Command uv -ErrorAction SilentlyContinue) {
    Write-Host "    (using uv)"
    & uv pip install --python $venvPy -r requirements.txt pytest
    $installExit = $LASTEXITCODE
} else {
    & $venvPy -m pip install --upgrade --quiet pip
    if ($LASTEXITCODE -ne 0) {
        & $venvPy -m ensurepip --upgrade
        & $venvPy -m pip install --upgrade --quiet pip
    }
    & $venvPy -m pip install --quiet -r requirements.txt pytest
    $installExit = $LASTEXITCODE
}
$ErrorActionPreference = 'Stop'
if ($installExit -ne 0) { throw "dependency install failed (exit $installExit)" }

# 4) scaffold config + specs (this repo's CLI has no --init; write config directly)
if (-not (Test-Path config.yaml)) {
    Write-Host "    writing config.yaml"
    @'
specs_dir: specs
out_dir: library
contact_email: ""       # used for Unpaywall requests; or set ACQUIRE_EMAIL
min_interval: 1.0       # seconds between requests to the same host
timeout: 30
retries: 3
adapters: [arxiv, openlibrary, gutenberg, unpaywall]
'@ | Set-Content -Path config.yaml -Encoding UTF8
}
if (-not (Test-Path specs)) { New-Item -ItemType Directory specs | Out-Null }

# 5) .gitignore for artifacts
if (-not (Test-Path .gitignore)) {
    @'
.venv/
library/
__pycache__/
.pytest_cache/
*.pyc
'@ | Set-Content -Path .gitignore -Encoding UTF8
}

Write-Host "==> done" -ForegroundColor Green
Write-Host '  1. Put your Unpaywall email in config.yaml (contact_email:) OR set $env:ACQUIRE_EMAIL'
Write-Host '  2. Drop specs into .\specs\   (or import: python -m pipeline.citations <file.md>)'
Write-Host '  3. .\scripts\dev.ps1     # pytest + dry-run'
Write-Host '  4. .\scripts\run.ps1     # real bulk run'