# LangChain RAG 集成说明

当前版本的 RAG 统一为：

`LangChain Document -> OllamaEmbeddings -> FAISS -> Retriever -> LangGraph`

## 安装与准备

```powershell
python -m pip install -r requirements.txt
ollama pull qwen3-embedding:0.6b
python -m scripts.build_vector_index
```

`.env`：

```env
RAG_ENABLED=true
RAG_KNOWLEDGE_DIR=knowledge/demo
RAG_TOP_K=3
RAG_FAIL_OPEN=true
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_EMBED_MODEL=qwen3-embedding:0.6b
```

## 验证

```powershell
python -m scripts.test_vector_retrieval
python -m scripts.evaluate_rag_retrieval
```

RAG 只是知识参考。如果索引缺失或向量服务不可用，`RAG_FAIL_OPEN=true` 时工作流继续使用确定性诊断和模板报告，不允许检索故障改变诊断结论。
