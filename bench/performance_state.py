"""Infer GEMM performance state from saved per-clock measurements, never from raw TFLOPS alone.

Coarse telemetry is corroborating evidence; this does not read GPU selectors.
"""
import json
from pathlib import Path
import statistics

from compare import compare

ROOT=Path(__file__).resolve().parents[1]


def active_modes(data):
    result={}
    for mode in ('fp16','bf16','tf32','fp32'):
        samples=[]
        for row in data.get('telemetry',[]):
            if row.get('phase')!=mode or row.get('returncode'):
                continue
            try:
                values=[float(value.strip()) for value in row['stdout'].split(',')[:7]]
            except (ValueError,KeyError):
                continue
            if len(values)==7 and values[5]>=90 and values[3]>0:
                samples.append(values)
        benchmark=next((row for row in data.get('results',[]) if row['mode']==mode),None)
        if benchmark is None or not samples:
            continue
        clock=statistics.median(row[3] for row in samples)
        result[mode]=dict(tflops=benchmark['tflops'],active_samples=len(samples),
            median_sm_mhz=clock,median_power_w=statistics.median(row[2] for row in samples),
            maximum_temperature_c=max(row[1] for row in samples),
            tflops_per_ghz=benchmark['tflops']/(clock/1000))
    return result


def classify(data):
    locked=json.loads((ROOT/'results/baseline-2026-10-25.json').read_text())
    unlocked=json.loads((ROOT/'results/unlock-v3-B2-2026-10-25.json').read_text())
    result=dict(method='matched-GEMM-with-coarse-SM-clock-normalization-v2',
        classification='inconclusive',unlocked_performance_supported=False,
        direct_selector_read=False,
        limits=['SM telemetry covers active phase samples including warmup, not exact CUDA event intervals',
                'Inference corroborates boot logs; it is not a direct register read or exact IPC measurement'])
    try:
        rows=compare(locked,data)
        if not all(row['output_bit_identical'] for row in rows):
            raise ValueError('Full outputs differ from baseline')
        current,normal,fast=[active_modes(value) for value in (data,locked,unlocked)]
        for mode in ('fp16','bf16','tf32','fp32'):
            if mode not in current or current[mode]['active_samples']<5:
                raise ValueError('At least five active SM-clock samples required per mode')
            current[mode]['normalized_vs_locked']=current[mode]['tflops_per_ghz']/normal[mode]['tflops_per_ghz']
            current[mode]['normalized_vs_unlocked']=current[mode]['tflops_per_ghz']/fast[mode]['tflops_per_ghz']
        fp32_control=0.80<=current['fp32']['normalized_vs_locked']<=1.20
        tf32_stock=0.80<=current['tf32']['normalized_vs_locked']<=1.20
        tf32_full=1.50<=current['tf32']['normalized_vs_locked']<=2.40
        controls=fp32_control and (tf32_stock or tf32_full)
        matches_fast=controls and all(0.75<=current[mode]['normalized_vs_unlocked']<=1.25 and
            current[mode]['normalized_vs_locked']>1.5 for mode in ('fp16','bf16'))
        matches_normal=fp32_control and tf32_stock and all(0.80<=current[mode]['normalized_vs_locked']<=1.20 and
            current[mode]['normalized_vs_unlocked']<0.75 for mode in ('fp16','bf16'))
        result.update(modes=current,controls_per_clock_consistent=controls,
            tf32_classification='consistent_with_full_rate' if tf32_full else 'consistent_with_stock_rate' if tf32_stock else 'inconclusive',
            tf32_unlocked_performance_supported=matches_fast and tf32_full,
            classification='consistent_with_unlocked' if matches_fast else 'consistent_with_locked' if matches_normal else 'inconclusive',
            unlocked_performance_supported=matches_fast,
            locked_reference='results/baseline-2026-10-25.json',unlocked_reference='results/unlock-v3-B2-2026-10-25.json')
    except (ValueError,KeyError,ZeroDivisionError) as error:
        result['reason']=str(error)
    return result
