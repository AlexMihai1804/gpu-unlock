# Finish the already approved installation after files were verified.
# Never resizes, creates, formats or removes a partition. The original script
# lost the firmware privilege after its final SecureBoot cmdlet; obtain the
# restricted helper only AFTER all Storage/SecureBoot preflight calls.
param([Parameter(Mandatory=$true)][string]$InstallDirectory)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$directory=[IO.Path]::GetFullPath($InstallDirectory)
if (-not $directory.StartsWith((Join-Path $root 'results')+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Saved installation evidence required.' }
function Sha([string]$path) { (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() }
$approval=Get-Content -LiteralPath (Join-Path $directory 'approval.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$plan=Get-Content -LiteralPath (Join-Path $directory 'approved-plan.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if ((Sha (Join-Path $directory 'approved-plan.json')) -cne $approval.plan_sha256 -or
    -not $approval.enable_default_boot -or -not $approval.create_dedicated_FAT32) { throw 'Exact approved installation plan required.' }
foreach ($f in $plan.supporting_files.PSObject.Properties) { if ((Sha (Join-Path $root $f.Name)) -cne $f.Value) { throw 'Reviewed support file changed.' } }
$state=Get-Content -LiteralPath (Join-Path $directory 'activation-state.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$backup=Get-Content -LiteralPath (Join-Path $directory 'boot-backup.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$option=Get-Content -LiteralPath (Join-Path $directory 'load-option.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if ($state.boot_name -cne 'Boot0000' -or $state.partition -ine '{33333333-3333-4333-8333-333333333333}' -or
    $state.candidate_sha256 -cne $plan.file_sha256 -or $state.candidate_MOK_hash -cne $plan.pe_authenticode_sha256 -or
    $state.payload_base64 -cne $option.base64 -or $state.old_order_base64 -cne $backup.BootOrder -or
    $option.decoded.partition_guid -cne '33333333-3333-4333-8333-333333333333' -or $option.decoded.path -cne '\EFI\M6501GPU\shimx64.efi') { throw 'Saved activation state differs.' }
$part=Get-Partition -DiskNumber 1 -PartitionNumber 4
$data=Get-Partition -DiskNumber 1 -PartitionNumber 3
$disk=Get-Disk -Number 1
if ($part.Guid -ine $state.partition -or $part.Size -ne 536870912 -or $part.Offset -ne 2047869976576 -or
    $part.GptType -ine '{c12a7328-f81f-11d2-ba4b-00a0c93ec93b}' -or $part.DriveLetter -ne 'G' -or
    $data.Guid -ine $plan.E_partition_guid -or $data.Size -ne $plan.E_new_size -or
    $disk.SerialNumber.Trim() -cne $plan.disk_serial) { throw 'Existing installed partition layout differs.' }
$volume=Get-Volume -DriveLetter G
if ($volume.FileSystem -ne 'FAT32' -or $volume.FileSystemLabel -cne 'M6501GPU') { throw 'Installed FAT32 identity differs.' }
$package=Join-Path $root $plan.package
$manifest=Get-Content -LiteralPath (Join-Path $package 'MANIFEST.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if ((Sha (Join-Path $package 'MANIFEST.json')) -cne $plan.manifest_sha256) { throw 'Package manifest changed.' }
foreach ($f in $manifest.files.PSObject.Properties) {
    $path=[IO.Path]::GetFullPath((Join-Path 'G:\' $f.Name))
    if (-not $path.StartsWith('G:\EFI\M6501GPU\',[StringComparison]::OrdinalIgnoreCase) -or (Sha $path) -cne $f.Value) { throw 'Installed files differ.' }
}
if (-not (Confirm-SecureBootUEFI)) { throw 'Secure Boot must remain enabled.' }
Add-Type -Path (Join-Path $root 'scripts\BootVariables.cs')
$nvram=New-Object M6501BootVariables
try {
    # No Storage or SecureBoot cmdlets between privilege acquisition and writes.
    & whoami.exe /priv | Out-File -LiteralPath (Join-Path $directory 'activation-privileges.txt') -Encoding UTF8
    [byte[]]$current=$nvram.Read('BootOrder')
    $encodedCurrent=[Convert]::ToBase64String($current)
    if ($encodedCurrent -cne $state.old_order_base64 -and $encodedCurrent -cne $state.new_order_base64) { throw 'Boot order changed; refuse overwrite.' }
    foreach ($entry in $backup.entries.PSObject.Properties) {
        if ([Convert]::ToBase64String($nvram.Read($entry.Name)) -cne $entry.Value) { throw 'Original firmware entry changed.' }
    }
    [byte[]]$existing=$nvram.Read($state.boot_name)
    if ($null -eq $existing) { $nvram.Create($state.boot_name,[Convert]::FromBase64String($state.payload_base64)) }
    elseif ([Convert]::ToBase64String($existing) -cne $state.payload_base64) { throw 'Target slot is no longer our entry.' }
    if ($encodedCurrent -ceq $state.old_order_base64) {
        $nvram.ReplaceOrder([Convert]::FromBase64String($state.old_order_base64),[Convert]::FromBase64String($state.new_order_base64))
    }
    $after=[Convert]::ToBase64String($nvram.Read('BootOrder'))
    if ($after -cne $state.new_order_base64) { throw 'Default boot order readback failed.' }
    foreach ($entry in $backup.entries.PSObject.Properties) {
        if ([Convert]::ToBase64String($nvram.Read($entry.Name)) -cne $entry.Value) { throw 'Original entry changed after activation.' }
    }
    [ordered]@{utc=(Get-Date).ToUniversalTime().ToString('o');default_boot_enabled=$true;new_entry_verified=$true;original_entries_preserved=$true;BootOrder_base64=$after;partition_changes_in_this_step=$false;reboot_performed=$false;candidate_MOK_hash=$plan.pe_authenticode_sha256} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $directory 'activation-completed.json') -Encoding UTF8
} finally { $nvram.Dispose() }
$cleanupError=$null
try {
    Set-Partition -DiskNumber 1 -PartitionNumber 4 -NoDefaultDriveLetter $true
    Remove-PartitionAccessPath -DiskNumber 1 -PartitionNumber 4 -AccessPath 'G:\'
} catch { $cleanupError=$_.Exception.Message }
& bcdedit.exe /enum firmware | Out-File -LiteralPath (Join-Path $directory 'boot-entries-after.txt') -Encoding UTF8
[ordered]@{utc=(Get-Date).ToUniversalTime().ToString('o');stage='automatic-default-enabled';installed=$true;reboot_performed=$false;MOK_enrolled=$false;physical_automatic_boot_validated=$false;drive_letter_cleanup_error=$cleanupError;next='Physical exact-hash MOK enrollment, then automatic boot; do not rerun installer'} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $directory 'result.json') -Encoding UTF8
$directory | Set-Content -LiteralPath (Join-Path $root 'results\latest-internal-install.txt') -Encoding UTF8
Write-Output 'Approved internal default boot activated; original boot entries preserved. No reboot.'
