"""Isolated TCG/OVMF tests: workspace-only files; no host disks, network or passthrough."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import queue
import shutil
import struct
import subprocess
import sys
import threading
import time
import uuid
import zlib

ROOT=Path(__file__).resolve().parents[1]
VM=ROOT/"build/vm-lab"
QEMU=ROOT/"tools/downloads/qemu-portable"
COLLECTION=ROOT/"results/uefi-readonly-20261025-161851"
OWNER="77fa9abd-0359-4d32-bd60-28f4e78f784b"
OFFSET=1024*1024


def within(path):
    path=Path(path).resolve()
    if not path.is_relative_to(VM.resolve()):
        raise ValueError("VM state may only be written under build/vm-lab")
    return path


def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def compile_harness():
    build=module("m6501_build",ROOT/"tools/build.py")
    vendor=build.UPSTREAM
    llvm=ROOT/"tools/downloads/llvm-mingw-20261020-ucrt-x86_64/bin"
    include=vendor/"deps/edk2/MdePkg/Include"
    flags=["-target","x86_64-pc-windows-msvc","-std=c11","-ffreestanding","-fno-builtin","-fno-stack-protector",
           "-mno-red-zone","-fshort-wchar","-ffunction-sections","-fdata-sections","-Os","-Wall","-Wextra","-Werror",
           "-Wno-unused-function","-Wno-unused-parameter","-Wno-unused-variable","-D__KERNEL__","-DGU_UEFI_PORT","-DGU_RUNTIME_PROFILE_BUILD"]
    for path in (ROOT/"build/generated",ROOT/"uefi/include",vendor/"src/unlock",vendor/"src/unlock/vendor",vendor/"src/unlock/compat",include,include/"X64"):
        flags.extend(["-I",str(path)])
    obj=within(VM/"harness.obj")
    subprocess.run([str(llvm/"clang-23.exe"),*flags,"-c",str(ROOT/"tests/uefi_vm_harness.c"),"-o",str(obj)],check=True)
    names=["runtime","format","sha256","port","compat","runtime_profile","checks","ownership","app_io","vendor_vbios_610","vendor_gfw_eval","sbat"]
    objects=[str(ROOT/"build/generated"/(name+".obj")) for name in names]
    image=within(VM/"VM-HARNESS.EFI")
    subprocess.run([str(llvm/"ld.lld.exe"),"-flavor","link","/nologo","/nodefaultlib","/subsystem:efi_application",
                    "/entry:efi_main","/machine:x64","/base:0","/dynamicbase","/nxcompat","/timestamp:0","/opt:ref",
                    "/opt:icf","/include:m6501_sbat","/include:VmRelocAnchor","/out:"+str(image),str(obj),*objects],check=True)
    build.inspect_pe(image)
    return image


def gpt_image(path,files):
    from pyfatfs.PyFat import PyFat
    from pyfatfs.PyFatFS import PyFatFS
    path=within(path);total=128*1024*1024;last=total//512-1;part_last=last-33
    with path.open("wb") as f: f.truncate(total)
    fat=PyFat(offset=OFFSET)
    fat.mkfs(str(path),fat_type=PyFat.FAT_TYPE_FAT32,size=(part_last+1)*512-OFFSET,label="M6501VMLAB")
    fat.close()
    partition=bytearray(128*128)
    partition[:16]=uuid.UUID("c12a7328-f81f-11d2-ba4b-00a0c93ec93b").bytes_le
    partition[16:32]=uuid.UUID("11111111-1111-4111-8111-111111111111").bytes_le
    struct.pack_into("<QQQ",partition,32,2048,part_last,0)
    name="VM TEST ONLY".encode("utf-16le");partition[56:56+len(name)]=name
    disk_guid=uuid.UUID("23e70cdd-3060-4300-9000-000000000001").bytes_le
    def header(at,backup,entries):
        value=bytearray(512)
        struct.pack_into("<8sIIIIQQQQ16sQIII",value,0,b"EFI PART",0x10000,92,0,0,at,backup,34,last-33,disk_guid,entries,128,128,zlib.crc32(partition))
        struct.pack_into("<I",value,16,zlib.crc32(value[:92]))
        return value
    mbr=bytearray(512);mbr[446+4]=0xee;struct.pack_into("<II",mbr,446+8,1,min(last,0xffffffff));mbr[510:]=b"\x55\xaa"
    with path.open("r+b") as f:
        f.truncate(total);f.write(mbr);f.seek(512);f.write(header(1,last,2));f.write(partition)
        f.seek((last-32)*512);f.write(partition);f.write(header(last,1,last-32))
    with PyFatFS(str(path),offset=OFFSET) as fs:
        for name,data in files.items():
            parent=Path(name).parent.as_posix()
            if parent!=".": fs.makedirs(parent,recreate=True)
            fs.writebytes(name,bytes(data))
        fs.makedirs("RTX-UNLOCK",recreate=True)


def seed_vars(path,harness_hash,probe_hash,mode):
    from virt.firmware.varstore.edk2 import Edk2VarStore
    from virt.firmware.efi import efivar,ucs16
    base=Edk2VarStore(str(QEMU/"share/edk2-i386-vars.fd"));variables=base.get_varlist()
    for name in ("PK","KEK","db","dbx"):
        variables[name]=efivar.EfiVar(ucs16.from_string(name),data=(COLLECTION/(name+".bin")).read_bytes())
    variables.enable_secureboot()
    if mode=="s": variables.set_bool("SecureBootEnable",False)
    if mode!="n":
        variables.add_hash("MokList",OWNER,harness_hash)
        variables.add_hash("MokList",OWNER,probe_hash)
    if mode=="d": variables.add_hash("dbx",OWNER,probe_hash)
    base.write_varstore(str(within(path)),variables)


def run_vm(folder,timeout,internal=False):
    folder=within(folder)
    command=[str(QEMU/"qemu-system-x86_64.exe"),"-no-user-config","-nodefaults","-machine","q35,smm=on,smbios-entry-point-type=64",
             "-accel","tcg,thread=single","-cpu","max","-smp","1","-m","512","-global","driver=cfi.pflash01,property=secure,value=on",
             "-drive",f"if=pflash,format=raw,unit=0,readonly=on,file={QEMU/'share/edk2-x86_64-secure-code.fd'}",
             "-drive",f"if=pflash,format=raw,unit=1,file={folder/'VARS.fd'}",
             "-drive",f"if=none,id=vmusb,format=raw,file={folder/'USB.img'}","-device","qemu-xhci","-device","usb-storage,drive=vmusb,bootindex=1",
             "-device","VGA","-display","none","-serial",f"file:{folder/'serial.log'}","-debugcon",f"file:{folder/'debug.log'}",
             "-global","isa-debugcon.iobase=0x402","-device","isa-debug-exit,iobase=0x501,iosize=4","-monitor","none","-qmp","stdio",
             "-nic","none","-no-reboot","-smbios","type=0,version=M6501RM.313",
             "-smbios","type=1,manufacturer=ASUSTeK COMPUTER INC.,product=Vivobook_ASUSLaptop M6501RM_M6501RM"]
    if internal:
        # Same workspace-only image, attached through emulated NVMe instead of
        # USB, to exercise the SSD ESP source check. No host disk is attached.
        command[command.index('usb-storage,drive=vmusb,bootindex=1')]='nvme,drive=vmusb,serial=M6501VMLAB,bootindex=1'
    for image in (folder/"VARS.fd",folder/"USB.img"):
        if not within(image).is_file() or image.is_symlink():
            raise ValueError("Only regular workspace VM images may be attached")
    (folder/"qemu-command.json").write_text(json.dumps(command,indent=2))
    # Only local regular disk images are attached. No user-supplied QEMU options.
    errors=(folder/"qemu-stderr.log").open("wb")
    process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=errors,text=True)
    messages=queue.Queue()
    def reader():
        for line in process.stdout: messages.put(line)
    threading.Thread(target=reader,daemon=True).start()
    def qmp(command):
        process.stdin.write(json.dumps(command)+"\n");process.stdin.flush()
    try:
        greeting=messages.get(timeout=10)
        qmp({"execute":"qmp_capabilities"})
        deadline=time.monotonic()+timeout
        shot=False
        while process.poll() is None and time.monotonic()<deadline:
            if not shot and time.monotonic()>deadline-3:
                qmp({"execute":"screendump","arguments":{"filename":str(folder/"screen.png"),"format":"png"}})
                shot=True
            time.sleep(0.1)
        timed_out=process.poll() is None
        if timed_out:
            qmp({"execute":"quit"});process.wait(timeout=8)
        return {"returncode":process.returncode,"timed_out":timed_out,"qmp_greeting":json.loads(greeting)}
    finally:
        if process.poll() is None: process.kill();process.wait(timeout=5)
        errors.close()


def evaluate(mode,result,debug,serial):
    if mode=="n":
        return ("VM_HARNESS_ENTERED" not in debug and result["timed_out"]
                and "\\EFI\\BOOT\\grubx64.efi' Success" in debug
                and "Verification failed: (0x1A) Security Violation" in serial)
    if mode=="w":
        return ("REAL_WINDOWS_BOOT_MANAGER_START" in debug
                and "CHILD_LOAD=0x0000000000000000" in debug
                and "Windows Boot Manager" in serial
                and "\\EFI\\Microsoft\\Boot\\BCD" in serial and "0xc000000f" in serial)
    return "VM_TEST_PASS" in debug and result["returncode"]==33


def main():
    global COLLECTION
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case",choices=["probe","tamper","dbx","secure-off","no-mok","windows"],required=True)
    parser.add_argument("--timeout",type=int,default=25)
    parser.add_argument("--collection",type=Path,default=COLLECTION,help="Read-only exported PK/KEK/db/dbx directory")
    args=parser.parse_args()
    if not 8<=args.timeout<=50: parser.error("Bounded VM timeout required")
    COLLECTION=args.collection.resolve()
    for name in ("PK","KEK","db","dbx"):
        path=COLLECTION/(name+".bin")
        if not path.is_file() or not 0<path.stat().st_size<=4*1024*1024:
            parser.error("Missing or oversized public Secure Boot export: "+str(path))
    VM.mkdir(parents=True,exist_ok=True)
    folder=within(VM/(args.case+"-"+time.strftime("%Y%m%d-%H%M%S")))
    folder.mkdir()
    harness=compile_harness();probe=ROOT/"build/M6501-PROBE.EFI"
    audit=module("m6501_audit",ROOT/"tools/audit_trust.py")
    harness_hash=audit.pe_hash(harness.read_bytes())[0].hex();probe_hash=audit.pe_hash(probe.read_bytes())[0].hex()
    modes={"probe":"p","tamper":"t","dbx":"d","secure-off":"s","no-mok":"n","windows":"w"}
    mode=modes[args.case]
    files={"EFI/BOOT/BOOTX64.EFI":(ROOT/"build/shim/shimx64.efi").read_bytes(),
           "EFI/BOOT/mmx64.efi":(ROOT/"build/shim/mmx64.efi").read_bytes(),"EFI/BOOT/grubx64.efi":harness.read_bytes(),
           "PROBE.EFI":probe.read_bytes(),"EXPECT.BIN":mode.encode()}
    if mode=="t":
        modified=bytearray(files["PROBE.EFI"]);modified[0x40]^=1;files["PROBE.EFI"]=modified
    if mode=="w":
        source=Path(os.environ["SystemRoot"])/"Boot/EFI/bootmgfw.efi"
        files["EFI/Microsoft/Boot/bootmgfw.efi"]=source.read_bytes()
    gpt_image(folder/"USB.img",files)
    seed_vars(folder/"VARS.fd",harness_hash,probe_hash,mode)
    result=run_vm(folder,args.timeout)
    debug=(folder/"debug.log").read_text(errors="replace")
    serial=(folder/"serial.log").read_text(errors="replace")
    passed=evaluate(mode,result,debug,serial)
    result.update({"case":args.case,"passed":passed,"scope":"Virtual UEFI only; no host disks/GPU/network/firmware attached",
                   "laptop_hardware_validated":False,"harness_sha256":digest(harness),"probe_sha256":digest(probe),
                   "debug_output":debug,"virtual_host_key_snapshot_used":str(COLLECTION),"directory":str(folder)})
    (folder/"result.json").write_text(json.dumps(result,indent=2))
    concise={k:v for k,v in result.items() if k not in ("qmp_greeting","debug_output")}
    concise["harness_output"]=[line for line in debug.splitlines() if line.startswith(("VM_","LOG_OPEN","SECURE_BOOT","SETUP_MODE","ADAPTER_","CHILD_","REAL_WINDOWS"))]
    print(json.dumps(concise,indent=2),flush=True)
    return 0 if passed else 1


if __name__=="__main__":raise SystemExit(main())
