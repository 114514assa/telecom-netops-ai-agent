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
from app.llm.report_guardrails import build_auxiliary_request, validate_auxiliary_output


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


def seed_everything(seed: int) -> None:
    try:
        import torch
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    except ImportError:
        pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Final guarded local-LLM quality evaluation V4 (30 scenario variants)"
    )
    parser.add_argument("--model", required=True)
    parser.add_argument(
        "--modes",
        nargs="+",
        default=["fp16", "int4"],
        choices=["none", "fp16", "int8", "int4"],
    )
    parser.add_argument("--cases", default="data/evaluation/quality_cases_30.json")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--case-ids", nargs="+", default=None, help="Run only selected case IDs")
    parser.add_argument("--max-new-tokens", type=int, default=96)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", default="runtime/quality_eval_v4")
    return parser.parse_args()


def score_case(case: dict, raw_output: str, max_new_tokens: int, output_tokens: int | None) -> dict:
    guard = validate_auxiliary_output(case["input_report"], raw_output)
    truncated = bool(output_tokens is not None and output_tokens >= max_new_tokens)
    return {
        # This is the actual application decision in V4: the same guardrail is used by ReportComposer.
        "accepted_for_application": bool(guard.passed),
        "guardrail_passed": bool(guard.passed),
        "auxiliary_parse_ok": bool(guard.format_ok),
        "semantic_relevance": bool(guard.semantic_relevant),
        "identifier_free": bool(guard.identifier_free),
        "unsafe_free": bool(guard.unsafe_free),
        "contradiction_free": bool(guard.contradiction_free),
        "length_ok": bool(guard.length_ok),
        "complete_sentence": bool(guard.complete_sentence),
        "ignored_extra_lines": int(guard.ignored_extra_lines),
        "truncated": truncated,
        "guardrail_reasons": guard.reasons,
        "identifiers_in_auxiliary": guard.identifiers_in_auxiliary,
        "candidate_text": guard.candidate_text,
        "auxiliary_text": guard.auxiliary_text,
    }


def _rate(rows: list[dict], key: str) -> float | None:
    if not rows:
        return None
    return round(statistics.mean(int(bool(r[key])) for r in rows), 4)


def _mean_numeric(rows: list[dict], key: str, ndigits: int) -> float | None:
    values = [r[key] for r in rows if r.get(key) is not None]
    return round(statistics.mean(values), ndigits) if values else None


def summarize_mode(mode: str, rows: list[dict]) -> dict:
    valid = [r for r in rows if r["status"] == "ok"]
    reason_counts: Counter[str] = Counter()
    for row in valid:
        reason_counts.update(row.get("guardrail_reasons") or [])
    acceptance = _rate(valid, "accepted_for_application")
    return {
        "mode": mode,
        "cases": len(rows),
        "successful_cases": len(valid),
        "application_acceptance_rate": acceptance,
        "fallback_rate": round(1.0 - acceptance, 4) if acceptance is not None else None,
        "auxiliary_parse_rate": _rate(valid, "auxiliary_parse_ok"),
        "semantic_relevance_rate": _rate(valid, "semantic_relevance"),
        "identifier_free_rate": _rate(valid, "identifier_free"),
        "unsafe_free_rate": _rate(valid, "unsafe_free"),
        "contradiction_free_rate": _rate(valid, "contradiction_free"),
        "length_ok_rate": _rate(valid, "length_ok"),
        "complete_sentence_rate": _rate(valid, "complete_sentence"),
        "truncation_rate": _rate(valid, "truncated"),
        "mean_ignored_extra_lines": _mean_numeric(valid, "ignored_extra_lines", 4),
        "mean_latency_ms": _mean_numeric(valid, "latency_ms", 2),
        "mean_tokens_per_second": _mean_numeric(valid, "tokens_per_second", 3),
        "mean_output_tokens": _mean_numeric(valid, "output_tokens", 2),
        "rejection_reasons": json.dumps(dict(reason_counts), ensure_ascii=False, sort_keys=True),
    }


def run_mode(
    model: str,
    mode: str,
    cases: list[dict],
    max_new_tokens: int,
    seed: int,
) -> tuple[list[dict], dict]:
    print(f"\n[{mode}] loading model...", flush=True)
    seed_everything(seed)
    backend = LocalHFBackend(
        model_id=model,
        quantization=mode,
        max_new_tokens=max_new_tokens,
        temperature=0.0,
    )
    rows: list[dict] = []
    try:
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
            reason_text = ",".join(scores["guardrail_reasons"]) or "-"
            display_note = scores["auxiliary_text"] or scores["candidate_text"]
            print(
                f"[{mode}] {idx}/{len(cases)} done | {wall:.2f}s | tokens={result.output_tokens} | "
                f"accepted={scores['accepted_for_application']} | reasons={reason_text} | note={display_note!r}",
                flush=True,
            )
            rows.append({
                "case_id": case["case_id"],
                "scenario_family": case.get("scenario_family", "unknown"),
                "diagnosis_code": case.get("diagnosis_code", "unknown"),
                "variant": case.get("variant"),
                "mode": mode,
                "status": "ok" if raw_output else "empty",
                "latency_ms": result.latency_ms,
                "tokens_per_second": result.tokens_per_second,
                "output_tokens": result.output_tokens,
                **scores,
                "input_report": case["input_report"],
                "raw_output": raw_output,
            })
    finally:
        release_backend(backend)

    return rows, summarize_mode(mode, rows)


def build_family_summaries(all_rows: list[dict]) -> list[dict]:
    buckets: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in all_rows:
        if row["status"] == "ok":
            buckets[(row["mode"], row["scenario_family"])].append(row)
    output = []
    for (mode, family), rows in sorted(buckets.items()):
        output.append({
            "mode": mode,
            "scenario_family": family,
            "cases": len(rows),
            "application_acceptance_rate": _rate(rows, "accepted_for_application"),
            "semantic_relevance_rate": _rate(rows, "semantic_relevance"),
            "identifier_free_rate": _rate(rows, "identifier_free"),
            "unsafe_free_rate": _rate(rows, "unsafe_free"),
            "contradiction_free_rate": _rate(rows, "contradiction_free"),
        })
    return output


def main() -> None:
    args = parse_args()
    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    if args.case_ids:
        wanted = set(args.case_ids)
        cases = [case for case in cases if case.get("case_id") in wanted]
        found = {case.get("case_id") for case in cases}
        missing = sorted(wanted - found)
        if missing:
            raise SystemExit(f"Unknown --case-ids: {missing}")
    if args.limit is not None:
        if args.limit < 1:
            raise SystemExit("--limit must be >= 1")
        cases = cases[: args.limit]
    if not cases:
        raise SystemExit("No evaluation cases found")

    all_rows: list[dict] = []
    summaries: list[dict] = []
    for mode in args.modes:
        rows, summary = run_mode(args.model, mode, cases, args.max_new_tokens, args.seed)
        all_rows.extend(rows)
        summaries.append(summary)

    family_summaries = build_family_summaries(all_rows)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "evaluator_version": "v4-final-guarded-30",
        "model": args.model,
        "seed": args.seed,
        "max_new_tokens": args.max_new_tokens,
        "case_count": len(cases),
        "summary": summaries,
        "family_summary": family_summaries,
        "rows": all_rows,
    }
    json_path = output_dir / f"quality_eval_v4_{stamp}.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    summary_csv = output_dir / f"quality_summary_v4_{stamp}.csv"
    with summary_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summaries[0].keys()))
        writer.writeheader()
        writer.writerows(summaries)

    family_csv = output_dir / f"quality_family_v4_{stamp}.csv"
    if family_summaries:
        with family_csv.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(family_summaries[0].keys()))
            writer.writeheader()
            writer.writerows(family_summaries)

    detail_csv = output_dir / f"quality_detail_v4_{stamp}.csv"
    detail_fields = [
        "case_id", "scenario_family", "diagnosis_code", "variant", "mode", "status",
        "accepted_for_application", "guardrail_passed", "auxiliary_parse_ok",
        "semantic_relevance", "identifier_free", "unsafe_free", "contradiction_free",
        "length_ok", "complete_sentence", "ignored_extra_lines", "truncated",
        "latency_ms", "tokens_per_second", "output_tokens", "guardrail_reasons",
        "identifiers_in_auxiliary", "candidate_text", "auxiliary_text", "raw_output",
    ]
    with detail_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=detail_fields)
        writer.writeheader()
        for row in all_rows:
            writer.writerow({
                key: json.dumps(row.get(key), ensure_ascii=False)
                if isinstance(row.get(key), (dict, list)) else row.get(key)
                for key in detail_fields
            })

    manual_csv = output_dir / f"manual_review_v4_{stamp}.csv"
    manual_fields = [
        "case_id", "scenario_family", "mode", "accepted_for_application",
        "manual_relevant", "manual_factual_safe", "manual_no_hallucination",
        "manual_action_boundary_ok", "manual_readable", "manual_notes",
        "candidate_text", "raw_output",
    ]
    with manual_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=manual_fields)
        writer.writeheader()
        for row in all_rows:
            writer.writerow({
                "case_id": row["case_id"],
                "scenario_family": row["scenario_family"],
                "mode": row["mode"],
                "accepted_for_application": row["accepted_for_application"],
                "manual_relevant": "",
                "manual_factual_safe": "",
                "manual_no_hallucination": "",
                "manual_action_boundary_ok": "",
                "manual_readable": "",
                "manual_notes": "",
                "candidate_text": row["candidate_text"],
                "raw_output": row["raw_output"],
            })

    print("\n=== Quality summary V4 ===")
    print(json.dumps(summaries, ensure_ascii=False, indent=2))
    print(
        f"\nSaved: {json_path}\nSaved: {summary_csv}\nSaved: {family_csv}"
        f"\nSaved: {detail_csv}\nSaved: {manual_csv}"
    )


if __name__ == "__main__":
    main()
