# 本地模型量化：最终工程定版

本项目的量化目标不是追求研究型量化算法，而是验证一个新手可解释、可复现、可用于简历说明的本地部署方案。

## 最终范围

- 模型：`Qwen/Qwen2.5-0.5B-Instruct`
- 对比：FP16 / INT8 / INT4 性能基准；实际本地部署选择 INT4
- 业务边界：确定性解析器与规则引擎负责事实和诊断；LLM 只生成一句辅助说明
- 生成限制：`max_new_tokens=96`，`temperature=0.0`
- Guardrail：拦截网络标识符、诊断代码回显、危险修改建议、诊断矛盾、无关内容、超长或不完整输出
- 回退：LLM 辅助说明未通过时，直接使用确定性诊断报告，不影响主流程
- 质量评测：30 个模拟案例，10 类场景 × 3 个变体

## 最终运行命令

```powershell
pytest -q
python -m scripts.evaluate_quantization_quality_final --model Qwen/Qwen2.5-0.5B-Instruct --modes fp16 int4 --max-new-tokens 96 --seed 42
```

结果保存在：

```text
runtime/quality_eval_final/
```

如需人工复核，填写 `manual_review_final_*.csv` 后执行：

```powershell
python -m scripts.summarize_manual_review_final runtime\quality_eval_final\manual_review_final_<timestamp>.csv
```

## 停止标准

满足以下条件后不再继续迭代量化或 Guardrail：

1. INT4 可稳定加载并完成 Agent 场景生成；
2. 性能基准可复现，显存占用明显低于 FP16；
3. 30 条模拟场景均能完成主诊断流程；
4. 不合格的 LLM 辅助说明能够被 Guardrail 拦截并回退到确定性报告；
5. 不再为了提高辅助说明接受率而放宽安全边界。

这套方案定位为工程实践，不作为量化算法研究成果。
