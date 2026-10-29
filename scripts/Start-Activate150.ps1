param([Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$out=[IO.Path]::GetFullPath($OutputDirectory)
if (-not $out.StartsWith((Join-Path $root 'results\activate150-'),[StringComparison]::OrdinalIgnoreCase)) { throw 'Wrong activation output directory' }
if (-not (Test-Path -LiteralPath (Join-Path $out 'before.json'))) { throw 'Fresh zero-offset control missing' }
$principal=[Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    $process=Start-Process -FilePath (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe') -ArgumentList @('-NoProfile','-File',('"'+$PSCommandPath+'"'),'-OutputDirectory',('"'+$out+'"')) -Verb RunAs -WindowStyle Hidden -PassThru
    [ordered]@{pid=$process.Id;utc=(Get-Date).ToUniversalTime().ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $out 'uac-launch.json') -Encoding UTF8
    return
}
Set-Location -LiteralPath $root
$source=Join-Path $out 'source';New-Item -ItemType Directory -Path $source | Out-Null
foreach ($name in @('activate150.py','train_existing_cifar100.py','gemm.py','efficiency.py','endurance.py','nvidia_metrics.py','performance_state.py','compare.py')) {
    Copy-Item -LiteralPath (Join-Path $root ('bench\'+$name)) -Destination (Join-Path $source $name)
}
Copy-Item -LiteralPath $PSCommandPath -Destination (Join-Path $source 'Start-Activate150.ps1')
$ErrorActionPreference='Continue'
& (Join-Path $root '.venv\Scripts\python.exe') -X utf8 (Join-Path $root 'bench\activate150.py') --output-directory $out *> (Join-Path $out 'controller-console.log')
$trialExit=$LASTEXITCODE
[ordered]@{utc=(Get-Date).ToUniversalTime().ToString('o');windows_boot_utc=(Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToUniversalTime().ToString('o');secure_boot_registry=(Get-ItemProperty -LiteralPath 'HKLM:\SYSTEM\CurrentControlSet\Control\SecureBoot\State' -Name UEFISecureBootEnabled).UEFISecureBootEnabled} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $out 'context-after.json') -Encoding UTF8
Set-Content -LiteralPath (Join-Path $out 'launcher-exit.txt') -Value $trialExit -Encoding ASCII
