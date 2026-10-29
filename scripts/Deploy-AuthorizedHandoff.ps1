# Applies the explicitly approved HANDOFF stage to the identified USB only.
# No format, firmware, MOK, BCD or Windows ESP write is performed here.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$source = Join-Path $projectRoot 'build\release-20261025-v2\USB-HANDOFF'
$usbRoot = 'F:\'
$expectedProbe = '8f099671f487eca54c7584d913ba29b133f40cc6d86cb1c7e325344d2f509070'
$expectedHandoff = 'c646f027c42795505b6f3b618e3f5586920054fe2c94b57ac288f1aab238c83b'
$expectedShim = 'e103c5d02657879f141b086ed703584d28bb9e2721b423333be085ee1b4d397b'
$expectedManager = '30ea13138310f0819c1d875fcf3a6cdce8a1607cfd7578053a2df894a41630ae'

function Assert-Usb {
    $part = Get-Partition -DriveLetter F
    $disk = $part | Get-Disk
    $volume = $part | Get-Volume
    if ($disk.Number -ne 2 -or [string]$disk.BusType -ne 'USB' -or $disk.IsBoot -or $disk.IsSystem -or
        [uint64]$disk.Size -ne 15376000000 -or ([string]$disk.SerialNumber).Trim() -cne 'USB_SERIAL_REQUIRES_LOCAL_REVIEW' -or
        [string]$part.Guid -ine '{22222222-2222-4222-8222-222222222222}' -or $part.IsBoot -or $part.IsSystem -or
        [string]$volume.FileSystem -ine 'FAT32' -or [string]$volume.FileSystemLabel -cne 'M6501PROBE') {
        throw 'USB identity or partition state changed.'
    }
}

function Get-Sha([string]$Path) { return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }

function Usb-Path([string]$Relative) {
    $resolved = [IO.Path]::GetFullPath((Join-Path $usbRoot $Relative))
    if (-not $resolved.StartsWith($usbRoot,[StringComparison]::OrdinalIgnoreCase)) { throw 'Destination escapes authorized USB.' }
    return $resolved
}

Assert-Usb
$statusPath = Join-Path $projectRoot 'results\STATUS.json'
$status = Get-Content -LiteralPath $statusPath -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $status.physical_handoff_authorized) { throw 'HANDOFF approval has not been recorded.' }
$manifest = Get-Content -LiteralPath (Join-Path $source 'STAGING-MANIFEST.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if ($manifest.mode -ne 'handoff') { throw 'Wrong source mode.' }
if ((Get-Sha (Join-Path $source 'EFI\BOOT\grubx64.efi')) -cne $expectedHandoff -or
    (Get-Sha (Join-Path $source 'EFI\BOOT\BOOTX64.EFI')) -cne $expectedShim -or
    (Get-Sha (Join-Path $source 'EFI\BOOT\mmx64.efi')) -cne $expectedManager) { throw 'Source images differ from tested HANDOFF package.' }
if ((Get-Sha (Usb-Path 'EFI\BOOT\grubx64.efi')) -cne $expectedProbe -or
    (Get-Sha (Usb-Path 'EFI\BOOT\BOOTX64.EFI')) -cne $expectedShim -or
    (Get-Sha (Usb-Path 'EFI\BOOT\mmx64.efi')) -cne $expectedManager) { throw 'USB no longer contains the expected PROBE stage.' }
$systemParts = @(Get-Partition | Where-Object IsSystem)
if ($systemParts.Count -ne 1 -or [string]$systemParts[0].Guid -ine '{11111111-1111-4111-8111-111111111111}') { throw 'Windows ESP GUID differs from tested HANDOFF profile.' }
$sourceFiles = @(Get-ChildItem -LiteralPath $source -Recurse -File)
foreach ($file in $sourceFiles) {
    if ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Source reparse point refused.' }
}
foreach ($entry in $manifest.files_sha256.PSObject.Properties) {
    $path = [IO.Path]::GetFullPath((Join-Path $source $entry.Name))
    if (-not $path.StartsWith($source + '\',[StringComparison]::OrdinalIgnoreCase) -or (Get-Sha $path) -cne $entry.Value) { throw 'Staging hash/path mismatch.' }
}
$folder = Join-Path $projectRoot ('results\handoff-deployment-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
if (Test-Path -LiteralPath $folder) { throw 'Deployment report directory exists.' }
New-Item -ItemType Directory -Path $folder | Out-Null
$backup = Join-Path $folder 'USB-PROBE-BACKUP'
New-Item -ItemType Directory -Path $backup | Out-Null
foreach ($name in @('EFI','RTX-UNLOCK','STAGING-MANIFEST.json','READ-FIRST.txt')) {
    Copy-Item -LiteralPath (Usb-Path $name) -Destination $backup -Recurse
}
# Verify every existing PROBE log is in the backup before replacing anything.
$logs = @(Get-ChildItem -LiteralPath (Usb-Path 'RTX-UNLOCK') -Recurse -File)
foreach ($log in $logs) {
    $relative = $log.FullName.Substring($usbRoot.Length)
    if ((Get-Sha $log.FullName) -cne (Get-Sha (Join-Path $backup $relative))) { throw 'PROBE evidence backup mismatch.' }
}
Assert-Usb
$copied = @()
foreach ($file in $sourceFiles) {
    $relative = $file.FullName.Substring($source.Length + 1)
    if ($relative -ieq 'EFI\BOOT\BOOTX64.EFI' -or $relative -ieq 'EFI\BOOT\mmx64.efi') {
        # Signed chain files already match. Keep their bytes and names unchanged.
        continue
    }
    $target = Usb-Path $relative
    $parent = Split-Path -Parent $target
    if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent | Out-Null }
    Copy-Item -LiteralPath $file.FullName -Destination $target -Force
    if ((Get-Sha $target) -cne (Get-Sha $file.FullName)) { throw 'HANDOFF copy readback mismatch.' }
    $copied += [ordered]@{file=$relative; sha256=(Get-Sha $target)}
}
Assert-Usb
if ((Get-Sha (Usb-Path 'EFI\BOOT\grubx64.efi')) -cne $expectedHandoff) { throw 'Final HANDOFF image differs.' }
foreach ($log in $logs) {
    if ((Get-Sha $log.FullName) -cne (Get-Sha (Join-Path $backup $log.FullName.Substring($usbRoot.Length)))) { throw 'A PROBE log changed during deployment.' }
}
$report = [ordered]@{
    utc=(Get-Date).ToUniversalTime().ToString('o'); deployed=$true; mode='handoff'; formatted=$false
    usb_root=$usbRoot; usb_label='M6501PROBE'; usb_serial='USB_SERIAL_REQUIRES_LOCAL_REVIEW'
    handoff_file_sha256=$expectedHandoff
    handoff_pe_authenticode_sha256='578950703436fdda4130666bf45f168e419d5d9932babdc81ac67281bbe24c5f'
    windows_esp_guid='11111111-1111-4111-8111-111111111111'
    probe_logs_preserved=$logs.Count; backup=$backup; verified_copied_files=$copied
    boot_performed=$false; handoff_mok_enrolled=$false; gpu_unlock_applied=$false
    windows_esp_written=$false; boot_configuration_written=$false; firmware_written=$false
}
$report | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath (Join-Path $folder 'deployment.json') -Encoding UTF8
Set-Content -LiteralPath (Join-Path $projectRoot 'results\latest-handoff-deployment.txt') -Value $folder -Encoding UTF8
Write-Output ('HANDOFF deployed without format; PROBE logs preserved. Report: ' + $folder)
