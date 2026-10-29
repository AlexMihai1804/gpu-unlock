param([Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$out=[IO.Path]::GetFullPath($OutputDirectory)
if (-not $out.StartsWith((Join-Path $root 'results')+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Use project results.' }
$principal=[Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    $process=Start-Process -FilePath (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe') -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',('"'+$PSCommandPath+'"'),'-OutputDirectory',('"'+$out+'"')) -Verb RunAs -WindowStyle Hidden -PassThru
    [ordered]@{pid=$process.Id;output=$out;utc=(Get-Date).ToUniversalTime().ToString('o')} | ConvertTo-Json |
        Set-Content -LiteralPath (Join-Path $root 'results\latest-tf32-post-collection-launch.json') -Encoding UTF8
    return
}
try {
    & (Join-Path $PSScriptRoot 'Collect-InternalAutomatic.ps1') -Profile TF32 -OutputDirectory $out
    [ordered]@{completed=$true;utc=(Get-Date).ToUniversalTime().ToString('o')} | ConvertTo-Json |
        Set-Content -LiteralPath (Join-Path $out 'launcher-result.json') -Encoding UTF8
} catch {
    if (Test-Path -LiteralPath $out) {
        [ordered]@{completed=$false;error=$_.Exception.Message;stack=$_.ScriptStackTrace} | ConvertTo-Json |
            Set-Content -LiteralPath (Join-Path $out 'launcher-result.json') -Encoding UTF8
    }
    throw
}
