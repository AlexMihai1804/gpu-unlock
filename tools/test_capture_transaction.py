"""Run the retained transaction against saved board data and fake EFI services.

Uses the original PROM only as input bytes. No PCI/MMIO/DMA or firmware executes
on physical hardware. Generated harness and binaries stay in the build folder.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT/"vendor/rtx30-unlock"


def replace(source, old, new, count=1):
    if source.count(old) != count:
        raise ValueError(f"Pinned harness changed: {old!r}")
    return source.replace(old, new)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--evidence",type=Path,required=True)
    p.add_argument("--build-root",type=Path,required=True)
    p.add_argument("--output-name",default="capture-transaction-tests")
    p.add_argument('--ss1-full-experiment', action='store_true',
                   help='Validate the separate SS1=8 build; all services remain simulated')
    a=p.parse_args()
    evidence, build=a.evidence.resolve(), a.build_root.resolve()
    if not evidence.is_relative_to((ROOT/"results").resolve()) or not build.is_relative_to((ROOT/"build").resolve()):
        p.error("Use saved evidence under results/ and a build under build/")
    built=json.loads((build/'build-report.json').read_text())
    full=built.get('ss1_policy','').startswith('EXPERIMENTAL:')
    if full != a.ss1_full_experiment:
        p.error('Explicit test policy must match the build policy')
    review=json.loads((evidence/"capture-review.json").read_text())
    if not review["capture_passed"] or not review.get("uefi_trust",{}).get("passed"):
        raise ValueError("Reviewed successful CAPTURE and post-boot trust required")
    rom=evidence/"RTX-UNLOCK/PROM00.ROM"
    if hashlib.sha256(rom.read_bytes()).hexdigest()!=review["rom_sha256"]:
        raise ValueError("Saved PROM changed")
    log=(evidence/"RTX-UNLOCK/RUN05/UNLOCK.TXT").read_text()
    words=[]
    for line in log.splitlines():
        if line.startswith("CFG "):
            fields=line.split()
            if int(fields[1],16)!=len(words)*4:
                raise ValueError("Non-contiguous saved PCI configuration")
            words.extend(int(x,16) for x in fields[2:])
    if len(words)!=64:
        raise ValueError("Complete PCI configuration required")
    layout_values=dict((int(x,16),int(y,16)) for x,y in re.findall(r"LAYOUT_REG offset=(0x[0-9a-f]+) value=(0x[0-9a-f]+|0)\b",log))
    if not re.fullmatch(r"[a-zA-Z0-9_-]+",a.output_name):
        p.error("Output name must be a simple new folder name")
    out=build/a.output_name
    out.mkdir(exist_ok=False)
    source=(VENDOR/"src/unlock/tests/test_efi_transaction.c").read_text()
    source=source.replace('#include "../','#include "'+(VENDOR/"src/unlock").as_posix()+"/")
    # Preserve the original failure assertions; adapt only this board's data and
    # expected publication addresses. A changed upstream harness fails closed.
    if full:
        source=replace(source,'  SCENARIO_COUNT\n',
                       '  SS1_WRITE_REJECT,\n  SS1_READBACK_MISMATCH,\n  SCENARIO_COUNT\n')
        source=replace(source,'"fwsec-error-code"};',
                       '"fwsec-error-code", "ss1-write-rejected", "ss1-readback-mismatch"};')
        source=replace(source,'static UINT8 config[256], prom[1024 * 1024];',
                       'static UINT8 config[256], prom[1024 * 1024];\nstatic UINTN ss1_write_attempts;')
        source=replace(source,'  UINT32 v = *(UINT32 *)value;', '''  if (offset == SS1) {
    ss1_write_attempts++;
    CHECK(ss1_write_attempts==1 && GuProfile.ss1==3);
    CHECK(registers[SS0/4]==0x88888888 && fake.sec2_starts==1 && !fake.flrs);
    if (fake.mode == SS1_WRITE_REJECT) return EFI_DEVICE_ERROR;
  }
  UINT32 v = *(UINT32 *)value;
  if (offset==SS1) {
    CHECK(v==8);
    if (fake.mode==SS1_READBACK_MISMATCH) v=3;
  }''')
        source=replace(source,'    setup((enum scenario)mode);',
                       '    ss1_write_attempts=0;\n    setup((enum scenario)mode);')
        source=replace(source,'    /* App-level containment must work', '''    CHECK(ss1_write_attempts<=1);
    if (mode==SUCCESS || mode==FWSEC_RUNNING || mode==PIO_UNAVAILABLE)
      CHECK(ss1_write_attempts==1);
    if (mode==SS1_WRITE_REJECT || mode==SS1_READBACK_MISMATCH)
      CHECK(result && ss1_write_attempts==1 && !fake.flrs);
    /* App-level containment must work''')
    else:
        source=replace(source,"if (fake.mode == SELECTOR_LOST) registers[SS1 / 4] = 3;",
                       "if (fake.mode == SELECTOR_LOST) registers[SS1 / 4] = 6;")
        source=replace(source,"registers[SS1 / 4] == 8","registers[SS1 / 4] == 3")
        source=replace(source,"UINT32 v = *(UINT32 *)value;",
                       "CHECK(offset != SS1); /* Never write SS1. */\n  UINT32 v = *(UINT32 *)value;")
    # Windows may place a host allocation at the fake bus address by chance.
    # Keep the non-identity-mapping assertion and deterministically skip that
    # simulated address instead of treating random host VA layout as a GPU bug.
    source=replace(source,"  b->dma = fake.next_dma;",
                   "  if (fake.next_dma == (UINT64)(UINTN)cpu) fake.next_dma += 4096;\n  b->dma = fake.next_dma;")
    replacements={"0xdf00":"0xe100","0xe700":"0xe900","0x43060":"0x411d8",
                  "0x27fe00":"0x17fe00","0x275400000ULL":"0x175400000ULL",
                  "0x27ada0000ULL":"0x17ada0000ULL","0x27fdfa000ULL":"0x17fdfa000ULL",
                  "0x27fe00000ULL":"0x17fe00000ULL","0x27ff00000ULL":"0x17ff00000ULL",
                  "0x280000000ULL":"0x180000000ULL","0x27fe000":"0x17fe000",
                  "0x27feff0":"0x17feff0","0xb72000a1":"0xb76000a1",
                  "0x46254040":"0x10420030","0x2800":"0x1800","0x26ffff0":"0x16ffff0",
                  "0x84000000":"0xdc000000"}
    for old,new in replacements.items():
        pattern=r"\b"+re.escape(old)+r"\b"
        if not re.search(pattern,source):
            raise ValueError("Expected fixture constant missing: "+old)
        source=re.sub(pattern,new,source)
    start=source.index("  fake.pci_attributes = EFI_PCI_IO_ATTRIBUTE_IO | EFI_PCI_IO_ATTRIBUTE_MEMORY;")
    end=source.index("  registers[0] =",start)
    snapshot=",".join(f"0x{x:08x}U" for x in words)
    source=source[:start]+("  fake.pci_attributes = EFI_PCI_IO_ATTRIBUTE_MEMORY;\n"
        f"  static const UINT32 saved_config[64] = {{{snapshot}}};\n"
        "  memcpy(config,saved_config,sizeof(config));\n"
        "  config[4] |= 2; /* App already enabled MEMORY; no physical PCI. */\n")+source[end:]
    values=",".join(hex(layout_values[x])+"U" for x in (0x625f04,0x1fa7c8,0x1fa82c,0x1fa830,0x1fa824,0x1fa828))
    profile=("  GuProfile=(GU_RUNTIME_PROFILE){.identity=0x252010deU,.subsystem=0x13131043U,"
             ".chip=0xb76000a1U,.class_revision=0x030000a1U,.plm=0xffffff8fU,"
             ".ss0=0x10420030U,.ss1=3U,.fb_mib=6144U,.bar_size=0x1000000ULL,"
             f'.layout={{{values}}},.prom_sha256="{review["rom_sha256"]}"'+'};\n')
    source=replace(source,"  GuInit(&bs, &pci);","  GuInit(&bs, &pci);\n"+profile)
    test_file=out/"test_saved_m6501_transaction.c"
    test_file.write_text(source,encoding="utf-8")
    llvm=ROOT/"tools/downloads/llvm-mingw-20261020-ucrt-x86_64/bin"
    env={**os.environ,"PATH":str(llvm)+os.pathsep+os.environ["PATH"]}
    include=VENDOR/"deps/edk2/MdePkg/Include"
    flags=["-std=c11","-O1","-fno-builtin","-ffunction-sections","-fdata-sections","-Wl,--gc-sections",
           "-Wall","-Wextra","-Werror","-Wno-unused-function","-Wno-unused-parameter","-Wno-unused-variable",
           "-D_CRT_SECURE_NO_WARNINGS","-D__KERNEL__","-DGU_UEFI_PORT","-DGU_RUNTIME_PROFILE_BUILD"]
    for path in (include,include/"X64",VENDOR/"src/unlock",VENDOR/"src/unlock/compat",VENDOR/"src/unlock/vendor"):
        flags.extend(["-I",str(path)])
    core=build/('generated/unlock_610_ss1_full.c' if full else 'generated/unlock_610_ss0.c')
    if full and hashlib.sha256(core.read_bytes()).hexdigest()!=built['original_core_sha256']:
        raise ValueError('SS1 experiment must retain the pinned upstream transaction unchanged')
    sources=[test_file,core]+[VENDOR/f"src/unlock/{x}.c" for x in
             ("port","compat","runtime_profile","sha256","vendor/prep_610","vendor/layout_610","vendor/vbios_610","vendor/gfw_eval")]
    exe=out/"test-saved-m6501-transaction.exe"
    subprocess.run([str(llvm/"x86_64-w64-mingw32-clang.exe"),*flags,*map(str,sources),"-o",str(exe)],check=True,env=env)
    run=subprocess.run([str(exe),str(rom),str(ROOT/"build/firmware")],capture_output=True,text=True,env=env)
    (out/"run.log").write_text(run.stdout+run.stderr,encoding="utf-8")
    print(run.stdout,flush=True)
    if run.returncode:
        raise SystemExit(run.stderr or f"Saved-board transaction test failed: {run.returncode}")
    (out/"capture_fixture.h").write_text(f"static const UINT32 saved_capture_config[64]={{{snapshot}}};\n")
    guard_exe=out/"test-unlock-preflight.exe"
    guard_sources=[ROOT/"tests/test_unlock_preflight.c"]+[VENDOR/f"src/unlock/{x}.c" for x in
        ("port","compat","checks","sha256","runtime_profile","vendor/prep_610","vendor/vbios_610","vendor/gfw_eval")]
    experiment_flags=['-DM6501_SS1_FULL_EXPERIMENT'] if full else []
    subprocess.run([str(llvm/"x86_64-w64-mingw32-clang.exe"),*flags,*experiment_flags,"-I",str(out),"-I",str(build/"generated"),
                    *map(str,guard_sources),"-o",str(guard_exe)],check=True,env=env)
    guards=subprocess.run([str(guard_exe),str(rom)],capture_output=True,text=True,env=env)
    (out/"preflight-guards.log").write_text(guards.stdout+guards.stderr,encoding="utf-8")
    if guards.returncode:
        raise SystemExit(guards.stdout+guards.stderr or "Saved-board preflight guards failed")
    print(guards.stdout,flush=True)
    report={"passed":True,"hardware_executed":False,"physical_firmware_executed":False,
            "scope":"Retained transaction fault/success scenarios, runtime profile, saved M6501 PCI/ROM and fake EFI services",
            "rom_sha256":review["rom_sha256"],"runtime_profile_build":True,"ss1_write_forbidden":not full,
            "ss1_full_experiment":full,"transaction_scenarios":22 if full else 20,
            "ss1_write_reject_and_readback_mismatch_tested":full,
            "saved_board_preflight_cases":14 if full else 13,"preflight_arms_or_writes_gpu":False,
            "generated_harness_sha256":hashlib.sha256(test_file.read_bytes()).hexdigest(),
            "limitations":"Mock execution checks software ownership, geometry and failure paths; does not emulate GPU firmware execution or validate driver 580.97"}
    (out/"report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")


if __name__=="__main__":
    main()
