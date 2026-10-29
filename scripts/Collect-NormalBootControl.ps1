# Read-only current-boot check. Does not require administrator or modify devices.
param([Parameter(Mandatory=$true)][string]$OutputDirectory)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$out=[IO.Path]::GetFullPath($OutputDirectory)
if (-not $out.StartsWith((Join-Path $projectRoot 'results')+'\',[StringComparison]::OrdinalIgnoreCase) -or
    (Test-Path -LiteralPath $out)) { throw 'Use a new ordinary directory under project results.' }
$boot=(Get-CimInstance Win32_OperatingSystem).LastBootUpTime
$uptime=((Get-Date)-$boot).TotalSeconds
if ($uptime -lt 60) { throw 'Wait until at least one minute after boot before collecting.' }
New-Item -ItemType Directory -Path $out | Out-Null
$events=@(Get-WinEvent -FilterHashtable @{LogName='System';StartTime=$boot;Level=1,2,3} -ErrorAction SilentlyContinue |
    Where-Object { $_.ProviderName -in @('Display','nvlddmkm','Microsoft-Windows-WHEA-Logger') })
$details=@($events | ForEach-Object {
    [xml]$xml=$_.ToXml()
    $fields=[ordered]@{}
    foreach ($item in $xml.SelectNodes("/*[local-name()='Event']/*[local-name()='EventData']/*[local-name()='Data']")) {
        $fields[$item.GetAttribute('Name')]=$item.InnerText
    }
    [ordered]@{utc=$_.TimeCreated.ToUniversalTime().ToString('o');id=$_.Id;provider=$_.ProviderName;level=$_.LevelDisplayName;message=$_.Message;fields=$fields}
})
$secure=(Get-ItemProperty -LiteralPath 'HKLM:\SYSTEM\CurrentControlSet\Control\SecureBoot\State' -Name UEFISecureBootEnabled).UEFISecureBootEnabled
$adapters=@(Get-NetAdapter | Select-Object Name,InterfaceDescription,Status,LinkSpeed,DriverVersion)
$report=[ordered]@{
    utc=(Get-Date).ToUniversalTime().ToString('o');read_only=$true
    boot_utc=$boot.ToUniversalTime().ToString('o');uptime_seconds=$uptime
    note='Caller must establish that this boot was direct without USB; this script cannot infer the complete UEFI path.'
    secure_boot_registry_value=$secure;events=$details;event_count=$details.Count
    network_adapters=$adapters
}
$report | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $out 'boot-control.json') -Encoding UTF8
& nvidia-smi.exe --query-gpu=name,pci.bus_id,driver_version,vbios_version --format=csv,noheader |
    Set-Content -LiteralPath (Join-Path $out 'nvidia-smi.txt') -Encoding UTF8
Write-Output ('Read-only boot control saved: '+$out)
