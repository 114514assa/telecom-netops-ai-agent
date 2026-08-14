from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

FIELDS = [
    "manual_relevant",
    "manual_factual_safe",
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
    parser = argparse.ArgumentParser(description="Summarize completed final manual review CSV")
    parser.add_argument("csv_path")
    args = parser.parse_args()

    path = Path(args.csv_path)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise SystemExit("No manual review rows found")

    by_mode: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_mode[row["mode"]].append(row)

    summary = []
    for mode, mode_rows in sorted(by_mode.items()):
        item = {"mode": mode, "rows": len(mode_rows)}
        complete_rows = 0
        for row in mode_rows:
            if all(parse_binary(row.get(field, "")) is not None for field in FIELDS):
                complete_rows += 1
        item["completed_rows"] = complete_rows
        for field in FIELDS:
            values = [parse_binary(row.get(field, "")) for row in mode_rows]
            valid = [v for v in values if v is not None]
            item[field + "_rate"] = round(sum(valid) / len(valid), 4) if valid else None
        all_pass = []
        for row in mode_rows:
            vals = [parse_binary(row.get(field, "")) for field in FIELDS]
            if all(v is not None for v in vals):
                all_pass.append(int(all(v == 1 for v in vals)))
        item["manual_all_pass_rate"] = round(sum(all_pass) / len(all_pass), 4) if all_pass else None
        summary.append(item)

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
