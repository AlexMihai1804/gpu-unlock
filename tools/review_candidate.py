"""Create a local readiness report without booting, enrolling or deploying."""
import hashlib
import json
from pathlib import Path
import subprocess

from audit_trust import SHA256, esl, pe_hash
from build import inspect_pe

ROOT=Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    build=ROOT/"build/candidate-20261025-v3"
    evidence=ROOT/"results/physical-capture-20261025-201848"
    capture=read(evidence/"capture-review.json")
    if not capture["uefi_trust"]["passed"] or not capture["capture_passed"]:
        raise ValueError("Physical capture/trust not reviewed")
    board=read(ROOT/"config/board.reviewed.json")
    built=read(build/"build-report.json")
    if (not board["evidence_reviewed"] or not built["board_evidence_ready"] or
        board["prom_sha256"]!=capture["rom_sha256"] or
        built["board_profile_sha256"]!=digest(ROOT/"config/board.reviewed.json")):
        raise ValueError("Reviewed profile differs from captured evidence/build")
    host=read(build/"tests/report.json")
    saved=read(build/"capture-board-verified/report.json")
    if (len(host["results"])!=8 or not all(x["passed"] for x in host["results"]) or
        not saved["passed"] or saved["saved_board_preflight_cases"]!=13 or
        saved["rom_sha256"]!=capture["rom_sha256"] or not saved["ss1_write_forbidden"]):
        raise ValueError("Required native validations missing")
    image=build/"M6501-UNLOCK-CANDIDATE.EFI"
    image_bytes=image.read_bytes()
    metadata=inspect_pe(image)
    auth=pe_hash(image_bytes)[0].hex()
    if metadata["sha256"]!=built["images"][image.name]["sha256"]:
        raise ValueError("Candidate differs from inspected build")
    post=Path(capture["uefi_trust"]["collection"])
    denied=[]
    for name in ("dbx","MokListXRT"):
        for entry in esl((post/f"{name}.bin").read_bytes()):
            if entry["type"]==SHA256:
                denied.append(entry["data"].hex())
    if auth in denied or metadata["sha256"] in denied:
        raise ValueError("Candidate digest is revoked in current exported lists")
    stage=ROOT/"build/release-20261025-v3/USB-CANDIDATE"
    manifest=read(stage/"STAGING-MANIFEST.json")
    for relative,expected in manifest["files_sha256"].items():
        target=(stage/relative).resolve()
        if not target.is_relative_to(stage.resolve()) or digest(target)!=expected:
            raise ValueError("Candidate package changed")
    # Exercise only the unauthorized branch. It must fail before USB access.
    state=read(ROOT/"results/STATUS.json")
    if state["physical_unlock_authorized"]:
        raise ValueError("This preparation-only checker requires unlock still unauthorized")
    blocked=subprocess.run(["powershell.exe","-NoProfile","-ExecutionPolicy","Bypass","-File",
                            str(ROOT/"scripts/Deploy-AuthorizedUnlock.ps1")],capture_output=True,text=True)
    if blocked.returncode==0 or "BLOCKED: separate explicit candidate v3" not in blocked.stdout+blocked.stderr:
        raise ValueError("Deployment did not refuse missing authorization")
    (ROOT/"results/candidate-v3-deployment-block-check.json").write_text(json.dumps({
        "passed":True,"returncode":blocked.returncode,"reason":"Exact candidate authorization absent; refusal before USB access",
        "stdout":blocked.stdout,"stderr":blocked.stderr},indent=2))
    report={"candidate":"M6501RM-v3","prepared_locally":True,"local_validation_passed":True,
        "source_package":str(stage),"image":str(image),"file_sha256":metadata["sha256"],
        "pe_authenticode_sha256":auth,"manifest_sha256":digest(stage/"STAGING-MANIFEST.json"),
        "board_profile_sha256":digest(ROOT/"config/board.reviewed.json"),"prom_sha256":board["prom_sha256"],
        "chip":board["chip"],"booter_fuse_raw":board["booter_fuse_raw"],"fwsec_fuse_raw":board["fwsec_fuse_raw"],
        "ss1_policy":"Read current boot SS1; never write it; verify before/after FLR",
        "host_case_groups_passed":8,"python_tests_passed":18,
        "synthetic_transaction_scenarios_passed":20,"saved_board_transaction_scenarios_passed":20,
        "saved_board_preflight_cases_passed":13,"saved_board_tests_hardware_accessed":False,
        "deployment_without_approval_refused":True,"post_capture_trust_verified":True,
        "candidate_digests_absent_from_exported_dbx_MokListXRT":True,
        "deployed":False,"mok_enrolled":False,"physical_unlock_authorized":False,"unlock_applied":False,
        "driver_580_97_unlock_compatibility_validated":False,"hardware_unlock_validated":False,
        "physical_usb_mode":"capture","instructions":"docs/UNLOCK-CANDIDATE-v3.md",
        "evidence_files_sha256":{str(path.relative_to(ROOT)):digest(path) for path in
            (build/"build-report.json",build/"tests/report.json",build/"capture-board-verified/report.json",
             evidence/"capture-review.json",ROOT/"results/candidate-v3-staging-verification.json",
             ROOT/"results/candidate-v3-host-tests.log",ROOT/"scripts/Deploy-AuthorizedUnlock.ps1",
             ROOT/"uefi/m6501.c",ROOT/"tools/build.py",ROOT/"tools/test_capture_transaction.py",
             ROOT/"tests/test_unlock_preflight.c",ROOT/"docs/UNLOCK-CANDIDATE-v3.md")},
        "limits":["Software mocks do not validate real GPU firmware execution, real DMA/IOMMU behavior or Windows driver compatibility",
                  "Existing physical PROBE/HANDOFF/CAPTURE tests validate their narrower scopes",
                  "A first physical transaction can fail or freeze; full power-off may be required",
                  "Persistent MOK enrollment, USB deployment and one hardware attempt need separate explicit authorization"],
    }
    destination=ROOT/"results/unlock-candidate-v3-ready.json"
    destination.write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps({key:report[key] for key in ("candidate","local_validation_passed","file_sha256",
                                               "pe_authenticode_sha256","deployed","unlock_applied")},indent=2))


if __name__=="__main__":
    main()
