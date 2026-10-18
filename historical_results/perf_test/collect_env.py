from __future__ import annotations

import json
import platform
import subprocess
import sys
from pathlib import Path

import psutil


def gpu_info():
    cmd = [
        "nvidia-smi",
        "--query-gpu=name,driver_version,memory.total",
        "--format=csv,noheader,nounits",
    ]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=3, check=True)
        gpus = []
        for row in p.stdout.splitlines():
            row = row.strip()
            if not row:
                continue
            name, driver, mem = [x.strip() for x in row.split(",", 2)]
            gpus.append({
                "name": name,
                "driver_version": driver,
                "memory_total_mb": float(mem),
            })
        return gpus
    except Exception:
        return []


info = {
    "platform": platform.platform(),
    "python": sys.version,
    "processor": platform.processor(),
    "logical_cpu_count": psutil.cpu_count(logical=True),
    "physical_cpu_count": psutil.cpu_count(logical=False),
    "ram_total_gb": round(psutil.virtual_memory().total / 1024**3, 3),
    "gpus": gpu_info(),
}

out = Path("perf_results") / "environment.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(info, ensure_ascii=False, indent=2))
print(f"\n[OUTPUT] {out.resolve()}")
