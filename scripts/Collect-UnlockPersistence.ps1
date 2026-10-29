# Read-only diagnostics. Does not change power policy, devices, drivers, firmware or boot settings.
param([string]$OutputDirectory)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
if (-not $OutputDirectory) { $OutputDirectory=Join-Path $root ('results\persistence-investigation-'+(Get-Date -Format 'yyyyMMdd-HHmmss')) }
$out=[IO.Path]::GetFullPath($OutputDirectory)
if (-not $out.StartsWith((Join-Path $root 'results')+'\',[StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $out)) { throw 'Choose a new project results directory.' }
New-Item -ItemType Directory -Path $out | Out-Null
$boot=(Get-CimInstance Win32_OperatingSystem).LastBootUpTime
function EventRecord($event) {
    [xml]$xml=$event.ToXml()
    $fields=[ordered]@{}
    foreach ($item in $xml.SelectNodes("/*[local-name()='Event']/*[local-name()='EventData']/*[local-name()='Data']")) { $fields[$item.GetAttribute('Name')]=$item.InnerText }
    [ordered]@{utc=$event.TimeCreated.ToUniversalTime().ToString('o');provider=$event.ProviderName;id=$event.Id;record_id=$event.RecordId;level=$event.Level;fields=$fields;message=$event.Message}
}
$providers=@('Microsoft-Windows-Kernel-Power','Microsoft-Windows-Power-Troubleshooter','Microsoft-Windows-WHEA-Logger','Display','nvlddmkm','Microsoft-Windows-Kernel-Boot')
$events=@(Get-WinEvent -FilterHashtable @{LogName='System';ProviderName=$providers;StartTime=$boot} -ErrorAction SilentlyContinue | Sort-Object TimeCreated | ForEach-Object { EventRecord $_ })
$events | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $out 'system-events.json') -Encoding UTF8
$channels=@(foreach ($name in @('Microsoft-Windows-Kernel-PnP/Configuration','Microsoft-Windows-DriverFrameworks-UserMode/Operational','Microsoft-Windows-DxgKrnl/Operational','Microsoft-Windows-Diagnostics-Performance/Operational')) {
    try {
        $log=Get-WinEvent -ListLog $name -ErrorAction Stop
        $matched=@()
        if ($log.IsEnabled) {
            $matched=@(Get-WinEvent -FilterHashtable @{LogName=$name;StartTime=$boot} -ErrorAction SilentlyContinue |
                Where-Object { $_.ToXml() -match 'VEN_10DE.*DEV_2520|VEN_1022.*DEV_14B8' } | ForEach-Object { EventRecord $_ })
        }
        [ordered]@{name=$name;enabled=$log.IsEnabled;matching_gpu_events=$matched}
    } catch { [ordered]@{name=$name;error=$_.Exception.Message} }
})
$channels | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $out 'device-events.json') -Encoding UTF8
$devices=@(Get-PnpDevice -Class Display -PresentOnly | ForEach-Object {
    $device=$_
    $properties=@(Get-PnpDeviceProperty -InstanceId $device.InstanceId -ErrorAction SilentlyContinue |
        Where-Object { $_.KeyName -match 'PowerData|D3Cold|Location|Parent$|DriverVersion$|DriverDate$|ProblemCode$|DevNodeStatus$|Service$|Address$' } |
        Select-Object KeyName,Type,Data)
    [ordered]@{name=$device.FriendlyName;status=$device.Status;instance_id=$device.InstanceId;properties=$properties}
})
$devices | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $out 'display-devices.json') -Encoding UTF8
$commands=@(
    @{name='sleep-capabilities';args=@('/a')},
    @{name='active-power-scheme';args=@('/getactivescheme')},
    @{name='pcie-power-policy';args=@('/query','SCHEME_CURRENT','SUB_PCIEXPRESS')},
    @{name='sleep-power-policy';args=@('/query','SCHEME_CURRENT','SUB_SLEEP')}
)
foreach ($command in $commands) {
    $arguments=$command.args
    & powercfg.exe @arguments | Out-File -LiteralPath (Join-Path $out ($command.name+'.txt')) -Encoding UTF8
}
& nvidia-smi.exe -q | Out-File -LiteralPath (Join-Path $out 'nvidia-smi.txt') -Encoding UTF8
$processes=@(Get-Process -ErrorAction SilentlyContinue | Where-Object ProcessName -Match 'ASUS|GHelper|Armoury|NVIDIA|nvcontainer' | Select-Object ProcessName,Id)
$services=@(Get-Service | Where-Object Name -Match 'ASUS|Armoury|NvContainer|NVDisplay' | Select-Object Name,Status,StartType)
[ordered]@{utc=(Get-Date).ToUniversalTime().ToString('o');boot_utc=$boot.ToUniversalTime().ToString('o');read_only=$true;secure_boot_registry=(Get-ItemProperty -LiteralPath 'HKLM:\SYSTEM\CurrentControlSet\Control\SecureBoot\State').UEFISecureBootEnabled;processes=$processes;services=$services;system_events=$events.Count;output=$out} |
    ConvertTo-Json -Depth 7 | Set-Content -LiteralPath (Join-Path $out 'collection.json') -Encoding UTF8
$out | Set-Content -LiteralPath (Join-Path $root 'results\latest-persistence-investigation.txt') -Encoding UTF8
Write-Output ('Read-only investigation: '+$out)
