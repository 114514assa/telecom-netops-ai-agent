"""Evaluate constrained report-assistant quality for local quantization modes.

This V2 evaluator mirrors production behavior: the model is only allowed to return
three constrained lines, while deterministic diagnosis remains the source of truth.

Examples:
  python -m scripts.evaluate_quantization_quality --model Qwen/Qwen2.5-0.5B-Instruct --modes fp16 int4 --limit 3
  python -m scripts.evaluate_quantization_quality --model Qwen/Qwen2.5-0.5B-Instruct --modes fp16 int4
"""
from __future__ import annotations

import argparse
import csv
import gc
import json
import re
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from app.llm.backends import LocalHFBackend
from app.llm.report_guardrails import (
    build_auxiliary_request,
    normalize_text,
    validate_auxiliary_output,
)


def release_backend(backend: LocalHFBackend) -> None:
    backend._model = None
    backend._tokenizer = None
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate quantized local-LLM constrained report quality V2")
    parser.add_argument("--model", required=True)
    parser.add_argument("--modes", nargs="+", default=["fp16", "int4"], choices=["none", "fp16", "int8", "int4"])
    parser.add_argument("--cases", default="data/evaluation/quality_cases.json")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--max-new-tokens", type=int, default=128)
    parser.add_argument("--output-dir", default="runtime/quality_eval_v2")
    return parser.parse_args()


def _fact_hit(fact: str, output: str) -> bool:
    fact = fact.strip()
    out_norm = normalize_text(output)

    vlan = re.fullmatch(r"(?i)VLAN\s+(\d+)", fact)
    if vlan:
        return bool(re.search(rf"(?i)vlan[^0-9\r\n]{{0,12}}{re.escape(vlan.group(1))}\b", output))

    port = re.fullmatch(r"(?i)(?:GE|GigabitEthernet)\s*(\d+/\d+/\d+)", fact)
    if port:
        return bool(re.search(rf"(?i)(?:GE|GigabitEthernet)\s*{re.escape(port.group(1))}\b", output))

    mac_compact = re.sub(r"[^0-9a-f]", "", fact.lower())
    if len(mac_compact) == 12 and re.search(r"[a-f]", mac_compact):
        output_compact = re.sub(r"[^0-9a-f]", "", output.lower())
        return mac_compact in output_compact

    return normalize_text(fact) in out_norm


def score_case(case: dict, raw_output: str, max_new_tokens: int, output_tokens: int | None) -> dict:
    source = case["input_report"]
    guard = validate_auxiliary_output(source, raw_output)

    # Facts are still measured for observability, but V2 does not require every source
    # fact to be repeated in the short auxiliary note.
    fact_hits = [(fact, _fact_hit(fact, raw_output)) for fact in case.get("expected_facts", [])]
    fact_retention = (
        sum(int(hit) for _, hit in fact_hits) / len(fact_hits) if fact_hits else 1.0
    )

    truncated = bool(output_tokens is not None and output_tokens >= max_new_tokens)
    accepted = bool(guard.passed and not truncated)
    return {
        "guardrail_passed": guard.passed,
        "accepted_for_application": accepted,
        "diagnosis_code_retained": guard.diagnosis_code_ok,
        "conclusion_retained": guard.conclusion_ok,
        "format_valid": guard.format_ok,
        "unexpected_identifier_count": sum(len(v) for v in guard.unexpected_identifiers.values()),
        "unsafe_instruction": bool(guard.unsafe_patterns),
        "truncated": truncated,
        "observed_fact_retention_rate": round(fact_retention, 4),
        "missing_observed_facts": [fact for fact, hit in fact_hits if not hit],
        "guardrail_reasons": guard.reasons,
        "unexpected_identifiers": guard.unexpected_identifiers,
        "auxiliary_text": guard.auxiliary_text,
    }


def run_mode(model: str, mode: str, cases: list[dict], max_new_tokens: int) -> tuple[list[dict], dict]:
    print(f"\n[{mode}] loading model...", flush=True)
    backend = LocalHFBackend(
        model_id=model,
        quantization=mode,
        max_new_tokens=max_new_tokens,
        temperature=0.0,
    )
    rows: list[dict] = []
    try:
        # Load once so model loading does not look like a hung first case.
        load_started = time.perf_counter()
        backend._load()
        print(f"[{mode}] model loaded in {time.perf_counter() - load_started:.2f}s", flush=True)

        for idx, case in enumerate(cases, start=1):
            print(f"[{mode}] {idx}/{len(cases)} {case['case_id']} ...", flush=True)
            request = build_auxiliary_request(case["input_report"])
            started = time.perf_counter()
            result = backend.generate(request)
            wall = time.perf_counter() - started
            raw_output = result.text or ""
            scores = score_case(case, raw_output, max_new_tokens, result.output_tokens)
            print(
                f"[{mode}] {idx}/{len(cases)} done | {wall:.2f}s | "
                f"tokens={result.output_tokens} | accepted={scores['accepted_for_application']}",
                flush=True,
            )
            rows.append(
                {
                    "case_id": case["case_id"],
                    "mode": mode,
                    "status": "ok" if raw_output else "empty",
                    "latency_ms": result.latency_ms,
                    "tokens_per_second": result.tokens_per_second,
                    "output_tokens": result.output_tokens,
                    **scores,
                    "input_report": case["input_report"],
                    "raw_output": raw_output,
                }
            )
    finally:
        release_backend(backend)

    valid = [row for row in rows if row["status"] == "ok"]
    mean = lambda values: round(statistics.mean(values), 4) if values else None
    summary = {
        "mode": mode,
        "cases": len(rows),
        "successful_cases": len(valid),
        "application_acceptance_rate": mean([int(r["accepted_for_application"]) for r in valid]),
        "diagnosis_code_retention_rate": mean([int(r["diagnosis_code_retained"]) for r in valid]),
        "conclusion_retention_rate": mean([int(r["conclusion_retained"]) for r in valid]),
        "format_valid_rate": mean([int(r["format_valid"]) for r in valid]),
        "unexpected_identifier_case_rate": mean([int(r["unexpected_identifier_count"] > 0) for r in valid]),
        "unsafe_instruction_case_rate": mean([int(r["unsafe_instruction"]) for r in valid]),
        "truncation_rate": mean([int(r["truncated"]) for r in valid]),
        "mean_observed_fact_retention_rate": mean([r["observed_fact_retention_rate"] for r in valid]),
        "mean_latency_ms": round(statistics.mean(r["latency_ms"] for r in valid if r["latency_ms"] is not None), 2) if valid else None,
        "mean_tokens_per_second": round(statistics.mean(r["tokens_per_second"] for r in valid if r["tokens_per_second"] is not None), 3) if valid else None,
    }
    return rows, summary


def main() -> None:
    args = parse_args()
    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    if args.limit is not None:
        if args.limit < 1:
            raise SystemExit("--limit must be >= 1")
        cases = cases[: args.limit]
    if not cases:
        raise SystemExit("No evaluation cases found")

    all_rows: list[dict] = []
    summaries: list[dict] = []
    for mode in args.modes:
        rows, summary = run_mode(args.model, mode, cases, args.max_new_tokens)
        all_rows.extend(rows)
        summaries.append(summary)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "evaluator_version": "v2-constrained-guarded",
        "model": args.model,
        "max_new_tokens": args.max_new_tokens,
        "case_count": len(cases),
        "summary": summaries,
        "rows": all_rows,
    }
    json_path = output_dir / f"quality_eval_v2_{stamp}.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    summary_csv = output_dir / f"quality_summary_v2_{stamp}.csv"
    with summary_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summaries[0].keys()))
        writer.writeheader()
        writer.writerows(summaries)

    detail_csv = output_dir / f"quality_detail_v2_{stamp}.csv"
    detail_fields = [
        "case_id", "mode", "status", "accepted_for_application", "guardrail_passed",
        "diagnosis_code_retained", "conclusion_retained", "format_valid",
        "unexpected_identifier_count", "unsafe_instruction", "truncated",
        "observed_fact_retention_rate", "latency_ms", "tokens_per_second", "output_tokens",
        "missing_observed_facts", "guardrail_reasons", "unexpected_identifiers", "raw_output",
    ]
    with detail_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=detail_fields)
        writer.writeheader()
        for row in all_rows:
            writer.writerow({
                key: json.dumps(row.get(key), ensure_ascii=False) if isinstance(row.get(key), (dict, list)) else row.get(key)
                for key in detail_fields
            })

    manual_csv = output_dir / f"manual_review_v2_{stamp}.csv"
    manual_fields = [
        "case_id", "mode", "accepted_for_application", "manual_semantic_factual_correct",
        "manual_semantic_diagnosis_correct", "manual_hallucination", "manual_readable",
        "manual_notes", "raw_output",
    ]
    with manual_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=manual_fields)
        writer.writeheader()
        for row in all_rows:
            writer.writerow({
                "case_id": row["case_id"],
                "mode": row["mode"],
                "accepted_for_application": row["accepted_for_application"],
                "manual_semantic_factual_correct": "",
                "manual_semantic_diagnosis_correct": "",
                "manual_hallucination": "",
                "manual_readable": "",
                "manual_notes": "",
                "raw_output": row["raw_output"],
            })

    print("\n=== Quality summary V2 ===")
    print(json.dumps(summaries, ensure_ascii=False, indent=2))
    print(f"\nSaved: {json_path}")
    print(f"Saved: {summary_csv}")
    print(f"Saved: {detail_csv}")
    print(f"Saved: {manual_csv}")


if __name__ == "__main__":
    main()
