# Restore priority of the old automatic boot. Keep both entries/files and MOK.
param([Parameter(Mandatory=$true)][string]$InstallDirectory)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$directory=[IO.Path]::GetFullPath($InstallDirectory)
if (-not $directory.StartsWith((Join-Path $root 'results\automatic-tf32-install-'),[StringComparison]::OrdinalIgnoreCase)) { throw 'Expected the saved TF32 installation directory.' }
$plan=Get-Content -LiteralPath (Join-Path $directory 'approved-plan.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$state=Get-Content -LiteralPath (Join-Path $directory 'activation-state.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if ($plan.mode -cne 'automatic-tf32-ss1-experiment' -or $state.old_automatic_entry -cne 'Boot0000' -or
    $state.windows_entry -cne 'Boot0001' -or $state.file_sha256 -cne $plan.file_sha256) { throw 'Wrong rollback context.' }
$latest=(Get-Content -LiteralPath (Join-Path $root 'results\latest-automatic-tf32-install.txt') -Raw -Encoding UTF8).Trim()
if ($directory -ine $latest) { throw 'Rollback context is not the current TF32 installation.' }
& (Join-Path $PSScriptRoot 'Set-GpuBootPriority.ps1') -Mode Previous
