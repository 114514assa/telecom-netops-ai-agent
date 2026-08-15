# 实验结果摘要

公开仓库仅保留聚合结果，不提交本地运行日志、原始模型输出、FAISS 索引或源资料。

## RAG 检索

当前 v0.3.0 使用 LangChain `OllamaEmbeddings + FAISS` 作为 RAG 链路。

更新后请重新运行当前 RAG 评测：

```powershell
python -m scripts.build_vector_index
python -m scripts.evaluate_rag_retrieval
```

新结果以本机重新生成的 `runtime/rag_eval/` 输出为准。

## Qwen2.5-0.5B 推理对比

GTX 1650 环境下：

| 模式 | tokens/s | 模型内存 | 峰值 GPU 显存 |
|---|---:|---:|---:|
| FP16 | 16.383 | 942.29 MB | 964.68 MB |
| INT8 | 2.968 | 601.04 MB | 627.60 MB |
| INT4/NF4 | 13.708 | 430.42 MB | 462.46 MB |

INT4 相较 FP16 的峰值 GPU 显存降低约 52%，用于本地轻量化辅助生成。

## 辅助说明质量验证

30 个模拟故障案例中，INT4 辅助说明接受率为 90%；未通过 Guardrail 的内容自动回退至确定性诊断报告。核心网络事实和诊断结论不由 LLM 决定。
