# Reads the existing private ESP and firmware variables; never writes boot settings.
param([Parameter(Mandatory=$true)][string]$OutputDirectory,[ValidateSet('SS0','TF32')][string]$Profile='SS0')
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$out=[IO.Path]::GetFullPath($OutputDirectory)
if (-not $out.StartsWith((Join-Path $root 'results')+'\',[StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $out)) { throw 'Use a new results directory.' }
New-Item -ItemType Directory -Path $out | Out-Null
$mounted=$false
try {
    $p=Get-Partition -DiskNumber 1 -PartitionNumber 4
    if ($p.Guid.Trim('{}') -ne '33333333-3333-4333-8333-333333333333' -or
        $p.GptType.Trim('{}') -ne 'c12a7328-f81f-11d2-ba4b-00a0c93ec93b' -or
        $p.Offset -ne 2047869976576 -or $p.Size -ne 536870912) { throw 'Unexpected internal ESP identity.' }
    if (Test-Path 'G:\') { throw 'G: is occupied; no mount was attempted.' }
    & mountvol.exe G: '\\?\Volume{33333333-3333-4333-8333-333333333333}\'
    if ($LASTEXITCODE -ne 0) { throw 'Temporary mount failed.' }
    $mounted=$true
    $drive=New-Object IO.DriveInfo('G:\')
    if ($drive.VolumeLabel -ne 'M6501GPU' -or $drive.DriveFormat -ne 'FAT32') { throw 'Unexpected volume label or filesystem.' }
    $manifestRelative=if ($Profile -eq 'TF32') {'build\automatic-tf32-release-20261026-v1\MANIFEST.json'} else {'build\internal-release-20261025-v1\MANIFEST.json'}
    $manifest=Get-Content -LiteralPath (Join-Path $root $manifestRelative) -Raw | ConvertFrom-Json
    $hashes=@(foreach ($entry in $manifest.files.PSObject.Properties) {
        $file=Join-Path 'G:\' $entry.Name.Replace('/','\')
        $actual=(Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne $entry.Value) { throw ('Installed file mismatch: '+$entry.Name) }
        [ordered]@{file=$entry.Name;sha256=$actual;bytes=(Get-Item -LiteralPath $file).Length}
    })
    $hashes | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $out 'installed-files.json') -Encoding UTF8
    $logs=Join-Path $out 'RTX-UNLOCK'
    New-Item -ItemType Directory -Path $logs | Out-Null
    $logRoot=if ($Profile -eq 'TF32') {'G:\EFI\M6501TF32\RTX-UNLOCK'} else {'G:\EFI\M6501GPU\RTX-UNLOCK'}
    $inventory=@(foreach ($dir in Get-ChildItem -LiteralPath $logRoot -Directory | Where-Object Name -Match '^RUN[0-9]{4}$') {
        $dest=Join-Path $logs $dir.Name
        New-Item -ItemType Directory -Path $dest | Out-Null
        foreach ($file in Get-ChildItem -LiteralPath $dir.FullName -File) {
            if ($file.Length -gt 16777216) { throw 'Unexpected log size.' }
            $target=Join-Path $dest $file.Name
            Copy-Item -LiteralPath $file.FullName -Destination $target
            $sourceHash=(Get-FileHash -LiteralPath $file.FullName).Hash.ToLowerInvariant()
            if ((Get-FileHash -LiteralPath $target).Hash.ToLowerInvariant() -ne $sourceHash) { throw 'Log archive readback mismatch.' }
            [ordered]@{file=($dir.Name+'/'+$file.Name);bytes=$file.Length;sha256=$sourceHash;last_write_utc=$file.LastWriteTimeUtc.ToString('o')}
        }
    })
    $inventory | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $out 'evidence-hashes.json') -Encoding UTF8
    [ordered]@{utc=(Get-Date).ToUniversalTime().ToString('o');windows_boot_utc=(Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToUniversalTime().ToString('o');partition_guid=$p.Guid;all_installed_hashes_match=$true;source_writes=$false;profile=$Profile} |
        ConvertTo-Json | Set-Content -LiteralPath (Join-Path $out 'windows-return.json') -Encoding UTF8
} catch {
    $_ | Out-String | Set-Content -LiteralPath (Join-Path $out 'failure.txt') -Encoding UTF8
    throw
} finally {
    if ($mounted) { & mountvol.exe G: /D; if ($LASTEXITCODE -ne 0) { throw 'Temporary mount cleanup failed.' } }
}
& (Join-Path $PSScriptRoot 'Collect-ReadOnly.ps1') -OutputDirectory (Join-Path $out 'trust')
$bootNames=@('BootOrder','BootCurrent','Boot0000','Boot0001')
if ($Profile -eq 'TF32') {
    $tf32Install=(Get-Content -LiteralPath (Join-Path $root 'results\latest-automatic-tf32-install.txt') -Raw -Encoding UTF8).Trim()
    if (-not $tf32Install.StartsWith((Join-Path $root 'results\automatic-tf32-install-'),[StringComparison]::OrdinalIgnoreCase)) { throw 'Wrong TF32 installation context.' }
    $tf32State=Get-Content -LiteralPath (Join-Path $tf32Install 'activation-state.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($tf32State.boot_name -notmatch '^Boot[0-9A-F]{4}$') { throw 'Wrong TF32 entry name.' }
    $bootNames += $tf32State.boot_name
}
$boot=@(foreach ($name in $bootNames) {
    $buffer=New-Object byte[] (1024*1024)
    [uint32]$attributes=0
    [int]$errorCode=0
    $length=[M6501FirmwareReader]::Read($name,'{8be4df61-93ca-11d2-aa0d-00e098032b8c}',$buffer,[ref]$attributes,[ref]$errorCode)
    if (-not $length) { throw ('Cannot read '+$name+': '+$errorCode) }
    $actual=New-Object byte[] $length
    [Array]::Copy($buffer,$actual,$length)
    [IO.File]::WriteAllBytes((Join-Path $out ($name+'.bin')),$actual)
    [ordered]@{name=$name;bytes=$length;attributes=$attributes;base64=[Convert]::ToBase64String($actual)}
})
$boot | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $out 'boot-variables.json') -Encoding UTF8
& (Join-Path $PSScriptRoot 'Collect-NormalBootControl.ps1') -OutputDirectory (Join-Path $out 'health-before')
[ordered]@{completed=$true;utc=(Get-Date).ToUniversalTime().ToString('o');temporary_mount_removed=(-not (Test-Path 'G:\'));boot_settings_written=$false} |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $out 'collection-complete.json') -Encoding UTF8
