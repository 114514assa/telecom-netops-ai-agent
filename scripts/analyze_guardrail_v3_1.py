"""V3.1 Guardrail metadata-only audit analyzer (stdlib, no model required).

Reads versioned or legacy audit files. Emits revision-named JSON and CSV
summaries; never exports candidate text, prompts, CLI evidence, or IPs.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

VERSION = "v3_1_1"


def summarize_records(records: list[dict]) -> dict:
    events = [x for x in records if x.get("event") == "report_composed" and isinstance(x.get("detail"), dict)]
    by_code = defaultdict(lambda: {"total": 0, "llm_accepted": 0, "llm_fallback": 0, "template_only": 0, "unclassified": 0, "reasons": Counter()})
    total_reasons = Counter()
    counts = Counter()
    for event in events:
        detail = event["detail"]
        code = str(detail.get("diagnosis_code") or "unknown")
        by_code[code]["total"] += 1
        generated = str(detail.get("generated_by") or "")
        if generated == "deterministic-template":
            label = "template_only"
        elif "fallback" in generated:
            label = "llm_fallback"
        elif generated.endswith(":guarded"):
            label = "llm_accepted"
        else:
            label = "unclassified"  # unknown schema must not be counted as accepted
        counts[label] += 1
        by_code[code][label] += 1
        reasons = detail.get("guardrail_reasons") or []
        # Accept only lists of reason codes (not input/candidate excerpts).
        if isinstance(reasons, list):
            for reason in reasons:
                if isinstance(reason, str) and reason.replace("_", "").isalnum() and len(reason) <= 80:
                    total_reasons[reason] += 1
                    by_code[code]["reasons"][reason] += 1
    result = {
        "revision": "v3.1.0", "source": "report_composed audit events",
        "events": len(events), "llm_accepted": counts["llm_accepted"],
        "llm_fallback": counts["llm_fallback"], "template_only": counts["template_only"], "unclassified": counts["unclassified"],
        "llm_acceptance_rate": round(counts["llm_accepted"] / max(1, counts["llm_accepted"] + counts["llm_fallback"]), 4)
            if counts["llm_accepted"] + counts["llm_fallback"] else None,
        "rejection_reasons": dict(total_reasons),
        "by_diagnosis": {
            key: {**{k: v for k, v in value.items() if k != "reasons"}, "reasons": dict(value["reasons"])}
            for key, value in sorted(by_code.items())
        },
        "note": "Counts reflect requests, not distinct incidents or field diagnosis accuracy. No raw candidate text is persisted.",
    }
    return result


def read_audit(path: Path) -> list[dict]:
    results = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                results.append(obj)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Malformed JSONL at line {n}: {exc}") from exc
    return results


def write_outputs(summary: dict, output_dir: Path, *, stamp: str | None = None) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = stamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    basename = f"guardrail_{VERSION}_{stamp}"
    summary_path = output_dir / f"{basename}_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    by_case_path = output_dir / f"{basename}_by_diagnosis.csv"
    with by_case_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["diagnosis_code", "total", "llm_accepted", "llm_fallback", "template_only", "unclassified", "rejection_reasons_json"])
        writer.writeheader()
        for k, row in summary["by_diagnosis"].items():
            writer.writerow({"diagnosis_code": k, **{name: row[name] for name in ("total", "llm_accepted", "llm_fallback", "template_only", "unclassified")}, "rejection_reasons_json": json.dumps(row["reasons"], ensure_ascii=False)})
    reasons_path = output_dir / f"{basename}_reasons.csv"
    with reasons_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f); writer.writerow(["reason_code", "occurrences"])
        for key, num in sorted(summary["rejection_reasons"].items(), key=lambda x: (-x[1], x[0])):
            writer.writerow([key, num])
    return [summary_path, by_case_path, reasons_path]


def main() -> None:
    parser = argparse.ArgumentParser(description="V3.1 Guardrail outcomes from report_composed JSONL")
    parser.add_argument("--audit", default="runtime_v3_1/audit.jsonl")
    parser.add_argument("--output-dir", default="runtime_v3_1/guardrail_analysis")
    args = parser.parse_args()
    path = Path(args.audit)
    if not path.is_file():
        raise SystemExit(f"Audit file not found: {path}. Run V3.1 Agent with LLM enabled first.")
    summary = summarize_records(read_audit(path))
    for out in write_outputs(summary, Path(args.output_dir)):
        print("WROTE", out)
    print(json.dumps({k: summary[k] for k in ("events", "llm_accepted", "llm_fallback", "template_only", "unclassified", "llm_acceptance_rate", "rejection_reasons")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
