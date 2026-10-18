> 本文件从 V3.1.0 更新为 V3.1.1。版本差异请先阅读 `docs/iterations/V3_1_1_HOTFIX.md`。

# V3.1.1 Windows 独立运行和复测命令

> **不要把本包内容覆盖到 `telecom-netops-ai-agent-hardened`。**
> 将 `telecom-netops-ai-agent-v3.1.1` 整个新文件夹解压到与旧 V2 同一级目录。原 V2 `.venv`、`.env`、`runtime`、Qwen 模型缓存均保留不动。所有命令在 PowerShell 中执行。

## 1. 在新目录执行环境脚本

```powershell
$Project = 'C:\Users\Lenovo\Desktop\秋招\agent教学\telecom-netops-ai-agent_B7E78B8AE5BAAEE6B4BAE781\telecom-netops-ai-agent-v3.1.1'
Set-Location -LiteralPath $Project
. .\RUN_V3_1_ENV.ps1
# 如果未自动找到旧 .venv，显式指定旧路径：
# . .\RUN_V3_1_ENV.ps1 -VenvPython 'C:\...\telecom-netops-ai-agent-hardened\.venv\Scripts\python.exe'
& $Py -m pip check
```

环境脚本自动隔离 `runtime_v3_1_1`，默认 RAG/LLM 关闭；旧 `.env` 中废弃的远程 API 不会复制进新包。**如手动创建新 `.env`，不得带入过期密钥。**

## 2. 先验证新旧功能

```powershell
& $Py -m pytest -q tests/test_guardrail_v3_1.py tests/test_report_guardrails.py --tb=short
& $Py -m pytest -q --tb=short
```

新用例还包含 `tests/test_report_composer_v3_1.py`，依赖你的 LangChain 环境。检查 84 项原有测试和新增测试是否都通过，不应先验假设测试数。

## 3. 初始化 V3.1 专用运行目录

```powershell
& $Py -m scripts.seed_db
$env:RAG_ENABLED = 'true'
& $Py -m scripts.build_vector_index
& $Py -m scripts.test_vector_retrieval
```

验证生成 `runtime_v3_1_1/vector_index/knowledge.faiss`，不使用旧 V2 `runtime/vector_index/knowledge.faiss`。

## 4. V3.1 Qwen INT4 端到端冒烟

同一个终端设置：

```powershell
$env:LLM_ENABLED = 'true'
$env:LLM_BACKEND = 'local_hf'
$env:LOCAL_LLM_QUANTIZATION = 'int4'
$env:RAG_ENABLED = 'true'
$env:DEMO_AUTH_ENABLED = 'false'   # 仅本机隔离演示
& $Py -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --workers 1
```

在第二个 PowerShell 里再次进入 V3.1 目录和 `. .\\RUN_V3_1_ENV.ps1`，该脚本只设置第二个终端的环境。随后：

```powershell
Invoke-RestMethod 'http://127.0.0.1:8001/health'
Invoke-RestMethod 'http://127.0.0.1:8001/api/v1/system/model' | Format-List
& $Py -m scripts.benchmark_agent_e2e `
  --base-url http://127.0.0.1:8001 `
  --label v3_1_1_local_int4_smoke --mode full `
  --concurrency 1 --requests-per-level 5 --repeats 1 --warmup 1 `
  --timeout 180 --output-dir runtime_v3_1_1/perf_e2e
```

**关键：**第二个终端环境脚本默认关闭 LLM/RAG，但服务器运行在第一个终端并已开启 LLM/RAG。以服务端 `/api/v1/system/model` 返回为准。

## 5. Guardrail 原因分析（无 GPU 计算）

```powershell
& $Py -m scripts.analyze_guardrail_v3_1 `
  --audit runtime_v3_1_1/audit.jsonl `
  --output-dir runtime_v3_1_1/guardrail_analysis
```

检查 `guardrail_v3_1_1_时间戳_summary.json`、`_by_diagnosis.csv`、`_reasons.csv`。未记录候选文本和网络标识。注意 `template_only` 不进入 LLM 接受率分母。

## 6. V3.1 与 V2 同条件 E2E 正式对照

```powershell
& $Py -m scripts.benchmark_agent_e2e `
  --base-url http://127.0.0.1:8001 `
  --label v3_1_1_local_int4_full --mode full `
  --concurrency 1 2 5 --requests-per-level 20 --repeats 3 --warmup 2 `
  --timeout 180 --output-dir runtime_v3_1_1/perf_e2e

& $Py -m scripts.analyze_guardrail_v3_1 `
  --audit runtime_v3_1_1/audit.jsonl `
  --output-dir runtime_v3_1_1/guardrail_analysis
```

对比 `reference_baselines/V2_20261017_user_runs` 中的汇总 CSV。对比前确认使用同一台 GPU、同样环境和用例、单 Worker、RAG/LLM 开启，并避免其他程序占用 GPU。请同时保存 `nvidia-smi`、`pip freeze`、模型配置截图/日志。不要把 V3.1 的结果写入 V2 的 `runtime`。

## 7. 可选：版本化组件实验

```powershell
& $Py -m scripts.evaluate_quantization_quality_50 `
  --modes int4 --limit 3 --seed 42 --baseline-mode int4 `
  --max-new-tokens 96 --output-dir runtime_v3_1_1/quant_quality_smoke

& $Py -m scripts.evaluate_quantization_quality_50 `
  --modes fp16 int8 int4 --limit 50 --seed 42 `
  --max-new-tokens 96 --output-dir runtime_v3_1_1/quant_quality_50

& $Py -m scripts.benchmark_quantization_v2 `
  --modes fp16 int8 int4 --baseline-mode fp16 `
  --repeats 5 --warmup 2 --max-new-tokens 96 `
  --output-dir runtime_v3_1_1/quant_benchmark_v2
```

Prompt 和模型参数本轮未改，组件测试可作为回归可选项。**输出目录版本号已区分，脚本本身仍保持原有组件评测口径。**

## 8. 常见问题

- `No knowledge chunks under knowledge/demo`：核对 `. .\\RUN_V3_1_ENV.ps1` 是否执行、`RAG_KNOWLEDGE_DIR` 是否为 `knowledge/sanitized`。
- `port 8001 in use`：检查 V3.1 服务，避免误连旧 V2 的 8000 端口。
- `DEMO_AUTH_ENABLED=false`：只用于 127.0.0.1 本机演示，非企业审批控制。
- CSV 中 `guardrail_reasons` 为空：候选通过或旧审计数据不含 V3.1 原因；以 `report_generated_by`、`guardrail_passed` 综合判断。
- V3.1.1 的拒绝原因改良仅针对部分否定表达。**不能预告 E2E 结果一定变好。**
