"""Read Windows-exposed ACPI/SMBIOS tables; never executes AML or accesses PCI."""
import argparse
import collections
import ctypes as ct
import hashlib
import json
from pathlib import Path
import struct
import sys


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    if sys.platform!="win32": p.error("Windows only")
    if a.output.exists(): p.error("Choose a new output directory")
    a.output.mkdir(parents=True)
    k=ct.WinDLL("kernel32",use_last_error=True)
    enum=k.EnumSystemFirmwareTables
    enum.argtypes=[ct.c_uint32,ct.c_void_p,ct.c_uint32];enum.restype=ct.c_uint32
    get=k.GetSystemFirmwareTable
    get.argtypes=[ct.c_uint32,ct.c_uint32,ct.c_void_p,ct.c_uint32];get.restype=ct.c_uint32
    def table(provider,identifier):
        size=get(provider,identifier,None,0)
        if not 0<size<=16*1024*1024: raise OSError(ct.get_last_error(),"Firmware table read size")
        buf=ct.create_string_buffer(size)
        if get(provider,identifier,buf,size)!=size: raise OSError(ct.get_last_error(),"Firmware table changed")
        return buf.raw
    provider=int.from_bytes(b"ACPI","big")
    size=enum(provider,None,0)
    if not size or size%4 or size>65536: raise OSError(ct.get_last_error(),"ACPI enumeration")
    buf=ct.create_string_buffer(size)
    if enum(provider,buf,size)!=size: raise OSError("ACPI enumeration changed")
    identifiers=list(struct.unpack("<"+"I"*(size//4),buf.raw))
    # DSDT is not enumerated on some Windows firmware interfaces but is readable
    # directly. This uses the same read-only API, never an AML method call.
    dsdt=int.from_bytes(b"DSDT","little")
    dsdt_error=None
    if dsdt not in identifiers:
        try:
            table(provider,dsdt)
            identifiers.append(dsdt)
        except OSError as error:
            dsdt_error=str(error)
    records=[]
    for identifier,multiplicity in collections.Counter(identifiers).items():
        if identifier==int.from_bytes(b"MSDM","little"):
            records.append({"signature":"MSDM","skipped":"OEM licensing data is irrelevant to GPU verification"})
            continue
        data=table(provider,identifier)
        name=data[:4].decode("ascii",errors="replace")
        if not name.isalnum(): raise ValueError("Unexpected ACPI signature")
        (a.output/(name+".bin")).write_bytes(data)
        markers={x.decode():[i for i in range(len(data)) if data.startswith(x,i)] for x in (b"_ROM",b"VFCT",b"PCIR",b"BIT",b"NVDA")}
        records.append({"signature":name,"bytes":len(data),"enumerated_count":multiplicity,
                        "sha256":hashlib.sha256(data).hexdigest(),"checksum_valid":sum(data)%256==0,
                        "markers":markers})
        if name=="VFCT":
            records[-1]["pcir_identities"]=[
                {"offset":at,"vendor":f"{struct.unpack_from('<H',data,at+4)[0]:04x}",
                 "device":f"{struct.unpack_from('<H',data,at+6)[0]:04x}"}
                for at in markers["PCIR"] if at+8<=len(data)]
    smbios=table(int.from_bytes(b"RSMB","big"),0)
    (a.output/"RSMB.bin").write_bytes(smbios)
    length=struct.unpack_from("<I",smbios,4)[0]
    if length>len(smbios)-8: raise ValueError("SMBIOS length exceeds result")
    raw=smbios[8:8+length]; pos=0; found={}
    while pos+6<=len(raw):
        kind,size=raw[pos:pos+2]
        if size<4 or pos+size>len(raw): raise ValueError("SMBIOS record length")
        end=raw.find(b"\0\0",pos+size)
        if end<0: raise ValueError("Unterminated SMBIOS strings")
        strings=raw[pos+size:end].split(b"\0")
        if kind in (0,1) and size>=6:
            index=raw[pos+5]
            found["bios_version" if kind==0 else "product_name"]=(strings[index-1].decode(errors="replace") if 0<index<=len(strings) else "")
        if kind==127: break
        pos=end+2
    report={"read_only":True,"aml_executed":False,"pci_accessed":False,"smbios_version":list(smbios[1:3]),
            "smbios_identity":found,"acpi":records,"licensing_table_excluded":True,"dsdt_direct_read_error":dsdt_error,
            "limitation":"Windows returns only the first ACPI table of each repeated signature. No physical-memory mapping or AML method execution attempted."}
    (a.output/"report.json").write_text(json.dumps(report,indent=2))
    print(json.dumps({"smbios":found,"tables":[{"name":r["signature"],"bytes":r["bytes"],"copies":r["enumerated_count"],"rom_markers":r["markers"]["_ROM"],"pcir":r["markers"]["PCIR"]} for r in records if "bytes" in r]},indent=2))


if __name__=="__main__": main()
