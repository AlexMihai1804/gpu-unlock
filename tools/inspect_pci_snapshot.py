"""Replay the pinned PCI config guard against archived CFG log lines. No hardware access."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("log",type=Path)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    out=a.output.resolve()
    if not out.is_relative_to((ROOT/"results").resolve()) or out.exists(): p.error("Choose a new results subdirectory")
    cells={}
    for line in a.log.read_text().splitlines():
        match=re.fullmatch(r"CFG ([0-9a-f]{2}) ((?:[0-9a-f]{8} ){3}[0-9a-f]{8})",line)
        if not match: continue
        offset=int(match[1],16)
        if offset in cells or offset%16: raise ValueError("Duplicate or misaligned CFG rows")
        cells[offset]=[int(x,16) for x in match[2].split()]
    if sorted(cells)!=list(range(0,256,16)): raise ValueError("Complete 256-byte CFG snapshot required")
    raw=struct.pack("<64I",*(x for off in sorted(cells) for x in cells[off]))
    llvm=ROOT/"tools/downloads/llvm-mingw-20261020-ucrt-x86_64/bin"
    upstream=ROOT/"vendor/rtx30-unlock/src/unlock"
    edk=ROOT/"vendor/rtx30-unlock/deps/edk2/MdePkg/Include"
    exe=ROOT/"build/inspect-pci.exe"
    flags=["-std=c11","-O1","-fno-builtin","-ffunction-sections","-fdata-sections","-Wl,--gc-sections",
           "-Wall","-Wextra","-Werror","-DGU_RUNTIME_PROFILE_BUILD","-D_CRT_SECURE_NO_WARNINGS"]
    for path in (upstream,edk,edk/"X64"): flags.extend(["-I",str(path)])
    env={**os.environ,"PATH":str(llvm)+os.pathsep+os.environ["PATH"]}
    subprocess.run([str(llvm/"x86_64-w64-mingw32-clang.exe"),*flags,str(ROOT/"tools/inspect_pci.c"),
                    str(upstream/"checks.c"),"-o",str(exe)],check=True,env=env)
    out.mkdir(parents=True)
    snapshot=out/"PCI-CONFIG-SNAPSHOT.bin";snapshot.write_bytes(raw)
    result=subprocess.run([str(exe),str(snapshot)],capture_output=True,text=True,env=env)
    if result.returncode not in (0,1): raise RuntimeError("Offline PCI analyzer rejected input")
    report=json.loads(result.stdout)
    report.update({"snapshot_sha256":hashlib.sha256(raw).hexdigest(),"source_log":str(a.log.resolve()),
                   "scope":"Only PCI capability/config snapshot; BAR resources, bridge windows, ownership and MMIO remain untested"})
    (out/"report.json").write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
    return result.returncode


if __name__=="__main__":raise SystemExit(main())
