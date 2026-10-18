from __future__ import annotations

import argparse
import csv
import gc
import json
import statistics
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from app.llm.backends import LocalHFBackend
from app.llm.langchain_report_chain import LangChainReportAssistant
from app.llm.report_guardrails import validate_auxiliary_output


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def resolve_output_dir(value: str) -> Path:
    """Resolve relative output paths against the repository root and create them."""
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path = path.resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json_atomic(path: Path, payload: object) -> None:
    """Write JSON safely; recreate the parent in case it was removed mid-run."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


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


def seed_everything(seed: int) -> None:
    try:
        import random
        random.seed(seed)
    except Exception:
        pass
    try:
        import numpy as np
        np.random.seed(seed)
    except ImportError:
        pass
    try:
        import torch
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    except ImportError:
        pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="50-case quantization quality evaluation for the Telecom NetOps Agent"
    )
    parser.add_argument("--model", default="Qwen/Qwen2.5-0.5B-Instruct")
    parser.add_argument(
        "--modes",
        nargs="+",
        default=["fp16", "int8", "int4"],
        choices=["none", "fp16", "int8", "int4"],
    )
    parser.add_argument("--cases", default="data/evaluation/quantization_cases_50.json")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--case-ids", nargs="+", default=None)
    parser.add_argument("--max-new-tokens", type=int, default=96)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", default="runtime/quant_eval_50")
    parser.add_argument("--baseline-mode", default="fp16", choices=["none", "fp16", "int8", "int4"])
    return parser.parse_args()


def _rate(rows: list[dict], key: str) -> float | None:
    if not rows:
        return None
    return round(statistics.mean(int(bool(row[key])) for row in rows), 4)


def _mean(rows: list[dict], key: str, ndigits: int = 3) -> float | None:
    vals = [row[key] for row in rows if row.get(key) is not None]
    return round(statistics.mean(vals), ndigits) if vals else None


def score_case(case: dict, raw_output: str, max_new_tokens: int, output_tokens: int | None) -> dict:
    """Score only what the current project actually delegates to the LLM.

    The application LLM does not decide the diagnosis and does not receive raw RAG chunks.
    It receives only the already-confirmed conclusion and read-only recommendation, then emits
    one guarded auxiliary sentence. Diagnostic-direction preservation is scored with explicit
    diagnosis-aware rules, not generic keyword relevance, so reversals such as
    'VLAN 不一致' -> 'VLAN 一致' are counted as failures.
    """
    guard = validate_auxiliary_output(case["input_report"], raw_output)
    truncated = bool(output_tokens is not None and output_tokens >= max_new_tokens)
    diagnostic_direction_preserved = bool(guard.direction_supported and guard.contradiction_free)
    safety_compliant = bool(guard.identifier_free and guard.unsafe_free and guard.diagnosis_code_free)
    report_complete = bool(guard.format_ok and guard.length_ok and guard.complete_sentence and guard.text_quality_ok)
    return {
        "accepted_for_application": bool(guard.passed),
        "diagnostic_direction_preserved": diagnostic_direction_preserved,
        "safety_compliant": safety_compliant,
        "report_complete": report_complete,
        "semantic_relevance": bool(guard.semantic_relevant),
        "direction_supported": bool(guard.direction_supported),
        "direction_contradicted": bool(guard.direction_contradicted),
        "contradiction_free": bool(guard.contradiction_free),
        "text_quality_ok": bool(guard.text_quality_ok),
        "identifier_free": bool(guard.identifier_free),
        "unsafe_free": bool(guard.unsafe_free),
        "diagnosis_code_free": bool(guard.diagnosis_code_free),
        "format_ok": bool(guard.format_ok),
        "length_ok": bool(guard.length_ok),
        "complete_sentence": bool(guard.complete_sentence),
        "ignored_extra_lines": int(guard.ignored_extra_lines),
        "truncated": truncated,
        "guardrail_reasons": list(guard.reasons),
        "candidate_text": guard.candidate_text,
        "auxiliary_text": guard.auxiliary_text,
    }


def summarize_mode(mode: str, rows: list[dict], mode_error: str | None = None) -> dict:
    generated = [r for r in rows if r.get("status") in {"ok", "empty"} and "accepted_for_application" in r]
    ok_rows = [r for r in rows if r.get("status") == "ok"]
    reasons: Counter[str] = Counter()
    for row in generated:
        reasons.update(row.get("guardrail_reasons") or [])
    # Application acceptance is measured over all requested cases: generation errors/empty
    # outputs necessarily fall back to the deterministic report and therefore count as not accepted.
    acceptance = round(
        sum(int(bool(r.get("accepted_for_application", False))) for r in rows) / len(rows), 4
    ) if rows else None
    generation_success = round(len(ok_rows) / len(rows), 4) if rows else None
    return {
        "mode": mode,
        "status": "ok" if ok_rows and mode_error is None else "error",
        "error": mode_error,
        "cases_requested": len(rows),
        "successful_generations": len(ok_rows),
        "generation_success_rate": generation_success,
        "application_acceptance_rate": acceptance,
        "fallback_rate": round(1.0 - acceptance, 4) if acceptance is not None else None,
        "diagnostic_direction_preservation_rate": _rate(generated, "diagnostic_direction_preserved"),
        "safety_compliance_rate": _rate(generated, "safety_compliant"),
        "report_completeness_rate": _rate(generated, "report_complete"),
        "semantic_relevance_rate": _rate(generated, "semantic_relevance"),
        "direction_support_rate": _rate(generated, "direction_supported"),
        "direction_contradiction_rate": _rate(generated, "direction_contradicted"),
        "contradiction_free_rate": _rate(generated, "contradiction_free"),
        "text_quality_pass_rate": _rate(generated, "text_quality_ok"),
        "identifier_free_rate": _rate(generated, "identifier_free"),
        "unsafe_free_rate": _rate(generated, "unsafe_free"),
        "diagnosis_code_free_rate": _rate(generated, "diagnosis_code_free"),
        "truncation_rate": _rate(generated, "truncated"),
        "mean_latency_ms": _mean(ok_rows, "latency_ms", 2),
        "mean_tokens_per_second": _mean(ok_rows, "tokens_per_second", 3),
        "mean_output_tokens": _mean(ok_rows, "output_tokens", 2),
        "rejection_reasons": json.dumps(dict(reasons), ensure_ascii=False, sort_keys=True),
    }


def run_mode(model: str, mode: str, cases: list[dict], max_new_tokens: int, seed: int) -> tuple[list[dict], dict]:
    print(f"\n[{mode}] loading model...", flush=True)
    seed_everything(seed)
    backend: LocalHFBackend | None = None
    rows: list[dict] = []
    mode_error: str | None = None
    try:
        backend = LocalHFBackend(
            model_id=model,
            quantization=mode,
            max_new_tokens=max_new_tokens,
            temperature=0.0,
        )
        backend._load()
        print(f"[{mode}] model loaded in {backend._load_seconds:.2f}s", flush=True)
        assistant = LangChainReportAssistant(backend)
        for idx, case in enumerate(cases, 1):
            print(f"[{mode}] {idx}/{len(cases)} {case['case_id']} ...", flush=True)
            try:
                started = time.perf_counter()
                result = assistant.generate(case["input_report"])
                wall = time.perf_counter() - started
                raw_output = result.text or ""
                score = score_case(case, raw_output, max_new_tokens, result.output_tokens)
                row = {
                    "case_id": case["case_id"],
                    "scenario_family": case.get("scenario_family", "unknown"),
                    "diagnosis_code": case.get("diagnosis_code", "unknown"),
                    "variant": case.get("variant"),
                    "variant_type": case.get("variant_type", "unknown"),
                    "mode": mode,
                    "status": "ok" if raw_output else "empty",
                    "error": None,
                    "latency_ms": result.latency_ms,
                    "tokens_per_second": result.tokens_per_second,
                    "output_tokens": result.output_tokens,
                    "memory_footprint_mb": result.memory_footprint_mb,
                    "peak_gpu_memory_mb": result.peak_gpu_memory_mb,
                    "load_seconds": result.extra.get("load_seconds"),
                    "wall_seconds": round(wall, 3),
                    **score,
                    "input_report": case["input_report"],
                    "raw_output": raw_output,
                }
                rows.append(row)
                reason_text = ",".join(score["guardrail_reasons"]) or "-"
                print(
                    f"[{mode}] done | {wall:.2f}s | accepted={score['accepted_for_application']} "
                    f"| direction={score['diagnostic_direction_preserved']} | reasons={reason_text}",
                    flush=True,
                )
            except Exception as exc:  # keep the other cases/modes auditable
                err = f"{type(exc).__name__}: {exc}"
                print(f"[{mode}] case error: {err}", flush=True)
                rows.append({
                    "case_id": case["case_id"],
                    "scenario_family": case.get("scenario_family", "unknown"),
                    "diagnosis_code": case.get("diagnosis_code", "unknown"),
                    "variant": case.get("variant"),
                    "variant_type": case.get("variant_type", "unknown"),
                    "mode": mode,
                    "status": "error",
                    "error": err,
                    "input_report": case["input_report"],
                    "raw_output": "",
                })
    except Exception as exc:
        mode_error = f"{type(exc).__name__}: {exc}"
        print(f"[{mode}] MODE ERROR: {mode_error}", flush=True)
        for case in cases:
            rows.append({
                "case_id": case["case_id"],
                "scenario_family": case.get("scenario_family", "unknown"),
                "diagnosis_code": case.get("diagnosis_code", "unknown"),
                "variant": case.get("variant"),
                "variant_type": case.get("variant_type", "unknown"),
                "mode": mode,
                "status": "error",
                "error": mode_error,
                "input_report": case["input_report"],
                "raw_output": "",
            })
    finally:
        release_backend(backend)
    return rows, summarize_mode(mode, rows, mode_error)


def grouped_summaries(all_rows: list[dict], group_key: str) -> list[dict]:
    buckets: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in all_rows:
        if row.get("status") == "ok":
            buckets[(row["mode"], str(row.get(group_key, "unknown")))].append(row)
    out = []
    for (mode, group), rows in sorted(buckets.items()):
        out.append({
            "mode": mode,
            group_key: group,
            "cases": len(rows),
            "application_acceptance_rate": _rate(rows, "accepted_for_application"),
            "diagnostic_direction_preservation_rate": _rate(rows, "diagnostic_direction_preserved"),
            "direction_support_rate": _rate(rows, "direction_supported"),
            "text_quality_pass_rate": _rate(rows, "text_quality_ok"),
            "safety_compliance_rate": _rate(rows, "safety_compliant"),
            "report_completeness_rate": _rate(rows, "report_complete"),
        })
    return out


def compare_to_baseline(summaries: list[dict], baseline_mode: str) -> list[dict]:
    by_mode = {row["mode"]: row for row in summaries}
    base = by_mode.get(baseline_mode)
    if not base or base.get("status") != "ok":
        return []
    metrics = [
        "application_acceptance_rate",
        "diagnostic_direction_preservation_rate",
        "safety_compliance_rate",
        "report_completeness_rate",
    ]
    out = []
    for mode, row in by_mode.items():
        if row.get("status") != "ok":
            continue
        item = {"baseline_mode": baseline_mode, "mode": mode}
        for metric in metrics:
            b = base.get(metric)
            v = row.get(metric)
            item[metric] = v
            item[f"{metric}_gap_pp"] = round((v - b) * 100, 2) if b is not None and v is not None else None
        out.append(item)
    return out


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                key: json.dumps(row.get(key), ensure_ascii=False) if isinstance(row.get(key), (dict, list)) else row.get(key)
                for key in fields
            })


def main() -> None:
    args = parse_args()
    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    if args.case_ids:
        wanted = set(args.case_ids)
        cases = [case for case in cases if case.get("case_id") in wanted]
        missing = sorted(wanted - {case.get("case_id") for case in cases})
        if missing:
            raise SystemExit(f"Unknown --case-ids: {missing}")
    if args.limit is not None:
        if args.limit < 1:
            raise SystemExit("--limit must be >= 1")
        cases = cases[: args.limit]
    if not cases:
        raise SystemExit("No evaluation cases found")

    output_dir = resolve_output_dir(args.output_dir)
    print(f"Output directory: {output_dir}", flush=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    all_rows: list[dict] = []
    summaries: list[dict] = []
    for mode in args.modes:
        rows, summary = run_mode(args.model, mode, cases, args.max_new_tokens, args.seed)
        all_rows.extend(rows)
        summaries.append(summary)
        # Per-mode checkpoint so an interrupted later mode does not erase completed results.
        write_json_atomic(
            output_dir / f"quant_quality50_partial_{stamp}_{mode}.json",
            {"summary": summary, "rows": rows},
        )

    family = grouped_summaries(all_rows, "scenario_family")
    variants = grouped_summaries(all_rows, "variant_type")
    comparisons = compare_to_baseline(summaries, args.baseline_mode)

    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "evaluator_version": "quant-quality-50-v3-direction-aware",
        "model": args.model,
        "modes": args.modes,
        "seed": args.seed,
        "max_new_tokens": args.max_new_tokens,
        "case_count": len(cases),
        "important_note": (
            "The current project LLM only writes a guarded auxiliary sentence from already-confirmed diagnosis fields. "
            "It does not decide the diagnosis and does not directly consume RAG chunks. Diagnostic-direction preservation "
            "uses diagnosis-specific expected/opposite semantic rules plus contradiction checks; it is a constrained "
            "generation-preservation metric, not a free-form diagnosis accuracy metric."
        ),
        "summary": summaries,
        "comparison_to_baseline": comparisons,
        "family_summary": family,
        "variant_summary": variants,
        "rows": all_rows,
    }
    json_path = output_dir / f"quant_quality50_{stamp}.json"
    write_json_atomic(json_path, payload)

    write_csv(output_dir / f"quant_quality50_summary_{stamp}.csv", summaries)
    write_csv(output_dir / f"quant_quality50_vs_{args.baseline_mode}_{stamp}.csv", comparisons)
    write_csv(output_dir / f"quant_quality50_family_{stamp}.csv", family)
    write_csv(output_dir / f"quant_quality50_variant_{stamp}.csv", variants)

    detail_fields = [
        "case_id", "scenario_family", "diagnosis_code", "variant", "variant_type", "mode", "status", "error",
        "accepted_for_application", "diagnostic_direction_preserved", "safety_compliant", "report_complete",
        "semantic_relevance", "direction_supported", "direction_contradicted", "contradiction_free", "text_quality_ok",
        "identifier_free", "unsafe_free", "diagnosis_code_free",
        "format_ok", "length_ok", "complete_sentence", "truncated", "latency_ms", "tokens_per_second",
        "output_tokens", "memory_footprint_mb", "peak_gpu_memory_mb", "load_seconds", "guardrail_reasons",
        "candidate_text", "auxiliary_text", "raw_output",
    ]
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / f"quant_quality50_detail_{stamp}.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=detail_fields)
        writer.writeheader()
        for row in all_rows:
            writer.writerow({
                key: json.dumps(row.get(key), ensure_ascii=False) if isinstance(row.get(key), (dict, list)) else row.get(key)
                for key in detail_fields
            })

    manual_fields = [
        "case_id", "scenario_family", "variant_type", "mode", "accepted_for_application",
        "manual_diagnosis_consistent", "manual_relevant", "manual_no_hallucination",
        "manual_action_boundary_ok", "manual_readable", "manual_notes", "candidate_text", "raw_output",
    ]
    with (output_dir / f"quant_quality50_manual_review_{stamp}.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=manual_fields)
        writer.writeheader()
        for row in all_rows:
            writer.writerow({
                "case_id": row.get("case_id"),
                "scenario_family": row.get("scenario_family"),
                "variant_type": row.get("variant_type"),
                "mode": row.get("mode"),
                "accepted_for_application": row.get("accepted_for_application"),
                "manual_diagnosis_consistent": "",
                "manual_relevant": "",
                "manual_no_hallucination": "",
                "manual_action_boundary_ok": "",
                "manual_readable": "",
                "manual_notes": "",
                "candidate_text": row.get("candidate_text"),
                "raw_output": row.get("raw_output"),
            })

    print("\n=== Quantization quality summary (50 cases) ===")
    print(json.dumps(summaries, ensure_ascii=False, indent=2))
    if comparisons:
        print(f"\n=== Comparison vs {args.baseline_mode} ===")
        print(json.dumps(comparisons, ensure_ascii=False, indent=2))
    print(f"\nSaved to: {output_dir.resolve()}")


if __name__ == "__main__":
    main()
