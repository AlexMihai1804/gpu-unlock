# Restore only the saved UEFI boot order and remove our exact new boot entry.
# Does not delete partitions/files, expand E, or remove MOK/platform keys.
param([Parameter(Mandatory=$true)][string]$InstallDirectory)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$directory=[IO.Path]::GetFullPath($InstallDirectory)
if (-not $directory.StartsWith((Join-Path $root 'results')+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Use saved installation evidence under results.' }
$state=Get-Content -LiteralPath (Join-Path $directory 'activation-state.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if ($state.boot_name -notmatch '^Boot[0-9A-F]{4}$') { throw 'Unexpected boot-entry name.' }
Add-Type -Path (Join-Path $root 'scripts\BootVariables.cs')
$nvram=New-Object M6501BootVariables
try {
    [byte[]]$current=$nvram.Read('BootOrder')
    [byte[]]$original=[Convert]::FromBase64String($state.old_order_base64)
    [byte[]]$installed=[Convert]::FromBase64String($state.new_order_base64)
    if ([Convert]::ToBase64String($current) -ceq $state.new_order_base64) { $nvram.ReplaceOrder($installed,$original) }
    elseif ([Convert]::ToBase64String($current) -cne $state.old_order_base64) { throw 'Boot order changed since install; refusing to overwrite it.' }
    if ($null -ne $nvram.Read($state.boot_name)) { $nvram.DeleteExact($state.boot_name,[Convert]::FromBase64String($state.payload_base64)) }
} finally { $nvram.Dispose() }
Write-Output 'Original UEFI boot order restored; our entry removed. Partitions, MOK and Windows loader retained.'
