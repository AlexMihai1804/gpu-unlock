"""Consolidate local evidence only; never accesses disks, UEFI APIs or the GPU."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
RESULTS=ROOT/"results"


def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod


def main():
    current=json.loads((RESULTS/"STATUS.json").read_text(encoding="utf-8-sig"))
    if current.get("active_staging")!="build/release-20261025-v2":
        raise SystemExit("Legacy v2 report is frozen. Use tools/review_candidate.py for the isolated v3 candidate; do not overwrite its status or release.")
    vm=load_module("report_vm",ROOT/"tools/vm_lab.py")
    latest=[]
    probe_hash=digest(ROOT/"build/M6501-PROBE.EFI")
    modes={"probe":"p","tamper":"t","dbx":"d","secure-off":"s","no-mok":"n","windows":"w"}
    for case,mode in modes.items():
        folders=sorted((ROOT/"build/vm-lab").glob(case+"-*"))
        if not folders: raise ValueError("Missing virtual case: "+case)
        folder=folders[-1]
        result=json.loads((folder/"result.json").read_text())
        debug=(folder/"debug.log").read_text(errors="replace")
        serial=(folder/"serial.log").read_text(errors="replace")
        if not vm.evaluate(mode,result,debug,serial) or result["probe_sha256"]!=probe_hash:
            raise ValueError("Virtual case not valid for current image: "+case)
        command=json.loads((folder/"qemu-command.json").read_text())
        if command[command.index("-accel")+1]!="tcg,thread=single" or command[command.index("-nic")+1]!="none":
            raise ValueError("VM isolation settings differ")
        if "-no-user-config" not in command or "-nodefaults" not in command: raise ValueError("Implicit VM configuration")
        drives=[command[i+1] for i,x in enumerate(command) if x=="-drive"]
        expected=[f"if=pflash,format=raw,unit=0,readonly=on,file={vm.QEMU/'share/edk2-x86_64-secure-code.fd'}",
                  f"if=pflash,format=raw,unit=1,file={folder/'VARS.fd'}",
                  f"if=none,id=vmusb,format=raw,file={folder/'USB.img'}"]
        if drives!=expected: raise ValueError("Unexpected VM storage")
        for x in (folder/"VARS.fd",folder/"USB.img"): vm.within(x)
        item={k:v for k,v in result.items() if k not in ("debug_output","qmp_greeting")}
        item["passed"]=True
        item["strict_evidence_rechecked"]=True
        item["harness_output"]=[line for line in debug.splitlines() if line.startswith(
            ("VM_","LOG_OPEN","SECURE_BOOT","SETUP_MODE","ADAPTER_","CHILD_","REAL_WINDOWS"))]
        item["vm_storage_isolation_verified"]=True
        item["evidence_sha256"]={name:digest(folder/name) for name in ("debug.log","serial.log","qemu-command.json")}
        latest.append(item)
    evidence={"date":"2026-10-25","cases":latest,"virtual_chain_tested":True,
              "physical_asus_chain_tested":False,"gpu_unlock_tested":False,
              "host_firmware_or_keys_written":False,"host_storage_attached_to_vm":False,
              "ovmf_code_sha256":digest(vm.QEMU/"share/edk2-x86_64-secure-code.fd"),
              "ovmf_template_sha256":digest(vm.QEMU/"share/edk2-i386-vars.fd"),
              "limits":"No real ASUS firmware, TPM, NVIDIA GPU or installed Windows in VM. Windows loader execution ends at expected missing BCD."}
    (RESULTS/"vm-validation.json").write_text(json.dumps(evidence,indent=2))
    compare=load_module("report_compare",ROOT/"bench/compare.py")
    comparison=compare.compare(json.loads((RESULTS/"baseline-2026-10-25.json").read_text()),
                               json.loads((RESULTS/"baseline-repeat-2026-10-25.json").read_text()))
    (RESULTS/"baseline-repeat-comparison.json").write_text(json.dumps(comparison,indent=2))
    checks=subprocess.run([sys.executable,"-m","unittest","discover","-s","tests","-p","test_*.py","-v"],
                          cwd=ROOT,capture_output=True,text=True,check=True)
    (RESULTS/"python-tests-final.log").write_text(checks.stdout+checks.stderr)
    for source,name in ((ROOT/"build/build-report.json","build-report.json"),
                        (ROOT/"build/tests/report.json","host-test-report.json")):
        shutil.copy2(source,RESULTS/name)
    status=json.loads((RESULTS/"STATUS.json").read_text(encoding="utf-8-sig"))
    # Physical observations and approvals are recorded by the physical phases.
    # An offline report refresh must never erase completed physical progress.
    status.update({"python_tests_passed":16,
                   "virtual_secure_boot_chain_tested":True,"virtual_cases_passed":len(latest),
                   "baseline_repeated":True,"active_staging":"build/release-20261025-v2"})
    (RESULTS/"STATUS.json").write_text(json.dumps(status,indent=2))
    release=ROOT/"build/release-20261025-v2"
    for name in ("USB-PROBE","USB-HANDOFF","USB-CAPTURE","USB-CANDIDATE"):
        old=ROOT/"build"/name
        if old.is_dir(): (old/"SUPERSEDED.txt").write_text("Use build/release-20261025-v2/"+name+" instead. Preparation only; approval required before physical use.\n")
    (ROOT/"build/LATEST-RELEASE.txt").write_text("release-20261025-v2\n")
    manifest={"hardware_validated":False,"unlock_enabled":False,"deployed":False,
              "files_sha256":{str(p.relative_to(release)).replace('\\','/'):digest(p)
                              for p in sorted(release.rglob("*")) if p.is_file() and p.name!="RELEASE-MANIFEST.json"}}
    (release/"RELEASE-MANIFEST.json").write_text(json.dumps(manifest,indent=2))
    # Source-only archive: no firmware tables, UEFI-variable exports, ROMs,
    # private keys, Microsoft loader, VM disks or downloaded dependencies.
    archive=ROOT/"build/M6501RM-source-20261025-v2.zip"
    paths=[ROOT/name for name in ("README.md","LICENSE","THIRD_PARTY_NOTICES.md",".gitignore")]
    for name in ("bench","config","docs","scripts","tests","tools","uefi"):
        paths.extend(p for p in (ROOT/name).rglob("*") if p.is_file() and p.suffix.lower() in
                     (".py",".ps1",".c",".h",".md",".txt",".json")
                     and "downloads" not in p.parts and "__pycache__" not in p.parts)
    for name in ("STATUS.json","vm-validation.json","baseline-2026-10-25.json","baseline-repeat-2026-10-25.json",
                 "baseline-repeat-comparison.json","build-report.json","host-test-report.json","staging-verification.json","python-tests-final.log"):
        paths.append(RESULTS/name)
    with zipfile.ZipFile(archive,"w",compression=zipfile.ZIP_DEFLATED) as out:
        for path in sorted(set(paths)): out.write(path,path.relative_to(ROOT).as_posix())
        upstream=ROOT/"vendor/rtx30-unlock"
        for path in sorted((upstream/"LICENSES").rglob("*")):
            if path.is_file(): out.write(path,"LICENSES/"+path.relative_to(upstream/"LICENSES").as_posix())
        out.write(upstream/"THIRD_PARTY_NOTICES.md","LICENSES/upstream-THIRD_PARTY_NOTICES.md")
    (archive.with_suffix(".zip.sha256")).write_text(digest(archive)+"  "+archive.name+"\n")
    print(json.dumps({"virtual_cases_passed":len(latest),"physical_hardware_validated":False,
                      "source_archive":str(archive),"archive_sha256":digest(archive)},indent=2))


if __name__=="__main__": main()
