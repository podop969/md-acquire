# scripts/run.ps1 -- the bulk pass (resume-safe; re-run freely).
[CmdletBinding()]
param(
    [switch]$Force,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8   # CJK/diacritic filenames on PS 5.1

$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

$venvPy = Join-Path $repo ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) { throw "run .\scripts\setup.ps1 first" }

# Unpaywall needs an email; config.yaml is also accepted (needed for Task Scheduler).
$email = $env:ACQUIRE_EMAIL
if (-not $email) {
    $cfgPath = Join-Path $repo "config.yaml"
    if (Test-Path $cfgPath) {
        # Guarded: an empty contact_email (fresh setup) matches nothing,
        # and indexing .Matches on a null Select-String result would abort.
        $hit = Select-String -Path $cfgPath -Pattern '^contact_email:\s*"?([^"\s]+)"?' |
               Select-Object -First 1
        if ($hit) { $email = $hit.Matches.Groups[1].Value }
    }
}
if (-not $email) {
    Write-Warning "No contact_email / ACQUIRE_EMAIL set. Unpaywall adapter will be skipped."
}

$cliArgs = @()
if ($Force)  { $cliArgs += '--force' }
if ($DryRun) { $cliArgs += '--dry-run' }

& $venvPy -m pipeline.bulk @cliArgs
$code = $LASTEXITCODE

Write-Host ""
Write-Host "report : $repo\library\report.md"
Write-Host "wanted : $repo\library\wanted.md"
Write-Host "html   : $repo\library\wanted.html"
Write-Host "manifest: $repo\library\manifest.jsonl"
exit $code