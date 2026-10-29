param([Parameter(Mandatory=$true)][ValidateSet(0,150)][int]$Offset)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$principal=[Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Start-Process -FilePath (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe') -ArgumentList @('-NoProfile','-File',('"'+$PSCommandPath+'"'),'-Offset',([string]$Offset)) -Verb RunAs -WindowStyle Hidden | Out-Null
    return
}
Set-Location -LiteralPath $root
@'
import datetime,json,pathlib,sys
sys.path.insert(0,'bench')
from nvidia_metrics import Nvml
from efficiency import set_trial_offset
offset=int(sys.argv[1])
if offset not in (0,150):raise ValueError('Only zero or +150 MHz allowed')
meter=Nvml()
before=meter.offsets();memory=meter.offset(0,2)
try:
    set_trial_offset(meter,offset)
    after=meter.offsets();memory_after=meter.offset(0,2)
    if any(v['offset']!=offset for v in after.values()) or memory_after!=memory:
        raise RuntimeError('Graphics readback mismatch or memory offset changed')
    result=dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),completed=True,
        graphics_offset_mhz=offset,before=before,after=after,memory_before=memory,memory_after=memory_after,
        training_started=False,benchmark_started=False,persistent_startup_profile=False)
    pathlib.Path('results/latest-session-graphics-offset.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print('Graphics offset applied and verified:',offset,'MHz')
except BaseException:
    original=set(v['offset'] for v in before.values())
    if len(original)==1 and next(iter(original)) in (0,150):
        set_trial_offset(meter,next(iter(original)))
    raise
finally:
    meter.close()
'@ | & (Join-Path $root '.venv\Scripts\python.exe') -X utf8 - $Offset
if ($LASTEXITCODE -ne 0) { throw 'Graphics offset operation failed' }
