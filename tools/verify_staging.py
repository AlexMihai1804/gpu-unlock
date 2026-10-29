"""Verify local staged USB artifacts without accessing removable media or UEFI."""
import hashlib
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--root", type=Path, default=ROOT/"build")
p.add_argument("--image-root", type=Path, default=ROOT/"build")
p.add_argument("--report", type=Path, default=ROOT/"results/staging-verification.json")
a = p.parse_args()
stage_root = a.root.resolve()
if not stage_root.is_relative_to((ROOT/"build").resolve()):
    p.error("Only ordinary staged directories under build/ are supported")
image_root = a.image_root.resolve()
if not image_root.is_relative_to((ROOT/"build").resolve()):
    p.error("Image root must be under build/")
report_path = a.report.resolve()
if not report_path.is_relative_to((ROOT/"results").resolve()):
    p.error("Verification report must be under results/")
report = []
for name in ("USB-PROBE", "USB-HANDOFF", "USB-CAPTURE", "USB-CANDIDATE"):
    folder = stage_root/name
    manifest = json.loads((folder/"STAGING-MANIFEST.json").read_text())
    for relative, expected in manifest["files_sha256"].items():
        path = (folder/relative).resolve()
        if not path.is_relative_to(folder.resolve()):
            raise SystemExit("Manifest path leaves package")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise SystemExit("Staged file hash mismatch: "+str(path))
    expected_images = {"BOOTX64.EFI", "mmx64.efi", "grubx64.efi"}
    if {p.name for p in (folder/"EFI/BOOT").iterdir()} != expected_images:
        raise SystemExit("Unexpected boot image or fallback helper")
    if list(folder.rglob("*.ROM")):
        raise SystemExit("ROM files must not be packaged as firmware assets")
    if manifest["deployed"] or manifest["mok_enrolled"] or manifest["hardware_tested"]:
        raise SystemExit("Staging cannot claim deployment or hardware validation")
    image = {"USB-PROBE":"M6501-PROBE.EFI", "USB-HANDOFF":"M6501-HANDOFF.EFI",
             "USB-CAPTURE":"M6501-CAPTURE.EFI", "USB-CANDIDATE":"M6501-UNLOCK-CANDIDATE.EFI"}[name]
    if (folder/"EFI/BOOT/grubx64.efi").read_bytes() != (image_root/image).read_bytes():
        raise SystemExit("Staging contains an older application: "+str(folder))
    report.append({"stage": name, "directory": str(folder), "files_verified": len(manifest["files_sha256"]),
                   "hardware_tested": False, "deployed": False})
report_path.write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
