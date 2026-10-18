# TNO·AI Agent 性能 / 并发 / 资源测试

这套文件只负责第二阶段测试：

1. 端到端延迟：Avg / P50 / P95 / P99 / Max
2. 并发：1 / 5 / 10 / 20
3. 吞吐量：requests/s
4. 稳定性：HTTP 成功率
5. 资源：系统 CPU / 内存；可选 Agent 进程 RSS / CPU；NVIDIA GPU 利用率 / 显存
6. FP16 / INT8 / INT4 可重复对比

它**不替代**第一阶段的功能正确性、鲁棒性和安全边界测试。

---

## 0. 先改请求样例

`perf_cases.jsonl` 每一行就是一次 POST 的 JSON 请求体。

当前文件中的 `{"query": "..."}` 只是模板。你必须按照你当前 FastAPI 接口真正接受的 JSON schema 修改，例如你的接口如果实际要求：

```json
{"ip":"10.0.0.1","question":"检查端口状态"}
```

那么 JSONL 也应改成该结构。

性能测试不需要 350 条质量测试全部放进来。建议选择 5~20 条能稳定走完整 Agent 主链路的代表性请求，然后循环压测。

---

## 1. 安装

在项目根目录执行：

```bat
python -m pip install -r perf_test\requirements-perf.txt
```

---

## 2. 启动你原来的 Agent / FastAPI

继续使用你项目原来的启动命令。

确认实际 POST 接口，例如：

```text
http://127.0.0.1:8000/你的真实接口
```

先在浏览器的 `/docs` 或你原来的调用脚本中确认路径和请求 JSON，不要为了测试新造一个接口。

---

## 3. 记录测试机器环境

```bat
python perf_test\collect_env.py
```

输出：

```text
perf_results\environment.json
```

用于记录 CPU、RAM、GPU、Python 环境，保证以后比较 INT4/INT8/FP16 时环境一致。

---

## 4. 第一轮：INT4

假设真实接口为：

```text
http://127.0.0.1:8000/diagnose
```

执行：

```bat
python perf_test\benchmark_agent.py ^
  --url http://127.0.0.1:8000/diagnose ^
  --cases perf_test\perf_cases.jsonl ^
  --concurrency 1,5,10,20 ^
  --requests-per-level 100 ^
  --warmup 5 ^
  --timeout 120 ^
  --label int4
```

结果：

```text
perf_results\int4\summary.csv
perf_results\int4\raw_requests.csv
perf_results\int4\resource_samples.csv
perf_results\int4\report.md
```

---

## 5. 监控 Agent 自身进程内存（推荐）

默认只能统计整机 CPU/内存。

先查 FastAPI / Python 进程 PID。

### Windows PowerShell

```powershell
Get-Process python | Select-Object Id,ProcessName,CPU,WorkingSet
```

假设 Agent PID 为 `12345`：

```bat
python perf_test\benchmark_agent.py ^
  --url http://127.0.0.1:8000/diagnose ^
  --cases perf_test\perf_cases.jsonl ^
  --concurrency 1,5,10,20 ^
  --requests-per-level 100 ^
  --warmup 5 ^
  --timeout 120 ^
  --label int4 ^
  --pid 12345
```

这样 `summary.csv` 中会多出 Agent 进程峰值 RSS。

---

## 6. FP16 / INT8 / INT4 对比

**不要在同一次 Agent 进程里临时切模型。**

每次按你项目现有方式启动对应模型配置，保持：
- 测试机器相同
- 请求集相同
- 并发级别相同
- 请求数相同
- timeout 相同

分别执行：

```bat
python perf_test\benchmark_agent.py --url http://127.0.0.1:8000/diagnose --cases perf_test\perf_cases.jsonl --concurrency 1,5,10,20 --requests-per-level 100 --warmup 5 --timeout 120 --label fp16
```

```bat
python perf_test\benchmark_agent.py --url http://127.0.0.1:8000/diagnose --cases perf_test\perf_cases.jsonl --concurrency 1,5,10,20 --requests-per-level 100 --warmup 5 --timeout 120 --label int8
```

```bat
python perf_test\benchmark_agent.py --url http://127.0.0.1:8000/diagnose --cases perf_test\perf_cases.jsonl --concurrency 1,5,10,20 --requests-per-level 100 --warmup 5 --timeout 120 --label int4
```

然后：

```bat
python perf_test\compare_runs.py ^
  perf_results\fp16\summary.csv ^
  perf_results\int8\summary.csv ^
  perf_results\int4\summary.csv
```

---

## 7. 如果接口有 Header

例如：

```bat
python perf_test\benchmark_agent.py ^
  --url http://127.0.0.1:8000/diagnose ^
  --header "Authorization: Bearer YOUR_TOKEN" ^
  --label int4
```

不要把真实 token 提交到 GitHub。

---

## 8. 如何看结果

重点看：

1. `success_rate_pct`
   - 并发提高后是否下降。
2. `latency_p50_ms`
   - 普通请求的典型体验。
3. `latency_p95_ms` / `latency_p99_ms`
   - 尾延迟；AI 服务不能只看平均时延。
4. `throughput_rps`
   - 并发提高后实际吞吐是否提升。
5. `process_rss_peak_mb`
   - 需要传 `--pid`。
6. `gpu_mem_peak_mb`
   - 本机存在 NVIDIA GPU 且 `nvidia-smi` 可用时自动采集。

本阶段先建立**基线**，不要人为设“必须 P95 < 某数值”的门槛。
等真实结果跑出来后，再根据你的机器和模型形成验收阈值，第三阶段放进 CI/CD 回归门禁。

---

## 9. 建议第一轮固定协议

```text
Warmup         = 5
Requests/level = 100
Concurrency    = 1, 5, 10, 20
Timeout        = 120 s
Cases          = 同一批 5~20 条主链路请求
Repeat         = 最好独立重复 3 次后再总结
```

如果本地小模型在 20 并发时大量 timeout，不代表脚本有问题；先保留失败结果，再决定是否把后续正式基线调整成 1/2/5/10。

---

## 10. Windows 一键运行

先修改 `run_perf_windows.bat` 中的 URL，或者：

```bat
set AGENT_URL=http://127.0.0.1:8000/你的真实接口
set MODEL_LABEL=int4
perf_test\run_perf_windows.bat
```
