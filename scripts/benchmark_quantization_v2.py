from __future__ import annotations

import argparse
import csv
import gc
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path

from app.llm.backends import LocalHFBackend
from app.llm.langchain_report_chain import LangChainReportAssistant


def release_backend(backend: LocalHFBackend | None) -> None:
    if backend is None:
        return
    backend._model = None
    backend._tokenizer = None
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    pos = (len(xs) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    if lo == hi:
        return xs[lo]
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Production-prompt quantization benchmark v2")
    p.add_argument("--model", default="Qwen/Qwen2.5-0.5B-Instruct")
    p.add_argument("--modes", nargs="+", default=["fp16", "int8", "int4"], choices=["none", "fp16", "int8", "int4"])
    p.add_argument("--cases", default="data/evaluation/quantization_cases_50.json")
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--warmup", type=int, default=1)
    p.add_argument("--max-new-tokens", type=int, default=96)
    p.add_argument("--output-dir", default="runtime/quant_benchmark_v2")
    p.add_argument("--baseline-mode", default="fp16", choices=["none", "fp16", "int8", "int4"])
    return p.parse_args()


def select_representative_cases(cases: list[dict]) -> list[dict]:
    """Select exactly one standard case from each scenario family (10 prompts)."""
    chosen: dict[str, dict] = {}
    for case in cases:
        fam = case.get("scenario_family", "unknown")
        if fam not in chosen or case.get("variant") == 1:
            chosen[fam] = case
    return list(chosen.values())


def run_mode(args: argparse.Namespace, mode: str, prompts: list[dict]) -> tuple[list[dict], dict]:
    backend: LocalHFBackend | None = None
    rows: list[dict] = []
    error: str | None = None
    try:
        print(f"\n[{mode}] loading model...", flush=True)
        backend = LocalHFBackend(
            model_id=args.model,
            quantization=mode,
            max_new_tokens=args.max_new_tokens,
            temperature=0.0,
        )
        backend._load()
        assistant = LangChainReportAssistant(backend)
        print(f"[{mode}] load_seconds={backend._load_seconds:.3f}", flush=True)

        for i in range(args.warmup):
            print(f"[{mode}] warmup {i+1}/{args.warmup}", flush=True)
            assistant.generate(prompts[0]["input_report"])

        for case in prompts:
            for repeat in range(1, args.repeats + 1):
                print(f"[{mode}] {case['case_id']} repeat {repeat}/{args.repeats}", flush=True)
                result = assistant.generate(case["input_report"])
                rows.append({
                    "mode": mode,
                    "case_id": case["case_id"],
                    "scenario_family": case.get("scenario_family"),
                    "repeat": repeat,
                    "latency_ms": result.latency_ms,
                    "tokens_per_second": result.tokens_per_second,
                    "input_tokens": result.input_tokens,
                    "output_tokens": result.output_tokens,
                    "memory_footprint_mb": result.memory_footprint_mb,
                    "peak_gpu_memory_mb": result.peak_gpu_memory_mb,
                })
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        print(f"[{mode}] ERROR: {error}", flush=True)
    finally:
        load_seconds = getattr(backend, "_load_seconds", None) if backend is not None else None
        release_backend(backend)

    lat = [float(r["latency_ms"]) for r in rows if r.get("latency_ms") is not None]
    tps = [float(r["tokens_per_second"]) for r in rows if r.get("tokens_per_second") is not None]
    mem = [float(r["memory_footprint_mb"]) for r in rows if r.get("memory_footprint_mb") is not None]
    peak = [float(r["peak_gpu_memory_mb"]) for r in rows if r.get("peak_gpu_memory_mb") is not None]
    outs = [float(r["output_tokens"]) for r in rows if r.get("output_tokens") is not None]
    summary = {
        "mode": mode,
        "status": "ok" if rows and error is None else "error",
        "error": error,
        "prompts": len(prompts),
        "repeats": args.repeats,
        "formal_runs": len(rows),
        "load_seconds": round(load_seconds, 3) if load_seconds is not None else None,
        "mean_latency_ms": round(statistics.mean(lat), 2) if lat else None,
        "median_latency_ms": round(statistics.median(lat), 2) if lat else None,
        "p95_latency_ms": round(percentile(lat, 0.95), 2) if lat else None,
        "mean_tokens_per_second": round(statistics.mean(tps), 3) if tps else None,
        "median_tokens_per_second": round(statistics.median(tps), 3) if tps else None,
        "memory_footprint_mb": round(max(mem), 2) if mem else None,
        "peak_gpu_memory_mb": round(max(peak), 2) if peak else None,
        "mean_output_tokens": round(statistics.mean(outs), 2) if outs else None,
    }
    return rows, summary


def pct_reduction(baseline: float | None, value: float | None) -> float | None:
    if baseline is None or value is None or baseline == 0:
        return None
    return round((baseline - value) / baseline * 100, 2)


def pct_change(baseline: float | None, value: float | None) -> float | None:
    if baseline is None or value is None or baseline == 0:
        return None
    return round((value - baseline) / baseline * 100, 2)


def build_comparison(summaries: list[dict], baseline_mode: str) -> list[dict]:
    by = {x["mode"]: x for x in summaries}
    base = by.get(baseline_mode)
    if not base or base.get("status") != "ok":
        return []
    out = []
    for mode, row in by.items():
        if row.get("status") != "ok":
            continue
        out.append({
            "baseline_mode": baseline_mode,
            "mode": mode,
            "peak_vram_reduction_pct": pct_reduction(base.get("peak_gpu_memory_mb"), row.get("peak_gpu_memory_mb")),
            "model_memory_reduction_pct": pct_reduction(base.get("memory_footprint_mb"), row.get("memory_footprint_mb")),
            "mean_latency_change_pct": pct_change(base.get("mean_latency_ms"), row.get("mean_latency_ms")),
            "mean_tokens_per_second_change_pct": pct_change(base.get("mean_tokens_per_second"), row.get("mean_tokens_per_second")),
        })
    return out


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    fields = list(rows[0].keys())
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader(); w.writerows(rows)


def main() -> None:
    args = parse_args()
    if args.repeats < 1 or args.warmup < 0:
        raise SystemExit("--repeats must be >=1 and --warmup must be >=0")
    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    prompts = select_representative_cases(cases)
    if len(prompts) != 10:
        raise SystemExit(f"Expected 10 scenario families, got {len(prompts)}")

    all_rows: list[dict] = []
    summaries: list[dict] = []
    for mode in args.modes:
        rows, summary = run_mode(args, mode, prompts)
        all_rows.extend(rows); summaries.append(summary)

    comparison = build_comparison(summaries, args.baseline_mode)
    out = Path(args.output_dir); out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "benchmark_version": "quant-benchmark-v2-production-prompt",
        "model": args.model,
        "max_new_tokens": args.max_new_tokens,
        "warmup": args.warmup,
        "repeats": args.repeats,
        "prompt_count": len(prompts),
        "note": "Values are machine-specific. Benchmark uses the same LangChainReportAssistant prompt path as the application.",
        "summary": summaries,
        "comparison_to_baseline": comparison,
        "rows": all_rows,
    }
    (out/f"quant_benchmark_v2_{stamp}.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    write_csv(out/f"quant_benchmark_v2_summary_{stamp}.csv", summaries)
    write_csv(out/f"quant_benchmark_v2_vs_{args.baseline_mode}_{stamp}.csv", comparison)
    write_csv(out/f"quant_benchmark_v2_detail_{stamp}.csv", all_rows)

    print("\n=== Benchmark summary ===")
    print(json.dumps(summaries, ensure_ascii=False, indent=2))
    if comparison:
        print(f"\n=== Comparison vs {args.baseline_mode} ===")
        print(json.dumps(comparison, ensure_ascii=False, indent=2))
    print(f"\nSaved to: {out.resolve()}")


if __name__ == "__main__":
    main()
