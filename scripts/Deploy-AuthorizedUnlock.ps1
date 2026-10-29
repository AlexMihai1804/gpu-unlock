# Candidate v3 deployment ONLY after separate explicit approval is recorded.
# Copies files to the identified USB. Never boots, enrolls MOK, accesses GPU,
# changes BCD/Windows ESP, formats a drive or writes firmware.
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$source=Join-Path $projectRoot 'build\release-20261025-v3\USB-CANDIDATE'
$usbRoot='F:\'
$expectedCandidate='f716f8827c38a63b353fd28ad505bb2e7713991fb152df6b34a250c89bd08336'
$expectedCapture='2fc636dbc15b351a9e3139e4811a01e953b0d8bf99176e606774bdc248486022'
$expectedShim='e103c5d02657879f141b086ed703584d28bb9e2721b423333be085ee1b4d397b'
$expectedManager='30ea13138310f0819c1d875fcf3a6cdce8a1607cfd7578053a2df894a41630ae'
$candidateMok='5dca60a7602255a01ff4f7771aacac62100afda4138f9235d0476f9b48f68642'
$expectedManifest='348e4deedfceea89e176c6dc1abe1f71b72978271e9c75fc0f3c8341e13fa31f'
function Get-Sha([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
function Usb-Path([string]$Relative) {
    $path=[IO.Path]::GetFullPath((Join-Path $usbRoot $Relative))
    if (-not $path.StartsWith($usbRoot,[StringComparison]::OrdinalIgnoreCase)) { throw 'Target escapes authorized USB.' }
    return $path
}
function Assert-Usb {
    $part=Get-Partition -DriveLetter F
    $disk=$part | Get-Disk
    $volume=$part | Get-Volume
    if ($disk.Number -ne 2 -or [string]$disk.BusType -ne 'USB' -or $disk.IsBoot -or $disk.IsSystem -or
        [uint64]$disk.Size -ne 15376000000 -or ([string]$disk.SerialNumber).Trim() -cne 'USB_SERIAL_REQUIRES_LOCAL_REVIEW' -or
        $part.IsBoot -or $part.IsSystem -or [string]$part.Guid -ine '{22222222-2222-4222-8222-222222222222}' -or
        [string]$volume.FileSystem -ine 'FAT32' -or [string]$volume.FileSystemLabel -cne 'M6501PROBE') {
        throw 'USB identity/partition changed.'
    }
}
$status=Get-Content -LiteralPath (Join-Path $projectRoot 'results\STATUS.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $status.physical_unlock_authorized -or -not $status.unlock_usb_deployment_authorized -or
    -not $status.unlock_mok_enrollment_authorized -or -not $status.unlock_hardware_attempt_authorized -or
    $status.authorized_unlock_pe_authenticode_sha256 -cne $candidateMok) {
    throw 'BLOCKED: separate explicit candidate v3 deployment/MOK/hardware approval has not been recorded.'
}
if (-not $status.post_capture_administrative_collection_completed -or -not $status.physical_capture_passed -or
    -not $status.candidate_local_validation_passed -or -not $status.physical_handoff_functional_passed) {
    throw 'Candidate prerequisite review missing.'
}
$ready=Get-Content -LiteralPath (Join-Path $projectRoot 'results\unlock-candidate-v3-ready.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $ready.local_validation_passed -or $ready.file_sha256 -cne $expectedCandidate -or
    $ready.pe_authenticode_sha256 -cne $candidateMok) { throw 'Candidate readiness report differs.' }
Assert-Usb
$manifestPath=Join-Path $source 'STAGING-MANIFEST.json'
if ((Get-Sha $manifestPath) -cne $expectedManifest) { throw 'Source package manifest changed.' }
$manifest=Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($manifest.mode -ne 'candidate') { throw 'Wrong source mode.' }
$entries=@(Get-ChildItem -LiteralPath $source -Recurse -Force)
if ((Get-Item -LiteralPath $source).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Source root reparse point refused.' }
foreach ($entry in $entries) {
    if ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Source reparse point refused.' }
}
$files=@($entries | Where-Object { -not $_.PSIsContainer })
foreach ($entry in $manifest.files_sha256.PSObject.Properties) {
    $path=[IO.Path]::GetFullPath((Join-Path $source $entry.Name))
    if (-not $path.StartsWith($source+'\',[StringComparison]::OrdinalIgnoreCase) -or (Get-Sha $path) -cne $entry.Value) {
        throw 'Source manifest hash/path mismatch.'
    }
}
if (@($files | Where-Object { $_.Extension -ieq '.ROM' }).Count) { throw 'Original ROM must not be deployed as a firmware asset.' }
$images=@{'grubx64.efi'=$expectedCandidate;'BOOTX64.EFI'=$expectedShim;'mmx64.efi'=$expectedManager}
foreach ($name in $images.Keys) {
    if ((Get-Sha (Join-Path $source ('EFI\BOOT\'+$name))) -cne $images[$name]) { throw 'Source executable changed.' }
    $existing=if ($name -eq 'grubx64.efi') { $expectedCapture } else { $images[$name] }
    if ((Get-Sha (Usb-Path ('EFI\BOOT\'+$name))) -cne $existing) { throw 'USB no longer contains expected CAPTURE stage.' }
}
$bootNames=@(Get-ChildItem -LiteralPath (Join-Path $source 'EFI\BOOT') -File | Select-Object -ExpandProperty Name | Sort-Object)
if (($bootNames -join ',') -ine 'BOOTX64.EFI,grubx64.efi,mmx64.efi') { throw 'Unexpected boot images.' }
$folder=Join-Path $projectRoot ('results\unlock-deployment-'+(Get-Date -Format 'yyyyMMdd-HHmmss'))
if (Test-Path -LiteralPath $folder) { throw 'Report directory exists.' }
New-Item -ItemType Directory -Path $folder | Out-Null
$backup=Join-Path $folder 'USB-CAPTURE-BACKUP'
New-Item -ItemType Directory -Path $backup | Out-Null
foreach ($name in @('EFI','RTX-UNLOCK','STAGING-MANIFEST.json','READ-FIRST.txt')) {
    Copy-Item -LiteralPath (Usb-Path $name) -Destination $backup -Recurse
}
if ((Get-Sha (Join-Path $backup 'EFI\BOOT\grubx64.efi')) -cne $expectedCapture) { throw 'CAPTURE backup mismatch.' }
$evidence=@(Get-ChildItem -LiteralPath (Usb-Path 'RTX-UNLOCK') -Recurse -File)
foreach ($item in $evidence) {
    if ((Get-Sha $item.FullName) -cne (Get-Sha (Join-Path $backup $item.FullName.Substring($usbRoot.Length)))) { throw 'Evidence backup mismatch.' }
}
Assert-Usb
# Copy verified assets first. Replace the executable last, so an incomplete
# asset copy leaves the old CAPTURE application in place.
$orderedFiles=@($files | Where-Object { $_.Name -ine 'grubx64.efi' })+@($files | Where-Object { $_.Name -ieq 'grubx64.efi' })
foreach ($file in $orderedFiles) {
    $relative=$file.FullName.Substring($source.Length+1)
    if ($relative -ieq 'EFI\BOOT\BOOTX64.EFI' -or $relative -ieq 'EFI\BOOT\mmx64.efi') { continue }
    $destination=Usb-Path $relative
    $parent=Split-Path -Parent $destination
    if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent | Out-Null }
    Copy-Item -LiteralPath $file.FullName -Destination $destination -Force
    if ((Get-Sha $destination) -cne (Get-Sha $file.FullName)) { throw 'Immediate USB readback mismatch.' }
}
Assert-Usb
$verified=@()
foreach ($file in $files) {
    $relative=$file.FullName.Substring($source.Length+1)
    $actual=Get-Sha (Usb-Path $relative)
    if ($actual -cne (Get-Sha $file.FullName)) { throw 'Final USB readback mismatch.' }
    $verified+=[ordered]@{file=$relative;sha256=$actual;bytes=$file.Length}
}
foreach ($item in $evidence) {
    if ((Get-Sha $item.FullName) -cne (Get-Sha (Join-Path $backup $item.FullName.Substring($usbRoot.Length)))) { throw 'Existing evidence changed.' }
}
$report=[ordered]@{
    utc=(Get-Date).ToUniversalTime().ToString('o');mode='candidate-v3';deployed=$true;formatted=$false
    candidate_file_sha256=$expectedCandidate;candidate_pe_authenticode_sha256=$candidateMok
    backup=$backup;existing_evidence_files_preserved=$evidence.Count;verified_files=$verified
    boot_performed=$false;mok_enrolled=$false;gpu_unlock_applied=$false
    windows_esp_written=$false;boot_configuration_written=$false;firmware_written=$false;pci_or_mmio_hardware_accessed=$false
}
$report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $folder 'deployment.json') -Encoding UTF8
$folder | Set-Content -LiteralPath (Join-Path $projectRoot 'results\latest-unlock-deployment.txt') -Encoding UTF8
Write-Output ('Approved candidate files copied and verified. No boot or GPU action. Report: '+$folder)
