param([string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path $projectRoot ('results\uefi-readonly-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
}
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script manually in an Administrator PowerShell. It reads firmware variables; it does not change them.'
}
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Choose a new output directory.' }
New-Item -ItemType Directory -Path $OutputDirectory | Out-Null
$report = [ordered]@{
    utc = (Get-Date).ToUniversalTime().ToString('o')
    operations = 'Read only; local output files. No firmware/keys/boot settings modified.'
}
$report.secure_boot = Confirm-SecureBootUEFI
$report.system = Get-CimInstance Win32_ComputerSystem | Select-Object Manufacturer,Model
$report.bios = Get-CimInstance Win32_BIOS | Select-Object SMBIOSBIOSVersion,ReleaseDate
$report.os = Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,BuildNumber
$report.tpm = Get-Tpm | Select-Object TpmPresent,TpmReady,TpmEnabled,TpmActivated
$report.bitlocker = @(Get-BitLockerVolume | Select-Object MountPoint,VolumeStatus,ProtectionStatus)
$report.system_partitions = @(Get-Partition | Where-Object IsSystem | Select-Object DiskNumber,PartitionNumber,Guid,GptType)
$variables = @()
foreach ($name in @('SecureBoot','SetupMode','PK','KEK','db','dbx')) {
    try {
        $v = Get-SecureBootUEFI -Name $name
        $destination = Join-Path $OutputDirectory ($name + '.bin')
        [IO.File]::WriteAllBytes($destination, $v.Bytes)
        $variables += [ordered]@{ name=$name; bytes=$v.Bytes.Length; attributes=[string]$v.Attributes; sha256=(Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash }
    } catch {
        $variables += [ordered]@{ name=$name; error=$_.Exception.Message }
    }
}
$report.variables = $variables
# Read shim variables using the correct namespace. There is no SetVariable API here.
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class M6501FirmwareReader {
    [StructLayout(LayoutKind.Sequential)] private struct Luid { public UInt32 Low; public Int32 High; }
    [StructLayout(LayoutKind.Sequential)] private struct TokenPrivileges { public UInt32 Count; public Luid Id; public UInt32 Attributes; }
    [DllImport("kernel32.dll")] private static extern IntPtr GetCurrentProcess();
    [DllImport("kernel32.dll")] private static extern bool CloseHandle(IntPtr handle);
    [DllImport("advapi32.dll", SetLastError=true)] private static extern bool OpenProcessToken(IntPtr process, UInt32 access, out IntPtr token);
    [DllImport("advapi32.dll", CharSet=CharSet.Unicode, SetLastError=true)] private static extern bool LookupPrivilegeValue(string system, string name, out Luid id);
    [DllImport("advapi32.dll", SetLastError=true)] private static extern bool AdjustTokenPrivileges(IntPtr token, bool disable, ref TokenPrivileges state, UInt32 size, out TokenPrivileges previous, out UInt32 needed);
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    private static extern UInt32 GetFirmwareEnvironmentVariableExW(string name, string guid, byte[] data, UInt32 size, out UInt32 attributes);
    public static UInt32 Read(string name, string guid, byte[] data, out UInt32 attributes, out Int32 error) {
        attributes=0; error=0;
        IntPtr token;
        if (!OpenProcessToken(GetCurrentProcess(),0x28,out token)) { error=Marshal.GetLastWin32Error(); return 0; }
        TokenPrivileges oldState=new TokenPrivileges();
        bool adjusted=false;
        try {
            Luid id;
            if (!LookupPrivilegeValue(null,"SeSystemEnvironmentPrivilege",out id)) { error=Marshal.GetLastWin32Error(); return 0; }
            TokenPrivileges requested=new TokenPrivileges { Count=1, Id=id, Attributes=2 };
            UInt32 needed;
            if (!AdjustTokenPrivileges(token,false,ref requested,(UInt32)Marshal.SizeOf(typeof(TokenPrivileges)),out oldState,out needed)) {
                error=Marshal.GetLastWin32Error(); return 0;
            }
            adjusted=true;
            Int32 privilegeError=Marshal.GetLastWin32Error();
            if (privilegeError!=0) { error=privilegeError; return 0; }
            UInt32 length=GetFirmwareEnvironmentVariableExW(name,guid,data,(UInt32)data.Length,out attributes);
            if (length==0) error=Marshal.GetLastWin32Error();
            return length;
        } finally {
            if (adjusted) {
                TokenPrivileges ignored; UInt32 needed;
                AdjustTokenPrivileges(token,false,ref oldState,(UInt32)Marshal.SizeOf(typeof(TokenPrivileges)),out ignored,out needed);
            }
            CloseHandle(token);
        }
    }
}
'@
$mok = @()
foreach ($name in @('MokSBStateRT','MokListRT','MokListXRT','SbatLevelRT','MokIgnoreDB','MokPolicyRT')) {
    $data = New-Object byte[] (1024 * 1024)
    [uint32]$attributes = 0
    [int]$readError = 0
    $length = [M6501FirmwareReader]::Read($name,'{605dab50-e046-4300-abb6-3dd810dd8b23}',$data,[ref]$attributes,[ref]$readError)
    if ($length) {
        $destination = Join-Path $OutputDirectory ($name + '.bin')
        $actual = New-Object byte[] $length
        [Array]::Copy($data,$actual,$length)
        [IO.File]::WriteAllBytes($destination,$actual)
        $mok += [ordered]@{name=$name; bytes=$length; attributes=$attributes}
    } else {
        $mok += [ordered]@{name=$name; win32_error=$readError}
    }
}
$report.shim_variables = $mok
$report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $OutputDirectory 'report.json') -Encoding UTF8
& bcdedit.exe /enum firmware | Out-File -LiteralPath (Join-Path $OutputDirectory 'boot-entries.txt') -Encoding UTF8
& nvidia-smi.exe -q | Out-File -LiteralPath (Join-Path $OutputDirectory 'nvidia-smi.txt') -Encoding UTF8
Write-Output ('Read-only collection saved to: ' + $OutputDirectory)
