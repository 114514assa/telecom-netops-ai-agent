# 量化质量评测 V3

V3 不再要求小模型复述诊断代码、结论、IP、MAC、端口或 VLAN 等受保护事实。
这些字段始终由确定性规则引擎生成并保留，LLM 只允许输出一句“辅助说明”。

## 为什么这样改

V2 的三行复述任务仍然把受保护字段交给了 0.5B 模型，导致：
- 同义改写被严格字符串匹配误判；
- 小模型可能篡改诊断代码或结论；
- 模型可能复述/虚构网络标识符；
- “事实保持率”与“只输出短辅助说明”的应用设计相冲突。

V3 将可变自然语言与确定性事实彻底分离：
- 确定性报告：规则引擎负责；
- LLM：只生成一句短辅助说明；
- 解析器只提取 `辅助说明：...` 一行，其他模型输出不会进入最终报告；
- Guardrail 检查网络标识符、置信度/百分比、危险操作、语义矛盾、长度与句子完整性；
- 未通过即回退到纯确定性报告。

## 运行

冒烟测试：

```powershell
python -m scripts.evaluate_quantization_quality_v3 --model Qwen/Qwen2.5-0.5B-Instruct --modes fp16 int4 --limit 3 --max-new-tokens 96
```

完整 10 条：

```powershell
python -m scripts.evaluate_quantization_quality_v3 --model Qwen/Qwen2.5-0.5B-Instruct --modes fp16 int4 --max-new-tokens 96
```

输出目录：`runtime/quality_eval_v3/`。

## 重点指标

- `application_acceptance_rate`：最终可安全追加到报告的辅助说明比例。
- `auxiliary_parse_rate`：能否提取辅助说明。
- `semantic_relevance_rate`：是否包含与当前案例相关的核查/转交语义。
- `identifier_free_rate`：辅助说明是否避免复述/新增网络标识符和置信度数值。
- `unsafe_free_rate`：是否避免配置修改、重启、关闭等操作建议。
- `contradiction_free_rate`：是否避免与确定性诊断相矛盾的表述。
- `complete_sentence_rate`：辅助说明是否完整结束。

`truncation_rate` 仅用于观察原始生成是否触及上限；如果完整安全的辅助说明已经在前面被提取，额外被截断内容不会进入应用报告。
