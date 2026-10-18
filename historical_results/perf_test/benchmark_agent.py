from __future__ import annotations

import argparse
import asyncio
import csv
import json
import math
import os
import subprocess
import threading
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import httpx
import psutil


def percentile(values: list[float], p: float) -> float:
    if not values:
        return float("nan")
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    rank = (len(xs) - 1) * p
    lo = math.floor(rank)
    hi = math.ceil(rank)
    if lo == hi:
        return xs[lo]
    return xs[lo] + (xs[hi] - xs[lo]) * (rank - lo)


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"{path} 第 {line_no} 行不是合法 JSON: {e}") from e
            if not isinstance(obj, dict):
                raise ValueError(f"{path} 第 {line_no} 行必须是 JSON object")
            cases.append(obj)
    if not cases:
        raise ValueError(f"{path} 没有可用测试样例")
    return cases


def gpu_snapshot() -> dict[str, float | None]:
    cmd = [
        "nvidia-smi",
        "--query-gpu=utilization.gpu,memory.used,memory.total",
        "--format=csv,noheader,nounits",
    ]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=2, check=True)
        rows = [x.strip() for x in p.stdout.splitlines() if x.strip()]
        if not rows:
            return {"gpu_util_pct": None, "gpu_mem_used_mb": None, "gpu_mem_total_mb": None}
        util, used, total = rows[0].split(",")
        return {
            "gpu_util_pct": float(util.strip()),
            "gpu_mem_used_mb": float(used.strip()),
            "gpu_mem_total_mb": float(total.strip()),
        }
    except Exception:
        return {"gpu_util_pct": None, "gpu_mem_used_mb": None, "gpu_mem_total_mb": None}


class ResourceSampler:
    def __init__(self, label: str, concurrency: int, pid: int | None, interval: float = 0.5):
        self.label = label
        self.concurrency = concurrency
        self.pid = pid
        self.interval = interval
        self.rows: list[dict[str, Any]] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._proc = None
        if pid:
            try:
                self._proc = psutil.Process(pid)
            except psutil.Error:
                self._proc = None

    def start(self):
        psutil.cpu_percent(interval=None)
        if self._proc:
            try:
                self._proc.cpu_percent(interval=None)
            except psutil.Error:
                self._proc = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            vm = psutil.virtual_memory()
            row = {
                "timestamp": time.time(),
                "label": self.label,
                "concurrency": self.concurrency,
                "system_cpu_pct": psutil.cpu_percent(interval=None),
                "system_mem_pct": vm.percent,
                "system_mem_used_mb": vm.used / 1024 / 1024,
                "process_cpu_pct": None,
                "process_rss_mb": None,
            }
            if self._proc:
                try:
                    row["process_cpu_pct"] = self._proc.cpu_percent(interval=None)
                    row["process_rss_mb"] = self._proc.memory_info().rss / 1024 / 1024
                except psutil.Error:
                    pass
            row.update(gpu_snapshot())
            self.rows.append(row)
            self._stop.wait(self.interval)

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=self.interval * 3)


@dataclass
class RequestResult:
    label: str
    concurrency: int
    request_id: int
    case_index: int
    ok: bool
    status_code: int | None
    latency_ms: float
    error: str = ""


def parse_headers(header_args: list[str]) -> dict[str, str]:
    headers = {}
    for item in header_args:
        if ":" not in item:
            raise ValueError(f"--header 格式错误: {item!r}，应为 'Name: Value'")
        k, v = item.split(":", 1)
        headers[k.strip()] = v.strip()
    return headers


async def run_one_level(
    *,
    url: str,
    cases: list[dict[str, Any]],
    concurrency: int,
    total_requests: int,
    timeout_s: float,
    headers: dict[str, str],
    label: str,
    verify_ssl: bool,
    pid: int | None,
) -> tuple[list[RequestResult], list[dict[str, Any]], float]:
    semaphore = asyncio.Semaphore(concurrency)
    limits = httpx.Limits(
        max_connections=max(concurrency, 1),
        max_keepalive_connections=max(concurrency, 1),
    )
    timeout = httpx.Timeout(timeout_s)

    sampler = ResourceSampler(label=label, concurrency=concurrency, pid=pid)
    sampler.start()
    started = time.perf_counter()

    async with httpx.AsyncClient(
        headers=headers,
        timeout=timeout,
        limits=limits,
        verify=verify_ssl,
    ) as client:

        async def one(i: int) -> RequestResult:
            case_index = i % len(cases)
            body = cases[case_index]
            async with semaphore:
                t0 = time.perf_counter()
                try:
                    response = await client.post(url, json=body)
                    latency_ms = (time.perf_counter() - t0) * 1000
                    ok = 200 <= response.status_code < 300
                    return RequestResult(
                        label=label,
                        concurrency=concurrency,
                        request_id=i,
                        case_index=case_index,
                        ok=ok,
                        status_code=response.status_code,
                        latency_ms=latency_ms,
                        error="" if ok else response.text[:300].replace("\n", " "),
                    )
                except Exception as e:
                    latency_ms = (time.perf_counter() - t0) * 1000
                    return RequestResult(
                        label=label,
                        concurrency=concurrency,
                        request_id=i,
                        case_index=case_index,
                        ok=False,
                        status_code=None,
                        latency_ms=latency_ms,
                        error=f"{type(e).__name__}: {e}",
                    )

        results = await asyncio.gather(*(one(i) for i in range(total_requests)))

    elapsed = time.perf_counter() - started
    sampler.stop()
    return results, sampler.rows, elapsed


def max_or_none(rows: list[dict[str, Any]], key: str):
    vals = [r[key] for r in rows if r.get(key) is not None]
    return max(vals) if vals else None


def avg_or_none(rows: list[dict[str, Any]], key: str):
    vals = [r[key] for r in rows if r.get(key) is not None]
    return sum(vals) / len(vals) if vals else None


def summarize(
    label: str,
    concurrency: int,
    results: list[RequestResult],
    resource_rows: list[dict[str, Any]],
    elapsed_s: float,
) -> dict[str, Any]:
    lat = [r.latency_ms for r in results]
    ok_count = sum(r.ok for r in results)
    total = len(results)
    return {
        "label": label,
        "concurrency": concurrency,
        "requests": total,
        "success_count": ok_count,
        "failure_count": total - ok_count,
        "success_rate_pct": round(ok_count / total * 100, 3) if total else 0.0,
        "elapsed_s": round(elapsed_s, 3),
        "throughput_rps": round(total / elapsed_s, 3) if elapsed_s > 0 else None,
        "latency_avg_ms": round(sum(lat) / len(lat), 3) if lat else None,
        "latency_p50_ms": round(percentile(lat, 0.50), 3) if lat else None,
        "latency_p95_ms": round(percentile(lat, 0.95), 3) if lat else None,
        "latency_p99_ms": round(percentile(lat, 0.99), 3) if lat else None,
        "latency_max_ms": round(max(lat), 3) if lat else None,
        "system_cpu_avg_pct": round(avg_or_none(resource_rows, "system_cpu_pct"), 3)
        if avg_or_none(resource_rows, "system_cpu_pct") is not None else None,
        "system_cpu_peak_pct": round(max_or_none(resource_rows, "system_cpu_pct"), 3)
        if max_or_none(resource_rows, "system_cpu_pct") is not None else None,
        "system_mem_peak_pct": round(max_or_none(resource_rows, "system_mem_pct"), 3)
        if max_or_none(resource_rows, "system_mem_pct") is not None else None,
        "process_rss_peak_mb": round(max_or_none(resource_rows, "process_rss_mb"), 3)
        if max_or_none(resource_rows, "process_rss_mb") is not None else None,
        "gpu_util_peak_pct": round(max_or_none(resource_rows, "gpu_util_pct"), 3)
        if max_or_none(resource_rows, "gpu_util_pct") is not None else None,
        "gpu_mem_peak_mb": round(max_or_none(resource_rows, "gpu_mem_used_mb"), 3)
        if max_or_none(resource_rows, "gpu_mem_used_mb") is not None else None,
    }


def write_csv(path: Path, rows: list[dict[str, Any]]):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def write_report(path: Path, summaries: list[dict[str, Any]], args):
    lines = [
        "# Agent Performance Test Report",
        "",
        f"- URL: `{args.url}`",
        f"- Label: `{args.label}`",
        f"- Requests per level: {args.requests_per_level}",
        f"- Timeout: {args.timeout}s",
        f"- PID monitoring: {args.pid if args.pid else 'disabled'}",
        "",
        "## Summary",
        "",
        "|并发|成功率|吞吐量(req/s)|P50(ms)|P95(ms)|P99(ms)|峰值RSS(MB)|峰值GPU显存(MB)|",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for s in summaries:
        def fmt(v):
            return "-" if v is None else str(v)
        lines.append(
            f"|{s['concurrency']}|{fmt(s['success_rate_pct'])}%|{fmt(s['throughput_rps'])}|"
            f"{fmt(s['latency_p50_ms'])}|{fmt(s['latency_p95_ms'])}|{fmt(s['latency_p99_ms'])}|"
            f"{fmt(s['process_rss_peak_mb'])}|{fmt(s['gpu_mem_peak_mb'])}|"
        )
    lines += [
        "",
        "## 判读原则",
        "",
        "- 先看成功率是否随并发上升明显下降。",
        "- 再看 P95/P99 是否出现突增，避免只看平均时延。",
        "- 同一台机器、同一批请求、同一模型配置下再比较 FP16 / INT8 / INT4。",
        "- 若未传 `--pid`，进程 RSS 不统计；GPU 指标为 nvidia-smi 能看到的整卡指标。",
        "- 性能测试中的 HTTP 2xx 仅代表接口成功，业务正确性仍由原有质量/鲁棒性测试集负责。",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


async def warmup(url, cases, headers, timeout_s, verify_ssl, n):
    if n <= 0:
        return
    async with httpx.AsyncClient(headers=headers, timeout=timeout_s, verify=verify_ssl) as client:
        for i in range(n):
            try:
                await client.post(url, json=cases[i % len(cases)])
            except Exception:
                pass


async def main_async(args):
    cases = load_cases(Path(args.cases))
    headers = parse_headers(args.header)
    levels = [int(x.strip()) for x in args.concurrency.split(",") if x.strip()]
    if not levels or any(x <= 0 for x in levels):
        raise ValueError("--concurrency 必须是正整数列表，例如 1,5,10,20")

    out_dir = Path(args.out) / args.label
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] target={args.url}")
    print(f"[INFO] label={args.label}")
    print(f"[INFO] cases={len(cases)}")
    print(f"[INFO] concurrency={levels}")
    print(f"[INFO] requests_per_level={args.requests_per_level}")

    print(f"[WARMUP] {args.warmup} requests")
    await warmup(args.url, cases, headers, args.timeout, args.verify_ssl, args.warmup)

    all_results: list[dict[str, Any]] = []
    all_resources: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []

    for c in levels:
        print(f"\n[RUN] concurrency={c}")
        results, resources, elapsed = await run_one_level(
            url=args.url,
            cases=cases,
            concurrency=c,
            total_requests=args.requests_per_level,
            timeout_s=args.timeout,
            headers=headers,
            label=args.label,
            verify_ssl=args.verify_ssl,
            pid=args.pid,
        )
        s = summarize(args.label, c, results, resources, elapsed)
        summaries.append(s)
        all_results.extend(asdict(r) for r in results)
        all_resources.extend(resources)
        print(
            f"[DONE] success={s['success_rate_pct']}% "
            f"p50={s['latency_p50_ms']}ms "
            f"p95={s['latency_p95_ms']}ms "
            f"p99={s['latency_p99_ms']}ms "
            f"throughput={s['throughput_rps']} req/s"
        )

    write_csv(out_dir / "summary.csv", summaries)
    write_csv(out_dir / "raw_requests.csv", all_results)
    write_csv(out_dir / "resource_samples.csv", all_resources)
    write_report(out_dir / "report.md", summaries, args)

    print(f"\n[OUTPUT] {out_dir.resolve()}")


def build_parser():
    p = argparse.ArgumentParser(description="FastAPI/HTTP Agent 性能、并发和资源基线测试")
    p.add_argument("--url", required=True, help="Agent POST 接口完整 URL")
    p.add_argument("--cases", default="perf_test/perf_cases.jsonl", help="JSONL 请求体文件")
    p.add_argument("--concurrency", default="1,5,10,20", help="并发级别")
    p.add_argument("--requests-per-level", type=int, default=100, help="每个并发级别请求数")
    p.add_argument("--warmup", type=int, default=5, help="正式测试前预热请求数")
    p.add_argument("--timeout", type=float, default=120.0, help="单请求超时秒数")
    p.add_argument("--label", default="int4", help="运行标签，例如 fp16/int8/int4")
    p.add_argument("--out", default="perf_results", help="结果根目录")
    p.add_argument("--pid", type=int, default=None, help="FastAPI/Agent 进程 PID，用于进程 RSS/CPU 监控")
    p.add_argument("--header", action="append", default=[], help="HTTP header，可重复，例如 --header \"Authorization: Bearer xxx\"")
    p.add_argument("--verify-ssl", action="store_true", help="启用 SSL 证书校验；本地 HTTP 通常无需设置")
    return p


if __name__ == "__main__":
    args = build_parser().parse_args()
    if args.requests_per_level <= 0:
        raise SystemExit("--requests-per-level 必须 > 0")
    asyncio.run(main_async(args))
