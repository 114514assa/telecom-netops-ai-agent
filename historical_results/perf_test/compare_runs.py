from __future__ import annotations

import argparse
import csv
from pathlib import Path


def read_csv(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def main():
    ap = argparse.ArgumentParser(description="比较多个性能测试 summary.csv")
    ap.add_argument("summaries", nargs="+", help="例如 perf_results/fp16/summary.csv perf_results/int4/summary.csv")
    args = ap.parse_args()

    rows = []
    for item in args.summaries:
        p = Path(item)
        for r in read_csv(p):
            rows.append(r)

    print("|label|并发|成功率|吞吐量(req/s)|P50(ms)|P95(ms)|P99(ms)|峰值RSS(MB)|峰值GPU显存(MB)|")
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for r in rows:
        print(
            f"|{r.get('label','')}|{r.get('concurrency','')}|{r.get('success_rate_pct','')}%|"
            f"{r.get('throughput_rps','')}|{r.get('latency_p50_ms','')}|{r.get('latency_p95_ms','')}|"
            f"{r.get('latency_p99_ms','')}|{r.get('process_rss_peak_mb','')}|{r.get('gpu_mem_peak_mb','')}|"
        )


if __name__ == "__main__":
    main()
