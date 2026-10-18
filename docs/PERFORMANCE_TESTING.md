# Agent 性能、并发与资源测试说明

## 1. 为什么当前仓库需要补这一层

当前项目已经具备两类评测：

1. **质量 / 鲁棒性评测**：关注诊断或辅助生成在不同输入扰动下是否保持预期行为。
2. **量化模型基准**：`scripts/benchmark_quantization_v2.py` 已比较 FP16 / INT8 / INT4 的生成时延、tokens/s、模型内存和峰值显存。

因此第二阶段不应该再次写一套“模型量化性能脚本”，而应补充：

> FastAPI → LangGraph → 资源查询 → 证据解析 → 确定性诊断 → RAG → 报告生成 → HITL → 归档

这一完整系统链路的端到端性能和稳定性。

## 2. 实际接口

当前代码定义的主接口是：

- `POST /api/v1/incidents`
- `POST /api/v1/incidents/{thread_id}/resume`
- `GET /api/v1/system/model`
- `GET /health`

请求体直接复用 `data/sample_requests/*.json`，与 `StartIncidentRequest` 一致，不增加虚构的 query API。

## 3. 两种时延

### Start latency

从创建 incident 到：

- 解析
- 诊断
- RAG
- 报告生成
- `awaiting_approval`

结束。

### End-to-end latency

在 `REQUIRE_APPROVAL=true` 时继续执行：

- resume approval
- finalize
- 报告归档
- `completed`

因此完整 E2E 比 start 多了 HITL resume/finalize。

## 4. 推荐正式基线

### 确定性核心

```env
REQUIRE_APPROVAL=true
RAG_ENABLED=false
LLM_ENABLED=false
```

建议：

```powershell
python -m scripts.benchmark_agent_e2e `
  --label deterministic_core `
  --mode full `
  --concurrency 1 5 10 20 `
  --requests-per-level 50 `
  --repeats 3
```

### 完整 INT4

```env
REQUIRE_APPROVAL=true
RAG_ENABLED=true
LLM_ENABLED=true
LLM_BACKEND=local_hf
LOCAL_LLM_QUANTIZATION=int4
LOCAL_LLM_MAX_NEW_TOKENS=96
LOCAL_LLM_TEMPERATURE=0.0
```

建议：

```powershell
python -m scripts.benchmark_agent_e2e `
  --label int4_full `
  --mode full `
  --concurrency 1 2 5 10 `
  --requests-per-level 20 `
  --repeats 3
```

完整本地模型场景先使用 1/2/5/10，而不是直接把 20 并发写成“必须达标”。如果 10 并发仍稳定，再增加 20。

## 5. 指标解释

- `success_rate_pct`：HTTP 和工作流业务状态同时成功。
- `throughput_rps`：完整请求吞吐。
- `e2e_p50_ms`：中位端到端时延。
- `e2e_p95_ms` / `e2e_p99_ms`：尾延迟。
- `process_rss_peak_mb`：指定 uvicorn PID 后的进程峰值 RSS。
- `gpu_mem_peak_mb`：整卡 nvidia-smi 采样值。
- `llm_mean_latency_ms`：来自报告 generation_meta 的本地/远端 LLM 生成时延。

## 6. 与量化基准的边界

`benchmark_quantization_v2.py` 的 `peak_gpu_memory_mb` 更适合描述**模型自身推理峰值显存**。

`benchmark_agent_e2e.py` 的 `gpu_mem_peak_mb` 更适合描述**完整运行环境下 GPU 总占用**。

两者不要混为同一口径。

## 7. 简历中最终希望形成的证据链

第一阶段：

> 通过基线、格式扰动、证据缺失、上下文噪声、冲突证据、安全边界和语义改写测试发现具体失效模式。

第二阶段：

> 建立端到端性能基线，在不同并发下统计成功率、P50/P95/P99、吞吐与 CPU/内存/GPU 资源占用，并区分确定性核心、RAG 与本地 INT4 模型带来的系统开销。

第三阶段再将稳定的质量和性能阈值接入 CI/CD 回归门禁。
