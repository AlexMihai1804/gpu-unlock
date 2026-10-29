# Formats only the explicitly authorized SanDisk USB partition. No firmware,
# Windows ESP, BCD, boot order or Secure Boot variable is written by this script.
param([Parameter(Mandatory=$true)][string]$PlanPath, [switch]$ValidateOnly)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$resultsRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot 'results'))
$planFile = [IO.Path]::GetFullPath($PlanPath)
if (-not $planFile.StartsWith($resultsRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Plan must be a local results file.' }
$plan = Get-Content -LiteralPath $planFile -Raw -Encoding UTF8 | ConvertFrom-Json
$outDir = [IO.Path]::GetFullPath([string]$plan.output_directory)
if ($ValidateOnly) { $outDir += '-validation' }
if (-not $outDir.StartsWith($resultsRoot + '\', [StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $outDir)) {
    throw 'Output must be a new ordinary directory under results.'
}
New-Item -ItemType Directory -Path $outDir | Out-Null
$resultFile = Join-Path $outDir 'result.json'
$report = [ordered]@{
    utc = (Get-Date).ToUniversalTime().ToString('o')
    operation = 'User-authorized USB quick format FAT32 and PROBE copy only'
    success = $false
    validation_only = [bool]$ValidateOnly
    format_started = $false
    format_completed = $false
    firmware_written = $false
    secure_boot_keys_enrolled = $false
    boot_configuration_changed = $false
    hardware_probe_executed = $false
    unlock_applied = $false
}
Start-Transcript -LiteralPath (Join-Path $outDir 'transcript.txt') | Out-Null

function Assert-UsbTarget {
    $disk = Get-Disk -Number ([uint32]$plan.disk_number)
    if ([string]$disk.BusType -ne 'USB' -or $disk.IsBoot -or $disk.IsSystem -or $disk.IsOffline -or $disk.IsReadOnly -or
        [string]$disk.PartitionStyle -ne 'GPT' -or [uint64]$disk.Size -ne [uint64]$plan.disk_bytes -or
        ([string]$disk.SerialNumber).Trim() -cne [string]$plan.serial -or
        [string]$disk.UniqueId -cne [string]$plan.unique_id -or [string]$disk.Path -ine [string]$plan.device_path) {
        throw 'USB identity/state changed; refusing to format.'
    }
    $parts = @(Get-Partition -DiskNumber $disk.Number)
    if ($parts.Count -ne 1) { throw 'Expected exactly one USB partition.' }
    $part = $parts[0]
    if ($part.IsBoot -or $part.IsSystem -or $part.PartitionNumber -ne [uint32]$plan.partition_number -or
        [string]$part.DriveLetter -cne [string]$plan.drive_letter -or
        [string]$part.Guid -ine [string]$plan.partition_guid -or [string]$part.GptType -ine '{ebd0a0a2-b9e5-4433-87c0-68b6b72699c7}' -or
        [uint64]$part.Offset -ne [uint64]$plan.partition_offset -or [uint64]$part.Size -ne [uint64]$plan.partition_bytes) {
        throw 'USB partition identity/state changed.'
    }
    $volumes = @($part | Get-Volume)
    if ($volumes.Count -ne 1 -or [string]$volumes[0].DriveType -ne 'Removable' -or
        [string]$volumes[0].DriveLetter -cne [string]$plan.drive_letter) { throw 'Expected one removable USB volume.' }
    return $part
}

function Internal-StorageSnapshot {
    return [ordered]@{
        disks = @(Get-Disk | Where-Object { [string]$_.BusType -ne 'USB' } | Sort-Object Number |
            Select-Object Number,UniqueId,PartitionStyle,Size,IsBoot,IsSystem)
        partitions = @(Get-Partition | Where-Object { $_.DiskNumber -ne [uint32]$plan.disk_number } |
            Sort-Object DiskNumber,PartitionNumber | Select-Object DiskNumber,PartitionNumber,DriveLetter,Guid,GptType,Offset,Size,IsBoot,IsSystem)
    }
}

try {
    $principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $ValidateOnly -and -not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'UAC elevation required for the authorized USB format.' }
    $source = [IO.Path]::GetFullPath([string]$plan.source_directory)
    $expectedSource = Join-Path $projectRoot 'build\release-20261025-v2\USB-PROBE'
    if ($source -ine $expectedSource -or -not (Test-Path -LiteralPath $source -PathType Container)) { throw 'Wrong PROBE source.' }
    $sourceEntries = @(Get-ChildItem -LiteralPath $source -Force -Recurse)
    if ((Get-Item -LiteralPath $source).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Source is a reparse point.' }
    foreach ($entry in $sourceEntries) {
        if ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Reparse points are not allowed in USB sources.' }
    }
    $sourceFiles = @($sourceEntries | Where-Object { -not $_.PSIsContainer })
    $expectedNames = @($plan.files_sha256.PSObject.Properties | ForEach-Object { $_.Name } | Sort-Object)
    $actualNames = @($sourceFiles | ForEach-Object { $_.FullName.Substring($source.Length + 1).Replace('\','/') } | Sort-Object)
    if (($actualNames -join "`n") -cne ($expectedNames -join "`n")) { throw 'Source file set changed after plan creation.' }
    $manifest = Get-Content -LiteralPath (Join-Path $source 'STAGING-MANIFEST.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($manifest.mode -ne 'probe' -or $manifest.hardware_tested -or $manifest.mok_enrolled) { throw 'Source is not an untested PROBE package.' }
    $bootFiles = @(Get-ChildItem -LiteralPath (Join-Path $source 'EFI\BOOT') -File | Select-Object -ExpandProperty Name | Sort-Object)
    if (($bootFiles -join ',') -ine 'BOOTX64.EFI,grubx64.efi,mmx64.efi') { throw 'Unexpected boot images.' }
    foreach ($item in $plan.files_sha256.PSObject.Properties) {
        $path = [IO.Path]::GetFullPath((Join-Path $source $item.Name))
        if (-not $path.StartsWith($source + '\', [StringComparison]::OrdinalIgnoreCase) -or
            (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ine [string]$item.Value) { throw 'Source hash/path mismatch.' }
    }
    if ((Get-FileHash -LiteralPath (Join-Path $source 'EFI\BOOT\grubx64.efi') -Algorithm SHA256).Hash -ine
        '8f099671f487eca54c7584d913ba29b133f40cc6d86cb1c7e325344d2f509070') { throw 'Wrong tested PROBE image.' }
    $internalBefore = Internal-StorageSnapshot
    $internalBeforeJson = $internalBefore | ConvertTo-Json -Depth 8 -Compress
    $internalBefore | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $outDir 'internal-storage-before.json') -Encoding UTF8
    $partition = Assert-UsbTarget
    $volume = $partition | Get-Volume
    if ([string]$volume.FileSystem -ine [string]$plan.initial_filesystem) { throw 'Initial USB filesystem changed.' }
    $usbRoot = [IO.Path]::GetFullPath(([string]$plan.drive_letter + ':\'))
    if ($usbRoot -ine 'F:\' -or $usbRoot -ieq [IO.Path]::GetPathRoot($env:SystemRoot)) { throw 'Unexpected or system volume root.' }
    Write-Output ('Formatting only USB ' + $plan.serial + ' at ' + $usbRoot)
    $partition = Assert-UsbTarget
    $volume = $partition | Get-Volume
    if ($ValidateOnly) {
        $report.success = $true
        $report.target_identity_validated = $true
        Write-Output 'Read-only validation passed. No format or USB file writes performed.'
        exit 0
    }
    $report.format_started = $true
    $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $resultFile -Encoding UTF8
    $volume | Format-Volume -FileSystem FAT32 -NewFileSystemLabel M6501PROBE -Force -Confirm:$false -ErrorAction Stop | Out-Null
    $report.format_completed = $true
    $partition = Assert-UsbTarget
    $formatted = $partition | Get-Volume
    if ([string]$formatted.FileSystem -ine 'FAT32' -or [string]$formatted.FileSystemLabel -cne 'M6501PROBE') { throw 'FAT32 format verification failed.' }
    foreach ($file in $sourceFiles) {
        $relative = $file.FullName.Substring($source.Length + 1)
        $destination = [IO.Path]::GetFullPath((Join-Path $usbRoot $relative))
        if (-not $destination.StartsWith($usbRoot, [StringComparison]::OrdinalIgnoreCase)) { throw 'Copy target escapes the authorized USB.' }
        $parent = Split-Path -Parent $destination
        if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent | Out-Null }
        Copy-Item -LiteralPath $file.FullName -Destination $destination -ErrorAction Stop
    }
    # Empty directory is needed by the UEFI log writer.
    if (-not (Test-Path -LiteralPath (Join-Path $usbRoot 'RTX-UNLOCK'))) { New-Item -ItemType Directory -Path (Join-Path $usbRoot 'RTX-UNLOCK') | Out-Null }
    $verified = @()
    foreach ($item in $plan.files_sha256.PSObject.Properties) {
        $destination = [IO.Path]::GetFullPath((Join-Path $usbRoot $item.Name))
        if (-not $destination.StartsWith($usbRoot, [StringComparison]::OrdinalIgnoreCase)) { throw 'Verification target escapes USB.' }
        $actual = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -cne ([string]$item.Value).ToLowerInvariant()) { throw 'USB readback hash mismatch.' }
        $verified += [ordered]@{ file=$item.Name; sha256=$actual; bytes=(Get-Item -LiteralPath $destination).Length }
    }
    $partition = Assert-UsbTarget
    $internalAfter = Internal-StorageSnapshot
    $internalAfter | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $outDir 'internal-storage-after.json') -Encoding UTF8
    if (($internalAfter | ConvertTo-Json -Depth 8 -Compress) -cne $internalBeforeJson) { throw 'Internal partition inventory changed during USB preparation; inspect report.' }
    $report.usb = [ordered]@{ disk=[uint32]$plan.disk_number; serial=[string]$plan.serial; root=$usbRoot; filesystem='FAT32'; label='M6501PROBE' }
    $report.verified_files = $verified
    $report.internal_partition_inventory_unchanged = $true
    $report.success = $true
    Write-Output 'USB PROBE prepared and every copied file read back and verified. No reboot or enrollment performed.'
} catch {
    $report.error = $_.Exception.Message
    Write-Output ('Preparation stopped: ' + $_.Exception.Message)
} finally {
    $report.completed_utc = (Get-Date).ToUniversalTime().ToString('o')
    $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $resultFile -Encoding UTF8
    Stop-Transcript | Out-Null
}
if (-not $report.success) { exit 1 }
