"""Validate +150 MHz with GEMM and real training, then retain it for this session.

The established independent watchdog restores zero on interrupted validation.
After successful tests it verifies zero, exits, and an explicit final commit
sets the user-requested +150 MHz. No startup profile or other device setters.
"""
import argparse
import ctypes as ct
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import traceback

from compare import compare
from efficiency import restore_original, restored, set_trial_offset, watchdog
from endurance import ROOT, ac_power, check_health, read_health, save, utc
from nvidia_metrics import Nvml
from performance_state import classify

TORCH_PYTHON = Path(os.environ.get('GPU_UNLOCK_TORCH_PYTHON', sys.executable))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-directory',type=Path,required=True)
    parser.add_argument('--watchdog-parent',type=int)
    args=parser.parse_args()
    out=args.output_directory.resolve()
    if not out.is_relative_to(ROOT/'results') or not out.is_dir():parser.error('Project results directory required')
    if args.watchdog_parent is not None:
        watchdog(out,args.watchdog_parent,1800);return 0
    if not ct.windll.shell32.IsUserAnAdmin():parser.error('Native UAC elevation required')
    if (out/'activation-summary.json').exists():parser.error('Use a new directory')
    state=dict(utc=utc(),completed=False,status='initializing',requested_offset_mhz=150,
        persistent_startup_profile=False,no_voltage_power_memory_boot_writes=True,stages=[])
    save(out/'activation-summary.json',state)
    meter=watcher=None;original=None;armed=False
    stop=threading.Event();failures=[];worker=None

    def health():
        data=read_health(state['utc']);save(out/'health-latest.json',data);check_health(data['events'])

    def guard():
        (out/'heartbeat').touch()
        if failures:raise RuntimeError('; '.join(failures))
        if watcher is not None and watcher.poll() is not None:raise RuntimeError('Restoration watchdog exited early')
        if ac_power()!=1 or (out/'STOP').exists():raise RuntimeError('AC disconnected or STOP requested')

    def monitor():
        last_health=0.
        def report_error(event):
            event['utc']=utc()
            with (out/'telemetry-errors.jsonl').open('a',encoding='utf-8') as log:
                log.write(json.dumps(event)+'\n')
        try:
            with (out/'controller-telemetry.jsonl').open('x',encoding='utf-8') as log:
                while not stop.is_set():
                    (out/'heartbeat').touch()
                    sample=meter.sample_with_retry(report_error, delay_seconds=.5);sample['utc']=utc()
                    log.write(json.dumps(sample)+'\n');log.flush()
                    if ac_power()!=1:raise RuntimeError('AC disconnected')
                    if time.monotonic()-last_health>25:
                        health();last_health=time.monotonic()
                    stop.wait(.5)
        except BaseException as error:failures.append(str(error))

    def child(label,command):
        guard()
        entry=dict(label=label,started_utc=utc(),command=[str(x) for x in command])
        state['stages'].append(entry);save(out/'activation-summary.json',state)
        with (out/(label+'-console.log')).open('w',encoding='utf-8') as log:
            process=subprocess.Popen([str(x) for x in command],stdout=log,stderr=subprocess.STDOUT,
                cwd=ROOT,creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                while process.poll() is None:
                    guard();time.sleep(.5)
            except BaseException:
                (out/'training/STOP').parent.mkdir(exist_ok=True)
                (out/'training/STOP').touch()
                try:process.wait(timeout=15)
                except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=15)
                raise
        entry.update(finished_utc=utc(),exit_code=process.returncode)
        save(out/'activation-summary.json',state)
        if process.returncode:raise RuntimeError(label+' failed; see console log')
        guard();health()

    def verify_gemm(filename):
        data=json.loads((out/filename).read_text())
        rows=compare(before,data)
        if not all(row['output_bit_identical'] for row in rows):raise RuntimeError('Full GEMM output differs from reference')
        diagnosis=classify(data);save(out/(filename+'.performance-state.json'),diagnosis)
        if not diagnosis.get('tf32_unlocked_performance_supported'):raise RuntimeError('Full FP16/BF16/TF32 unlock not corroborated')
        return rows

    try:
        meter=Nvml();original=meter.inventory();save(out/'inventory-before.json',original)
        if any(v['offset']!=0 for v in original['graphics_offsets'].values()) or original['memory_offset']['offset']!=0:
            raise RuntimeError('Initial graphics and memory offsets must be zero')
        before=json.loads((out/'before.json').read_text())
        diagnosis=classify(before);save(out/'performance-state-before.json',diagnosis)
        if not diagnosis.get('tf32_unlocked_performance_supported'):raise RuntimeError('Fresh zero-offset control does not establish full unlock')
        guard()
        watcher=subprocess.Popen([sys.executable,'-X','utf8',str(Path(__file__).resolve()),
            '--output-directory',str(out),'--watchdog-parent',str(os.getpid())],creationflags=subprocess.CREATE_NO_WINDOW)
        for _ in range(100):
            if (out/'watchdog-ready.json').exists():break
            if watcher.poll() is not None:raise RuntimeError('Watchdog initialization failed')
            time.sleep(.1)
        else:raise RuntimeError('Watchdog initialization timeout')
        worker=threading.Thread(target=monitor,daemon=True);worker.start()
        if not ct.windll.kernel32.SetThreadExecutionState(ct.c_uint(0x80000003)):raise RuntimeError('Cannot inhibit idle sleep')
        armed=True;set_trial_offset(meter,150)
        save(out/'inventory-at150.json',meter.inventory())
        state.update(status='testing',offset_applied_utc=utc());save(out/'activation-summary.json',state)
        child('gemm-at150',[sys.executable,'-X','utf8',ROOT/'bench/gemm.py','--output',out/'at150.json','--label','Temporary +150 MHz current unlock validation'])
        state['gemm_at150_comparison']=verify_gemm('at150.json')
        training=out/'training';training.mkdir()
        child('training-at150',[TORCH_PYTHON,'-X','utf8',ROOT/'bench/train_existing_cifar100.py',
            '--output-directory',training,'--expected-offset','150','--train-examples','4096','--validation-examples','2048'])
        train=json.loads((training/'training-summary.json').read_text())
        if not train['completed'] or not train.get('final_offsets_match_expected') or len(train['runs'])!=3:
            raise RuntimeError('Three-mode training validation incomplete')
        if not all(r['examples']==4096 and r['all_parameters_finite'] and r['classifier_weight_change_l2']>0 and r['validation']['examples']==2048 for r in train['runs']):
            raise RuntimeError('Training counts, numerical checks or weight update failed')
        state['training_passed']=True
        child('gemm-after-training',[sys.executable,'-X','utf8',ROOT/'bench/gemm.py','--output',out/'after-training.json','--label','Full unlock +150 MHz after real three-mode training'])
        state['gemm_after_training_comparison']=verify_gemm('after-training.json')
        guard();health()
        restore_original(meter,original['graphics_offsets'])
        if not restored(meter,original['graphics_offsets']):raise RuntimeError('Zero readback before commit failed')
        state['zero_restored_before_commit_verified']=True
        (out/'watchdog-done').touch();watcher.wait(timeout=10)
        if watcher.returncode or not json.loads((out/'watchdog-result.json').read_text())['verified']:
            raise RuntimeError('Watchdog verification failed')
        watcher=None
        if failures:raise RuntimeError('; '.join(failures))
        # The tests passed. Leave only the explicitly requested session offset.
        set_trial_offset(meter,150)
        final=meter.inventory();save(out/'inventory-final.json',final)
        if any(v['offset']!=150 for v in final['graphics_offsets'].values()) or final['memory_offset']!=original['memory_offset']:
            raise RuntimeError('Final requested offset readback failed')
        state.update(status='passed',completed=True,final_graphics_offset_mhz=150,
            final_memory_offset_mhz=0,final_commit_utc=utc())
    except BaseException as error:
        state.update(status='stopped',completed=False,error=str(error),traceback=traceback.format_exc())
        if meter is not None and original is not None:
            try:
                if armed:restore_original(meter,original['graphics_offsets'])
                state['restored_zero_after_failure']=restored(meter,original['graphics_offsets'])
                save(out/'inventory-final.json',meter.inventory())
            except BaseException as restore_error:state['restoration_error']=str(restore_error)
        if watcher is not None and state.get('restored_zero_after_failure'):
            (out/'watchdog-done').touch()
            try:watcher.wait(timeout=10)
            except BaseException as wait_error:state['watchdog_error']=str(wait_error)
    finally:
        stop.set()
        if worker is not None:worker.join(timeout=25)
        if meter is not None:meter.close()
        ct.windll.kernel32.SetThreadExecutionState(ct.c_uint(0x80000000))
        state['finished_utc']=utc()
        save(out/'activation-summary.json',state)
    return 0 if state['completed'] else 1


if __name__=='__main__':raise SystemExit(main())
