"""Identify cuBLAS kernels and compare TF32 math modes; no GPU/boot setters.

CUPTI driver launch callbacks observe kernel names, without performance counters,
injection into other processes, registry changes, or an administrator service.
Timings are instrumented diagnostics, not a replacement for unprofiled baselines.
"""
import argparse
from collections import Counter
import ctypes as ct
import datetime as dt
import hashlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import statistics
import threading
import time
import traceback

from endurance import ac_power
from gemm import Blas, smi
from nvidia_metrics import Nvml

ROOT = Path(__file__).resolve().parents[1]


class CallbackData(ct.Structure):
    # Exact CUpti_CallbackData ABI from the pinned 12.9.79 cupti_callbacks.h.
    _fields_ = [('callbackSite', ct.c_int), ('functionName', ct.c_char_p),
                ('functionParams', ct.c_void_p), ('functionReturnValue', ct.c_void_p),
                ('symbolName', ct.c_char_p), ('context', ct.c_void_p),
                ('contextUid', ct.c_uint32), ('correlationData', ct.c_void_p),
                ('correlationId', ct.c_uint32)]


class KernelTrace:
    def __init__(self, directory):
        self.phase = 'initialization'
        self.counts, self.errors = Counter(), []
        dll = directory / 'nvidia/cuda_cupti/bin/cupti64_2025.2.1.dll'
        self.dll_directory = os.add_dll_directory(str(dll.parent.resolve()))
        self.lib = ct.WinDLL(str(dll.resolve()))
        self.library = str(dll.resolve())
        self.sha256 = hashlib.sha256(dll.read_bytes()).hexdigest()
        callback_type = ct.CFUNCTYPE(None, ct.c_void_p, ct.c_uint32, ct.c_uint32, ct.c_void_p)

        def callback(userdata, domain, identifier, pointer):
            try:
                if domain != 1:
                    return
                data = ct.cast(pointer, ct.POINTER(CallbackData)).contents
                function = (data.functionName or b'').decode('utf-8', errors='replace')
                if data.callbackSite == 0 and 'Launch' in function:
                    symbol = (data.symbolName or b'').decode('utf-8', errors='replace')
                    self.counts[(self.phase, function, symbol)] += 1
            except BaseException as error:
                self.errors.append(repr(error))

        self.callback = callback_type(callback)  # Keep alive until unsubscribe.
        self.handle = ct.c_void_p()
        self.subscribe = self.bind('cuptiSubscribe',
            [ct.POINTER(ct.c_void_p), callback_type, ct.c_void_p])
        self.enable = self.bind('cuptiEnableDomain', [ct.c_uint32, ct.c_void_p, ct.c_uint32])
        self.unsubscribe = self.bind('cuptiUnsubscribe', [ct.c_void_p])
        self.check(self.subscribe(ct.byref(self.handle), self.callback, None), 'subscribe')
        try:
            self.check(self.enable(1, self.handle, 1), 'enable driver callbacks')
        except BaseException:
            self.unsubscribe(self.handle)
            self.handle = ct.c_void_p()
            raise

    def bind(self, name, args):
        fn = getattr(self.lib, name)
        fn.argtypes, fn.restype = args, ct.c_int
        return fn

    def check(self, status, operation):
        if status:
            message = ct.c_char_p()
            self.bind('cuptiGetResultString', [ct.c_int, ct.POINTER(ct.c_char_p)])(
                status, ct.byref(message))
            raise RuntimeError(f'CUPTI {operation}: {status}: {message.value!r}')

    def rows(self):
        return [dict(phase=phase, api=api, kernel=name, count=count)
                for (phase, api, name), count in sorted(self.counts.items())]

    def close(self):
        if self.handle:
            self.check(self.enable(0, self.handle, 1), 'disable driver callbacks')
            self.check(self.unsubscribe(self.handle), 'unsubscribe')
            self.handle = ct.c_void_p()
        self.dll_directory.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-directory', type=Path, required=True)
    p.add_argument('--cupti-directory', type=Path,
                   default=ROOT / 'tools/downloads/cupti-12.9.79')
    args = p.parse_args()
    out = args.output_directory.resolve()
    if not out.is_relative_to(ROOT / 'results') or out.exists():
        p.error('Choose a NEW directory below results/')
    if os.environ.get('NVIDIA_TF32_OVERRIDE') == '0':
        p.error('NVIDIA_TF32_OVERRIDE=0 disables TF32; preserve and investigate it first')
    if ac_power() != 1:
        p.error('AC power is required')
    out.mkdir()
    report = dict(schema=1, utc=dt.datetime.now(dt.timezone.utc).isoformat(),
        hardware_configuration_writes=False, firmware_executed=False,
        profiling='CUPTI driver API launch callbacks; no hardware counters',
        configuration=dict(n=8192, samples=3, iterations=5, warmup_seconds=1),
        environment={key: os.environ.get(key) for key in
            ('NVIDIA_TF32_OVERRIDE', 'CUDA_VISIBLE_DEVICES', 'CUBLAS_WORKSPACE_CONFIG')},
        packages={key: metadata.version(key) for key in
            ('numpy', 'nvidia-cublas-cu12', 'nvidia-cuda-runtime-cu12')},
        gpu=smi('index,name,pci.bus_id,pci.device_id,driver_version,vbios_version,memory.total'),
        results=[], telemetry=[], completed=False)
    trace = blas = meter = None
    stop, errors = threading.Event(), []
    worker = None
    code = 0
    try:
        meter = Nvml()
        report['offsets_before'] = meter.offsets()
        report['memory_offset_before'] = meter.offset(0, 2)
        if any(value['offset'] != 0 for value in report['offsets_before'].values()):
            raise RuntimeError('Diagnostic requires zero graphics offset; no offset will be changed')
        trace = KernelTrace(args.cupti_directory.resolve())
        report['cupti'] = dict(path=trace.library, sha256=trace.sha256,
            provenance=json.loads((args.cupti_directory / 'provenance.json').read_text()),
            callback_structure_bytes=ct.sizeof(CallbackData))
        blas = Blas(0)
        report['cublas_version'] = blas.cublas_version.value

        def monitor():
            while not stop.is_set():
                try:
                    report['telemetry'].append(dict(phase=trace.phase,
                        monotonic=time.monotonic(), ac_line_status=ac_power(), **meter.sample()))
                except BaseException as error:
                    errors.append(repr(error))
                    return
                stop.wait(0.2)

        worker = threading.Thread(target=monitor, daemon=True)
        worker.start()
        cases = [('fp16-control', 'fp16', 16), ('bf16-control', 'bf16', 16),
                 ('tf32-original', 'tf32', 16), ('tf32-default-math', 'tf32', 0),
                 ('tf32-tensor-math', 'tf32', 19), ('fp32-control', 'fp32', 16),
                 ('tf32-original-repeat', 'tf32', 16)]
        for label, mode, math_mode in cases:
            if errors or ac_power() != 1 or (out / 'STOP').exists():
                raise RuntimeError(f'Diagnostic interrupted: monitor={errors}')
            trace.phase = label
            blas.check(blas.math(blas.handle, math_mode), 'diagnostic cublasSetMathMode')
            row = blas.run(mode, 8192, 1, 3, 5)
            row.update(phase=label, cublas_math_mode=math_mode)
            row['kernels'] = [item for item in trace.rows() if item['phase'] == label]
            if not row['kernels'] or not all(item['kernel'] for item in row['kernels']):
                raise RuntimeError('Missing kernel names for ' + label)
            active = [item for item in report['telemetry']
                      if item['phase'] == label and item['utilization_percent'] >= 90]
            row['active_telemetry_samples'] = len(active)
            row['clock_normalization_scope'] = (
                'Coarse whole-phase samples include startup and warmup; '
                'not synchronized to timed CUDA windows and not an unlock classification')
            if active:
                row['median_sm_clock_mhz'] = statistics.median(item['sm_clock_mhz'] for item in active)
                row['tflops_per_ghz'] = row['tflops'] * 1000 / row['median_sm_clock_mhz']
                row['max_temperature_c'] = max(item['temperature_c'] for item in active)
            report['results'].append(row)
            (out / 'diagnostic.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
            print(f"{label}: {row['tflops']:.3f} TFLOPS; numerical={row['correctness_passed']}; "
                  f"kernels={', '.join(item['kernel'] for item in row['kernels'])}", flush=True)
            if not row['correctness_passed'] or trace.errors:
                raise RuntimeError(f'Numerical or tracing failure: {trace.errors}')
        tf32 = [row for row in report['results'] if row['mode'] == 'tf32']
        report['tf32_outputs_bit_identical_across_math_modes'] = (
            len({row['output_sha256'] for row in tf32}) == 1)
        report['completed'] = True
    except BaseException as error:
        report['error'], report['traceback'] = str(error), traceback.format_exc()
        print(report['traceback'], flush=True)
        code = 1
    finally:
        stop.set()
        if worker:
            worker.join(timeout=5)
        if trace:
            report['launches'], report['callback_errors'] = trace.rows(), trace.errors
        for label, action in [('blas', lambda: blas.destroy(blas.handle) if blas else None),
                              ('cupti', lambda: trace.close() if trace else None)]:
            try:
                action()
            except BaseException as error:
                report[label + '_cleanup_error'] = repr(error)
                code = 1
        if meter:
            try:
                report['offsets_after'] = meter.offsets()
                report['memory_offset_after'] = meter.offset(0, 2)
                report['offsets_unchanged'] = (
                    report.get('offsets_before') == report['offsets_after'] and
                    report.get('memory_offset_before') == report['memory_offset_after'])
                if not report['offsets_unchanged']:
                    code = 1
            finally:
                meter.close()
        report['monitor_errors'] = errors
        report['passed'] = report['completed'] and not errors and code == 0
        (out / 'diagnostic.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return code


if __name__ == '__main__':
    raise SystemExit(main())
