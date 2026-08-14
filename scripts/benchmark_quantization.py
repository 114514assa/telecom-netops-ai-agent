"""Benchmark local Hugging Face report generation across precision/quantization modes.

Examples:
    python scripts/benchmark_quantization.py --model Qwen/Qwen2.5-0.5B-Instruct --modes fp16 int8 int4
    python scripts/benchmark_quantization.py --model Qwen/Qwen2.5-0.5B-Instruct --modes int4 --repeats 3

This script downloads/loads the selected public model only when explicitly run by the user.
Results are written to runtime/benchmarks as JSON and CSV for resume/project evidence.
"""

from __future__ import annotations

import argparse
import csv
import gc
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from app.llm.backends import LocalHFBackend


SAMPLE_REPORT = """# 终端网络故障辅助诊断报告

- 终端 IP：10.20.30.15
- 登记端口：GigabitEthernet0/0/15
- 目标 VLAN：160
- 接口状态：UP
- 目标 MAC：已学习
- MAC 学习 VLAN：120
- 诊断代码：VLAN_MISMATCH
- 结论：设备实时 VLAN 与资源登记不一致，建议人工核对资源台账及正式变更记录。
- 限制：仅允许整理已有证据，不得生成网络配置修改命令。
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark local LLM quantization modes")
    parser.add_argument("--model", required=True, help="Hugging Face causal-LM model id")
    parser.add_argument(
        "--modes",
        nargs="+",
        default=["fp16", "int8", "int4"],
        choices=["none", "fp16", "int8", "int4"],
    )
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--max-new-tokens", type=int, default=192)
    parser.add_argument("--output-dir", default="runtime/benchmarks")
    return parser.parse_args()


def release_backend(backend: LocalHFBackend) -> None:
    backend._model = None  # benchmark-only explicit release
    backend._tokenizer = None
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass


def run_mode(args: argparse.Namespace, mode: str) -> dict:
    backend = LocalHFBackend(
        model_id=args.model,
        quantization=mode,
        max_new_tokens=args.max_new_tokens,
        temperature=0.0,
    )
    rows = []
    error = None
    try:
        for repeat in range(args.repeats):
            result = backend.generate(SAMPLE_REPORT)
            rows.append(
                {
                    "repeat": repeat + 1,
                    "latency_ms": result.latency_ms,
                    "output_tokens": result.output_tokens,
                    "tokens_per_second": result.tokens_per_second,
                    "memory_footprint_mb": result.memory_footprint_mb,
                    "peak_gpu_memory_mb": result.peak_gpu_memory_mb,
                    "load_seconds": result.extra.get("load_seconds"),
                }
            )
    except Exception as exc:  # noqa: BLE001 - benchmark should record unsupported modes
        error = f"{type(exc).__name__}: {exc}"
    finally:
        release_backend(backend)

    valid_latency = [r["latency_ms"] for r in rows if r["latency_ms"] is not None]
    valid_tps = [r["tokens_per_second"] for r in rows if r["tokens_per_second"] is not None]
    valid_memory = [r["memory_footprint_mb"] for r in rows if r["memory_footprint_mb"] is not None]
    valid_peak = [r["peak_gpu_memory_mb"] for r in rows if r["peak_gpu_memory_mb"] is not None]
    return {
        "model": args.model,
        "mode": mode,
        "repeats": args.repeats,
        "status": "ok" if rows and not error else "error",
        "error": error,
        "mean_latency_ms": round(statistics.mean(valid_latency), 2) if valid_latency else None,
        "mean_tokens_per_second": round(statistics.mean(valid_tps), 3) if valid_tps else None,
        "memory_footprint_mb": round(max(valid_memory), 2) if valid_memory else None,
        "peak_gpu_memory_mb": round(max(valid_peak), 2) if valid_peak else None,
        "runs": rows,
    }


def main() -> None:
    args = parse_args()
    if args.repeats < 1:
        raise SystemExit("--repeats must be >= 1")

    results = [run_mode(args, mode) for mode in args.modes]
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stem = f"quantization_{stamp}"

    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model": args.model,
        "max_new_tokens": args.max_new_tokens,
        "note": "Benchmark values are environment-specific and must not be reported as universal performance claims.",
        "results": results,
    }
    json_path = output_dir / f"{stem}.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    csv_path = output_dir / f"{stem}.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "model",
                "mode",
                "status",
                "mean_latency_ms",
                "mean_tokens_per_second",
                "memory_footprint_mb",
                "peak_gpu_memory_mb",
                "error",
            ],
        )
        writer.writeheader()
        for item in results:
            writer.writerow({key: item.get(key) for key in writer.fieldnames})

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"\nSaved: {json_path}")
    print(f"Saved: {csv_path}")


if __name__ == "__main__":
    started = time.perf_counter()
    main()
    print(f"Total benchmark wall time: {time.perf_counter() - started:.2f}s")
