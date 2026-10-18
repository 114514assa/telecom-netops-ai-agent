from __future__ import annotations

import argparse
import asyncio
import csv
import json
import math
import os
import platform
import statistics
import subprocess
import threading
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import psutil


DEFAULT_CASE_ORDER = [
    "interface_down.json",
    "no_mac.json",
    "vlan_mismatch.json",
    "upstream.json",
    "resource_mismatch.json",
]


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


def round_or_none(value: float | None, digits: int = 3) -> float | None:
    return round(value, digits) if value is not None else None


def load_cases(case_dir: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for name in DEFAULT_CASE_ORDER:
        path = case_dir / name
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or "incident" not in payload or "evidence" not in payload:
            raise ValueError(f"{path} must contain top-level incident and evidence objects")
        cases.append({"case_name": path.stem, "payload": payload})
    if not cases:
        raise FileNotFoundError(
            f"No performance cases found in {case_dir}. "
            f"Expected one or more of: {', '.join(DEFAULT_CASE_ORDER)}"
        )
    return cases


def query_gpu() -> dict[str, float | str | None]:
    cmd = [
        "nvidia-smi",
        "--query-gpu=name,utilization.gpu,memory.used,memory.total",
        "--format=csv,noheader,nounits",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3, check=True)
        rows = [x.strip() for x in proc.stdout.splitlines() if x.strip()]
        if not rows:
            raise RuntimeError("no GPU rows")
        # Project demo is expected to use a single local GPU. Record the first GPU explicitly.
        name, util, used, total = [x.strip() for x in rows[0].split(",", 3)]
        return {
            "gpu_name": name,
            "gpu_util_pct": float(util),
            "gpu_mem_used_mb": float(used),
            "gpu_mem_total_mb": float(total),
        }
    except Exception:
        return {
            "gpu_name": None,
            "gpu_util_pct": None,
            "gpu_mem_used_mb": None,
            "gpu_mem_total_mb": None,
        }


def process_snapshot(pid: int | None) -> tuple[float | None, float | None]:
    if pid is None:
        return None, None
    try:
        proc = psutil.Process(pid)
        return proc.cpu_percent(interval=None), proc.memory_info().rss / 1024 / 1024
    except psutil.Error:
        return None, None


class ResourceSampler:
    def __init__(self, *, pid: int | None, label: str, concurrency: int, interval: float = 0.5):
        self.pid = pid
        self.label = label
        self.concurrency = concurrency
        self.interval = interval
        self.rows: list[dict[str, Any]] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._process: psutil.Process | None = None
        if pid is not None:
            try:
                self._process = psutil.Process(pid)
                self._process.cpu_percent(interval=None)
            except psutil.Error:
                self._process = None
        psutil.cpu_percent(interval=None)

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop.is_set():
            vm = psutil.virtual_memory()
            row: dict[str, Any] = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "label": self.label,
                "concurrency": self.concurrency,
                "system_cpu_pct": psutil.cpu_percent(interval=None),
                "system_mem_pct": vm.percent,
                "system_mem_used_mb": vm.used / 1024 / 1024,
                "process_cpu_pct": None,
                "process_rss_mb": None,
            }
            if self._process is not None:
                try:
                    row["process_cpu_pct"] = self._process.cpu_percent(interval=None)
                    row["process_rss_mb"] = self._process.memory_info().rss / 1024 / 1024
                except psutil.Error:
                    self._process = None
            row.update(query_gpu())
            self.rows.append(row)
            self._stop.wait(self.interval)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(2.0, self.interval * 4))


@dataclass
class RequestRow:
    label: str
    repeat: int
    concurrency: int
    request_index: int
    case_name: str
    success: bool
    http_status_start: int | None
    http_status_resume: int | None
    start_workflow_status: str | None
    final_workflow_status: str | None
    start_latency_ms: float
    resume_latency_ms: float | None
    e2e_latency_ms: float
    diagnosis_code: str | None
    report_generated_by: str | None
    rag_hit_count: int | None
    llm_latency_ms: float | None
    llm_tokens_per_second: float | None
    llm_output_tokens: int | None
    llm_peak_gpu_memory_mb: float | None
    guardrail_passed: bool | None = None
    guardrail_reasons: str = ""  # code-only, never the raw candidate
    fallback_reason: str | None = None
    error: str = ""


def extract_state_metadata(data: dict[str, Any]) -> dict[str, Any]:
    state = data.get("state") if isinstance(data, dict) else None
    if not isinstance(state, dict):
        state = {}

    diagnosis = state.get("diagnosis")
    if not isinstance(diagnosis, dict):
        diagnosis = {}

    report = state.get("report")
    if not isinstance(report, dict):
        report = {}

    generation_meta = report.get("generation_meta")
    if not isinstance(generation_meta, dict):
        generation_meta = {}

    hits = state.get("knowledge_hits")
    if not isinstance(hits, list):
        hits = None

    return {
        "diagnosis_code": diagnosis.get("code"),
        "report_generated_by": report.get("generated_by"),
        "rag_hit_count": len(hits) if hits is not None else None,
        "llm_latency_ms": generation_meta.get("latency_ms"),
        "llm_tokens_per_second": generation_meta.get("tokens_per_second"),
        "llm_output_tokens": generation_meta.get("output_tokens"),
        "llm_peak_gpu_memory_mb": generation_meta.get("peak_gpu_memory_mb"),
        "guardrail_passed": generation_meta.get("guardrail_passed"),
        "guardrail_reasons": "|".join(generation_meta.get("guardrail_reasons") or []),
        "fallback_reason": generation_meta.get("fallback_reason"),
    }


async def request_once(
    *,
    client: httpx.AsyncClient,
    base_url: str,
    case_name: str,
    payload: dict[str, Any],
    label: str,
    repeat: int,
    concurrency: int,
    request_index: int,
    mode: str,
) -> RequestRow:
    start_http: int | None = None
    resume_http: int | None = None
    start_status: str | None = None
    final_status: str | None = None
    resume_latency_ms: float | None = None
    metadata: dict[str, Any] = {}

    started_e2e = time.perf_counter()
    t0 = time.perf_counter()
    try:
        response = await client.post(f"{base_url}/api/v1/incidents", json=payload)
        start_latency_ms = (time.perf_counter() - t0) * 1000
        start_http = response.status_code
        response.raise_for_status()
        data = response.json()

        start_status = data.get("status")
        final_status = start_status
        metadata = extract_state_metadata(data)
        thread_id = data.get("thread_id")

        if mode == "full" and start_status == "awaiting_approval":
            if not thread_id:
                raise RuntimeError("start response is awaiting_approval but thread_id is missing")
            t1 = time.perf_counter()
            resume_response = await client.post(
                f"{base_url}/api/v1/incidents/{thread_id}/resume",
                json={"approved": True, "comment": "performance benchmark approval"},
            )
            resume_latency_ms = (time.perf_counter() - t1) * 1000
            resume_http = resume_response.status_code
            resume_response.raise_for_status()
            resume_data = resume_response.json()
            final_status = resume_data.get("status")
            # Resume response can still carry the same state/report metadata.
            resumed_meta = extract_state_metadata(resume_data)
            for key, value in resumed_meta.items():
                if value is not None:
                    metadata[key] = value

        if mode == "start":
            success = start_status in {"awaiting_approval", "completed"}
        else:
            success = final_status == "completed"

        e2e_ms = (time.perf_counter() - started_e2e) * 1000
        return RequestRow(
            label=label,
            repeat=repeat,
            concurrency=concurrency,
            request_index=request_index,
            case_name=case_name,
            success=success,
            http_status_start=start_http,
            http_status_resume=resume_http,
            start_workflow_status=start_status,
            final_workflow_status=final_status,
            start_latency_ms=round(start_latency_ms, 3),
            resume_latency_ms=round(resume_latency_ms, 3) if resume_latency_ms is not None else None,
            e2e_latency_ms=round(e2e_ms, 3),
            diagnosis_code=metadata.get("diagnosis_code"),
            report_generated_by=metadata.get("report_generated_by"),
            rag_hit_count=metadata.get("rag_hit_count"),
            llm_latency_ms=metadata.get("llm_latency_ms"),
            llm_tokens_per_second=metadata.get("llm_tokens_per_second"),
            llm_output_tokens=metadata.get("llm_output_tokens"),
            llm_peak_gpu_memory_mb=metadata.get("llm_peak_gpu_memory_mb"),
            guardrail_passed=metadata.get("guardrail_passed"),
            guardrail_reasons=metadata.get("guardrail_reasons") or "",
            fallback_reason=metadata.get("fallback_reason"),
            error="" if success else f"unexpected workflow status: {final_status}",
        )
    except Exception as exc:
        e2e_ms = (time.perf_counter() - started_e2e) * 1000
        start_ms = (time.perf_counter() - t0) * 1000 if start_http is None else 0.0
        return RequestRow(
            label=label,
            repeat=repeat,
            concurrency=concurrency,
            request_index=request_index,
            case_name=case_name,
            success=False,
            http_status_start=start_http,
            http_status_resume=resume_http,
            start_workflow_status=start_status,
            final_workflow_status=final_status,
            start_latency_ms=round(start_ms, 3),
            resume_latency_ms=round(resume_latency_ms, 3) if resume_latency_ms is not None else None,
            e2e_latency_ms=round(e2e_ms, 3),
            diagnosis_code=metadata.get("diagnosis_code"),
            report_generated_by=metadata.get("report_generated_by"),
            rag_hit_count=metadata.get("rag_hit_count"),
            llm_latency_ms=metadata.get("llm_latency_ms"),
            llm_tokens_per_second=metadata.get("llm_tokens_per_second"),
            llm_output_tokens=metadata.get("llm_output_tokens"),
            llm_peak_gpu_memory_mb=metadata.get("llm_peak_gpu_memory_mb"),
            guardrail_passed=metadata.get("guardrail_passed"),
            guardrail_reasons=metadata.get("guardrail_reasons") or "",
            fallback_reason=metadata.get("fallback_reason"),
            error=f"{type(exc).__name__}: {str(exc)[:400]}",
        )


async def run_level(
    *,
    base_url: str,
    cases: list[dict[str, Any]],
    label: str,
    repeat: int,
    concurrency: int,
    requests_per_level: int,
    timeout_seconds: float,
    mode: str,
    pid: int | None,
) -> tuple[list[RequestRow], list[dict[str, Any]], float]:
    limits = httpx.Limits(
        max_connections=max(1, concurrency),
        max_keepalive_connections=max(1, concurrency),
    )
    timeout = httpx.Timeout(timeout_seconds)
    semaphore = asyncio.Semaphore(concurrency)

    sampler = ResourceSampler(pid=pid, label=label, concurrency=concurrency)
    sampler.start()
    wall_started = time.perf_counter()

    async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
        async def worker(i: int) -> RequestRow:
            case = cases[i % len(cases)]
            async with semaphore:
                return await request_once(
                    client=client,
                    base_url=base_url,
                    case_name=case["case_name"],
                    payload=case["payload"],
                    label=label,
                    repeat=repeat,
                    concurrency=concurrency,
                    request_index=i,
                    mode=mode,
                )

        rows = await asyncio.gather(*(worker(i) for i in range(requests_per_level)))

    elapsed = time.perf_counter() - wall_started
    sampler.stop()
    return rows, sampler.rows, elapsed


def vals(rows: list[dict[str, Any]], key: str) -> list[float]:
    out: list[float] = []
    for row in rows:
        value = row.get(key)
        if value is not None:
            try:
                out.append(float(value))
            except (TypeError, ValueError):
                pass
    return out


def summarize_requests(
    *,
    label: str,
    repeat: int,
    concurrency: int,
    rows: list[RequestRow],
    resource_rows: list[dict[str, Any]],
    elapsed_seconds: float,
) -> dict[str, Any]:
    e2e = [r.e2e_latency_ms for r in rows]
    start = [r.start_latency_ms for r in rows]
    llm = [float(r.llm_latency_ms) for r in rows if r.llm_latency_ms is not None]
    ok = sum(1 for r in rows if r.success)
    total = len(rows)

    process_rss = vals(resource_rows, "process_rss_mb")
    system_cpu = vals(resource_rows, "system_cpu_pct")
    system_mem = vals(resource_rows, "system_mem_pct")
    gpu_util = vals(resource_rows, "gpu_util_pct")
    gpu_mem = vals(resource_rows, "gpu_mem_used_mb")

    return {
        "label": label,
        "repeat": repeat,
        "concurrency": concurrency,
        "requests": total,
        "success_count": ok,
        "failure_count": total - ok,
        "success_rate_pct": round(ok / total * 100, 3) if total else 0.0,
        "wall_seconds": round(elapsed_seconds, 3),
        "throughput_rps": round(total / elapsed_seconds, 4) if elapsed_seconds > 0 else None,
        "start_p50_ms": round_or_none(percentile(start, 0.50)),
        "start_p95_ms": round_or_none(percentile(start, 0.95)),
        "e2e_mean_ms": round(statistics.mean(e2e), 3) if e2e else None,
        "e2e_p50_ms": round_or_none(percentile(e2e, 0.50)),
        "e2e_p95_ms": round_or_none(percentile(e2e, 0.95)),
        "e2e_p99_ms": round_or_none(percentile(e2e, 0.99)),
        "e2e_max_ms": round(max(e2e), 3) if e2e else None,
        "llm_mean_latency_ms": round(statistics.mean(llm), 3) if llm else None,
        "system_cpu_avg_pct": round(statistics.mean(system_cpu), 3) if system_cpu else None,
        "system_cpu_peak_pct": round(max(system_cpu), 3) if system_cpu else None,
        "system_mem_peak_pct": round(max(system_mem), 3) if system_mem else None,
        "process_rss_peak_mb": round(max(process_rss), 3) if process_rss else None,
        "gpu_util_peak_pct": round(max(gpu_util), 3) if gpu_util else None,
        "gpu_mem_peak_mb": round(max(gpu_mem), 3) if gpu_mem else None,
    }


def aggregate_repeats(summary_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for row in summary_rows:
        groups.setdefault((str(row["label"]), int(row["concurrency"])), []).append(row)

    metric_keys = [
        "success_rate_pct",
        "throughput_rps",
        "start_p50_ms",
        "start_p95_ms",
        "e2e_mean_ms",
        "e2e_p50_ms",
        "e2e_p95_ms",
        "e2e_p99_ms",
        "e2e_max_ms",
        "llm_mean_latency_ms",
        "system_cpu_avg_pct",
        "system_cpu_peak_pct",
        "system_mem_peak_pct",
        "process_rss_peak_mb",
        "gpu_util_peak_pct",
        "gpu_mem_peak_mb",
    ]
    out: list[dict[str, Any]] = []
    for (label, concurrency), rows in sorted(groups.items(), key=lambda x: x[0][1]):
        item: dict[str, Any] = {
            "label": label,
            "concurrency": concurrency,
            "repeats": len(rows),
        }
        for key in metric_keys:
            values = [float(r[key]) for r in rows if r.get(key) is not None]
            item[f"{key}_mean"] = round(statistics.mean(values), 3) if values else None
            item[f"{key}_std"] = round(statistics.stdev(values), 3) if len(values) > 1 else 0.0 if values else None
        out.append(item)
    return out


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                keys.append(key)
                seen.add(key)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


async def fetch_json(client: httpx.AsyncClient, url: str) -> dict[str, Any] | None:
    try:
        response = await client.get(url)
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, dict) else {"value": data}
    except Exception:
        return None


async def preflight(base_url: str, timeout_seconds: float) -> tuple[dict[str, Any], dict[str, Any]]:
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        health = await fetch_json(client, f"{base_url}/health")
        model = await fetch_json(client, f"{base_url}/api/v1/system/model")
    if not health or health.get("status") != "ok" or not health.get("workflow_ready"):
        raise RuntimeError(
            f"Agent preflight failed at {base_url}/health. "
            f"Start uvicorn first and confirm workflow_ready=true. health={health}"
        )
    if not model:
        raise RuntimeError(f"Cannot read {base_url}/api/v1/system/model")
    return health, model


async def warmup(
    *,
    base_url: str,
    cases: list[dict[str, Any]],
    n: int,
    timeout_seconds: float,
    mode: str,
) -> None:
    if n <= 0:
        return
    limits = httpx.Limits(max_connections=1, max_keepalive_connections=1)
    async with httpx.AsyncClient(timeout=timeout_seconds, limits=limits) as client:
        for i in range(n):
            case = cases[i % len(cases)]
            row = await request_once(
                client=client,
                base_url=base_url,
                case_name=case["case_name"],
                payload=case["payload"],
                label="warmup",
                repeat=0,
                concurrency=1,
                request_index=i,
                mode=mode,
            )
            if not row.success:
                raise RuntimeError(f"Warmup request failed: {row.error}")


def local_environment() -> dict[str, Any]:
    vm = psutil.virtual_memory()
    gpu = query_gpu()
    return {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu": platform.processor(),
        "logical_cpu_count": psutil.cpu_count(logical=True),
        "physical_cpu_count": psutil.cpu_count(logical=False),
        "ram_total_gb": round(vm.total / 1024**3, 3),
        **gpu,
    }


def write_markdown_report(
    path: Path,
    *,
    args: argparse.Namespace,
    model_config: dict[str, Any],
    aggregate_rows: list[dict[str, Any]],
) -> None:
    lines = [
        "# Telecom NetOps AI Agent 端到端性能测试",
        "",
        f"- Label: `{args.label}`",
        f"- Mode: `{args.mode}`",
        f"- Base URL: `{args.base_url}`",
        f"- Concurrency: `{','.join(str(x) for x in args.concurrency)}`",
        f"- Requests/level: `{args.requests_per_level}`",
        f"- Repeats: `{args.repeats}`",
        f"- Warmup: `{args.warmup}`",
        "",
        "## 服务配置",
        "",
        "```json",
        json.dumps(model_config, ensure_ascii=False, indent=2),
        "```",
        "",
        "## 聚合结果",
        "",
        "|并发|成功率均值|吞吐均值(req/s)|E2E P50均值(ms)|E2E P95均值(ms)|E2E P99均值(ms)|进程RSS峰值均值(MB)|GPU显存峰值均值(MB)|",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in aggregate_rows:
        def f(key: str) -> str:
            value = row.get(key)
            return "-" if value is None else str(value)
        lines.append(
            f"|{row['concurrency']}|{f('success_rate_pct_mean')}%|{f('throughput_rps_mean')}|"
            f"{f('e2e_p50_ms_mean')}|{f('e2e_p95_ms_mean')}|{f('e2e_p99_ms_mean')}|"
            f"{f('process_rss_peak_mb_mean')}|{f('gpu_mem_peak_mb_mean')}|"
        )

    lines += [
        "",
        "## 解释边界",
        "",
        "- `start_latency`：POST `/api/v1/incidents` 从请求开始，到报告生成并进入 `awaiting_approval`（或审批关闭时直接 completed）的时间。",
        "- `e2e_latency`：`mode=full` 时包含 start + HITL resume + finalize；`mode=start` 时等于 start 阶段。",
        "- HTTP 2xx 不直接算成功；脚本同时校验业务状态。full 模式必须最终为 `completed`。",
        "- `llm_*` 来源于报告 `generation_meta`，只有 LLM 真正运行时才有值。",
        "- `gpu_mem_peak_mb` 来自 `nvidia-smi` 的整卡采样，可能同时包含 Ollama 和本地 HF 模型，不应直接称为“模型独占显存”。",
        "- 性能测试时使用单 worker、关闭 `--reload`。不要用多个 worker 复制本地 HF 模型后再把结果当作单实例基线。",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


async def main_async(args: argparse.Namespace) -> None:
    base_url = args.base_url.rstrip("/")
    cases = load_cases(Path(args.case_dir))
    health, model_config = await preflight(base_url, args.timeout)

    print("[PREFLIGHT] health =", json.dumps(health, ensure_ascii=False))
    print("[PREFLIGHT] model  =", json.dumps(model_config, ensure_ascii=False))
    print("[CASES] ", ", ".join(x["case_name"] for x in cases))

    await warmup(
        base_url=base_url,
        cases=cases,
        n=args.warmup,
        timeout_seconds=args.timeout,
        mode=args.mode,
    )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = Path(args.output_dir) / f"{args.label}_{stamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    request_rows: list[RequestRow] = []
    resource_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []

    for repeat in range(1, args.repeats + 1):
        for concurrency in args.concurrency:
            print(f"[RUN] repeat={repeat}/{args.repeats}, concurrency={concurrency}")
            rows, resources, elapsed = await run_level(
                base_url=base_url,
                cases=cases,
                label=args.label,
                repeat=repeat,
                concurrency=concurrency,
                requests_per_level=args.requests_per_level,
                timeout_seconds=args.timeout,
                mode=args.mode,
                pid=args.pid,
            )
            summary = summarize_requests(
                label=args.label,
                repeat=repeat,
                concurrency=concurrency,
                rows=rows,
                resource_rows=resources,
                elapsed_seconds=elapsed,
            )
            request_rows.extend(rows)
            resource_rows.extend(resources)
            summary_rows.append(summary)
            print(
                f"[DONE] success={summary['success_rate_pct']}% "
                f"throughput={summary['throughput_rps']} req/s "
                f"p50={summary['e2e_p50_ms']} ms "
                f"p95={summary['e2e_p95_ms']} ms "
                f"p99={summary['e2e_p99_ms']} ms"
            )

    aggregate_rows = aggregate_repeats(summary_rows)

    write_csv(output_dir / "agent_perf_detail.csv", [asdict(x) for x in request_rows])
    write_csv(output_dir / "agent_perf_resources.csv", resource_rows)
    write_csv(output_dir / "agent_perf_by_repeat.csv", summary_rows)
    write_csv(output_dir / "agent_perf_summary.csv", aggregate_rows)

    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "benchmark_version": "agent-e2e-v2",
        "label": args.label,
        "mode": args.mode,
        "base_url": base_url,
        "case_dir": args.case_dir,
        "case_names": [x["case_name"] for x in cases],
        "concurrency": args.concurrency,
        "requests_per_level": args.requests_per_level,
        "repeats": args.repeats,
        "warmup": args.warmup,
        "timeout_seconds": args.timeout,
        "pid": args.pid,
        "health": health,
        "model_config": model_config,
        "local_environment": local_environment(),
        "summary": aggregate_rows,
    }
    (output_dir / "agent_perf_run.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_markdown_report(
        output_dir / "agent_perf_report.md",
        args=args,
        model_config=model_config,
        aggregate_rows=aggregate_rows,
    )

    print(f"\n[OUTPUT] {output_dir.resolve()}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Telecom NetOps AI Agent FastAPI -> LangGraph end-to-end performance benchmark"
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--case-dir", default="data/sample_requests")
    parser.add_argument("--label", default="int4_full")
    parser.add_argument("--mode", choices=["start", "full"], default="full")
    parser.add_argument("--concurrency", nargs="+", type=int, default=[1, 2, 5, 10])
    parser.add_argument("--requests-per-level", type=int, default=20)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--pid", type=int, default=None)
    parser.add_argument("--output-dir", default="runtime/perf_e2e")
    args = parser.parse_args()

    if any(x <= 0 for x in args.concurrency):
        parser.error("--concurrency values must be positive")
    if args.requests_per_level <= 0:
        parser.error("--requests-per-level must be positive")
    if args.repeats <= 0:
        parser.error("--repeats must be positive")
    if args.warmup < 0:
        parser.error("--warmup must be >= 0")
    return args


if __name__ == "__main__":
    asyncio.run(main_async(parse_args()))
