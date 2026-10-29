# Explicitly approved CAPTURE deployment. USB files only; no format, boot,
# enrollment, firmware, Windows ESP, PCI or MMIO writes from this script.
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$source=Join-Path $projectRoot 'build\release-20261025-v2\USB-CAPTURE'
$usbRoot='F:\'
$expectedCapture='2fc636dbc15b351a9e3139e4811a01e953b0d8bf99176e606774bdc248486022'
$expectedHandoff='c646f027c42795505b6f3b618e3f5586920054fe2c94b57ac288f1aab238c83b'
$expectedShim='e103c5d02657879f141b086ed703584d28bb9e2721b423333be085ee1b4d397b'
$expectedManager='30ea13138310f0819c1d875fcf3a6cdce8a1607cfd7578053a2df894a41630ae'
$captureMok='7d073c9d54198ff2c18e9d27ad5531ce91bd0232a4c720f08351959356753f4a'

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
if (-not $status.physical_capture_authorized -or -not $status.capture_temporary_pci_memory_authorized -or
    -not $status.physical_handoff_functional_passed -or -not $status.normal_boot_control_completed -or
    $status.authorized_capture_pe_authenticode_sha256 -cne $captureMok) { throw 'Exact CAPTURE approval or prerequisite review missing.' }
Assert-Usb
$manifest=Get-Content -LiteralPath (Join-Path $source 'STAGING-MANIFEST.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if ($manifest.mode -ne 'capture') { throw 'Wrong source mode.' }
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
$images=@{ 'grubx64.efi'=$expectedCapture; 'BOOTX64.EFI'=$expectedShim; 'mmx64.efi'=$expectedManager }
foreach ($name in $images.Keys) {
    if ((Get-Sha (Join-Path $source ('EFI\BOOT\'+$name))) -cne $images[$name]) { throw 'Source image differs from approved build.' }
    $existing=if ($name -eq 'grubx64.efi') { $expectedHandoff } else { $images[$name] }
    if ((Get-Sha (Usb-Path ('EFI\BOOT\'+$name))) -cne $existing) { throw 'USB no longer contains the expected HANDOFF stage.' }
}
$bootNames=@(Get-ChildItem -LiteralPath (Join-Path $source 'EFI\BOOT') -File | Select-Object -ExpandProperty Name | Sort-Object)
if (($bootNames -join ',') -ine 'BOOTX64.EFI,grubx64.efi,mmx64.efi') { throw 'Unexpected boot image set.' }
$folder=Join-Path $projectRoot ('results\capture-deployment-'+(Get-Date -Format 'yyyyMMdd-HHmmss'))
if (Test-Path -LiteralPath $folder) { throw 'Report directory exists.' }
New-Item -ItemType Directory -Path $folder | Out-Null
$backup=Join-Path $folder 'USB-HANDOFF-BACKUP'
New-Item -ItemType Directory -Path $backup | Out-Null
foreach ($name in @('EFI','RTX-UNLOCK','STAGING-MANIFEST.json','READ-FIRST.txt')) {
    Copy-Item -LiteralPath (Usb-Path $name) -Destination $backup -Recurse
}
if ((Get-Sha (Join-Path $backup 'EFI\BOOT\grubx64.efi')) -cne $expectedHandoff) { throw 'HANDOFF backup mismatch.' }
$logs=@(Get-ChildItem -LiteralPath (Usb-Path 'RTX-UNLOCK') -Recurse -File)
foreach ($log in $logs) {
    if ((Get-Sha $log.FullName) -cne (Get-Sha (Join-Path $backup $log.FullName.Substring($usbRoot.Length)))) { throw 'Evidence backup mismatch.' }
}
Assert-Usb
foreach ($file in $files) {
    $relative=$file.FullName.Substring($source.Length+1)
    if ($relative -ieq 'EFI\BOOT\BOOTX64.EFI' -or $relative -ieq 'EFI\BOOT\mmx64.efi') { continue }
    $destination=Usb-Path $relative
    $parent=Split-Path -Parent $destination
    if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent | Out-Null }
    Copy-Item -LiteralPath $file.FullName -Destination $destination -Force
}
Assert-Usb
$verified=@()
foreach ($file in $files) {
    $relative=$file.FullName.Substring($source.Length+1)
    $actual=Get-Sha (Usb-Path $relative)
    if ($actual -cne (Get-Sha $file.FullName)) { throw 'USB readback mismatch.' }
    $verified += [ordered]@{file=$relative;sha256=$actual;bytes=$file.Length}
}
foreach ($log in $logs) {
    if ((Get-Sha $log.FullName) -cne (Get-Sha (Join-Path $backup $log.FullName.Substring($usbRoot.Length)))) { throw 'Existing evidence changed.' }
}
$report=[ordered]@{
    utc=(Get-Date).ToUniversalTime().ToString('o');mode='capture';deployed=$true;formatted=$false
    usb_root=$usbRoot;usb_label='M6501PROBE';usb_serial='USB_SERIAL_REQUIRES_LOCAL_REVIEW'
    capture_file_sha256=$expectedCapture;capture_pe_authenticode_sha256=$captureMok
    backup=$backup;existing_evidence_files_preserved=$logs.Count;verified_files=$verified
    boot_performed=$false;capture_mok_enrolled=$false;capture_performed=$false;gpu_unlock_applied=$false
    windows_esp_written=$false;boot_configuration_written=$false;firmware_written=$false;pci_or_mmio_hardware_accessed=$false
}
$report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $folder 'deployment.json') -Encoding UTF8
Set-Content -LiteralPath (Join-Path $projectRoot 'results\latest-capture-deployment.txt') -Value $folder -Encoding UTF8
Write-Output ('CAPTURE deployed and every file read back; no format or hardware action. Report: '+$folder)
