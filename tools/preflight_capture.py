"""Check saved CAPTURE data against pinned native parsers. No device access.

Compiles a host DLL and changes only temporary CPU buffers, never firmware or
the saved ROM. Passing this check does not establish hardware execution safety.
"""
import argparse
import ctypes as c
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[1]
U32, U64 = c.c_uint32, c.c_uint64


class FWSEC(c.Structure):
    _fields_ = [(name, U32) for name in (
        "image_off image_size imem_pa imem_size imem_va dmem_pa data_off "
        "dmem_size pkc_off interface_off ucode_id engine_mask sig_count "
        "sig_versions sig_off sig_bytes").split()]


class Span(c.Structure):
    _fields_ = [("offset", U64), ("size", U64)]


class LayoutIn(c.Structure):
    _fields_ = [("usable_fb", U64), ("vga_base", U64),
                ("mmu_lock_valid", c.c_bool)] + [(name, U64) for name in
        "mmu_lock_low frts_size boot_size image_size nonwpr_size heap_request".split()]


class LayoutOut(c.Structure):
    _fields_ = [(name, U64) for name in
        "reserved_top wpr_end frts_offset boot_offset gsp_offset heap_offset heap_size wpr_start nonwpr_start".split()]


class Booter(c.Structure):
    _fields_ = [(name, U32) for name in (
        "os_code_off os_code_size os_data_off os_data_size num_apps app_code_off "
        "app_code_size app_data_off app_data_size patch_loc ucode_id engine_id "
        "num_sigs sig_bytes").split()]


def buffer(data):
    return c.create_string_buffer(data, len(data))


def checked(code, operation):
    if code:
        raise ValueError(f"{operation} rejected saved evidence: {code}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    evidence = args.evidence.resolve()
    log = (evidence / "RTX-UNLOCK/RUN05/UNLOCK.TXT").read_text(encoding="ascii")
    raw = (evidence / "RTX-UNLOCK/PROM00.ROM").read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if len(raw) != 1048576 or f"PROM_SHA256 {digest}" not in log:
        raise ValueError("Full saved PROM must match this capture log")
    if "MEM_RESTORE status=0 confirmed=1 command=0" not in log or "EXIT status=0 GPU_MMIO_writes=0" not in log:
        raise ValueError("Capture did not confirm restoration and success")
    values = dict((int(off, 16), int(value, 16)) for off, value in
                  re.findall(r"LAYOUT_REG offset=(0x[0-9a-f]+) value=(0x[0-9a-f]+|0)\b", log))
    cold = re.search(r"COLD chip=(0x[0-9a-f]+) fb_mib=(\d+) ss0=(0x[0-9a-f]+) ss1=(0x[0-9a-f]+)", log)
    if cold is None:
        raise ValueError("Missing cold-state fields")
    chip, fb, ss0, ss1 = [int(x, 0) for x in cold.groups()]
    fw_fuse = int(re.search(r"FWSEC_FUSE raw=(0x[0-9a-f]+)", log)[1], 0)
    boot_fuse = int(re.search(r"BOOTER_FUSE raw=(0x[0-9a-f]+)", log)[1], 0)

    llvm = ROOT / "tools/downloads/llvm-mingw-20261020-ucrt-x86_64/bin"
    src = ROOT / "vendor/rtx30-unlock/src/unlock/vendor"
    env = {**os.environ, "PATH": str(llvm) + os.pathsep + os.environ["PATH"]}
    dll_path = ROOT / "build/capture-preflight.dll"
    subprocess.run([str(llvm / "x86_64-w64-mingw32-clang.exe"), "-shared", "-O1", "-std=c11",
                    "-Wall", "-Wextra", "-Werror", "-Wl,--export-all-symbols",
                    *[str(src / name) for name in ("vbios_610.c", "prep_610.c", "layout_610.c")],
                    "-o", str(dll_path)], check=True, env=env)
    dll_dir = os.add_dll_directory(str(llvm))
    lib = c.CDLL(str(dll_path))
    signatures = {
        "gpu_unlock_vbios_fwsec": ([c.c_void_p, c.c_size_t, c.POINTER(FWSEC)], c.c_int),
        "gpu_unlock_fuse_version": ([U32], U32),
        "gpu_unlock_fwsec_sig_offset": ([U32, U32, U32, c.POINTER(U32)], c.c_int),
        "gpu_unlock_fwsec_patch_frts": ([c.c_void_p, c.POINTER(FWSEC), U64], c.c_int),
        "gpu_unlock_elf_section": ([c.c_void_p, c.c_size_t, c.c_char_p, c.POINTER(Span)], c.c_int),
        "gpu_unlock_layout": ([c.POINTER(LayoutIn), c.POINTER(LayoutOut)], c.c_int),
        "gpu_unlock_booter_patch": ([c.c_void_p, U32, c.POINTER(Booter), c.c_void_p, U32, U32], c.c_int),
    }
    for name, (inputs, output) in signatures.items():
        function = getattr(lib, name)
        function.argtypes, function.restype = inputs, output
    fw = FWSEC()
    checked(lib.gpu_unlock_vbios_fwsec(buffer(raw), len(raw), c.byref(fw)), "FWSEC parser")
    fuse_version = lib.gpu_unlock_fuse_version(fw_fuse)
    sig_offset = U32()
    checked(lib.gpu_unlock_fwsec_sig_offset(fw.sig_versions, fuse_version, 384, c.byref(sig_offset)), "FWSEC signature selection")
    if sig_offset.value + 384 > fw.sig_bytes:
        raise ValueError("Selected signature exceeds descriptor")

    assets = ROOT / "build/release-20261025-v2/USB-CANDIDATE/RTX-UNLOCK/ASSETS"
    gsp = (assets / "gsp_ga10x.bin").read_bytes()
    span = Span()
    checked(lib.gpu_unlock_elf_section(buffer(gsp), len(gsp), b".fwimage", c.byref(span)), "GSP image section")
    fb_bytes = fb << 20
    vga = fb_bytes - (1 << 20)
    if values[0x625f04] & 8:
        vga = (values[0x625f04] >> 8) << 16
        if vga < fb_bytes - (1 << 20):
            vga = fb_bytes - 0x20000
    low, high = [(values[off] >> 4) << 12 for off in (0x1fa82c, 0x1fa830)]
    high_top = (high + 0xffff) & ~0xffff
    top_lock = high >= low and high_top >> 20 == fb
    if chip != 0xb76000a1 or fb != 6144 or not values[0x1fa7c8] & 1:
        raise ValueError("Unexpected chip, FB size or MMU state")
    boot_size = (assets / "gsp_boot_ga102.bin").stat().st_size
    layout_in = LayoutIn(fb_bytes, vga, top_lock, low, 1 << 20, boot_size,
                         span.size, 1 << 20, 88 << 20)
    layout = LayoutOut()
    checked(lib.gpu_unlock_layout(c.byref(layout_in), c.byref(layout)), "FB layout")
    if layout.nonwpr_start < fb_bytes - (256 << 20):
        raise ValueError("Reservations exceed top 256 MiB")
    scratch = buffer(raw[fw.image_off:fw.image_off + fw.image_size])
    checked(lib.gpu_unlock_fwsec_patch_frts(scratch, c.byref(fw), layout.frts_offset), "FWSEC FRTS mapper")
    booter_bytes = (assets / "booter_load_ga102.bin").read_bytes()
    hdr = Booter.from_buffer_copy(booter_bytes[8:64])
    image_size, sig_bytes = struct.unpack_from("<II", booter_bytes, 64)
    if len(booter_bytes) != 72 + image_size + sig_bytes:
        raise ValueError("Booter file length mismatch")
    boot_version = lib.gpu_unlock_fuse_version(boot_fuse)
    checked(lib.gpu_unlock_booter_patch(buffer(booter_bytes[72:72 + image_size]), image_size,
                                       c.byref(hdr), buffer(booter_bytes[72 + image_size:]),
                                       sig_bytes, boot_version), "Booter signature patch")
    report = {
        "scope": "Saved-file checks and temporary CPU-buffer patching only; no device access or firmware execution",
        "passed": True, "rom_sha256": digest, "chip": hex(chip), "fb_mib": fb,
        "ss0": hex(ss0), "ss1_to_preserve": hex(ss1),
        "fwsec_fuse_raw": hex(fw_fuse), "fwsec_signature_version": fuse_version,
        "fwsec_signature_offset": sig_offset.value, "fwsec_mapper_patch_accepted": True,
        "booter_fuse_raw": hex(boot_fuse), "booter_signature_version": boot_version,
        "booter_signature_patch_accepted": True,
        "gsp_image_bytes": span.size, "boot_image_bytes": boot_size,
        "mmu_top_lock_applies": top_lock, "mmu_low": hex(low), "mmu_high": hex(high),
        "layout": {name: hex(getattr(layout, name)) for name, _ in LayoutOut._fields_},
        "asset_hashes": {name: hashlib.sha256((assets / name).read_bytes()).hexdigest() for name in
                         ("booter_load_ga102.bin", "gsp_ga10x.bin", "gsp_boot_ga102.bin")},
        "hardware_unlock_validated": False, "driver_580_97_unlock_compatibility_validated": False,
        "limitations": ["Native layout decoding follows the pinned transaction formulas; actual firmware execution remains untested",
                        "Parser acceptance and signature availability do not cryptographically attest successful GPU execution",
                        "This report does not enable a board profile, build an unlock image, or authorize deployment"],
    }
    destination = evidence / "offline-preflight.json"
    if destination.exists():
        raise ValueError("Refusing to overwrite an existing offline review")
    destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
    dll_dir.close()
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
