from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

FIELDS = [
    "manual_diagnosis_consistent",
    "manual_relevant",
    "manual_no_hallucination",
    "manual_action_boundary_ok",
    "manual_readable",
]


def parse_binary(value: str) -> int | None:
    value = (value or "").strip().lower()
    if value in {"1", "true", "yes", "y", "是", "通过"}:
        return 1
    if value in {"0", "false", "no", "n", "否", "不通过"}:
        return 0
    return None


def main() -> None:
    p = argparse.ArgumentParser(description="Summarize manual review for the 50-case quantization evaluation")
    p.add_argument("csv_path")
    args = p.parse_args()
    path = Path(args.csv_path)
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise SystemExit("No rows found")

    by_mode: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_mode[row["mode"]].append(row)

    summary = []
    for mode, mode_rows in sorted(by_mode.items()):
        item = {"mode": mode, "rows": len(mode_rows)}
        completed = [r for r in mode_rows if all(parse_binary(r.get(field, "")) is not None for field in FIELDS)]
        item["completed_rows"] = len(completed)
        for field in FIELDS:
            vals = [parse_binary(r.get(field, "")) for r in mode_rows]
            vals = [v for v in vals if v is not None]
            item[field + "_rate"] = round(sum(vals) / len(vals), 4) if vals else None
        all_pass = []
        for row in completed:
            vals = [parse_binary(row.get(field, "")) for field in FIELDS]
            all_pass.append(int(all(v == 1 for v in vals)))
        item["manual_all_pass_rate"] = round(sum(all_pass) / len(all_pass), 4) if all_pass else None
        summary.append(item)

    out_json = path.with_name(path.stem + "_summary.json")
    out_csv = path.with_name(path.stem + "_summary.csv")
    out_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    if summary:
        with out_csv.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(summary[0].keys()))
            w.writeheader(); w.writerows(summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Saved: {out_json}")
    print(f"Saved: {out_csv}")


if __name__ == "__main__":
    main()
