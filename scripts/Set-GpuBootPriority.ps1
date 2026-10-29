# Select one of our two existing GPU boot entries. No entry/file/key changes.
param([ValidateSet('TF32','Previous')][string]$Mode='TF32')
$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$principal=[Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    $process=Start-Process -FilePath (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe') -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',('"'+$PSCommandPath+'"'),'-Mode',$Mode) -Verb RunAs -WindowStyle Hidden -PassThru
    [ordered]@{pid=$process.Id;mode=$Mode;utc=(Get-Date).ToUniversalTime().ToString('o')} | ConvertTo-Json |
        Set-Content -LiteralPath (Join-Path $root 'results\gpu-boot-priority-launch.json') -Encoding UTF8
    return
}
Set-StrictMode -Version Latest
$install=(Get-Content -LiteralPath (Join-Path $root 'results\latest-automatic-tf32-install.txt') -Raw -Encoding UTF8).Trim()
if (-not $install.StartsWith((Join-Path $root 'results\automatic-tf32-install-'),[StringComparison]::OrdinalIgnoreCase)) { throw 'Wrong installation context.' }
$state=Get-Content -LiteralPath (Join-Path $install 'activation-state.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$plan=Get-Content -LiteralPath (Join-Path $install 'approved-plan.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if ($plan.mode -cne 'automatic-tf32-ss1-experiment' -or $state.boot_name -cne 'Boot0006' -or
    $state.file_sha256 -cne $plan.file_sha256 -or $state.pe_authenticode_sha256 -cne $plan.pe_authenticode_sha256) { throw 'Unexpected authorized target.' }
if (-not (Confirm-SecureBootUEFI)) { throw 'Secure Boot must remain enabled.' }
$out=Join-Path $root ('results\gpu-boot-priority-'+(Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $out | Out-Null
$out | Set-Content -LiteralPath (Join-Path $root 'results\latest-gpu-boot-priority.txt') -Encoding UTF8
Add-Type -Path (Join-Path $root 'scripts\BootVariables.cs')
$nvram=New-Object M6501BootVariables
try {
    [byte[]]$current=$nvram.Read('BootOrder')
    if (-not $current -or $current.Length%2 -or $current.Length -gt 4096) { throw 'Invalid BootOrder.' }
    $ids=@(for ($i=0;$i -lt $current.Length;$i+=2) { [BitConverter]::ToUInt16($current,$i) })
    if (@($ids | Select-Object -Unique).Count -ne $ids.Count) { throw 'Duplicate boot entries.' }
    foreach ($required in @(0,1,6)) { if ($required -notin $ids) { throw 'Required preserved boot entry missing.' } }
    $entries=[ordered]@{}
    foreach ($id in $ids) {
        $name='Boot'+$id.ToString('X4')
        [byte[]]$bytes=$nvram.Read($name)
        if (-not $bytes) { throw 'Missing boot entry.' }
        $entries[$name]=[Convert]::ToBase64String($bytes)
    }
    if ($entries.Boot0006 -cne $state.payload_base64 -or
        $entries.Boot0000 -cne $plan.preflight_entries.Boot0000 -or
        $entries.Boot0001 -cne $plan.preflight_entries.Boot0001) { throw 'A protected boot entry changed.' }
    $preferred=if ($Mode -eq 'TF32') {@(6,0,1)} else {@(0,1,6)}
    $newIds=@($preferred)+@($ids | Where-Object { $_ -notin $preferred })
    [byte[]]$replacement=New-Object byte[] ($newIds.Count*2)
    for ($i=0;$i -lt $newIds.Count;$i++) { [Array]::Copy([BitConverter]::GetBytes([uint16]$newIds[$i]),0,$replacement,$i*2,2) }
    [ordered]@{mode=$Mode;before=$ids;after=$newIds;before_base64=[Convert]::ToBase64String($current);after_base64=[Convert]::ToBase64String($replacement);entries=$entries} |
        ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $out 'plan-and-backup.json') -Encoding UTF8
    $changed=[Convert]::ToBase64String($current) -cne [Convert]::ToBase64String($replacement)
    if ($changed) { $nvram.ReplaceOrder($current,$replacement) }
    foreach ($name in $entries.Keys) {
        if ([Convert]::ToBase64String($nvram.Read($name)) -cne $entries[$name]) { throw 'An entry changed during priority update.' }
    }
    [ordered]@{completed=$true;mode=$Mode;changed=$changed;BootOrder_base64=[Convert]::ToBase64String($nvram.Read('BootOrder'));entries_unchanged=$true;files_written=$false;keys_written=$false;reboot_performed=$false;utc=(Get-Date).ToUniversalTime().ToString('o')} |
        ConvertTo-Json | Set-Content -LiteralPath (Join-Path $out 'result.json') -Encoding UTF8
} catch {
    [ordered]@{completed=$false;error=$_.Exception.Message;stack=$_.ScriptStackTrace} | ConvertTo-Json |
        Set-Content -LiteralPath (Join-Path $out 'failure.json') -Encoding UTF8
    throw
} finally { $nvram.Dispose() }
