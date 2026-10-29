"""Review archived CAPTURE evidence, optional UEFI exports and control GEMM.

Reads local files only and writes a review report; never enables an unlock.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import re

from audit_trust import SHA256, esl, pe_hash
from review_probe import bootmgr_block, sha

ROOT = Path(__file__).resolve().parents[1]


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--post", type=Path)
    args = parser.parse_args()
    evidence = args.evidence.resolve()
    if not evidence.is_relative_to((ROOT / "results").resolve()):
        parser.error("Evidence must be under results/")
    for item in read_json(evidence / "evidence-hashes.json"):
        data = (evidence / "RTX-UNLOCK" / item["file"]).read_bytes()
        if len(data) != item["bytes"] or sha(data) != item["sha256"]:
            raise ValueError("Archived evidence changed")
    image = (ROOT / "build/M6501-CAPTURE.EFI").read_bytes()
    image_sha, auth_sha = sha(image), pe_hash(image)[0].hex()
    images = read_json(evidence / "usb-image-hashes.json")
    if not any(item["name"].lower() == "grubx64.efi" and item["sha256"] == image_sha for item in images):
        raise ValueError("USB snapshot differs from reviewed CAPTURE image")
    log = (evidence / "RTX-UNLOCK/RUN05/UNLOCK.TXT").read_text(encoding="ascii")
    required = (
        "SECURE SecureBoot=1 SetupMode=0; MokSBStateRT absent or zero",
        "SMBIOS M6501RM_product=1 BIOS_313=1", "TARGET exact_matches=1",
        "GOP owner=16811002 independent_AMD=1", "BRIDGE 0:1.1 MEM=1",
        "covers=1", "ownership: records=8 exclusive=1 status=0",
        "MEM_ENABLE status=0 command=0x2 attributes=0x200",
        "PROM_FILE index=0 bytes=1048576 status=0",
        "MEM_RESTORE status=0 confirmed=1 command=0", "EXIT status=0 GPU_MMIO_writes=0")
    if any(text not in log for text in required):
        raise ValueError("Required CAPTURE checks missing or failed")
    raw = (evidence / "RTX-UNLOCK/PROM00.ROM").read_bytes()
    digest = sha(raw)
    if len(raw) != 1048576 or f"PROM_SHA256 {digest}" not in log:
        raise ValueError("ROM does not match capture log")
    offline = read_json(evidence / "offline-preflight.json")
    if not offline["passed"] or offline["rom_sha256"] != digest:
        raise ValueError("Offline preflight missing or mismatched")
    spec = importlib.util.spec_from_file_location("gemm_compare", ROOT / "bench/compare.py")
    compare = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(compare)
    comparison = compare.compare(read_json(ROOT / "results/baseline-2026-10-25.json"), read_json(args.control))
    health_path = evidence / "post-benchmark-health/boot-control.json"
    if not health_path.is_file():
        health_path = evidence / "post-boot-health/boot-control.json"
    health = read_json(health_path)
    display_errors = [item for item in health["events"] if item["provider"] in ("Display", "nvlddmkm")]
    trust = None
    if args.post:
        before = ROOT / "results/uefi-readonly-20261025-161851"
        post = args.post.resolve()
        same = {name: (before / f"{name}.bin").read_bytes() == (post / f"{name}.bin").read_bytes()
                for name in ("PK", "KEK", "db", "dbx")}
        hashes = [entry["data"].hex() for entry in esl((post / "MokListRT.bin").read_bytes()) if entry["type"] == SHA256]
        mok_state_file = post / "MokSBStateRT.bin"
        mok_validation = not mok_state_file.exists() or mok_state_file.read_bytes() == b"\x00"
        boot = (post / "boot-entries.txt").read_text(encoding="utf-8-sig")
        old_boot = (before / "boot-entries.txt").read_text(encoding="utf-8-sig")
        trust = {
            "secure_boot": (post / "SecureBoot.bin").read_bytes().hex(),
            "setup_mode": (post / "SetupMode.bin").read_bytes().hex(),
            "platform_trust_unchanged": same, "capture_hash_present_in_MokListRT": auth_sha in hashes,
            "shim_validation_enabled": mok_validation,
            "windows_boot_manager_entry_unchanged": bootmgr_block(boot) == bootmgr_block(old_boot),
            "windows_boot_manager_first": bool(re.search(r"displayorder\s+\{bootmgr\}", boot)),
            "collection": str(post),
        }
        trust["passed"] = (trust["secure_boot"] == "01" and trust["setup_mode"] == "00" and
                           all(same.values()) and trust["capture_hash_present_in_MokListRT"] and mok_validation and
                           trust["windows_boot_manager_entry_unchanged"] and trust["windows_boot_manager_first"])
    report = {
        "scope": "Physical CAPTURE, original saved PROM, offline native-parser checks and Windows control; GPU unlock remains untested",
        "capture_passed": True, "temporary_pci_memory_restored": True, "rom_bytes": len(raw), "rom_sha256": digest,
        "capture_file_sha256": image_sha, "capture_pe_authenticode_sha256": auth_sha,
        "secure_boot_preboot": 1, "secure_boot_windows_registry": health["secure_boot_registry_value"],
        "uefi_post_collection_pending": trust is None, "uefi_trust": trust,
        "offline_preflight_passed": True, "control_comparison": comparison,
        "control_outputs_bit_identical": all(row["output_bit_identical"] for row in comparison),
        "max_absolute_control_change_percent": max(abs(row["gain_percent"]) for row in comparison),
        "display_or_nvlddmkm_events": len(display_errors), "current_boot_hardware_events": health["events"],
        "health_collection_utc": health["utc"],
        "gpu_unlock_applied": False,
        "enabled_unlock_profile_created": (ROOT / "config/board.reviewed.json").is_file(),
        "limitations": ["Preboot log and USB image snapshot are evidence, not TPM-backed execution attestation",
                        "A short GEMM control and current-boot event check do not prove long-term stability",
                        "Offline acceptance does not validate GPU firmware execution or compatibility with driver 580.97"],
    }
    (evidence / "capture-review.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key not in ("current_boot_hardware_events", "limitations")}, indent=2))
    return 0 if report["control_outputs_bit_identical"] and not display_errors and (trust is None or trust["passed"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
