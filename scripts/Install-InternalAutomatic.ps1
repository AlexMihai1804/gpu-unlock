# Prepared installer. Requires explicit approval of the exact reviewed plan.
# Shrinks only E: on disk 1, formats only the newly created 512 MiB partition,
# installs its own files there and adds a UEFI entry. Never writes disk 0 files.
param([Parameter(Mandatory=$true)][string]$ApprovalRecord)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
function Sha([string]$p) { (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant() }
$readyPath=Join-Path $root 'results\automatic-internal-ready.json'
$approval=Get-Content -LiteralPath $ApprovalRecord -Raw -Encoding UTF8 | ConvertFrom-Json
if ($approval.plan_sha256 -cne (Sha $readyPath) -or -not $approval.resize_E_512MiB -or
    -not $approval.create_dedicated_FAT32 -or -not $approval.enable_default_boot -or -not $approval.enroll_exact_MOK_hash) {
    throw 'Explicit approval of this exact partition/boot/MOK plan is required.'
}
$ready=Get-Content -LiteralPath $readyPath -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $ready.local_validation_passed -or $approval.pe_authenticode_sha256 -cne $ready.pe_authenticode_sha256) { throw 'Unreviewed image or missing validation.' }
foreach ($f in $ready.supporting_files.PSObject.Properties) {
    if ((Sha (Join-Path $root $f.Name)) -cne $f.Value) { throw ('Reviewed installer/support file changed: '+$f.Name) }
}
if (-not (Confirm-SecureBootUEFI)) { throw 'Secure Boot must remain enabled.' }
$disk=Get-Disk -Number 1
$part=Get-Partition -DiskNumber 1 -PartitionNumber 3
if ($disk.SerialNumber.Trim() -cne $ready.disk_serial -or [uint64]$disk.Size -ne $ready.disk_size -or
    $part.Guid -ine '{44444444-4444-4444-8444-444444444444}' -or $part.DriveLetter -ne 'E' -or
    $part.IsSystem -or $part.IsBoot -or [uint64]$part.Size -ne 107374182400 -or
    [uint64]$part.Offset -ne 1941032665088 -or $disk.LogicalSectorSize -ne 512) { throw 'Disk/E identity or layout changed.' }
$system=Get-Partition -DiskNumber 0 -PartitionNumber 1
if ($system.Guid -ine '{11111111-1111-4111-8111-111111111111}' -or -not $system.IsSystem) { throw 'Windows ESP identity changed.' }
if (Test-Path -LiteralPath 'G:\') { throw 'G is occupied; no resize performed.' }
$bitlocker=Get-BitLockerVolume -MountPoint 'E:'
if ([int]$bitlocker.ProtectionStatus -ne 0 -or [int]$bitlocker.VolumeStatus -ne 0) { throw 'E must be fully decrypted.' }
$newSize=[uint64]$part.Size-536870912
$offset=[uint64]$part.Offset+$newSize
$limit=Get-PartitionSupportedSize -DiskNumber 1 -PartitionNumber 3
if ($limit.SizeMin -gt $newSize) { throw '512 MiB shrink no longer supported.' }
$others=@(Get-Partition -DiskNumber 1 | Where-Object PartitionNumber -ne 3)
$beforeGuids=@(Get-Partition -DiskNumber 1 | Select-Object -ExpandProperty Guid)
foreach ($other in $others) {
    if ($other.Offset -lt $offset+536870912 -and $other.Offset+$other.Size -gt $offset) { throw 'Target region overlaps another partition.' }
}
$source=[IO.Path]::GetFullPath((Join-Path $root $ready.package))
if (-not $source.StartsWith((Join-Path $root 'build')+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Package outside build.' }
$manifest=Get-Content -LiteralPath (Join-Path $source 'MANIFEST.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if ((Sha (Join-Path $source 'MANIFEST.json')) -cne $ready.manifest_sha256) { throw 'Package manifest changed.' }
foreach ($file in $manifest.files.PSObject.Properties) {
    $path=[IO.Path]::GetFullPath((Join-Path $source $file.Name))
    if (-not $path.StartsWith($source+'\',[StringComparison]::OrdinalIgnoreCase) -or
        -not $file.Name.StartsWith('EFI/M6501GPU/',[StringComparison]::OrdinalIgnoreCase) -or
        (Sha $path) -cne $file.Value) { throw 'Package path/hash mismatch.' }
}
if (@(Get-ChildItem -LiteralPath $source -Recurse -Force | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }).Count) { throw 'Reparse points refused.' }
$out=Join-Path $root ('results\internal-install-'+(Get-Date -Format 'yyyyMMdd-HHmmss'))
if (Test-Path -LiteralPath $out) { throw 'Result exists.' }
New-Item -ItemType Directory -Path $out | Out-Null
Copy-Item -LiteralPath $ApprovalRecord -Destination (Join-Path $out 'approval.json')
Copy-Item -LiteralPath $readyPath -Destination (Join-Path $out 'approved-plan.json')
Get-Partition | Select-Object DiskNumber,PartitionNumber,Guid,GptType,Offset,Size,DriveLetter,IsBoot,IsSystem | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $out 'partitions-before.json') -Encoding UTF8
& bcdedit.exe /enum firmware | Out-File -LiteralPath (Join-Path $out 'boot-entries-before.txt') -Encoding UTF8
Add-Type -Path (Join-Path $root 'scripts\BootVariables.cs')
$nvram=New-Object M6501BootVariables
$stage='preflight'
try {
    [byte[]]$oldOrder=$nvram.Read('BootOrder')
    if (-not $oldOrder -or $oldOrder.Length%2) { throw 'Unexpected original BootOrder.' }
    $oldEntries=[ordered]@{}
    $hasWindows=$false
    for ($i=0;$i -lt $oldOrder.Length;$i+=2) {
        $name='Boot'+[BitConverter]::ToUInt16($oldOrder,$i).ToString('X4')
        $bytes=$nvram.Read($name)
        if (-not $bytes) { throw 'Original BootOrder contains a missing entry.' }
        $oldEntries[$name]=[Convert]::ToBase64String($bytes)
        if ([Text.Encoding]::Unicode.GetString($bytes).ToLowerInvariant().Contains('\efi\microsoft\boot\bootmgfw.efi')) { $hasWindows=$true }
    }
    if (-not $hasWindows) { throw 'Original Windows boot entry missing; no resize performed.' }
    $newName=$null
    for ($i=0;$i -lt 1024;$i++) {
        $name='Boot'+$i.ToString('X4')
        if (-not $oldEntries.Contains($name) -and $null -eq $nvram.Read($name)) { $newName=$name; $newId=[uint16]$i; break }
    }
    if (-not $newName) { throw 'No unused boot slot in allowed range.' }
    [ordered]@{BootOrder=[Convert]::ToBase64String($oldOrder);entries=$oldEntries} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $out 'boot-backup.json') -Encoding UTF8
    # This is the first change to a data partition. Nothing above resizes/writes it.
    Resize-Partition -DiskNumber 1 -PartitionNumber 3 -Size $newSize
    $stage='E-shrunk'
    $created=New-Partition -DiskNumber 1 -Offset $offset -Size 536870912 -DriveLetter G -GptType '{ebd0a0a2-b9e5-4433-87c0-68b6b72699c7}'
    if ($created.Size -ne 536870912 -or $created.Offset -ne $offset -or $created.PartitionNumber -le 3 -or
        $created.IsBoot -or $created.IsSystem -or $created.Guid -in $beforeGuids) { throw 'New partition identity invalid; formatting refused.' }
    $stage='new-partition-created'
    Format-Volume -Partition $created -FileSystem FAT32 -NewFileSystemLabel M6501GPU -AllocationUnitSize 4096 -Confirm:$false | Out-Null
    $stage='new-partition-formatted'
    foreach ($file in $manifest.files.PSObject.Properties) {
        $target=[IO.Path]::GetFullPath((Join-Path 'G:\' $file.Name))
        if (-not $target.StartsWith('G:\EFI\M6501GPU\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Target outside private directory.' }
        $parent=Split-Path -Parent $target
        if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent | Out-Null }
        Copy-Item -LiteralPath (Join-Path $source $file.Name) -Destination $target
        if ((Sha $target) -cne $file.Value) { throw 'Installed file readback differs.' }
    }
    $stage='files-verified'
    Set-Partition -DiskNumber 1 -PartitionNumber $created.PartitionNumber -GptType '{c12a7328-f81f-11d2-ba4b-00a0c93ec93b}'
    $created=Get-Partition -DiskNumber 1 -PartitionNumber $created.PartitionNumber
    $info=Join-Path $out 'installed-partition.json'
    [ordered]@{disk=1;partition_number=$created.PartitionNumber;guid=$created.Guid;gpt_type=$created.GptType;offset=$created.Offset;size=$created.Size} | ConvertTo-Json | Set-Content -LiteralPath $info -Encoding UTF8
    $option=Join-Path $out 'load-option.json'
    & (Join-Path $root '.venv\Scripts\python.exe') -X utf8 (Join-Path $root 'tools\internal_boot.py') --partition-info $info --output $option
    if ($LASTEXITCODE -ne 0) { throw 'Load-option encoder rejected partition.' }
    $data=Get-Content -LiteralPath $option -Raw -Encoding UTF8 | ConvertFrom-Json
    [byte[]]$payload=[Convert]::FromBase64String($data.base64)
    [byte[]]$newOrder=@([BitConverter]::GetBytes($newId))+$oldOrder
    $state=[ordered]@{utc=(Get-Date).ToUniversalTime().ToString('o');boot_name=$newName;payload_base64=$data.base64;old_order_base64=[Convert]::ToBase64String($oldOrder);new_order_base64=[Convert]::ToBase64String($newOrder);partition=$created.Guid;E_original_size=107374182400;E_new_size=$newSize;new_partition_size=536870912;windows_esp_files_written=$false;existing_boot_entries_modified=$false;candidate_sha256=$ready.file_sha256;candidate_MOK_hash=$ready.pe_authenticode_sha256}
    $state | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $out 'activation-state.json') -Encoding UTF8
    if (-not (Confirm-SecureBootUEFI)) { throw 'Secure Boot changed; activation refused.' }
    $nvram.Create($newName,$payload)
    $stage='new-boot-entry-created'
    foreach ($name in $oldEntries.Keys) {
        if ([Convert]::ToBase64String($nvram.Read($name)) -cne $oldEntries[$name]) { throw 'An existing firmware entry changed; activation refused.' }
    }
    $nvram.ReplaceOrder($oldOrder,$newOrder)
    $stage='automatic-default-enabled'
    Set-Partition -DiskNumber 1 -PartitionNumber $created.PartitionNumber -NoDefaultDriveLetter $true
    Remove-PartitionAccessPath -DiskNumber 1 -PartitionNumber $created.PartitionNumber -AccessPath 'G:\'
    & bcdedit.exe /enum firmware | Out-File -LiteralPath (Join-Path $out 'boot-entries-after.txt') -Encoding UTF8
    [ordered]@{stage=$stage;installed=$true;reboot_performed=$false;MOK_enrolled=$false;physical_automatic_boot_validated=$false;next='Enroll only the reviewed grubx64.efi hash in MOK, then boot automatically; keep Secure Boot enabled'} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $out 'result.json') -Encoding UTF8
    $out | Set-Content -LiteralPath (Join-Path $root 'results\latest-internal-install.txt') -Encoding UTF8
} catch {
    [ordered]@{stage=$stage;error=$_.Exception.Message;automatic_retry=$false;note='Do not format/delete another partition or repeat installation. Review saved state first.'} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $out 'failure.json') -Encoding UTF8
    throw
} finally { $nvram.Dispose() }
Write-Output ('Installed in dedicated internal FAT32; no reboot. Evidence: '+$out)
