"""Review archived physical PROBE evidence and read-only UEFI exports; no hardware writes."""
import argparse
import hashlib
import json
from pathlib import Path
import re

from audit_trust import esl, SHA256, pe_hash

ROOT=Path(__file__).resolve().parents[1]


def sha(data): return hashlib.sha256(data).hexdigest()


def bootmgr_block(text):
    match=re.search(r"(?ms)^Windows Boot Manager\n-+\n(.*?)(?=\n\n|\Z)",text)
    if not match: raise ValueError("Missing Windows Boot Manager block")
    # bcdedit leaves a terminal newline when this is the final block. Preserve
    # every field/space, but do not mistake that formatting for a BCD change.
    return match.group(1).rstrip("\r\n")


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--evidence",type=Path,required=True)
    p.add_argument("--post",type=Path,required=True)
    p.add_argument("--before",type=Path,default=ROOT/"results/uefi-readonly-20261025-161851")
    a=p.parse_args()
    evidence=a.evidence.resolve()
    if not evidence.is_relative_to((ROOT/"results").resolve()): p.error("Evidence must be under results/")
    image=(ROOT/"build/M6501-PROBE.EFI").read_bytes()
    image_sha=sha(image);auth_sha=pe_hash(image)[0].hex()
    copied=json.loads((evidence/"usb-image-hashes.json").read_text(encoding="utf-8-sig"))
    if not any(row["Path"].lower().endswith("\\grubx64.efi") and row["Hash"].lower()==image_sha for row in copied):
        raise ValueError("Observed USB image differs from current tested PROBE")
    required=("SECURE SecureBoot=1 SetupMode=0; MokSBStateRT absent or zero",
              "SMBIOS M6501RM_product=1 BIOS_313=1","TARGET exact_matches=1",
              "GOP owner=16811002 independent_AMD=1",
              "PROBE complete: no GPU config writes, no MMIO, no firmware load. display_safe=1",
              "EXIT status=0 GPU_MMIO_writes=0")
    runs=[]
    for path in sorted(evidence.glob("RUN[0-9][0-9]/UNLOCK.TXT")):
        raw=path.read_bytes();text=raw.decode("ascii")
        if any(token not in text for token in required): raise ValueError("PROBE checks not complete: "+str(path))
        target=re.search(r"PCI 0000:01:00\.0 id=252010de subsystem=13131043 classrev=030000a1 command=([0-9a-f]+) ROM_bytes=(\d+)",text)
        if not target or int(target[1],16)!=0: raise ValueError("Unexpected GPU cold inventory")
        runs.append({"file":str(path.relative_to(ROOT)),"sha256":sha(raw),"exit_status":0,
                     "gpu_mmio_writes":0,"gpu_pci_command":0,"uefi_rom_image_bytes":int(target[2])})
    if not runs: raise ValueError("No PROBE logs")
    trust={name:(a.before/(name+".bin")).read_bytes()==(a.post/(name+".bin")).read_bytes()
           for name in ("PK","KEK","db","dbx")}
    mok=esl((a.post/"MokListRT.bin").read_bytes())
    hashes=[entry["data"].hex() for entry in mok if entry["type"]==SHA256]
    trusted=auth_sha in hashes
    sb=(a.post/"SecureBoot.bin").read_bytes();setup=(a.post/"SetupMode.bin").read_bytes()
    before_boot=(a.before/"boot-entries.txt").read_text(encoding="utf-8-sig")
    after_boot=(a.post/"boot-entries.txt").read_text(encoding="utf-8-sig")
    manager_same=bootmgr_block(before_boot)==bootmgr_block(after_boot)
    windows_first=bool(re.search(r"displayorder\s+\{bootmgr\}",after_boot))
    report={"scope":"Physical ASUS shim/MOK/PROBE only; no handoff or GPU transaction",
            "passed":sb==b"\x01" and setup==b"\x00" and all(trust.values()) and trusted and manager_same and windows_first,
            "runs":runs,"probe_file_sha256":image_sha,"probe_pe_authenticode_sha256":auth_sha,
            "probe_hash_present_in_MokListRT":trusted,"secure_boot":sb.hex(),"setup_mode":setup.hex(),
            "platform_trust_unchanged":trust,"windows_boot_manager_entry_unchanged":manager_same,
            "windows_boot_manager_first":windows_first,
            "firmware_boot_inventory_changed":before_boot!=after_boot,
            "boot_inventory_note":"Before: generic CD/DVD, removable and network entries; after: concrete UEFI SanDisk entry. No BCD/boot-variable write command issued by project; firmware inventory differs.",
            "gpu_unlock_applied":False,"full_nvidia_rom_obtained":False,
            "post_collection":str(a.post.resolve()),"evidence_directory":str(evidence)}
    (evidence/"probe-review.json").write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
    return 0 if report["passed"] else 1


if __name__=="__main__":raise SystemExit(main())
