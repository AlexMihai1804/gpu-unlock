"""Inspect a saved ROM using the actual pinned FWSEC parser. Reads files only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("rom", type=Path)
    a = p.parse_args()
    if not a.rom.is_file() or not 0 < a.rom.stat().st_size <= 1048576:
        p.error("Expected a saved ROM file of at most 1 MiB")
    llvm = ROOT/"tools/downloads/llvm-mingw-20261020-ucrt-x86_64/bin"
    src = ROOT/"vendor/rtx30-unlock/src/unlock/vendor"
    output = ROOT/"build/inspect-rom.exe"
    env = {**os.environ, "PATH": str(llvm)+os.pathsep+os.environ["PATH"]}
    subprocess.run([str(llvm/"x86_64-w64-mingw32-clang.exe"),"-std=c11","-O1","-Wall","-Wextra","-Werror",
                    "-D_CRT_SECURE_NO_WARNINGS","-I",str(src),str(ROOT/"tools/inspect_rom.c"),
                    str(src/"vbios_610.c"),"-o",str(output)],check=True,env=env)
    run = subprocess.run([str(output),str(a.rom.resolve())],capture_output=True,text=True,env=env)
    if run.returncode:
        raise SystemExit(run.stderr or "ROM parsing failed")
    result = json.loads(run.stdout)
    result["sha256"] = hashlib.sha256(a.rom.read_bytes()).hexdigest()
    result["is_full_1MiB_capture"] = a.rom.stat().st_size == 1048576
    result["provenance"] = "caller-supplied file; board identity/authenticity not established by this parser"
    print(json.dumps(result,indent=2))


if __name__ == "__main__":
    main()
