"""Extract a checksum-pinned portable QEMU into this workspace; never install it."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import urllib.request

ROOT=Path(__file__).resolve().parents[1]


def main():
    entry=json.loads((ROOT/"config/sources.lock.json").read_text())["qemu_vm_only"]
    downloads=ROOT/"tools/downloads"
    downloads.mkdir(parents=True,exist_ok=True)
    archive=downloads/"qemu-w64-setup-20260811.exe"
    if not archive.exists():
        part=archive.with_suffix(".part")
        request=urllib.request.Request(entry["url"],headers={"User-Agent":"M6501-VM-Lab/0.1"})
        with urllib.request.urlopen(request,timeout=60) as response,part.open("wb") as target:
            if not response.url.startswith("https://"): raise ValueError("Insecure redirect")
            total=0
            while block:=response.read(1024*1024):
                total+=len(block)
                if total>1024**3: raise ValueError("Download exceeds limit")
                target.write(block)
        with part.open("rb") as source:
            if hashlib.file_digest(source,"sha512").hexdigest()!=entry["sha512"]:
                raise ValueError("SHA512 mismatch")
        part.replace(archive)
    with archive.open("rb") as source:
        if hashlib.file_digest(source,"sha512").hexdigest()!=entry["sha512"]:
            raise ValueError("Cached QEMU archive differs from lock")
    out=(downloads/"qemu-portable").resolve()
    if not out.is_relative_to(downloads.resolve()): raise ValueError("Invalid extraction directory")
    exe=out/"qemu-system-x86_64.exe"
    if not exe.exists():
        if out.exists(): raise ValueError("Use an absent extraction directory")
        seven=shutil.which("7z")
        if not seven: raise SystemExit("7-Zip is required for archive extraction; do not run the installer")
        subprocess.run([seven,"x",str(archive),"-o"+str(out),"-y"],check=True,stdout=subprocess.DEVNULL)
    version=subprocess.check_output([str(exe),"--version"],text=True)
    if "version "+entry["version"] not in version: raise ValueError("Unexpected QEMU version")
    print(version.splitlines()[0])
    print("Archive extracted only; no service, driver, registry or boot setting changed.")


if __name__=="__main__": main()
