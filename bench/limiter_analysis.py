"""Summarize observed NVIDIA limiter flags; sample fractions are not exact GPU-time fractions."""
import json
from datetime import datetime
from pathlib import Path
import statistics


def read_lines(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


def analyze(directory):
    rows=read_lines(directory/'endurance/telemetry.jsonl')
    active=[row for row in rows if row.get('utilization_percent',0)>=90]
    bits={'sw_power_cap':0x4,'hw_slowdown':0x8,'sw_thermal_slowdown':0x20,
          'hw_thermal_slowdown':0x40,'hw_power_brake':0x80,'applications_clocks':0x2,
          'sync_boost':0x10,'display_clocks':0x100}
    counts={name:sum(bool(int(row['clocks_event_reasons'],16)&mask) for row in active) for name,mask in bits.items()}
    snapshots=read_lines(directory/'limits-snapshots.jsonl')
    summary_path=directory/'endurance/summary.json'
    summary=json.loads(summary_path.read_text()) if summary_path.exists() else {}
    caps=[]
    for snapshot in snapshots:
        if snapshot.get('clocks_event_reasons',{}).get('clocks_event_reason_gpu_idle')=='Active':
            continue
        if summary.get('load_started_utc') and snapshot.get('utc') and datetime.fromisoformat(snapshot['utc'])<datetime.fromisoformat(summary['load_started_utc']):
            continue
        if summary.get('finished_utc') and snapshot.get('utc') and datetime.fromisoformat(snapshot['utc'])>datetime.fromisoformat(summary['finished_utc']):
            continue
        value=snapshot.get('gpu_power_readings',{}).get('current_power_limit','N/A')
        try:caps.append(float(value.split()[0]))
        except (ValueError,IndexError):pass
    return dict(scope='Observed active telemetry samples, utilization >=90%; not exact CUDA-event duty attribution',
        active_samples=len(active),limiter_sample_counts=counts,
        limiter_sample_percent={name:100*value/len(active) if active else None for name,value in counts.items()},
        maximum_temperature_c=max((row['temperature_c'] for row in rows),default=None),
        median_active_power_w=statistics.median(row['power_w'] for row in active) if active else None,
        observed_current_power_limit_w=dict(min=min(caps),median=statistics.median(caps),max=max(caps)) if caps else None,
        snapshot_count=len(snapshots),active_load_cap_snapshots=len(caps),
        source='https://docs.nvidia.com/deploy/archive/R535/nvml-api/group__nvmlClocksEventReasons.html')
