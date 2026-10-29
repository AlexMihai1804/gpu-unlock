"""Build local EFI files only. Does not install, enroll, reboot, or write a USB."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / "vendor/rtx30-unlock"
PIN = "5c076dc4ee7fa369639669fa591ac74d8f6dfcd8"


def run(args, **kw):
    return subprocess.run([str(a) for a in args], check=True, **kw)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def output_directory(path):
    """An isolated build must not overwrite earlier reviewed executables."""
    base = (ROOT/"build").resolve()
    if path is None:
        return base
    output = path.resolve()
    if output == base or not output.is_relative_to(base) or output.exists():
        raise ValueError("Choose a new ordinary subdirectory under build/")
    return output


def patch_core(source):
    """Change SS1 writes AND both readback expectations to preserve this boot's SS1."""
    old = "#define GU_SS1_UNLOCK 0x8u"
    if source.count(old) != 1:
        raise ValueError("Upstream SS1 constant changed; review required")
    source = source.replace(old, "#define GU_SS1_UNLOCK (GU_INITIAL_SS1)")
    old = 'return ret ? ret : write_selector(work, "SS1", GU_FEAT_SS1_OFFSET, GU_SS1_UNLOCK);'
    if source.count(old) != 1:
        raise ValueError("Upstream selector implementation changed; review required")
    new = '''u32 actual;
    if (ret) return ret;
    if (read_bar(work, GU_FEAT_SS1_OFFSET, &actual) || actual != GU_SS1_UNLOCK)
        return GU_RESULT(-EIO);
    dev_info(&work->pdev->dev, "SS1 preserved: actual=%#x expected=%#x (no write)\\n", actual, GU_SS1_UNLOCK);
    return 0;'''
    source = source.replace(old, new)
    source = source.replace("/* SS0 selects the full BF16 rate; SS1 gets the same field value. FLR keeps both. */",
                            "/* Local M6501RM change: SS0 only, preserve and verify current-boot SS1. */")
    source = source.replace("/* SS0 holds eight 4-bit fields; SS1 stores only its low 4 bits (0x2 when\n * cold). Both get the same per-field value 8. */",
                            "/* Local M6501RM change: preserve SS1; no borrowed desktop/mobile constant. */")
    return source


def experimental_full_core(source):
    """Retain the pinned upstream SS0+SS1 transaction for a separate manual test."""
    required = ('#define GU_SS0_UNLOCK 0x88888888u', '#define GU_SS1_UNLOCK 0x8u',
                'return ret ? ret : write_selector(work, "SS1", GU_FEAT_SS1_OFFSET, GU_SS1_UNLOCK);')
    if any(source.count(item) != 1 for item in required):
        raise ValueError('Pinned full-selector transaction changed; review required')
    return source


def patch_experiment_io(source):
    """Keep experiment assets/logs separate on either a USB or the project ESP."""
    old = 'L"\\\\RTX-UNLOCK"'
    if source.count(old) != 1:
        raise ValueError('Pinned experiment IO path changed; review required')
    return source.replace(old, 'L"\\\\EFI\\\\M6501TF32\\\\RTX-UNLOCK"')


def board_header(path):
    board = json.loads(path.read_text(encoding="utf-8-sig"))
    fixed = {"model": "M6501RM", "bios": "M6501RM.313", "identity": "0x252010de",
             "subsystem": "0x13131043", "class_revision": "0x030000a1", "fb_mib": 6144,
             "vbios": "94.06.38.00.38", "pci": "0000:01:00.0"}
    if any(board.get(k) != v for k, v in fixed.items()):
        raise ValueError("Board identity differs from this adapter")
    ready = board.get("evidence_reviewed") is True
    digest = board.get("prom_sha256")
    chip = board.get("chip")
    windows = board.get("windows_partition")
    guid = uuid.UUID(windows).bytes_le if windows else bytes(16)
    if ready:
        if not isinstance(digest, str) or not re.fullmatch("[a-f0-9]{64}", digest):
            raise ValueError("Reviewed original 1 MiB PROM SHA256 required")
        chip = int(chip, 0) if isinstance(chip, str) else chip
        if not isinstance(chip, int) or chip & 0xfff00000 != 0xb7600000 or chip & 255 != 0xa1:
            raise ValueError("Reviewed GA106 A1 PMC_BOOT_0 required")
        guid = uuid.UUID(windows).bytes_le
        booter_fuse = int(str(board.get("booter_fuse_raw")), 0)
        fwsec_fuse = int(str(board.get("fwsec_fuse_raw")), 0)
        if booter_fuse != 1 or fwsec_fuse != 3:
            raise ValueError("Reviewed M6501 fuse values required")
    else:
        digest, chip = "", 0
        booter_fuse, fwsec_fuse = 0, 0
    guid_values = ",".join(str(x) for x in guid)
    return (f'#define M6501_EVIDENCE_READY {int(ready)}\n'
            f'#define M6501_EXPECTED_PROM "{digest}"\n'
            f'#define M6501_EXPECTED_CHIP 0x{chip:08x}U\n'
            f'#define M6501_EXPECTED_BOOTER_FUSE 0x{booter_fuse:x}U\n'
            f'#define M6501_EXPECTED_FWSEC_FUSE 0x{fwsec_fuse:x}U\n'
            f'static const unsigned char M6501_WINDOWS_GUID[16] = {{{guid_values}}};\n'), ready


def patch_auto_io(source):
    """Private SSD directory and 10,000 append-only boot logs; pinned source only."""
    changes={
        'L"\\\\RTX-UNLOCK"':'L"\\\\EFI\\\\M6501GPU\\\\RTX-UNLOCK"',
        'Selected >= 100':'Selected >= 10000',
        ' : 100); slot++':' : 10000); slot++',
        'CHAR16 name[] = L"RUN00";':'CHAR16 name[] = L"RUN0000";',
        "name[3] = (CHAR16)('0' + slot / 10);":"name[3] = (CHAR16)('0' + slot / 1000);\n    name[4] = (CHAR16)('0' + slot / 100 % 10);\n    name[5] = (CHAR16)('0' + slot / 10 % 10);",
        "name[4] = (CHAR16)('0' + slot % 10);":"name[6] = (CHAR16)('0' + slot % 10);",
        'experiment\\nRUN%02u':'automatic internal boot\\nRUN%04u',
        'fix unproven; one manual attempt per launch.':'transaction; one automatic attempt per launch.',
    }
    for old,new in changes.items():
        if source.count(old)!=1:
            raise ValueError('Automatic IO patch differs from pinned source: '+repr(old))
        source=source.replace(old,new)
    return source


def patch_auto_tf32_io(source):
    """Authorized automatic SS1 experiment, in its own assets/log directory."""
    source = patch_auto_io(source)
    old = 'L"\\\\EFI\\\\M6501GPU\\\\RTX-UNLOCK"'
    if source.count(old) != 1:
        raise ValueError('Automatic private IO path changed; review required')
    return source.replace(old, 'L"\\\\EFI\\\\M6501TF32\\\\RTX-UNLOCK"')


def inspect_pe(path):
    data = path.read_bytes()
    pe = struct.unpack_from("<I", data, 0x3c)[0]
    if data[pe:pe+4] != b"PE\0\0":
        raise ValueError("Not a PE file")
    machine, sections = struct.unpack_from("<HH", data, pe+4)
    opt_size = struct.unpack_from("<H", data, pe+20)[0]
    opt = pe+24
    subsystem, flags = struct.unpack_from("<HH", data, opt+68)
    if machine != 0x8664 or struct.unpack_from("<H", data, opt)[0] != 0x20b or subsystem != 10:
        raise ValueError("Expected AMD64 PE32+ EFI application")
    alignment = struct.unpack_from("<I", data, opt+32)[0]
    parsed = []
    for i in range(sections):
        offset = opt+opt_size+40*i
        name = data[offset:offset+8].rstrip(b"\0").decode("ascii")
        vs, va, raw_size, raw = struct.unpack_from("<IIII", data, offset+8)
        attributes = struct.unpack_from("<I", data, offset+36)[0]
        if attributes & 0x20000000 and attributes & 0x80000000:
            raise ValueError(f"Writable executable section: {name}")
        if va % alignment:
            raise ValueError(f"Misaligned section: {name}")
        parsed.append({"name": name, "virtual_address": va, "virtual_size": vs,
                       "raw_size": raw_size, "attributes": attributes})
        if name == ".sbat":
            if b"m6501-gpu-lab,1," not in data[raw:raw+raw_size]:
                raise ValueError("Missing local SBAT identity")
    if not flags & 0x100 or not flags & 0x40 or alignment < 4096:
        raise ValueError("NX/DYNAMICBASE/page alignment required")
    if not any(x["name"] == ".sbat" for x in parsed):
        raise ValueError("SBAT section missing")
    if not any(x["name"] == ".reloc" for x in parsed):
        raise ValueError("Relocations missing")
    import_size = struct.unpack_from("<II", data, opt+112+8)[1]
    if import_size:
        raise ValueError("Firmware executable must not import Windows DLLs")
    return {"sha256": sha(path), "machine": "AMD64", "subsystem": "EFI_APPLICATION",
            "nx_compatible": True, "dynamic_base": True, "section_alignment": alignment,
            "sections": parsed}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--llvm", type=Path)
    parser.add_argument("--board", type=Path, default=ROOT/"config/board.pending.json")
    parser.add_argument("--output", type=Path, help="New isolated directory under build/; existing builds are preserved")
    parser.add_argument("--automatic",action="store_true",help="Also build the separate SSD automatic image")
    parser.add_argument('--ss1-full-experiment', action='store_true',
                        help='Build a SEPARATE manual SS1=8 candidate; no automatic image or deployment')
    parser.add_argument('--automatic-ss1-experiment', action='store_true',
                        help='Explicit automatic SS1=8 build, separately authorized; never deploys itself')
    args = parser.parse_args()
    if args.ss1_full_experiment and args.automatic:
        parser.error('The SS1 experiment cannot build an automatic image')
    if args.automatic_ss1_experiment and (args.ss1_full_experiment or args.automatic):
        parser.error('Use the explicit automatic SS1 option on its own')
    full_ss1 = args.ss1_full_experiment or args.automatic_ss1_experiment
    if subprocess.check_output(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"], text=True).strip() != PIN:
        raise SystemExit("Pinned rtx30-unlock checkout required")
    if subprocess.check_output(["git", "-C", str(UPSTREAM), "status", "--porcelain"], text=True).strip():
        raise SystemExit("Upstream checkout has local changes; review before building")
    default = ROOT/"tools/downloads/llvm-mingw-20261020-ucrt-x86_64/bin"
    llvm = args.llvm or Path(os.environ.get("LLVM_BIN", str(default)))
    compiler = llvm/("clang-23.exe" if (llvm/"clang-23.exe").is_file() else "clang.exe")
    linker = llvm/"lld-link.exe"
    link_prefix = [linker]
    if not linker.is_file() and (llvm/"ld.lld.exe").is_file():
        linker = llvm/"ld.lld.exe"
        link_prefix = [linker, "-flavor", "link"]
    if not compiler.is_file() or not linker.is_file():
        raise SystemExit("Set --llvm to a portable LLVM bin directory")
    build = output_directory(args.output)
    generated = build/"generated"
    generated.mkdir(parents=True, exist_ok=True)
    header, ready = board_header(args.board)
    if (args.automatic or full_ss1) and not ready:
        parser.error('Automatic image and SS1 experiment require the reviewed board profile')
    (generated/"board.h").write_text(header, encoding="ascii")
    core = UPSTREAM/"src/unlock/vendor/unlock_610.c"
    patched = generated/("unlock_610_ss1_full.c" if full_ss1 else "unlock_610_ss0.c")
    transform = experimental_full_core if full_ss1 else patch_core
    transformed = transform(core.read_text())
    if full_ss1:
        # Preserve the pinned bytes as well as the code, including line endings.
        patched.write_bytes(core.read_bytes())
    else:
        patched.write_text(transformed, encoding="utf-8")
    sources = ["runtime", "format", "sha256", "port", "compat", "runtime_profile", "checks", "ownership", "app_io", "vendor/vbios_610", "vendor/gfw_eval"]
    include = UPSTREAM/"deps/edk2/MdePkg/Include"
    flags = ["-target", "x86_64-pc-windows-msvc", "-std=c11", "-ffreestanding", "-fno-builtin",
             "-fno-stack-protector", "-mno-red-zone", "-fshort-wchar", "-ffunction-sections", "-fdata-sections", "-Os", "-Wall", "-Wextra",
             "-Werror", "-Wno-unused-parameter", "-Wno-unused-function", "-Wno-unused-variable",
             "-D__KERNEL__", "-DGU_UEFI_PORT", "-DGU_RUNTIME_PROFILE_BUILD",
             "-I", str(generated), "-I", str(ROOT/"uefi/include"), "-I", str(UPSTREAM/"src/unlock"),
             "-I", str(UPSTREAM/"src/unlock/vendor"), "-I", str(UPSTREAM/"src/unlock/compat"),
             "-I", str(include), "-I", str(include/"X64")]
    common = []
    for source in sources:
        target = generated/(source.replace("/", "_")+".obj")
        run([compiler, *flags, "-c", UPSTREAM/f"src/unlock/{source}.c", "-o", target])
        common.append(target)
    sbat = generated/"sbat.obj"
    run([compiler, *flags, "-c", ROOT/"uefi/sbat.c", "-o", sbat])
    common.append(sbat)
    transaction = []
    for source in [patched, *[UPSTREAM/f"src/unlock/vendor/{x}.c" for x in ("layout_610", "prep_610")]]:
        obj = generated/(source.stem+".obj")
        run([compiler, *flags, "-c", source, "-o", obj])
        transaction.append(obj)
    report = {"upstream_commit": PIN, "board_evidence_ready": ready, "hardware_tested": False,
              "signed": False, "deployed": False, "compiler": subprocess.check_output([str(compiler), "--version"], text=True),
              "board_profile": str(args.board.resolve()), "board_profile_sha256": sha(args.board),
              "output_directory": str(build),
              "original_core_sha256": sha(core), "patched_core_sha256": sha(patched), "images": {}}
    if full_ss1:
        report.update(ss1_policy='EXPERIMENTAL: SS0=0x88888888, SS1=0x8; entry SS1 must be 3',
                      physical_confirmation_key=None if args.automatic_ss1_experiment else 'T',
                      automatic_mode=args.automatic_ss1_experiment,
                      experimental_private_directory='EFI/M6501TF32',
                      physical_test_authorized=False, hardware_tested=False)
        if not args.automatic_ss1_experiment:
            io_source=generated/'tf32_experiment_io.c'
            io_source.write_text(patch_experiment_io((UPSTREAM/'src/unlock/app_io.c').read_text()),
                                 encoding='utf-8')
            io_obj=generated/'tf32_experiment_io.obj'
            run([compiler,*flags,'-DGU_SSD_EXPERIMENT','-c',io_source,'-o',io_obj])
            common=[x for x in common if x!=generated/'app_io.obj']+[io_obj]
    modes=[("PROBE", "M6501-PROBE.EFI"), ("HANDOFF", "M6501-HANDOFF.EFI"), ("CAPTURE", "M6501-CAPTURE.EFI"),
           ("UNLOCK", "M6501-UNLOCK-CANDIDATE.EFI")]
    if args.automatic:
        modes.append(("AUTO", "M6501-AUTOMATIC.EFI"))
    if args.ss1_full_experiment:
        modes = [("UNLOCK", "M6501-TF32-SS1-CANDIDATE.EFI")]
    if args.automatic_ss1_experiment:
        modes = [("AUTO", "M6501-AUTOMATIC-TF32.EFI")]
    for mode, name in modes:
        obj = generated/(mode+".obj")
        extra=["-DMODE_UNLOCK","-DM6501_AUTOMATIC"] if mode=="AUTO" else ["-DMODE_"+mode]
        if full_ss1:
            extra.append('-DM6501_SS1_FULL_EXPERIMENT')
        if args.automatic_ss1_experiment:
            extra.append('-DM6501_AUTO_SS1_EXPERIMENT')
        run([compiler, *flags, *extra, "-c", ROOT/"uefi/m6501.c", "-o", obj])
        image = build/name
        objects = [*common, obj, *(transaction if mode in ("UNLOCK","AUTO") else [])]
        if mode=="AUTO":
            io_source=generated/'automatic_io.c'
            io_patch=patch_auto_tf32_io if args.automatic_ss1_experiment else patch_auto_io
            io_source.write_text(io_patch((UPSTREAM/'src/unlock/app_io.c').read_text()),encoding='utf-8')
            io_obj=generated/'automatic_io.obj'
            run([compiler,*flags,"-DGU_SSD_EXPERIMENT","-c",io_source,"-o",io_obj])
            objects=[x for x in objects if x!=generated/'app_io.obj']+[io_obj]
            report.update(automatic_mode=True,automatic_countdown_seconds=5,
                          automatic_private_directory='EFI/M6501TF32' if args.automatic_ss1_experiment else 'EFI/M6501GPU',
                          automatic_logs_append_only_limit=10000)
        run([*link_prefix, "/nologo", "/nodefaultlib", "/subsystem:efi_application", "/entry:efi_main",
             "/machine:x64", "/base:0", "/dynamicbase", "/nxcompat", "/filealign:512",
             "/timestamp:0", "/opt:ref", "/opt:icf", "/include:m6501_sbat", "/map:"+str(image.with_suffix(".map")),
             "/out:"+str(image), *objects])
        report["images"][name] = inspect_pe(image)
        print(name, report["images"][name]["sha256"])
    (build/"build-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("Local files built. No USB, boot setting, firmware, or key was modified.")


if __name__ == "__main__":
    main()
