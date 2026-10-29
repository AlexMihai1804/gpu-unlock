# Add the authorized automatic SS1 experiment on the EXISTING private ESP.
# No resizing/formatting, existing file replacement, key writes or reboot.
param([Parameter(Mandatory=$true)][string]$ApprovalRecord,[switch]$ValidateOnly)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
function Sha([string]$path) { (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() }
function Save-Json($value,[string]$path) { $value | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $path -Encoding UTF8 }
$principal=[Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $ValidateOnly -and -not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Run through the approved UAC launcher.' }
$approvalPath=[IO.Path]::GetFullPath($ApprovalRecord)
if (-not $approvalPath.StartsWith((Join-Path $root 'results')+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Approval must be saved under results.' }
$approval=Get-Content -LiteralPath $approvalPath -Raw -Encoding UTF8 | ConvertFrom-Json
$readyPath=Join-Path $root 'results\automatic-tf32-ready.json'
if ($approval.plan_sha256 -cne (Sha $readyPath) -or -not $approval.install_separate_directory -or
    -not $approval.enable_automatic_ss1_default -or -not $approval.additional_exact_MOK_hash -or
    -not $approval.preserve_old_automatic_entry) { throw 'Exact authorized automatic TF32 plan required.' }
$ready=Get-Content -LiteralPath $readyPath -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $ready.local_validation_passed -or $ready.mode -cne 'automatic-tf32-ss1-experiment' -or
    $approval.pe_authenticode_sha256 -cne $ready.pe_authenticode_sha256) { throw 'Unreviewed automatic TF32 candidate.' }
foreach ($entry in $ready.supporting_files.PSObject.Properties) {
    if ((Sha (Join-Path $root $entry.Name)) -cne $entry.Value) { throw ('Reviewed support file changed: '+$entry.Name) }
}
$source=[IO.Path]::GetFullPath((Join-Path $root $ready.package))
if (-not $source.StartsWith((Join-Path $root 'build')+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Package outside build.' }
$manifestPath=Join-Path $source 'MANIFEST.json'
if ((Sha $manifestPath) -cne $ready.manifest_sha256) { throw 'Package manifest changed.' }
$manifest=Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($manifest.mode -cne 'automatic-tf32-ss1-experiment' -or $manifest.countdown_seconds -ne 5 -or
    $manifest.candidate_sha256 -cne $ready.file_sha256 -or
    $manifest.candidate_pe_authenticode_sha256 -cne $ready.pe_authenticode_sha256) { throw 'Package identity differs.' }
foreach ($entry in $manifest.files.PSObject.Properties) {
    $file=[IO.Path]::GetFullPath((Join-Path $source $entry.Name))
    if (-not $entry.Name.StartsWith('EFI/M6501TF32/',[StringComparison]::Ordinal) -or
        -not $file.StartsWith($source+'\',[StringComparison]::OrdinalIgnoreCase) -or
        (Sha $file) -cne $entry.Value) { throw 'Source path/hash differs.' }
}
if (@(Get-ChildItem -LiteralPath $source -Recurse -Force | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }).Count) { throw 'Package reparse point refused.' }
if ($ValidateOnly) { Write-Output 'Local authorization, package paths and hashes validated; no Storage/firmware access.'; return }
if (-not (Confirm-SecureBootUEFI)) { throw 'Secure Boot must remain enabled.' }
$partition=Get-Partition -DiskNumber 1 -PartitionNumber 4
$disk=Get-Disk -Number 1
$system=Get-Partition -DiskNumber 0 -PartitionNumber 1
if ($disk.SerialNumber.Trim() -cne $ready.disk_serial -or [uint64]$disk.Size -ne $ready.disk_size -or
    $partition.Guid.Trim('{}') -cne '33333333-3333-4333-8333-333333333333' -or
    $partition.GptType.Trim('{}') -cne 'c12a7328-f81f-11d2-ba4b-00a0c93ec93b' -or
    [uint64]$partition.Offset -ne 2047869976576 -or [uint64]$partition.Size -ne 536870912 -or
    $system.Guid.Trim('{}') -cne '11111111-1111-4111-8111-111111111111' -or -not $system.IsSystem) { throw 'Disk/ESP identity changed.' }
if (Test-Path -LiteralPath 'G:\') { throw 'G is occupied; no mount attempted.' }
$out=Join-Path $root ('results\automatic-tf32-install-'+(Get-Date -Format 'yyyyMMdd-HHmmss'))
if (Test-Path -LiteralPath $out) { throw 'Output already exists.' }
New-Item -ItemType Directory -Path $out | Out-Null
Copy-Item -LiteralPath $approvalPath -Destination (Join-Path $out 'approval.json')
Copy-Item -LiteralPath $readyPath -Destination (Join-Path $out 'approved-plan.json')
$out | Set-Content -LiteralPath (Join-Path $root 'results\latest-automatic-tf32-install.txt') -Encoding UTF8
$mounted=$false; $nvram=$null; $created=$false; $activated=$false
$newName=$null; $payload=$null; $oldOrder=$null; $newOrder=$null
$stage='preflight'
try {
    & mountvol.exe G: '\\?\Volume{33333333-3333-4333-8333-333333333333}\'
    if ($LASTEXITCODE -ne 0) { throw 'Private ESP mount failed.' }
    $mounted=$true
    $volume=New-Object IO.DriveInfo('G:\')
    if ($volume.DriveFormat -cne 'FAT32' -or $volume.VolumeLabel -cne 'M6501GPU' -or
        $volume.AvailableFreeSpace -lt ([uint64]$manifest.bytes+16777216)) { throw 'Wrong filesystem/label or insufficient space.' }
    if (Test-Path -LiteralPath 'G:\EFI\M6501TF32') { throw 'TF32 directory already exists; no existing file will be overwritten.' }
    $oldManifest=Get-Content -LiteralPath (Join-Path $root 'build\internal-release-20261025-v1\MANIFEST.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($entry in $oldManifest.files.PSObject.Properties) {
        if ((Sha (Join-Path 'G:\' $entry.Name)) -cne $entry.Value) { throw ('Original automatic file differs: '+$entry.Name) }
    }
    Save-Json $oldManifest (Join-Path $out 'old-automatic-manifest.json')
    [ordered]@{disk=1;partition_number=4;guid=$partition.Guid;gpt_type=$partition.GptType;offset=[uint64]$partition.Offset;size=[uint64]$partition.Size} |
        ConvertTo-Json | Set-Content -LiteralPath (Join-Path $out 'partition.json') -Encoding UTF8
    $optionPath=Join-Path $out 'load-option.json'
    & (Join-Path $root '.venv\Scripts\python.exe') -X utf8 (Join-Path $root 'tools\internal_boot.py') --profile tf32-automatic --partition-info (Join-Path $out 'partition.json') --output $optionPath
    if ($LASTEXITCODE -ne 0) { throw 'Boot option encoder rejected the target.' }
    $option=Get-Content -LiteralPath $optionPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($option.decoded.path -cne '\EFI\M6501TF32\shimx64.efi' -or
        $option.decoded.partition_guid -cne '33333333-3333-4333-8333-333333333333') { throw 'Wrong encoded boot path.' }
    foreach ($entry in $manifest.files.PSObject.Properties) {
        $target=[IO.Path]::GetFullPath((Join-Path 'G:\' $entry.Name))
        if (-not $target.StartsWith('G:\EFI\M6501TF32\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Target outside new private directory.' }
        $parent=Split-Path -Parent $target
        if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent | Out-Null }
        Copy-Item -LiteralPath (Join-Path $source $entry.Name) -Destination $target
        if ((Sha $target) -cne $entry.Value) { throw 'Installed file readback mismatch.' }
    }
    foreach ($entry in $oldManifest.files.PSObject.Properties) {
        if ((Sha (Join-Path 'G:\' $entry.Name)) -cne $entry.Value) { throw 'Original automatic files changed during copy.' }
    }
    $stage='files-verified'
    # Storage and SecureBoot cmdlets may alter token privileges. Acquire the
    # restricted helper only after every such call, as in the validated install.
    if (-not (Confirm-SecureBootUEFI)) { throw 'Secure Boot changed; activation refused.' }
    Add-Type -Path (Join-Path $root 'scripts\BootVariables.cs')
    $nvram=New-Object M6501BootVariables
    [byte[]]$oldOrder=$nvram.Read('BootOrder')
    if ([Convert]::ToBase64String($oldOrder) -cne $ready.preflight_boot_order_base64) { throw 'BootOrder changed since preflight; refusing replacement.' }
    $entries=[ordered]@{}
    for ($i=0;$i -lt $oldOrder.Length;$i+=2) {
        $name='Boot'+[BitConverter]::ToUInt16($oldOrder,$i).ToString('X4')
        [byte[]]$bytes=$nvram.Read($name)
        if (-not $bytes) { throw 'A current boot entry is missing.' }
        $entries[$name]=[Convert]::ToBase64String($bytes)
    }
    foreach ($name in @('Boot0000','Boot0001')) {
        if (-not $entries.Contains($name) -or $entries[$name] -cne $ready.preflight_entries.$name) { throw 'Original automatic/Windows entry changed.' }
    }
    for ($i=2;$i -lt 1024;$i++) {
        $name='Boot'+$i.ToString('X4')
        if (-not $entries.Contains($name) -and $null -eq $nvram.Read($name)) { $newName=$name; $newId=[uint16]$i; break }
    }
    if (-not $newName) { throw 'No unused boot slot.' }
    [byte[]]$payload=[Convert]::FromBase64String($option.base64)
    [byte[]]$newOrder=@([BitConverter]::GetBytes($newId))+$oldOrder
    Save-Json ([ordered]@{BootOrder=[Convert]::ToBase64String($oldOrder);entries=$entries}) (Join-Path $out 'boot-backup.json')
    Save-Json ([ordered]@{boot_name=$newName;payload_base64=$option.base64;old_order_base64=[Convert]::ToBase64String($oldOrder);new_order_base64=[Convert]::ToBase64String($newOrder);file_sha256=$ready.file_sha256;pe_authenticode_sha256=$ready.pe_authenticode_sha256;old_automatic_entry='Boot0000';windows_entry='Boot0001'}) (Join-Path $out 'activation-state.json')
    $nvram.Create($newName,$payload)
    $created=$true; $stage='new-entry-created'
    foreach ($name in $entries.Keys) {
        if ([Convert]::ToBase64String($nvram.Read($name)) -cne $entries[$name]) { throw 'An existing boot entry changed.' }
    }
    $nvram.ReplaceOrder($oldOrder,$newOrder)
    $activated=$true; $stage='automatic-tf32-default-enabled-pending-MOK'
    foreach ($name in $entries.Keys) {
        if ([Convert]::ToBase64String($nvram.Read($name)) -cne $entries[$name]) { throw 'An existing entry changed after activation.' }
    }
    Save-Json ([ordered]@{installed=$true;automatic_default_enabled=$true;new_entry=$newName;BootOrder_base64=[Convert]::ToBase64String($nvram.Read('BootOrder'));old_automatic_preserved=$true;original_windows_entry_preserved=$true;windows_esp_files_written=$false;partition_layout_changed=$false;MOK_enrolled=$false;physical_ss1_executed=$false;reboot_performed=$false;candidate_sha256=$ready.file_sha256;candidate_MOK_hash=$ready.pe_authenticode_sha256;stage=$stage;utc=(Get-Date).ToUniversalTime().ToString('o')}) (Join-Path $out 'result.json')
} catch {
    $reason=$_.Exception.Message; $rollbackError=$null
    if ($nvram -and $created) {
        try {
            if ($activated) { $nvram.ReplaceOrder($newOrder,$oldOrder); $activated=$false }
            if ([Convert]::ToBase64String($nvram.Read('BootOrder')) -ceq [Convert]::ToBase64String($oldOrder)) {
                $nvram.DeleteExact($newName,$payload); $created=$false
            }
        } catch { $rollbackError=$_.Exception.Message }
    }
    Save-Json ([ordered]@{installed=$false;stage=$stage;error=$reason;rollback_error=$rollbackError;new_entry_retained=$created;new_default_retained=$activated;reboot_performed=$false;automatic_retry=$false}) (Join-Path $out 'failure.json')
    throw
} finally {
    if ($nvram) { $nvram.Dispose() }
    if ($mounted) {
        & mountvol.exe G: /D
        Save-Json ([ordered]@{temporary_mount_removed=($LASTEXITCODE -eq 0);utc=(Get-Date).ToUniversalTime().ToString('o')}) (Join-Path $out 'mount-cleanup.json')
    }
}
Write-Output ('Automatic TF32 installed; exact MOK enrollment pending. No restart: '+$out)
