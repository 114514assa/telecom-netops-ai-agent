# Telecom NetOps AI Agent：50 Case 量化实验说明

## 1. 这次实验测什么

本实验基于当前项目的实际 LLM 调用链：

```text
确定性 Parser / Rule Engine
        ↓
已确认诊断代码、结论、建议
        ↓
LangChain ChatPromptTemplate
        ↓
Qwen2.5-0.5B-Instruct
        ↓
Guardrail
        ↓
通过：追加一句辅助说明
失败：回退到确定性报告
```

因此，本实验**不把 LLM 当作故障分类器**，也不让它重新判断故障。量化质量评测关注的是：

1. `application_acceptance_rate`：输出能否通过项目真实 Guardrail 并进入最终报告；
2. `diagnostic_direction_preservation_rate`：辅助说明是否保持原诊断方向且没有语义矛盾；
3. `safety_compliance_rate`：是否不泄露标识符、不输出诊断代码、不建议写操作；
4. `report_completeness_rate`：格式、长度、句子完整性是否满足约束；
5. `fallback_rate`：量化模型输出被 Guardrail 拒绝、回退确定性报告的比例。

> 重要：当前项目的 LLM 辅助层只接收已确认的诊断代码、结论和只读建议，并不直接接收 RAG Top-K 文本。因此这里没有人为加入“固定 RAG Context”。那样会改变当前系统本身，而不是评测现有项目。

如果需要在简历中使用“诊断结论一致率”这一名称，建议完成脚本生成的人工复核表；自动指标中的 `diagnostic_direction_preservation_rate` 是规则化代理指标，不等同于人工语义一致率。

## 2. 数据集

新增：

```text
data/evaluation/quantization_cases_50.json
```

由当前项目已有 30 Case 扩展为：

```text
10 类场景 × 5 个变体 = 50 Case
```

10 类与项目原质量评测保持一致：

1. VLAN 不一致 `vlan_mismatch`
2. 接口 DOWN `interface_down`
3. 接口 UP 无 MAC `no_mac`
4. 资源端口不一致 `resource_port_mismatch`
5. 接入侧正常、继续排查上层 `upstream`
6. 终端网关/地址配置不一致 `gateway_mismatch`
7. 链路错误统计异常 `link_errors`
8. MAC 已学习但 ARP / 三层证据不足 `arp_missing`
9. 资源登记设备不一致 `device_mismatch`
10. 接入侧无明显异常 `normal_access`

每类 5 个变体：

- `standard`
- `paraphrase`
- `multi_evidence`
- `noisy_or_long_context`
- `conservative_boundary`

前 30 条沿用项目已有质量评测 Case，新增 20 条更强调长表述、证据边界和保守表达。

## 3. 环境检查

在项目根目录运行：

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -r requirements-llm.txt
```

检查 GPU：

```powershell
python -c "import torch; print(torch.__version__); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
```

检查 bitsandbytes：

```powershell
python -c "import bitsandbytes as bnb; print(bnb.__version__)"
```

## 4. 先验证补丁数据集

```powershell
pytest -q tests/test_quantization_eval_50.py
```

预期：测试通过，并确认 50 条、10 类、每类 5 条。

## 5. 冒烟测试

先只使用 INT4 跑 3 条，确认模型、显卡、bitsandbytes 与脚本都正常：

```powershell
python -m scripts.evaluate_quantization_quality_50 `
  --model Qwen/Qwen2.5-0.5B-Instruct `
  --modes int4 `
  --limit 3 `
  --max-new-tokens 96 `
  --seed 42
```

成功后再做正式实验。

## 6. 正式质量实验

推荐一次跑：

```powershell
python -m scripts.evaluate_quantization_quality_50 `
  --model Qwen/Qwen2.5-0.5B-Instruct `
  --modes fp16 int8 int4 `
  --cases data/evaluation/quantization_cases_50.json `
  --max-new-tokens 96 `
  --seed 42
```

脚本会按模式逐个加载，避免同时占用多份模型显存；某个模式加载失败时会记录错误，并继续保留其他模式结果。

输出目录：

```text
runtime/quant_eval_50/
```

重点文件：

```text
quant_quality50_summary_*.csv
quant_quality50_vs_fp16_*.csv
quant_quality50_family_*.csv
quant_quality50_variant_*.csv
quant_quality50_detail_*.csv
quant_quality50_manual_review_*.csv
quant_quality50_*.json
```

脚本还会在每个模式结束后保存 `partial_*.json`，即使后面的模式异常，前面已完成的数据仍保留。

## 7. 性能 Benchmark

新版 Benchmark 不再只使用一个固定字符串，而是从 10 类场景中各取 1 条代表性 Case，并走与项目一致的 `LangChainReportAssistant` Prompt 链。

推荐：

```powershell
python -m scripts.benchmark_quantization_v2 `
  --model Qwen/Qwen2.5-0.5B-Instruct `
  --modes fp16 int8 int4 `
  --repeats 5 `
  --warmup 2 `
  --max-new-tokens 96
```

正式推理次数：

```text
10 个代表性 Prompt × 5 次 × 3 个模式 = 150 次
```

输出目录：

```text
runtime/quant_benchmark_v2/
```

重点指标：

- `load_seconds`
- `memory_footprint_mb`
- `peak_gpu_memory_mb`
- `mean_latency_ms`
- `median_latency_ms`
- `p95_latency_ms`
- `mean_tokens_per_second`

`quant_benchmark_v2_vs_fp16_*.csv` 会自动计算：

- 相对 FP16 的峰值显存降低百分比；
- 模型内存降低百分比；
- 延迟变化百分比；
- tokens/s 变化百分比。

> 所有性能数字都是当前机器环境结果，不能写成模型的通用性能。

## 8. 人工复核（建议做）

质量脚本会生成：

```text
quant_quality50_manual_review_*.csv
```

对每行填写 `1/0`：

- `manual_diagnosis_consistent`：是否与已确认诊断方向一致；
- `manual_relevant`：是否与当前排障场景相关；
- `manual_no_hallucination`：是否没有新增无依据事实；
- `manual_action_boundary_ok`：是否保持只读、不建议配置变更；
- `manual_readable`：是否自然、完整、可读。

填完后：

```powershell
python -m scripts.summarize_quantization_manual_review_50 runtime\quant_eval_50\quant_quality50_manual_review_<timestamp>.csv
```

如果 50 Case × 3 模式全部人工复核，就是 150 行。

## 9. 如何选择 INT4

不要只看显存。建议同时满足：

1. INT4 峰值显存明显低于 FP16；
2. `application_acceptance_rate` 与 FP16 接近；
3. `diagnostic_direction_preservation_rate` 没有明显下降；
4. `safety_compliance_rate` 没有下降；
5. 人工复核中的 `manual_diagnosis_consistent_rate` 与 FP16 接近；
6. 即使个别输出失败，也能被 Guardrail 拦截并回退到确定性报告。

## 10. 简历数字怎么取

先不要预填结果。跑完后优先从两张表取：

```text
runtime/quant_benchmark_v2/quant_benchmark_v2_vs_fp16_*.csv
runtime/quant_eval_50/quant_quality50_summary_*.csv
```

如果人工复核完成，再补：

```text
manual_diagnosis_consistent_rate
```

推荐最终表达结构：

> 使用 Transformers 与 bitsandbytes 对 Qwen2.5-0.5B-Instruct 进行 FP16、INT8、INT4/NF4 对比，在 50 个模拟故障 Case 上评估显存、推理速度及受限辅助说明质量；INT4 峰值显存较 FP16 降低约 XX%，Guardrail 通过率/人工诊断方向一致率达到 XX%，最终作为本地轻量推理方案。

只有实际跑出的数字才能替换 `XX`。
