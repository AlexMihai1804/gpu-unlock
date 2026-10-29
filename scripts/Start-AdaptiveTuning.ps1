param([ValidateSet('Original','Compare150')][string]$Plan='Original')
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$principal=[Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Start-Process -FilePath (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe') -ArgumentList @('-NoProfile','-File',('"'+$PSCommandPath+'"'),'-Plan',$Plan) -Verb RunAs -WindowStyle Hidden | Out-Null
    return
}
Set-Location -LiteralPath $root
$prefix=if ($Plan -eq 'Compare150') {'compare150-tuning-'} else {'adaptive-tuning-'}
$offsets=if ($Plan -eq 'Compare150') {@(120,150)} else {@(60,90,120)}
$out=Join-Path $root ('results\'+$prefix+(Get-Date -Format 'yyyyMMdd-HHmmss'))
if (Test-Path -LiteralPath $out) { throw 'Output already exists' }
New-Item -ItemType Directory -Path $out | Out-Null
Set-Content -LiteralPath (Join-Path $root 'results\latest-adaptive-tuning.txt') -Value $out -Encoding UTF8
if ($Plan -eq 'Compare150') { Set-Content -LiteralPath (Join-Path $root 'results\latest-150-tuning.txt') -Value $out -Encoding UTF8 }
function Save-Context([string]$Name) {
    [ordered]@{utc=(Get-Date).ToUniversalTime().ToString('o');windows_boot_utc=(Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToUniversalTime().ToString('o');secure_boot_registry=(Get-ItemProperty -LiteralPath 'HKLM:\SYSTEM\CurrentControlSet\Control\SecureBoot\State' -Name UEFISecureBootEnabled).UEFISecureBootEnabled} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $out $Name) -Encoding UTF8
}
Save-Context 'test-context.json'
nvidia-smi --query-gpu=pstate,temperature.gpu,power.draw,clocks.sm,clocks.mem,utilization.gpu,memory.used --format=csv | Set-Content -LiteralPath (Join-Path $out 'idle-before.csv') -Encoding UTF8
$source=Join-Path $out 'source'
New-Item -ItemType Directory -Path $source | Out-Null
foreach ($file in @('adaptive_tuning.py','report_adaptive_tuning.py','efficiency.py','nvidia_metrics.py','endurance.py','gemm.py','performance_state.py','compare.py')) {
    Copy-Item -LiteralPath (Join-Path $root ('bench\'+$file)) -Destination (Join-Path $source $file)
}
Copy-Item -LiteralPath $PSCommandPath -Destination (Join-Path $source 'Start-AdaptiveTuning.ps1')
$python=Join-Path $root '.venv\Scripts\python.exe'
$previous=$ErrorActionPreference
try {
    $ErrorActionPreference='Continue'
    & $python -X utf8 (Join-Path $root 'bench\gemm.py') --output (Join-Path $out 'before.json') --label ('Fresh unlocked control for bounded adaptive '+($offsets -join '/')+' trial') *> (Join-Path $out 'reference-console.log')
    if ($LASTEXITCODE -ne 0) { throw 'Reference benchmark failed' }
    & $python -X utf8 (Join-Path $root 'bench\adaptive_tuning.py') --output-directory $out --screen-offsets @offsets *> (Join-Path $out 'adaptive-console.log')
    $trialExit=$LASTEXITCODE
    Save-Context 'test-context-after.json'
} finally {
    $ErrorActionPreference=$previous
}
Set-Content -LiteralPath (Join-Path $out 'launcher-exit.txt') -Value $trialExit -Encoding ASCII
