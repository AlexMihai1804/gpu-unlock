"""Prepare verified files in this workspace only. Never installs or boots anything."""
import argparse
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
LOCK = json.loads((ROOT/"config/sources.lock.json").read_text())
DOWNLOADS = ROOT/"tools/downloads"


def digest(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def fetch(url, target, expected):
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        part = target.with_name(target.name+".part")
        request = urllib.request.Request(url, headers={"User-Agent": "M6501-GPU-Lab/0.1"})
        print("Downloading", target.name, flush=True)
        with urllib.request.urlopen(request, timeout=60) as response, part.open("wb") as out:
            if not response.url.startswith("https://"):
                raise ValueError("Refusing insecure redirect")
            total = 0
            while block := response.read(1024*1024):
                total += len(block)
                if total > 2*1024**3:
                    raise ValueError("Download limit exceeded")
                out.write(block)
        if digest(part) != expected:
            raise ValueError("SHA256 mismatch: " + target.name)
        part.replace(target)
    if digest(target) != expected:
        raise ValueError("Cached artifact differs from lock: " + target.name)
    return target


def check_repository(folder):
    entry = next(e for e in LOCK["repositories"] if e["folder"] == folder)
    repo = ROOT/"vendor"/folder
    if not repo.exists():
        repo.parent.mkdir(exist_ok=True)
        subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", entry["url"]], check=True)
        subprocess.run(["git", "-C", str(repo), "fetch", "--depth", "1", "origin", entry["commit"]], check=True)
        subprocess.run(["git", "-C", str(repo), "checkout", "--detach", "FETCH_HEAD"], check=True)
    actual = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain"], text=True).strip()
    if actual != entry["commit"] or dirty:
        raise ValueError("Unexpected source revision or local changes: " + folder)
    return repo


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ar_members(data):
    if data[:8] != b"!<arch>\n":
        raise ValueError("Invalid Debian ar archive")
    pos = 8
    while pos+60 <= len(data):
        header = data[pos:pos+60]
        if header[58:60] != b"`\n":
            raise ValueError("Invalid ar header")
        size = int(header[48:58])
        name = header[:16].decode("ascii").strip().rstrip("/")
        pos += 60
        if size < 0 or pos+size > len(data):
            raise ValueError("Invalid ar member size")
        yield name, data[pos:pos+size]
        pos += size + (size & 1)


def shim():
    out = ROOT/"build/shim"
    out.mkdir(parents=True, exist_ok=True)
    records = []
    for entry in LOCK["shim_packages"]:
        path = fetch("https://deb.debian.org/debian/"+entry["filename"], DOWNLOADS/Path(entry["filename"]).name, entry["sha256"])
        for name, data in ar_members(path.read_bytes()):
            if not name.startswith("data.tar"):
                continue
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as archive:
                for member in archive:
                    base = Path(member.name).name
                    if base == "copyright" and "usr/share/doc/" in member.name and member.isfile() and member.size < 1024*1024:
                        (out/(entry["package"]+".copyright")).write_bytes(archive.extractfile(member).read())
                        continue
                    # fbx64.efi is deliberately excluded: it can create firmware boot entries.
                    if base not in ("shimx64.efi.signed", "shimx64.efi.signed.latest", "mmx64.efi.signed"):
                        continue
                    if not member.isfile() or member.size > 4*1024*1024:
                        continue
                    destination = out/("shimx64.efi" if base.startswith("shimx64") else "mmx64.efi")
                    blob = archive.extractfile(member).read()
                    if destination.exists() and destination.read_bytes() != blob:
                        raise ValueError("Multiple or changed shim images; inspect package")
                    destination.write_bytes(blob)
                    records.append({"file": destination.name, "sha256": digest(destination), **entry})
    if {x["file"] for x in records} != {"shimx64.efi", "mmx64.efi"}:
        raise ValueError("Expected shim and MokManager not found in pinned packages")
    (out/"manifest.json").write_text(json.dumps({"files": records, "firmware_trust_tested": False}, indent=2))
    print("Prepared signed shim/MokManager only in build/shim; no enrollment or boot.")


def firmware():
    import zstandard
    repo = check_repository("ga106")
    manifest = json.loads((repo/"firmware/artifacts-610.43.03.json").read_text())
    source, _, package = manifest["source_artifacts"]
    archive = fetch(source["url"], DOWNLOADS/source["filename"], source["sha256"])
    out = ROOT/"build/firmware"
    extracted = ROOT/"build/nvidia-source"
    extractor = load_module("m6501_extract_assets", repo/"firmware/extract_boot_assets.py")
    wanted = set(extractor.PINNED)
    found = set()
    # Extract only the two hash-pinned generated C data files; no archive code runs.
    with tarfile.open(archive, "r:*") as tar:
        for member in tar:
            name = Path(member.name).name
            if name not in wanted:
                continue
            if name in found or not member.isfile() or member.size > 16*1024*1024:
                raise ValueError("Invalid NVIDIA source member")
            found.add(name)
            target = extracted/"src/nvidia/generated"/name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(tar.extractfile(member).read())
    if found != wanted:
        raise ValueError("NVIDIA generated sources missing")
    extractor.extract_assets(extracted, out)
    pkg = fetch(package["url"], DOWNLOADS/package["filename"], package["sha256"])
    generator = load_module("m6501_v67", repo/"firmware/generate_v67.py")
    members = {"usr/lib/firmware/nvidia/610.43.03/gsp_ga10x.bin":
               ("gsp_ga10x.bin", generator.GSP_SHA256),
               package["notice"]["path"]: ("NVIDIA-LICENSE", package["notice"]["sha256"])}
    found = set()
    with pkg.open("rb") as stream, zstandard.ZstdDecompressor().stream_reader(stream) as decoded:
        with tarfile.open(fileobj=decoded, mode="r|") as tar:
            for member in tar:
                if member.name not in members:
                    continue
                if member.name in found or not member.isfile() or member.size > 128*1024*1024:
                    raise ValueError("Invalid package member")
                found.add(member.name)
                filename, expected = members[member.name]
                data = tar.extractfile(member).read()
                if hashlib.sha256(data).hexdigest() != expected:
                    raise ValueError("Firmware/license hash mismatch")
                (out/filename).write_bytes(data)
    if found != set(members):
        raise ValueError("Firmware package incomplete")
    payload = generator.build_payload()
    if hashlib.sha256(payload).hexdigest() != generator.PAYLOAD_SHA256:
        raise ValueError("Generated V67 hash mismatch")
    (out/"v67-ga102-610.43.03.bin").write_bytes(payload)
    shutil.copy2(repo/"firmware/artifacts-610.43.03.json", out/"upstream-manifest.json")
    print("Firmware prepared and hashes verified; nothing executed on the GPU.")


def bootstrap():
    for entry in LOCK["repositories"]:
        check_repository(entry["folder"])
    entry = LOCK["llvm"]
    archive = fetch(entry["url"], DOWNLOADS/"llvm.zip", entry["sha256"])
    if not (DOWNLOADS/"llvm-mingw-20261020-ucrt-x86_64/bin/clang-23.exe").is_file():
        with zipfile.ZipFile(archive) as z:
            for member in z.infolist():
                target = (DOWNLOADS/member.filename).resolve()
                if not target.is_relative_to(DOWNLOADS.resolve()):
                    raise ValueError("Unsafe ZIP path")
            z.extractall(DOWNLOADS)
    print("Pinned sources and portable compiler ready.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["bootstrap", "shim", "firmware"])
    try:
        globals()[parser.parse_args().action]()
    except Exception as e:
        raise SystemExit(f"Preparation failed: {e}")
