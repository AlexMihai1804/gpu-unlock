# Read-only preflight for the authorized TF32 automatic update.
param([Parameter(Mandatory=$true)][string]$OutputDirectory)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$out=[IO.Path]::GetFullPath($OutputDirectory)
if (-not $out.StartsWith((Join-Path $root 'results')+'\',[StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $out)) { throw 'Use a new directory under results.' }
try {
    & (Join-Path $PSScriptRoot 'Collect-InternalAutomatic.ps1') -OutputDirectory $out
    $partition=Get-Partition -DiskNumber 1 -PartitionNumber 4
    $volume=$partition | Get-Volume
    $disk=Get-Disk -Number 1
    [ordered]@{
        completed=$true;utc=(Get-Date).ToUniversalTime().ToString('o')
        disk_serial=$disk.SerialNumber.Trim();disk_size=[uint64]$disk.Size
        partition_guid=$partition.Guid;partition_size=[uint64]$partition.Size
        partition_offset=[uint64]$partition.Offset
        free_bytes=[uint64]$volume.SizeRemaining;filesystem=$volume.FileSystem
        volume_label=$volume.FileSystemLabel
        windows_boot_utc=(Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToUniversalTime().ToString('o')
        source_files_written=$false;boot_variables_written=$false
    } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $out 'tf32-preflight.json') -Encoding UTF8
} catch {
    if (Test-Path -LiteralPath $out) {
        [ordered]@{completed=$false;error=$_.Exception.Message;utc=(Get-Date).ToUniversalTime().ToString('o')} |
            ConvertTo-Json | Set-Content -LiteralPath (Join-Path $out 'tf32-preflight-failure.json') -Encoding UTF8
    }
    throw
}
