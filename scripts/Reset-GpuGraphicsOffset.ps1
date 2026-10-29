# Explicit user-invoked reset to zero. Does not change memory/voltage/power/boot.
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$principal=[Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Start-Process -FilePath (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe') -ArgumentList @('-NoProfile','-File',('"'+$PSCommandPath+'"')) -Verb RunAs -WindowStyle Hidden | Out-Null
    return
}
Set-Location -LiteralPath $root
@'
import json,pathlib,sys
sys.path.insert(0,'bench')
from nvidia_metrics import Nvml
from efficiency import set_trial_offset
from endurance import utc,save
meter=Nvml()
try:
    before=meter.inventory()
    set_trial_offset(meter,0)
    after=meter.inventory()
    if any(v['offset']!=0 for v in after['graphics_offsets'].values()) or before['memory_offset']!=after['memory_offset']:
        raise RuntimeError('Reset readback failed or memory offset changed')
    result=dict(utc=utc(),completed=True,graphics_offset_mhz=0,memory_unchanged=True,before=before,after=after)
    save(pathlib.Path('results/latest-gpu-graphics-reset.json'),result)
    print('Graphics offset reset to zero; memory unchanged.')
finally:
    meter.close()
'@ | & (Join-Path $root '.venv\Scripts\python.exe') -X utf8 -
if ($LASTEXITCODE -ne 0) { throw 'GPU graphics offset reset failed; see output.' }
