# Read capacity and shrink limits only. Temporarily mounts the existing ESP;
# never writes its files, resizes partitions, formats or changes boot variables.
param([Parameter(Mandatory=$true)][string]$OutputDirectory)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$out=[IO.Path]::GetFullPath($OutputDirectory)
if (-not $out.StartsWith((Join-Path $projectRoot 'results')+'\',[StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $out)) { throw 'Use a new directory under project results.' }
$esp=Get-Partition -DiskNumber 0 -PartitionNumber 1
if (-not $esp.IsSystem -or $esp.Guid -ine '{11111111-1111-4111-8111-111111111111}') { throw 'System ESP identity changed.' }
if (Test-Path -LiteralPath 'Z:\') { throw 'Z is occupied; no mount performed.' }
New-Item -ItemType Directory -Path $out | Out-Null
$mounted=$false
try {
    & mountvol.exe Z: /S
    if ($LASTEXITCODE -ne 0) { throw 'ESP inspection mount failed.' }
    $mounted=$true
    # mountvol /S mounts the system ESP without assigning a Storage drive letter.
    # Get-Partition -DriveLetter therefore cannot resolve this temporary mount.
    $volume=New-Object IO.DriveInfo('Z:\')
    $files=@(Get-ChildItem -LiteralPath 'Z:\EFI' -Recurse -File | Select-Object @{n='path';e={$_.FullName.Substring(3)}},Length)
    $limits=@()
    foreach ($letter in @('D','E')) {
        $part=Get-Partition -DriveLetter $letter
        try {
            $limit=Get-PartitionSupportedSize -DriveLetter $letter
            $limits += [ordered]@{drive=$letter;disk=$part.DiskNumber;partition=$part.PartitionNumber;guid=$part.Guid;size=$part.Size;size_min=$limit.SizeMin;size_max=$limit.SizeMax;shrink_512MiB_supported=($limit.SizeMin -le $part.Size-536870912)}
        } catch { $limits += [ordered]@{drive=$letter;error=$_.Exception.Message} }
    }
    [ordered]@{
        utc=(Get-Date).ToUniversalTime().ToString('o');operations='Read only; temporary ESP mount removed in finally'
        secure_boot=Confirm-SecureBootUEFI
        esp=[ordered]@{disk=0;partition=1;guid=$esp.Guid;size=$volume.TotalSize;free_bytes=$volume.AvailableFreeSpace;filesystem=$volume.DriveFormat}
        esp_files=$files;partition_shrink_limits=$limits
        disks=@(Get-Disk | Select-Object Number,SerialNumber,UniqueId,Size,LargestFreeExtent,LogicalSectorSize,PhysicalSectorSize)
        partitions=@(Get-Partition | Select-Object DiskNumber,PartitionNumber,Guid,GptType,Offset,Size,DriveLetter,IsBoot,IsSystem)
        bitlocker=@(Get-BitLockerVolume | Select-Object MountPoint,VolumeStatus,ProtectionStatus)
    } | ConvertTo-Json -Depth 9 | Set-Content -LiteralPath (Join-Path $out 'inspection.json') -Encoding UTF8
} finally {
    if ($mounted) { & mountvol.exe Z: /D; if ($LASTEXITCODE -ne 0) { Write-Warning 'Temporary Z mount could not be removed.' } }
}
Write-Output ('Internal boot inspection saved: '+$out)
