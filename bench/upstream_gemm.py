"""Reproduce the GEMM timing protocol reported in Zagitta/gpu-unlock #53.

8192-square, FP32 accumulation, 20 s warmup per mode, five samples of twenty
GEMMs, two full runs. Uses the installed PyTorch, not the report's Linux stack.
No training, device setters, firmware actions or power-limit changes.
"""
import argparse
import ctypes as ct
import hashlib
import json
import math
from pathlib import Path
import statistics
import threading
import time
import traceback

import numpy as np
import torch

from endurance import ROOT, ac_power, check_health, read_health, save, utc
from gemm import smi
from nvidia_metrics import Nvml

N, WARMUP, SAMPLES, ITERATIONS, RUNS = 8192, 20, 5, 20, 2
MODES = ('fp16', 'bf16', 'tf32', 'fp32')


@torch.inference_mode()
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-directory',type=Path,required=True)
    args=parser.parse_args()
    out=args.output_directory.resolve()
    if not out.is_relative_to(ROOT/'results') or not out.is_dir():parser.error('Existing project results directory required')
    if (out/'summary.json').exists():parser.error('Use a fresh directory')
    state=dict(utc=utc(),completed=False,status='initializing',training_performed=False,
        device_settings_changed=False,source='https://github.com/Zagitta/gpu-unlock/issues/53',
        upstream_reporting='https://github.com/Zagitta/gpu-unlock/blob/7eb51bccae0a0b7e599e084d971170e9a1e82d0c/.github/ISSUE_TEMPLATE/unlock-failure.yml',
        protocol=dict(n=N,warmup_seconds_per_mode=WARMUP,samples=SAMPLES,iterations=ITERATIONS,
            full_runs=RUNS,modes=list(MODES),accumulation='FP32',output='FP32',timing='CUDA events'),
        environment_difference='Report: Linux torch 2.14.1+cu130; this run uses existing Windows torch 2.8.0+cu126',
        output_dtype_note='Upstream report specifies accumulation, not output dtype; FP32 output is explicit here',
        temperature_cutoff=None,rows=[])
    save(out/'summary.json',state)
    meter=None;worker=None;stop=threading.Event();failures=[];telemetry=[];events={}
    phase=['initialization']

    def guard():
        if failures:raise RuntimeError('; '.join(failures))
        if ac_power()!=1 or (out/'STOP').exists():raise RuntimeError('AC disconnected or STOP requested')

    def monitor():
        last_health=0.
        def report_error(event):
            event.update(utc=utc(),phase=phase[0])
            with (out/'telemetry-errors.jsonl').open('a',encoding='utf-8') as log:log.write(json.dumps(event)+'\n')
        try:
            with (out/'telemetry.jsonl').open('x',encoding='utf-8') as log:
                while not stop.is_set():
                    row=meter.sample_with_retry(report_error,delay_seconds=.5)
                    row.update(utc=utc(),phase=phase[0]);telemetry.append(row)
                    log.write(json.dumps(row)+'\n');log.flush()
                    if time.monotonic()-last_health>25:
                        health=read_health(state['utc']);save(out/'health-latest.json',health)
                        for event in health['events']:events[str(event.get('record_id',event['utc']))]=event
                        check_health(health['events']);last_health=time.monotonic()
                    if ac_power()!=1:raise RuntimeError('AC disconnected')
                    stop.wait(.5)
        except BaseException as error:failures.append(str(error))

    try:
        meter=Nvml()
        initial_graphics=meter.offsets();initial_memory=meter.offset(0,2)
        save(out/'offsets-before.json',dict(graphics=initial_graphics,memory=initial_memory))
        if any(row['offset']!=150 for row in initial_graphics.values()) or initial_memory['offset']!=0:
            raise RuntimeError('Expected the user-requested +150 MHz graphics and zero memory offset')
        worker=threading.Thread(target=monitor,daemon=True);worker.start()
        if not ct.windll.kernel32.SetThreadExecutionState(ct.c_uint(0x80000003)):
            raise RuntimeError('Cannot inhibit idle sleep')
        torch.set_num_threads(4)
        torch.cuda.set_device(0)
        if torch.cuda.get_device_capability(0)!=(8,6):raise RuntimeError('Expected Ampere GPU')
        torch.backends.cuda.matmul.allow_fp16_reduced_precision_reduction=False
        torch.backends.cuda.matmul.allow_bf16_reduced_precision_reduction=False
        torch.backends.cuda.matmul.allow_fp16_accumulation=False
        state.update(torch=torch.__version__,cuda_runtime=torch.version.cuda,device=torch.cuda.get_device_name(0),
            gpu=smi('index,name,pci.bus_id,pci.device_id,driver_version,vbios_version,memory.total'),
            flags=dict(allow_fp16_reduced_precision_reduction=False,
                       allow_bf16_reduced_precision_reduction=False,allow_fp16_accumulation=False),
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),status='running')
        save(out/'summary.json',state)
        for run in range(1,RUNS+1):
            for mode in MODES:
                guard();phase[0]=f'run-{run}-{mode}'
                dtype={'fp16':torch.float16,'bf16':torch.bfloat16,'tf32':torch.float32,'fp32':torch.float32}[mode]
                torch.backends.cuda.matmul.allow_tf32=mode=='tf32'
                rng=torch.Generator(device='cuda').manual_seed(3060)
                a=(torch.randn(N,N,device='cuda',dtype=torch.float32,generator=rng)/math.sqrt(N)).to(dtype)
                b=(torch.randn(N,N,device='cuda',dtype=torch.float32,generator=rng)/math.sqrt(N)).to(dtype)
                c=torch.empty((N,N),device='cuda',dtype=torch.float32)
                def multiply():
                    if mode in ('fp16','bf16'):
                        torch.mm(a,b,out_dtype=torch.float32,out=c)
                    else:torch.mm(a,b,out=c)
                print(f'RUN {run}/2 {mode.upper()}: warmup 20 s',flush=True)
                torch.cuda.synchronize();deadline=time.perf_counter()+WARMUP;warmup_gemms=0
                while time.perf_counter()<deadline:
                    guard();multiply();torch.cuda.synchronize();warmup_gemms+=1
                timings=[]
                start,end=[torch.cuda.Event(enable_timing=True) for _ in range(2)]
                for _ in range(SAMPLES):
                    guard();start.record()
                    for _ in range(ITERATIONS):multiply()
                    end.record();end.synchronize()
                    timings.append(start.elapsed_time(end)/ITERATIONS)
                if any(not math.isfinite(x) or x<=0 for x in timings):raise RuntimeError('Invalid CUDA timing')
                rows=torch.linspace(0,N-1,32,device='cuda',dtype=torch.long)
                cols=torch.linspace(0,N-1,64,device='cuda',dtype=torch.long)
                reference=a.index_select(0,rows).double().cpu().numpy() @ b.index_select(1,cols).double().cpu().numpy()
                observed=c.index_select(0,rows).index_select(1,cols).double().cpu().numpy()
                relative=float(np.linalg.norm(observed-reference)/np.linalg.norm(reference))
                finite=bool(torch.isfinite(c).all().item())
                output_hash=hashlib.sha256(c.cpu().numpy().tobytes()).hexdigest()
                input_hashes=[hashlib.sha256(x.cpu().view(torch.uint8).numpy().tobytes()).hexdigest() for x in (a,b)]
                median=statistics.median(timings)
                active=[s for s in telemetry if s['phase']==phase[0] and s['utilization_percent']>=90]
                row=dict(run=run,mode=mode,median_ms=median,tflops=2*N**3/(median*1e9),sample_ms=timings,
                    input_dtype=str(dtype),output_dtype='torch.float32',warmup_gemms=warmup_gemms,
                    measured_gemms=SAMPLES*ITERATIONS,full_output_finite=finite,
                    reference='2048 CPU FP64 values from actual quantized inputs',sample_relative_l2=relative,
                    correctness_passed=finite and relative<(0.003 if mode=='tf32' else .0001),
                    input_sha256=input_hashes,output_sha256=output_hash,
                    active_samples=len(active),median_active_power_w=statistics.median(s['power_w'] for s in active) if active else None,
                    median_active_sm_mhz=statistics.median(s['sm_clock_mhz'] for s in active) if active else None,
                    maximum_temperature_c=max((s['temperature_c'] for s in telemetry if s['phase']==phase[0]),default=None))
                state['rows'].append(row);save(out/'summary.json',state);save(out/'progress.json',row)
                print(json.dumps(row),flush=True)
                if not row['correctness_passed']:raise RuntimeError('GEMM numerical validation failed')
                if run==2:
                    previous=next(r for r in state['rows'] if r['run']==1 and r['mode']==mode)
                    if previous['input_sha256']!=input_hashes or previous['output_sha256']!=output_hash:
                        raise RuntimeError('Two-run full-output reproducibility failed')
                del a,b,c,reference,observed,rows,cols
                torch.cuda.empty_cache()
        guard()
        health=read_health(state['utc']);save(out/'health-at-completion.json',health);check_health(health['events'])
        state.update(completed=True,status='passed')
    except BaseException as error:
        state.update(completed=False,status='stopped',error=str(error),traceback=traceback.format_exc())
        print('STOPPED '+str(error),flush=True)
    finally:
        stop.set()
        if worker is not None:worker.join(timeout=25)
        if meter is not None:
            final_graphics=meter.offsets();final_memory=meter.offset(0,2)
            save(out/'offsets-after.json',dict(graphics=final_graphics,memory=final_memory))
            state['offsets_preserved']=final_graphics==initial_graphics and final_memory==initial_memory
            meter.close()
        ct.windll.kernel32.SetThreadExecutionState(ct.c_uint(0x80000000))
        state.update(finished_utc=utc(),maximum_temperature_c=max((s['temperature_c'] for s in telemetry),default=None),
                     hardware_events=list(events.values()))
        save(out/'summary.json',state)
    return 0 if state['completed'] else 1


if __name__=='__main__':raise SystemExit(main())
