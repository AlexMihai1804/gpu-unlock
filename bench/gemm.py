"""Dense cuBLAS GEMM only. Never accesses PCI, firmware, clocks, or boot settings."""
import argparse
import ctypes as ct
import datetime as dt
import hashlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import threading
import time

import numpy as np


def smi(fields):
    p = subprocess.run(
        ["nvidia-smi", "--query-gpu=" + fields, "--format=csv,noheader,nounits"],
        capture_output=True, text=True, timeout=10,
    )
    return {"returncode": p.returncode, "stdout": p.stdout.strip(), "stderr": p.stderr.strip()}


class Blas:
    def __init__(self, device):
        if sys.platform != "win32":
            raise RuntimeError("This loader is for the pinned Windows NVIDIA wheels")
        self.dirs = []
        for package in ("nvidia-cublas-cu12", "nvidia-cuda-runtime-cu12", "nvidia-cuda-nvrtc-cu12"):
            dist = metadata.distribution(package)
            for item in dist.files or []:
                if str(item).lower().endswith(".dll"):
                    folder = str(Path(dist.locate_file(item)).parent)
                    self.dirs.append(os.add_dll_directory(folder))
        def library(package, filename):
            dist = metadata.distribution(package)
            match = [dist.locate_file(f) for f in dist.files or [] if Path(f).name == filename]
            if len(match) != 1:
                raise RuntimeError(f"Cannot uniquely find {filename}")
            return ct.WinDLL(str(match[0]))
        self.rt = library("nvidia-cuda-runtime-cu12", "cudart64_12.dll")
        self.cb = library("nvidia-cublas-cu12", "cublas64_12.dll")
        ptr, ip = ct.c_void_p, ct.POINTER(ct.c_int)
        def bind(lib, name, args):
            f = getattr(lib, name)
            f.argtypes, f.restype = args, ct.c_int
            return f
        self.set_device = bind(self.rt, "cudaSetDevice", [ct.c_int])
        self.malloc = bind(self.rt, "cudaMalloc", [ct.POINTER(ptr), ct.c_size_t])
        self.free = bind(self.rt, "cudaFree", [ptr])
        self.copy = bind(self.rt, "cudaMemcpy", [ptr, ptr, ct.c_size_t, ct.c_int])
        self.sync = bind(self.rt, "cudaDeviceSynchronize", [])
        self.event_create = bind(self.rt, "cudaEventCreate", [ct.POINTER(ptr)])
        self.event_record = bind(self.rt, "cudaEventRecord", [ptr, ptr])
        self.event_sync = bind(self.rt, "cudaEventSynchronize", [ptr])
        self.event_ms = bind(self.rt, "cudaEventElapsedTime", [ct.POINTER(ct.c_float), ptr, ptr])
        self.event_destroy = bind(self.rt, "cudaEventDestroy", [ptr])
        self.create = bind(self.cb, "cublasCreate_v2", [ct.POINTER(ptr)])
        self.destroy = bind(self.cb, "cublasDestroy_v2", [ptr])
        self.math = bind(self.cb, "cublasSetMathMode", [ptr, ct.c_int])
        self.gemm = bind(self.cb, "cublasGemmEx", [ptr] + [ct.c_int] * 5 +
                         [ptr, ptr, ct.c_int, ct.c_int, ptr, ct.c_int, ct.c_int,
                          ptr, ptr, ct.c_int, ct.c_int, ct.c_int, ct.c_int])
        self.version = bind(self.cb, "cublasGetVersion_v2", [ptr, ip])
        self.check(self.set_device(device), "cudaSetDevice")
        self.handle = ptr()
        self.check(self.create(ct.byref(self.handle)), "cublasCreate")
        # CUBLAS_DEFAULT_MATH | CUBLAS_MATH_DISALLOW_REDUCED_PRECISION_REDUCTION.
        self.check(self.math(self.handle, 16), "cublasSetMathMode")
        self.cublas_version = ct.c_int()
        self.check(self.version(self.handle, ct.byref(self.cublas_version)), "cublasGetVersion")

    @staticmethod
    def check(status, operation):
        if status:
            raise RuntimeError(f"{operation}: status {status}")

    def run(self, name, n, warmup, samples, iterations):
        rng = np.random.default_rng(3060)
        datatype, compute = {"fp16": (2, 68), "bf16": (14, 68),
                             "tf32": (0, 77), "fp32": (0, 69)}[name]
        def inputs():
            values = np.asfortranarray(rng.standard_normal((n, n), dtype=np.float32) / np.sqrt(np.float32(n)))
            if name == "fp16":
                storage = np.asfortranarray(values.astype(np.float16))
                quantized = np.asfortranarray(storage.astype(np.float32))
            elif name == "bf16":
                bits = values.view(np.uint32)
                rounded = bits + np.uint32(0x7fff) + ((bits >> 16) & 1)
                storage = np.asfortranarray((rounded >> 16).astype(np.uint16))
                quantized = np.asfortranarray((storage.astype(np.uint32) << 16).view(np.float32))
            else:
                storage, quantized = values, values
            return storage, quantized
        a, qa = inputs()
        b, qb = inputs()
        output = np.empty((n, n), dtype=np.float32, order="F")
        pointers, events = [], []
        try:
            for host in (a, b, output):
                p = ct.c_void_p()
                self.check(self.malloc(ct.byref(p), host.nbytes), "cudaMalloc")
                pointers.append(p)
            for p, host in zip(pointers[:2], (a, b)):
                self.check(self.copy(p, host.ctypes.data, host.nbytes, 1), "cudaMemcpy H2D")
            alpha, beta = ct.c_float(1), ct.c_float(0)
            def multiply():
                self.check(self.gemm(self.handle, 0, 0, n, n, n, ct.byref(alpha),
                           pointers[0], datatype, n, pointers[1], datatype, n,
                           ct.byref(beta), pointers[2], 0, n, compute, -1), "cublasGemmEx")
            for _ in range(2):
                e = ct.c_void_p()
                self.check(self.event_create(ct.byref(e)), "cudaEventCreate")
                events.append(e)
            deadline = time.perf_counter() + warmup
            while time.perf_counter() < deadline:
                multiply()
                self.check(self.sync(), "warmup synchronize")
            timings = []
            for _ in range(samples):
                self.check(self.event_record(events[0], None), "event start")
                for _ in range(iterations):
                    multiply()
                self.check(self.event_record(events[1], None), "event stop")
                self.check(self.event_sync(events[1]), "event synchronize")
                elapsed = ct.c_float()
                self.check(self.event_ms(ct.byref(elapsed), *events), "event elapsed")
                timings.append(elapsed.value / iterations)
            self.check(self.copy(output.ctypes.data, pointers[2], output.nbytes, 2), "cudaMemcpy D2H")
            rows = np.linspace(0, n - 1, 32, dtype=int)
            cols = np.linspace(0, n - 1, 64, dtype=int)
            reference = qa[rows, :].astype(np.float64) @ qb[:, cols].astype(np.float64)
            observed = output[np.ix_(rows, cols)].astype(np.float64)
            rel = float(np.linalg.norm(observed - reference) / np.linalg.norm(reference))
            finite = bool(np.isfinite(output).all())
            passed = finite and rel < (0.003 if name == "tf32" else 0.0001)
            median = statistics.median(timings)
            return {"mode": name, "n": n, "sample_ms": timings, "median_ms": median,
                    "tflops": 2 * n**3 / (median * 1e9), "output": "FP32",
                    "compute_type": compute, "input_cuda_type": datatype,
                    "finite_entire_output": finite, "sample_relative_l2": rel,
                    "sample_count": int(reference.size), "correctness_passed": passed,
                    "input_sha256": [hashlib.sha256(x.tobytes(order="F")).hexdigest() for x in (a, b)],
                    "output_sha256": hashlib.sha256(output.tobytes(order="F")).hexdigest()}
        finally:
            for e in events:
                self.event_destroy(e)
            for p in pointers:
                self.free(p)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=8192, choices=[1024, 4096, 8192])
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--warmup", type=float, default=4)
    parser.add_argument("--device", type=int, default=0)
    parser.add_argument("--label", default="baseline")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.samples < 1 or args.iterations < 1 or args.warmup < 0:
        parser.error("Invalid sample, iteration, or warmup count")
    if args.output.exists():
        parser.error("Output already exists; choose a new result file")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result = {"schema": 1, "label": args.label, "utc": dt.datetime.now(dt.timezone.utc).isoformat(),
              "unlock_performed_by_benchmark": False, "unlock_state": "unknown; established by boot log separately",
              "configuration": {**vars(args), "output": str(args.output)},
              "packages": {p: metadata.version(p) for p in
                           ("numpy", "nvidia-cublas-cu12", "nvidia-cuda-runtime-cu12", "nvidia-cuda-nvrtc-cu12")},
              "environment": {k: os.environ.get(k) for k in ("CUDA_VISIBLE_DEVICES", "NVIDIA_TF32_OVERRIDE", "CUBLAS_WORKSPACE_CONFIG")},
              "gpu": smi("index,name,pci.bus_id,pci.device_id,driver_version,vbios_version,memory.total"),
              "results": [], "telemetry": []}
    stop = threading.Event()
    phase = ["initialization"]
    def monitor():
        while not stop.is_set():
            row = {"utc": dt.datetime.now(dt.timezone.utc).isoformat(), "phase": phase[0],
                   **smi("index,temperature.gpu,power.draw,clocks.sm,clocks.mem,utilization.gpu,memory.used,pstate")}
            result["telemetry"].append(row)
            stop.wait(0.5)
    worker = threading.Thread(target=monitor, daemon=True)
    worker.start()
    blas = None
    code = 0
    try:
        blas = Blas(args.device)
        result["cublas_version"] = blas.cublas_version.value
        result["math_mode"] = "DEFAULT | DISALLOW_REDUCED_PRECISION_REDUCTION (16)"
        for mode in ("fp16", "bf16", "tf32", "fp32"):
            phase[0] = mode
            print(f"Running {mode} n={args.n}", flush=True)
            row = blas.run(mode, args.n, args.warmup, args.samples, args.iterations)
            result["results"].append(row)
            print(f"{mode}: {row['tflops']:.3f} TFLOPS; {row['median_ms']:.3f} ms; correctness={row['correctness_passed']}", flush=True)
            if not row["correctness_passed"]:
                raise RuntimeError(f"Numerical validation failed for {mode}")
    except Exception as error:
        result["error"] = str(error)
        code = 1
        print(f"ERROR: {error}", file=sys.stderr)
    finally:
        if blas is not None:
            blas.destroy(blas.handle)
        stop.set()
        worker.join(timeout=12)
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
