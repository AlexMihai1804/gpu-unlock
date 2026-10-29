// Restricted UEFI boot-variable access. Does not expose platform keys or flash.
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text.RegularExpressions;
public sealed class M6501BootVariables : IDisposable {
    const string GuidName="{8be4df61-93ca-11d2-aa0d-00e098032b8c}";
    [StructLayout(LayoutKind.Sequential)] struct Luid { public UInt32 Low; public Int32 High; }
    [StructLayout(LayoutKind.Sequential)] struct Privilege { public UInt32 Count; public Luid Id; public UInt32 Attributes; }
    [DllImport("kernel32.dll")] static extern IntPtr GetCurrentProcess();
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr handle);
    [DllImport("advapi32.dll",SetLastError=true)] static extern bool OpenProcessToken(IntPtr process,UInt32 access,out IntPtr token);
    [DllImport("advapi32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool LookupPrivilegeValue(string system,string name,out Luid id);
    [DllImport("advapi32.dll",SetLastError=true)] static extern bool AdjustTokenPrivileges(IntPtr token,bool disable,ref Privilege state,UInt32 size,out Privilege previous,out UInt32 needed);
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern UInt32 GetFirmwareEnvironmentVariableExW(string name,string guid,byte[] data,UInt32 size,out UInt32 attributes);
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool SetFirmwareEnvironmentVariableExW(string name,string guid,byte[] data,UInt32 size,UInt32 attributes);
    IntPtr token;
    Privilege oldState;
    bool adjusted;
    public M6501BootVariables() {
        try {
            if (!OpenProcessToken(GetCurrentProcess(),0x28,out token)) throw new Win32Exception();
            Luid id;
            if (!LookupPrivilegeValue(null,"SeSystemEnvironmentPrivilege",out id)) throw new Win32Exception();
            Privilege requested=new Privilege {Count=1,Id=id,Attributes=2}; UInt32 needed;
            if (!AdjustTokenPrivileges(token,false,ref requested,(UInt32)Marshal.SizeOf(typeof(Privilege)),out oldState,out needed)) throw new Win32Exception();
            adjusted=true;
            int error=Marshal.GetLastWin32Error();
            if (error!=0) throw new Win32Exception(error);
        } catch { Dispose(); throw; }
    }
    static void Allowed(string name) {
        if (name!="BootOrder" && !Regex.IsMatch(name,"\\ABoot[0-9A-F]{4}\\z")) throw new ArgumentException("Only BootOrder/Boot#### allowed");
    }
    public byte[] Read(string name) {
        Allowed(name); byte[] buffer=new byte[65536]; UInt32 attributes;
        UInt32 size=GetFirmwareEnvironmentVariableExW(name,GuidName,buffer,(UInt32)buffer.Length,out attributes);
        if (size==0) {
            int error=Marshal.GetLastWin32Error();
            if (error==203) return null;
            throw new Win32Exception(error);
        }
        if (attributes!=7) throw new InvalidOperationException("Unexpected boot-variable attributes");
        Array.Resize(ref buffer,(int)size); return buffer;
    }
    static bool Same(byte[] a,byte[] b) {
        if (a==null || b==null) return a==b;
        if (a.Length!=b.Length) return false;
        for (int i=0;i<a.Length;i++) if (a[i]!=b[i]) return false;
        return true;
    }
    void Write(string name,byte[] data) {
        Allowed(name);
        if (data==null || data.Length>65536) throw new ArgumentException("Invalid boot variable bytes");
        if (!SetFirmwareEnvironmentVariableExW(name,GuidName,data,(UInt32)data.Length,7)) throw new Win32Exception();
    }
    public void Create(string name,byte[] data) {
        if (name=="BootOrder" || Read(name)!=null) throw new InvalidOperationException("Will not replace an existing entry");
        Write(name,data);
        if (!Same(Read(name),data)) throw new InvalidOperationException("Boot entry readback differs");
    }
    public void ReplaceOrder(byte[] expected,byte[] replacement) {
        if (replacement==null || replacement.Length==0 || replacement.Length%2!=0 || replacement.Length>4096 || !Same(Read("BootOrder"),expected))
            throw new InvalidOperationException("BootOrder changed or replacement invalid");
        Write("BootOrder",replacement);
        if (!Same(Read("BootOrder"),replacement)) throw new InvalidOperationException("BootOrder readback differs");
    }
    public void DeleteExact(string name,byte[] expected) {
        if (name=="BootOrder" || !Same(Read(name),expected)) throw new InvalidOperationException("Refuse deletion of changed boot entry");
        Write(name,new byte[0]);
        if (Read(name)!=null) throw new InvalidOperationException("Boot entry was not removed");
    }
    public void Dispose() {
        if (token!=IntPtr.Zero) {
            if (adjusted) { Privilege ignored; UInt32 needed; AdjustTokenPrivileges(token,false,ref oldState,(UInt32)Marshal.SizeOf(typeof(Privilege)),out ignored,out needed); }
            CloseHandle(token); token=IntPtr.Zero;
        }
    }
}
