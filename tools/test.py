"""Run host-only validation; no EFI image is launched and no hardware is accessed."""
import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import struct
import argparse

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT/"vendor/rtx30-unlock"
OUT = ROOT/"build/tests"
LLVM = ROOT/"tools/downloads/llvm-mingw-20261020-ucrt-x86_64/bin"


def synthetic_prom():
    """Parser-valid test data. Contains NO board firmware and must never be booted."""
    rom = bytearray(1024*1024)
    def w32(offset, value):
        struct.pack_into("<I", rom, offset, value)
    rom[:2] = b"\x55\xaa"
    rom[0x18] = 32
    rom[32:36] = b"PCIR"
    rom[42] = 24
    struct.pack_into("<H", rom, 48, len(rom)//512)
    rom[53] = 0x80
    rom[64:69] = b"\xff\xb8BIT"
    rom[71:75] = bytes([1,12,6,1])
    rom[75] = (-sum(rom[64:75])) & 255
    rom[76:80] = bytes([0x70,2,4,0])
    w32(80,100); w32(100,128)
    rom[128:132] = bytes([1,6,6,1])
    rom[134] = 0x85; w32(136,0x43034)
    desc = 0x43034
    for offset, value in [(0,0x04ac0301),(4,0xe700),(8,0x5a4),(12,0x1c),(20,0xdf00),(32,0x800)]:
        w32(desc+offset,value)
    struct.pack_into("<HBBH",rom,desc+36,0x400,9,3,7)
    for i in range(1152):
        rom[desc+44+i] = (i*17+3)&255
    dmem = desc+0x4ac+0xdf00
    rom[dmem+0x1c:dmem+0x20] = bytes([1,4,8,2])
    w32(dmem+0x20,4); w32(dmem+0x24,0x100)
    w32(dmem+0x28,1); w32(dmem+0x2c,0x140)
    struct.pack_into("<IHHII",rom,dmem+0x100,0,3,64,0x7c0,64)
    path = OUT/"SYNTHETIC-NOT-HARDWARE.ROM"
    path.write_bytes(rom)
    return path


def main():
    global OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-root", type=Path, default=ROOT/"build")
    args = parser.parse_args()
    build_root = args.build_root.resolve()
    if not build_root.is_relative_to((ROOT/"build").resolve()) or not (build_root/"build-report.json").is_file():
        parser.error("Build root must be a completed local build under build/")
    OUT = build_root/"tests"
    OUT.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PATH": str(LLVM)+os.pathsep+os.environ["PATH"]}
    compiler = LLVM/"x86_64-w64-mingw32-clang.exe"
    include = VENDOR/"deps/edk2/MdePkg/Include"
    flags = ["-std=c11", "-O1", "-fno-builtin", "-ffunction-sections", "-fdata-sections", "-Wl,--gc-sections",
             "-Wall", "-Wextra", "-Werror", "-Wno-unused-function", "-Wno-unused-parameter", "-Wno-unused-variable",
             "-D_CRT_SECURE_NO_WARNINGS", "-I", str(include), "-I", str(include/"X64"),
             "-I", str(VENDOR/"src/unlock"), "-I", str(build_root/"generated")]
    results = []
    fixture = synthetic_prom()
    fixture_sha = hashlib.sha256(fixture.read_bytes()).hexdigest()
    sha_test = (VENDOR/"src/unlock/tests/test_sha256.c").read_text().replace(
        "F3DC8F07B0B8C9856D192DF172DFA7F7F84AC17EF6EDFDB448AD7FA94EFD2789", fixture_sha)
    sha_test = sha_test.replace('#include "../', '#include "'+(VENDOR/"src/unlock").as_posix()+"/")
    sha_source = OUT/"test_sha256_with_synthetic_prom.c"
    sha_source.write_text(sha_test)
    cases = [
        ("adapter", [ROOT/"tests/test_adapter.c"], []),
        ("automatic-countdown-and-fallback", [ROOT/"tests/test_automatic_boot.c"], []),
        ("pci-config-guards", [VENDOR/"src/unlock/tests/test_checks.c", VENDOR/"src/unlock/checks.c"], []),
        ("pci-port", [VENDOR/"src/unlock/tests/test_port.c", VENDOR/"src/unlock/port.c"], []),
        ("sha256", [sha_source, VENDOR/"src/unlock/sha256.c"], []),
    ]
    for name, sources, extra in cases:
        exe = OUT/(name+".exe")
        subprocess.run([str(compiler), *flags, *extra, *map(str, sources), "-o", str(exe)], check=True, env=env)
        arguments = [str(ROOT/"build/firmware/gsp_ga10x.bin"), str(fixture)] if name == "sha256" else []
        completed = subprocess.run([str(exe), *arguments], check=True, capture_output=True, text=True, env=env)
        print(name+": "+completed.stdout.strip())
        results.append({"case": name, "passed": True, "stdout": completed.stdout})
    integration = (VENDOR/"src/unlock/tests/test_efi_transaction.c").read_text()
    integration = integration.replace('#include "../', '#include "'+(VENDOR/"src/unlock").as_posix()+"/")
    integration = integration.replace("if (fake.mode == SELECTOR_LOST) registers[SS1 / 4] = 3;",
                                      "if (fake.mode == SELECTOR_LOST) registers[SS1 / 4] = 6;")
    integration = integration.replace("registers[SS1 / 4] == 8", "registers[SS1 / 4] == 3")
    integration = integration.replace("UINT32 v = *(UINT32 *)value;", "CHECK(offset != SS1); /* SS1 must NEVER be written. */\n  UINT32 v = *(UINT32 *)value;")
    test_source = OUT/"test_transaction_ss0_only.c"
    test_source.write_text(integration)
    board = OUT/"fixture_board.h"
    board.write_text('''#define GU_BOARD_ID 0x220610deU
#define GU_TARGET_PCI_ID 0x220610deU
#define GU_BOARD_SUBSYSTEM 0x38901462U
#define GU_BOARD_CHIP 0xb72000a1U
#define GU_INITIAL_PLM 0xffffff8fU
#define GU_INITIAL_SS0 0x46254040U
#define GU_INITIAL_SS1 3U
#define GU_FB_MIB 0x2800U
#define GU_BAR_SIZE 0x1000000ULL
#define GU_PROM_SHA256 "unused-in-this-host-test"
''')
    core_sources = [test_source, VENDOR/"src/unlock/port.c", VENDOR/"src/unlock/compat.c",
                    build_root/"generated/unlock_610_ss0.c",
                    *[VENDOR/f"src/unlock/vendor/{x}.c" for x in ("prep_610", "layout_610", "vbios_610", "gfw_eval")]]
    exe = OUT/"ss0-transaction.exe"
    extra = ["-D__KERNEL__", "-DGU_UEFI_PORT", "-include", str(board),
             "-I", str(VENDOR/"src/unlock/compat"), "-I", str(VENDOR/"src/unlock/vendor")]
    subprocess.run([str(compiler), *flags, *extra, *map(str,core_sources), "-o", str(exe)], check=True, env=env)
    completed = subprocess.run([str(exe),str(fixture),str(ROOT/"build/firmware")], check=False,
                               capture_output=True,text=True,env=env)
    print(completed.stdout)
    if completed.returncode:
        print(completed.stderr, file=sys.stderr)
        completed.check_returncode()
    results.append({"case": "SS0-only-real-core-with-synthetic-PROM-and-mocked-UEFI", "passed": True,
                    "stdout": completed.stdout, "synthetic_rom_sha256": fixture_sha})
    for mode in ("PROBE", "HANDOFF", "CAPTURE"):
        data = (build_root/f"M6501-{mode}.map").read_text()
        forbidden = ["GuWrite32", "GuConfigWrite", "GuEnableMaster", "GuFlr", "GuDmaAllocate", "gpu_unlock_610_unlock"]
        import re
        if any(re.search(r"\b"+x+r"\b", data) for x in forbidden):
            raise RuntimeError(mode+" links GPU mutation/DMA/FLR routines")
        results.append({"case": mode+"-no-linked-GPU-write-FLR-DMA-routines", "passed": True})
    subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-v"],
                   check=True, cwd=ROOT, env=env)
    (OUT/"report.json").write_text(json.dumps({"hardware_executed": False, "results": results}, indent=2))
    print("Host checks passed; physical GPU, ASUS Secure Boot and Windows handoff require separate hardware validation.")


if __name__ == "__main__":
    main()
