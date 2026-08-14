# RAG 向量检索接入补丁

该补丁基于当前项目结构制作，目标是保持现有 LangGraph 节点不变，仅将 `retrieve` 节点底层检索器改为可配置的双后端。

## 1. 覆盖文件

将 ZIP 中的目录合并到项目根目录。

**不要覆盖或提交你本地 `.env`。**

## 2. 安装依赖

```powershell
python -m pip install -r requirements.txt
```

## 3. `.env`

你已有配置可以继续使用，确认至少包含：

```env
RAG_BACKEND=vector
RAG_KNOWLEDGE_DIR=knowledge/demo
RAG_TOP_K=3
RAG_VECTOR_FALLBACK_TO_TFIDF=true

OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_EMBED_MODEL=qwen3-embedding:0.6b
OLLAMA_TIMEOUT_SECONDS=120

VECTOR_INDEX_PATH=runtime/vector_index/knowledge.faiss
VECTOR_METADATA_PATH=runtime/vector_index/metadata.json
```

## 4. 重新构建索引

补丁让建库脚本读取 `.env`，建议重新生成一次：

```powershell
python -m scripts.build_vector_index
```

## 5. 独立检索验证

```powershell
python -m scripts.test_vector_retrieval
```

## 6. 项目测试

```powershell
pytest -q
```

## 7. Agent 完整链路

```powershell
python -m scripts.run_demo --case vlan_mismatch
python -m scripts.run_demo --case no_mac
python -m scripts.run_demo --case upstream
```

报告中的 `## 六、知识依据` 应出现 `knowledge/demo` 对应文件与章节。

也可以启动 Web：

```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 8. 30 条检索评测

```powershell
python -m scripts.evaluate_rag_retrieval
```

输出：

```text
runtime/rag_eval/rag_eval_summary_*.csv
runtime/rag_eval/rag_eval_detail_*.csv
runtime/rag_eval/rag_eval_*.json
```

只比较：

- Hit@1
- Hit@3
- 平均检索耗时

不要为了让向量方案“赢”而修改标注；如果 TF-IDF 某些查询更好，也属于正常工程结果。

## 9. 设计边界

- TF-IDF 与向量检索使用同一套脱敏文档，保证对比公平。
- 向量检索失败时默认回退 TF-IDF。
- RAG 仅提供知识参考，不覆盖确定性规则诊断。
- 不接入真实生产设备、网管接口或内部敏感数据。
