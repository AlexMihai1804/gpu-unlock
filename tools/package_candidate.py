"""Archive candidate v3 source and local release manifests; no deployment.

Excludes ROMs, raw firmware tables/variables, downloaded code/tools, Windows
loader, NVIDIA binary assets, VM disks and private keys from the source ZIP.
"""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    ready=json.loads((ROOT/"results/unlock-candidate-v3-ready.json").read_text())
    if not ready["local_validation_passed"] or ready["deployed"] or ready["unlock_applied"]:
        raise ValueError("Expected a reviewed preparation-only candidate")
    release=ROOT/"build/release-20261025-v3"
    manifest=release/"RELEASE-MANIFEST.json"
    archive=ROOT/"build/M6501RM-source-20261025-v3.zip"
    if archive.exists() or manifest.exists():
        raise ValueError("Refusing to overwrite a finalized source/release archive")
    files={str(path.relative_to(release)).replace('\\','/'):digest(path)
           for path in sorted(release.rglob('*')) if path.is_file()}
    if any(name.lower().endswith('.rom') for name in files):
        raise ValueError("ROM unexpectedly packaged")
    manifest.write_text(json.dumps({"candidate":"M6501RM-v3","unlock_enabled_locally":True,
        "hardware_unlock_validated":False,"deployed":False,"physical_authorization":False,
        "candidate_file_sha256":ready["file_sha256"],"candidate_pe_authenticode_sha256":ready["pe_authenticode_sha256"],
        "files_sha256":files},indent=2),encoding="utf-8")
    source=[ROOT/name for name in ('README.md','LICENSE','THIRD_PARTY_NOTICES.md','.gitignore')]
    for folder in ('bench','config','docs','scripts','tests','tools','uefi'):
        source.extend(path for path in (ROOT/folder).rglob('*') if path.is_file() and
                      path.suffix.lower() in ('.py','.ps1','.c','.h','.md','.txt','.json') and
                      'downloads' not in path.parts and '__pycache__' not in path.parts)
    for name in ('STATUS.json','unlock-candidate-v3-ready.json','candidate-v3-staging-verification.json',
                 'candidate-v3-deployment-block-check.json','baseline-2026-10-25.json','capture-control-2026-10-25.json'):
        source.append(ROOT/'results'/name)
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as output:
        for path in sorted(set(source)):
            output.write(path,path.relative_to(ROOT).as_posix())
        upstream=ROOT/'vendor/rtx30-unlock'
        for path in sorted((upstream/'LICENSES').rglob('*')):
            if path.is_file(): output.write(path,'LICENSES/'+path.relative_to(upstream/'LICENSES').as_posix())
        output.write(upstream/'THIRD_PARTY_NOTICES.md','LICENSES/upstream-THIRD_PARTY_NOTICES.md')
    with zipfile.ZipFile(archive) as check:
        if check.testzip() is not None or any(name.lower().endswith(('.rom','.efi','.bin','.fd','.img','.pem','.key')) for name in check.namelist()):
            raise ValueError("Source archive verification failed")
    archive.with_suffix('.zip.sha256').write_text(digest(archive)+'  '+archive.name+'\n')
    result={"source_archive":str(archive),"archive_sha256":digest(archive),"archive_bytes":archive.stat().st_size,
            "release_manifest":str(manifest),"release_manifest_sha256":digest(manifest),
            "source_archive_excludes_rom_firmware_private_keys":True,"deployed":False,"unlock_applied":False}
    (ROOT/'results/candidate-v3-package.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
