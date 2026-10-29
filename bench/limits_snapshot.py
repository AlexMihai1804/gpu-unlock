"""Append read-only NVIDIA limiter/power snapshots to an existing benchmark directory."""
import datetime as dt
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]


def snapshot(directory):
    out=directory.resolve()
    if not out.is_relative_to(ROOT/'results') or not (out/'launch.json').exists():
        raise ValueError('Existing project benchmark directory required')
    process=subprocess.run(['nvidia-smi','-q','-x'],capture_output=True,text=True,timeout=10)
    if process.returncode:
        raise RuntimeError(process.stderr)
    gpu=ET.fromstring(process.stdout).find('gpu')
    if gpu is None:
        raise ValueError('Missing GPU in NVIDIA response')
    result={'utc':dt.datetime.now(dt.timezone.utc).isoformat(),'pci_bus_id':gpu.findtext('pci/pci_bus_id')}
    for name in ('clocks_event_reasons','clocks_event_reasons_counters','temperature','gpu_power_readings','clocks'):
        element=gpu.find(name)
        result[name]={child.tag:(child.text or '').strip() for child in element if len(child)==0} if element is not None else {}
    with (out/'limits-snapshots.jsonl').open('a',encoding='utf-8') as log:
        log.write(json.dumps(result)+'\n')
    return result


if __name__=='__main__':
    print(json.dumps(snapshot(Path(sys.argv[1])),indent=2))
