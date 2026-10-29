"""Create a reviewable USB layout in build/ only; never writes a physical USB."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=["probe", "handoff", "capture", "candidate", "tf32-experiment"], default="probe")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--image-root", type=Path, default=ROOT/"build",
                   help="Directory containing reviewed EFI images, under build/")
    a = p.parse_args()
    out = a.output.resolve()
    if not out.is_relative_to((ROOT/"build").resolve()) or out == (ROOT/"build").resolve():
        p.error("Output must be a new ordinary subdirectory under this project's build directory")
    if out.exists():
        p.error("Output already exists; never overwrite a staged image")
    image_root = a.image_root.resolve()
    if not image_root.is_relative_to((ROOT/"build").resolve()):
        p.error("Image root must be under this project's build directory")
    image = {"probe": "M6501-PROBE.EFI", "handoff": "M6501-HANDOFF.EFI", "capture": "M6501-CAPTURE.EFI",
             "candidate": "M6501-UNLOCK-CANDIDATE.EFI",
             "tf32-experiment": "M6501-TF32-SS1-CANDIDATE.EFI"}[a.mode]
    inputs = {"EFI/BOOT/BOOTX64.EFI": ROOT/"build/shim/shimx64.efi",
              "EFI/BOOT/mmx64.efi": ROOT/"build/shim/mmx64.efi",
              "EFI/BOOT/grubx64.efi": image_root/image}
    if a.mode in ("candidate", "tf32-experiment"):
        asset_prefix = 'EFI/M6501TF32/RTX-UNLOCK/ASSETS/' if a.mode == 'tf32-experiment' else 'RTX-UNLOCK/ASSETS/'
        for f in (ROOT/"build/firmware").iterdir():
            if f.is_file():
                inputs[asset_prefix+f.name] = f
    for source in inputs.values():
        if not source.is_file():
            p.error("Prepare missing input first: "+str(source))
    for notice in (ROOT/"build/shim").glob("*.copyright"):
        inputs["LICENSES/"+notice.name] = notice
    inputs["THIRD_PARTY_NOTICES.md"] = ROOT/"THIRD_PARTY_NOTICES.md"
    files = {}
    for name, source in inputs.items():
        destination = out/name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        files[name] = hashlib.sha256(destination.read_bytes()).hexdigest()
    (out/"RTX-UNLOCK").mkdir(exist_ok=True)
    for f in (ROOT/"vendor/rtx30-unlock/LICENSES").iterdir():
        if f.is_file():
            dst = out/"LICENSES"/f.name
            dst.parent.mkdir(exist_ok=True)
            shutil.copy2(f,dst)
    shutil.copy2(ROOT/"vendor/rtx30-unlock/LICENSE",out/"LICENSE")
    manifest = {"mode": a.mode, "hardware_tested": False, "deployed": False,
                "mok_enrolled": False, "files_sha256": files,
                "image_root": str(image_root),
                "note": "grubx64.efi is our local application, not GRUB. The application is unsigned and requires explicit MOK hash enrollment, or a reviewed signing route."}
    (out/"STAGING-MANIFEST.json").write_text(json.dumps(manifest,indent=2))
    (out/"READ-FIRST.txt").write_text(
        "PREPARATION ONLY. User approval required before booting this USB or enrolling anything.\n"
        f"Mode: {a.mode}. M6501RM.313 / 10de:2520 / 1043:1313 only.\n"
        "BOOTX64.EFI = Microsoft-signed Debian shim 16.1.\n"
        f"grubx64.efi = {image}; no GRUB configuration.\n"
        "No fallback.efi/fbx64.efi: do not add them.\n"
        "Do not overwrite the Windows ESP. Use the one-time ASUS USB boot menu.\n"
        "MOK enrollment changes persistent shim trust. It needs separate approval.\n"
        "Application files alone do not establish firmware trust; dbx/SBAT and actual chain must be tested.\n"
        "See project README.md and docs/TESTING.md before proceeding.\n",encoding="utf-8")
    print("Prepared local folder:",out)


if __name__ == "__main__":
    main()
