param([Parameter(Mandatory=$true)][string]$ApprovalRecord)
$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$approval=[IO.Path]::GetFullPath($ApprovalRecord)
$principal=[Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    $process=Start-Process -FilePath (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe') -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',('"'+$PSCommandPath+'"'),'-ApprovalRecord',('"'+$approval+'"')) -Verb RunAs -WindowStyle Hidden -PassThru
    [ordered]@{pid=$process.Id;utc=(Get-Date).ToUniversalTime().ToString('o');approval=$approval} | ConvertTo-Json |
        Set-Content -LiteralPath (Join-Path $root 'results\automatic-tf32-uac-launch.json') -Encoding UTF8
    return
}
try {
    Set-Location -LiteralPath $root
    & (Join-Path $PSScriptRoot 'Install-AutomaticTf32.ps1') -ApprovalRecord $approval
    [ordered]@{completed=$true;utc=(Get-Date).ToUniversalTime().ToString('o');reboot_performed=$false} | ConvertTo-Json |
        Set-Content -LiteralPath (Join-Path $root 'results\automatic-tf32-update-launch-result.json') -Encoding UTF8
} catch {
    [ordered]@{completed=$false;utc=(Get-Date).ToUniversalTime().ToString('o');error=$_.Exception.Message;stack=$_.ScriptStackTrace;reboot_performed=$false} | ConvertTo-Json |
        Set-Content -LiteralPath (Join-Path $root 'results\automatic-tf32-update-launch-result.json') -Encoding UTF8
    throw
}
