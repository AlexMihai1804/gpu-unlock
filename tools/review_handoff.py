"""Review archived HANDOFF, UEFI exports and control GEMM. No hardware writes."""
import argparse
import importlib.util
import json
from pathlib import Path
import re

from audit_trust import esl,SHA256,pe_hash
from review_probe import bootmgr_block,sha

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--evidence",type=Path,required=True)
    p.add_argument("--post",type=Path,required=True)
    p.add_argument("--control",type=Path,required=True)
    a=p.parse_args();evidence=a.evidence.resolve()
    if not evidence.is_relative_to((ROOT/"results").resolve()): p.error("Evidence must be under results/")
    before=ROOT/"results/uefi-readonly-20261025-161851"
    image=(ROOT/"build/M6501-HANDOFF.EFI").read_bytes()
    image_sha=sha(image);auth_sha=pe_hash(image)[0].hex()
    observed=json.loads((evidence/"usb-image-hashes.json").read_text(encoding="utf-8-sig"))
    if not any(x["Path"].lower().endswith("\\grubx64.efi") and x["Hash"].lower()==image_sha for x in observed):
        raise ValueError("Observed USB image is not current HANDOFF")
    required=("SECURE SecureBoot=1 SetupMode=0; MokSBStateRT absent or zero",
              "SMBIOS M6501RM_product=1 BIOS_313=1","TARGET exact_matches=1",
              "GOP owner=16811002 independent_AMD=1",
              "WINDOWS_PRELOAD status=0 unique_GUID_match=1",
              "HANDOFF-ONLY status=0 no_GPU_writes=1 no_firmware_load=1")
    runs=[]
    for path in sorted(evidence.glob("RUN[0-9][0-9]/UNLOCK.TXT")):
        raw=path.read_bytes();text=raw.decode("ascii")
        if "HANDOFF-ONLY" not in text: continue
        if any(token not in text for token in required): raise ValueError("HANDOFF checks did not pass")
        runs.append({"file":str(path.relative_to(ROOT)),"sha256":sha(raw),"preload_status":0,"handoff_status":0})
    if not runs: raise ValueError("No successful HANDOFF log")
    windows=json.loads((evidence/"windows-return.json").read_text(encoding="utf-8-sig"))
    if windows["user_message"]!="a intrat in windows": raise ValueError("Windows return not recorded")
    trust={name:(before/(name+".bin")).read_bytes()==(a.post/(name+".bin")).read_bytes()
           for name in ("PK","KEK","db","dbx")}
    sb=(a.post/"SecureBoot.bin").read_bytes();setup=(a.post/"SetupMode.bin").read_bytes()
    hashes=[x["data"].hex() for x in esl((a.post/"MokListRT.bin").read_bytes()) if x["type"]==SHA256]
    probe_hash="7ea0fcecbecd80da16abca6258aee855b48c4c954602bb810d56b71e0cf498ea"
    before_boot=(before/"boot-entries.txt").read_text(encoding="utf-8-sig")
    after_boot=(a.post/"boot-entries.txt").read_text(encoding="utf-8-sig")
    manager_same=bootmgr_block(before_boot)==bootmgr_block(after_boot)
    first=bool(re.search(r"displayorder\s+\{bootmgr\}",after_boot))
    spec=importlib.util.spec_from_file_location("gemm_compare",ROOT/"bench/compare.py")
    compare=importlib.util.module_from_spec(spec);spec.loader.exec_module(compare)
    comparison=compare.compare(json.loads((ROOT/"results/baseline-2026-10-25.json").read_text()),json.loads(a.control.read_text()))
    report={"scope":"ASUS shim/MOK/HANDOFF to installed Windows plus control GEMM; no GPU unlock",
            "passed":bool(runs) and sb==b"\x01" and setup==b"\x00" and all(trust.values()) and
                     auth_sha in hashes and probe_hash in hashes and manager_same and first and
                     all(x["output_bit_identical"] for x in comparison),
            "runs":runs,"handoff_file_sha256":image_sha,"handoff_pe_authenticode_sha256":auth_sha,
            "handoff_hash_present_in_MokListRT":auth_sha in hashes,"probe_hash_still_present_in_MokListRT":probe_hash in hashes,
            "secure_boot":sb.hex(),"setup_mode":setup.hex(),"platform_trust_unchanged":trust,
            "windows_boot_manager_entry_unchanged":manager_same,"windows_boot_manager_first":first,
            "control_comparison":comparison,"control_result":str(a.control.resolve()),
            "max_absolute_control_change_percent":max(abs(x["gain_percent"]) for x in comparison),
            "gpu_unlock_applied":False,"full_nvidia_rom_obtained":False,"post_collection":str(a.post.resolve())}
    (evidence/"handoff-review.json").write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
    return 0 if report["passed"] else 1


if __name__=="__main__":raise SystemExit(main())
