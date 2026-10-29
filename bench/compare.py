"""Compare matched GEMM runs; never infers the hardware unlock state."""
import argparse
import json
from pathlib import Path


def compare(a, b):
    keys = ("n", "samples", "iterations", "warmup", "device")
    for key in keys:
        if a["configuration"][key] != b["configuration"][key]:
            raise ValueError("Different benchmark configuration: "+key)
    for key in ("packages", "environment", "cublas_version", "math_mode", "gpu"):
        if a[key] != b[key]:
            raise ValueError("Different benchmark environment/GPU: "+key)
    ar, br = {r["mode"]: r for r in a["results"]}, {r["mode"]: r for r in b["results"]}
    if set(ar) != {"fp16", "bf16", "tf32", "fp32"} or set(br) != set(ar):
        raise ValueError("All four benchmark modes required")
    rows = []
    for name in ar:
        x, y = ar[name], br[name]
        if not x["correctness_passed"] or not y["correctness_passed"]:
            raise ValueError("Numerical validation failed: "+name)
        if x["input_sha256"] != y["input_sha256"]:
            raise ValueError("Input matrices differ: "+name)
        rows.append({"mode": name, "before_tflops": x["tflops"], "after_tflops": y["tflops"],
                     "gain_percent": (y["tflops"]/x["tflops"]-1)*100,
                     "output_bit_identical": x["output_sha256"] == y["output_sha256"]})
    return rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("before", type=Path)
    p.add_argument("after", type=Path)
    a = p.parse_args()
    rows = compare(json.loads(a.before.read_text()),json.loads(a.after.read_text()))
    print("| Mode | Before TFLOPS | After TFLOPS | Change | Bit-identical full output |")
    print("|---|---:|---:|---:|---|")
    for r in rows:
        print(f"| {r['mode'].upper()} | {r['before_tflops']:.3f} | {r['after_tflops']:.3f} | {r['gain_percent']:+.2f}% | {r['output_bit_identical']} |")
    print("Interpret alongside UEFI logs, temperatures/power/clocks, driver events and repeated boot pairs.")


if __name__ == "__main__":
    main()
