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
from app.llm.report_guardrails import build_auxiliary_request, validate_auxiliary_output


CASE_RELEVANCE = {
    "vlan_mismatch_01": ("台账", "变更", "登记", "核对"),
    "interface_down_01": ("终端", "线缆", "网卡", "接入", "链路", "核查"),
    "no_mac_01": ("终端", "流量", "接入", "学习", "核查"),
    "resource_mismatch_01": ("台账", "接入位置", "迁移", "资源", "核对"),
    "upstream_01": ("上层", "业务", "策略", "dns", "转交"),
    "gateway_mismatch_01": ("网关", "地址", "分配", "配置", "核对"),
    "link_errors_01": ("线缆", "网卡", "接口", "链路", "统计", "核查"),
    "arp_missing_01": ("补充", "网关", "上层", "证据", "核查"),
    "device_mismatch_01": ("接入设备", "资源", "台账", "核对"),
    "normal_access_01": ("上层", "业务", "转交", "继续", "维护"),
}


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
    parser = argparse.ArgumentParser(description="Evaluate guarded local-LLM auxiliary-note quality V3")
    parser.add_argument("--model", required=True)
    parser.add_argument("--modes", nargs="+", default=["fp16", "int4"], choices=["none", "fp16", "int8", "int4"])
    parser.add_argument("--cases", default="data/evaluation/quality_cases.json")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--max-new-tokens", type=int, default=96)
    parser.add_argument("--output-dir", default="runtime/quality_eval_v3")
    return parser.parse_args()


def semantic_relevance(case_id: str, auxiliary_text: str | None) -> bool:
    if not auxiliary_text:
        return False
    text = auxiliary_text.lower()
    terms = CASE_RELEVANCE.get(case_id, ("核查", "复核", "转交", "确认"))
    return any(term.lower() in text for term in terms)


def score_case(case: dict, raw_output: str, max_new_tokens: int, output_tokens: int | None) -> dict:
    guard = validate_auxiliary_output(case["input_report"], raw_output)
    truncated = bool(output_tokens is not None and output_tokens >= max_new_tokens)
    relevant = semantic_relevance(case["case_id"], guard.auxiliary_text)
    accepted = bool(guard.passed and relevant)
    return {
        "accepted_for_application": accepted,
        "guardrail_passed": guard.passed,
        "auxiliary_parse_ok": guard.format_ok,
        "semantic_relevance": relevant,
        "identifier_free": guard.identifier_free,
        "unsafe_free": guard.unsafe_free,
        "contradiction_free": guard.contradiction_free,
        "length_ok": guard.length_ok,
        "complete_sentence": guard.complete_sentence,
        "ignored_extra_lines": guard.ignored_extra_lines,
        "truncated": truncated,
        "guardrail_reasons": guard.reasons,
        "identifiers_in_auxiliary": guard.identifiers_in_auxiliary,
        "auxiliary_text": guard.auxiliary_text,
    }


def run_mode(model: str, mode: str, cases: list[dict], max_new_tokens: int) -> tuple[list[dict], dict]:
    print(f"\n[{mode}] loading model...", flush=True)
    backend = LocalHFBackend(model_id=model, quantization=mode, max_new_tokens=max_new_tokens, temperature=0.0)
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
            print(
                f"[{mode}] {idx}/{len(cases)} done | {wall:.2f}s | tokens={result.output_tokens} | "
                f"accepted={scores['accepted_for_application']} | note={scores['auxiliary_text']!r}",
                flush=True,
            )
            rows.append({
                "case_id": case["case_id"],
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

    valid = [r for r in rows if r["status"] == "ok"]
    mean = lambda values: round(statistics.mean(values), 4) if values else None
    summary = {
        "mode": mode,
        "cases": len(rows),
        "successful_cases": len(valid),
        "application_acceptance_rate": mean([int(r["accepted_for_application"]) for r in valid]),
        "auxiliary_parse_rate": mean([int(r["auxiliary_parse_ok"]) for r in valid]),
        "semantic_relevance_rate": mean([int(r["semantic_relevance"]) for r in valid]),
        "identifier_free_rate": mean([int(r["identifier_free"]) for r in valid]),
        "unsafe_free_rate": mean([int(r["unsafe_free"]) for r in valid]),
        "contradiction_free_rate": mean([int(r["contradiction_free"]) for r in valid]),
        "complete_sentence_rate": mean([int(r["complete_sentence"]) for r in valid]),
        "truncation_rate": mean([int(r["truncated"]) for r in valid]),
        "mean_ignored_extra_lines": mean([r["ignored_extra_lines"] for r in valid]),
        "mean_latency_ms": round(statistics.mean(r["latency_ms"] for r in valid if r["latency_ms"] is not None), 2) if valid else None,
        "mean_tokens_per_second": round(statistics.mean(r["tokens_per_second"] for r in valid if r["tokens_per_second"] is not None), 3) if valid else None,
        "mean_output_tokens": round(statistics.mean(r["output_tokens"] for r in valid if r["output_tokens"] is not None), 2) if valid else None,
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
        "evaluator_version": "v3-aux-only",
        "model": args.model,
        "max_new_tokens": args.max_new_tokens,
        "case_count": len(cases),
        "summary": summaries,
        "rows": all_rows,
    }
    json_path = output_dir / f"quality_eval_v3_{stamp}.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    summary_csv = output_dir / f"quality_summary_v3_{stamp}.csv"
    with summary_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summaries[0].keys()))
        writer.writeheader(); writer.writerows(summaries)

    detail_csv = output_dir / f"quality_detail_v3_{stamp}.csv"
    detail_fields = [
        "case_id", "mode", "status", "accepted_for_application", "guardrail_passed",
        "auxiliary_parse_ok", "semantic_relevance", "identifier_free", "unsafe_free",
        "contradiction_free", "length_ok", "complete_sentence", "ignored_extra_lines",
        "truncated", "latency_ms", "tokens_per_second", "output_tokens", "guardrail_reasons",
        "identifiers_in_auxiliary", "auxiliary_text", "raw_output",
    ]
    with detail_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=detail_fields); writer.writeheader()
        for row in all_rows:
            writer.writerow({
                key: json.dumps(row.get(key), ensure_ascii=False) if isinstance(row.get(key), (dict, list)) else row.get(key)
                for key in detail_fields
            })

    manual_csv = output_dir / f"manual_review_v3_{stamp}.csv"
    manual_fields = [
        "case_id", "mode", "accepted_for_application", "manual_relevant", "manual_factual_safe",
        "manual_no_hallucination", "manual_action_boundary_ok", "manual_readable", "manual_notes",
        "auxiliary_text", "raw_output",
    ]
    with manual_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=manual_fields); writer.writeheader()
        for row in all_rows:
            writer.writerow({
                "case_id": row["case_id"], "mode": row["mode"],
                "accepted_for_application": row["accepted_for_application"],
                "manual_relevant": "", "manual_factual_safe": "", "manual_no_hallucination": "",
                "manual_action_boundary_ok": "", "manual_readable": "", "manual_notes": "",
                "auxiliary_text": row["auxiliary_text"], "raw_output": row["raw_output"],
            })

    print("\n=== Quality summary V3 ===")
    print(json.dumps(summaries, ensure_ascii=False, indent=2))
    print(f"\nSaved: {json_path}\nSaved: {summary_csv}\nSaved: {detail_csv}\nSaved: {manual_csv}")


if __name__ == "__main__":
    main()
