# 加固版测试执行记录

## 已在当前构建环境运行

`PYTHONPATH=. pytest -q tests/test_parsers.py tests/test_diagnosis.py tests/test_repository.py tests/test_hardening_network.py tests/test_document_grounding.py tests/test_document_grounded_diagnosis.py tests/test_auth_boundaries.py`

结果：**22 passed**。覆盖原基础解析/诊断/仓库测试与新的字段归属、解析失败、VLAN 冲突、过期证据、模拟采集白名单、来源标注、Demo 令牌角色校验。

`python -m compileall -q app` 通过。

## 尚未通过验证的部分

全量 `pytest -q` 因当前容器没有 `langchain_core`，收集阶段出现 `ModuleNotFoundError`，**不是测试全部通过**。本环境无外网安装 LangGraph/LangChain/FAISS，也没有实际运行 Ollama、Qwen/DeepSeek 或 GPU；因此未进行完整 FastAPI→LangGraph 端到端集成测试，未获得新版本性能与诊断准确率指标。

完整环境安装后需要补充运行：

1. `pytest -q` 全量回归。
2. 真实 SQLite Checkpoint/interrupt/resume API 集成测试（批准、拒绝、重复提交、非法令牌）。
3. RAG 构建后：`python -m scripts.evaluate_rag_retrieval_150 --dataset data/rag_eval/queries_document_grounded.json --repeats 1 --warmup 1`。
4. 可用 GPU 条件下依照原量化脚本复测；旧数值只是基线存档。
5. DeepSeek 或本地模型的端到端负载基准重新运行，验证线程池修改后的 P50/P95，而不是直接推断速度提高。

注：不提供伪造的检索分数、诊断准确率或并发提升数字。


## PDF/MCP 2026-10-17 加固验证（本次容器）

- PDF 纯解析、网络 Parser、Rule Engine、HITL Demo 令牌相关的 27 项测试通过。
- 新增 3 项 FastAPI PDF API 合约测试在**stub Graph** 条件下通过。
- 全量 pytest 收集在本容器中被缺少 `langgraph`、`langchain_core` 阻断；此环境不等同于用户 Windows 旧 venv。
- 未验证真实 stdio MCP Bridge、Windows FastAPI/SQLite Checkpoint、OCR、LLM 或 GPU 推理。请遵循 `docs/PDF_MCP_WINDOWS_GUIDE.md` 在本机复测。
