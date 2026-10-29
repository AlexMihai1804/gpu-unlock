# Benchmark the current session as requested, without reboot or administrative changes.
param([ValidateRange(10,3600)][int]$Seconds=1200,[switch]$ThermalPacing,[string]$ReferenceRun)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
Set-Location -LiteralPath $root
$out=Join-Path $root ('results\long-current-state-'+(Get-Date -Format 'yyyyMMdd-HHmmss'))
if (Test-Path -LiteralPath $out) { throw 'Choose a new output directory.' }
New-Item -ItemType Directory -Path $out | Out-Null
$out | Set-Content -LiteralPath (Join-Path $root 'results\latest-long-benchmark.txt') -Encoding UTF8
$boot=(Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToUniversalTime()
[ordered]@{utc=(Get-Date).ToUniversalTime().ToString('o');boot_utc=$boot.ToString('o');pid=$PID;target_seconds=$Seconds;scope='current-state-no-restart';user_requested_no_restart=$true;fresh_firmware_trust_collection=$false;configuration_writes=$false;thermal_pacing=[bool]$ThermalPacing;reference_run=$ReferenceRun} |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $out 'launch.json') -Encoding UTF8
$python=Join-Path $root '.venv\Scripts\python.exe'
& (Join-Path $PSScriptRoot 'Collect-NormalBootControl.ps1') -OutputDirectory (Join-Path $out 'health-before')
& nvidia-smi.exe -q -d PERFORMANCE,POWER,CLOCK,TEMPERATURE | Out-File -LiteralPath (Join-Path $out 'nvidia-before.txt') -Encoding UTF8
if ($ReferenceRun) {
    $reference=[IO.Path]::GetFullPath($ReferenceRun)
    if (-not $reference.StartsWith((Join-Path $root 'results')+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Reference must be saved project evidence.' }
    $previous=Get-Content -LiteralPath (Join-Path $reference 'launch.json') -Raw | ConvertFrom-Json
    if ([DateTimeOffset]::Parse($previous.boot_utc).UtcDateTime -ne $boot) { throw 'Reference comes from another Windows boot.' }
    Copy-Item -LiteralPath (Join-Path $reference 'before.json') -Destination (Join-Path $out 'before.json')
} else {
    & $python -X utf8 'bench\gemm.py' --n 8192 --samples 5 --iterations 10 --warmup 4 --device 0 --label current-state-before-long --output (Join-Path $out 'before.json')
    if ($LASTEXITCODE -ne 0) { throw 'Pre-test numerical benchmark failed.' }
}
$workload=@('-X','utf8','bench\endurance.py','--seconds',[string]$Seconds,'--iterations','100','--output-directory',(Join-Path $out 'endurance'))
if ($ThermalPacing) { $workload=@('-X','utf8','bench\endurance.py','--seconds',[string]$Seconds,'--iterations','25','--thermal-pacing','--output-directory',(Join-Path $out 'endurance')) }
& $python @workload
if ($LASTEXITCODE -ne 0) {
    & (Join-Path $PSScriptRoot 'Collect-NormalBootControl.ps1') -OutputDirectory (Join-Path $out 'health-after')
    & nvidia-smi.exe -q -d PERFORMANCE,POWER,CLOCK,TEMPERATURE | Out-File -LiteralPath (Join-Path $out 'nvidia-after.txt') -Encoding UTF8
    & $python -X utf8 'bench\report_endurance.py' --directory $out --current-state --stopped
    throw ('Endurance test stopped. Partial report: '+(Join-Path $out 'REPORT.md'))
}
& $python -X utf8 'bench\gemm.py' --n 8192 --samples 5 --iterations 10 --warmup 4 --device 0 --label current-state-after-long --output (Join-Path $out 'after.json')
if ($LASTEXITCODE -ne 0) { throw 'Post-test numerical benchmark failed.' }
& (Join-Path $PSScriptRoot 'Collect-NormalBootControl.ps1') -OutputDirectory (Join-Path $out 'health-after')
& nvidia-smi.exe -q -d PERFORMANCE,POWER,CLOCK,TEMPERATURE | Out-File -LiteralPath (Join-Path $out 'nvidia-after.txt') -Encoding UTF8
& $python -X utf8 'bench\report_endurance.py' --directory $out --current-state
if ($LASTEXITCODE -ne 0) { throw 'Final current-session stability review failed.' }
Write-Output ('Current-session long benchmark completed: '+$out)
