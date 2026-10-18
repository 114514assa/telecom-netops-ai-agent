# V3.1.1 — Windows pytest 参数化 ID 兼容性修复（2026-10-17）

- 修复 V3.1.0 的 `tests/test_pdf_ingest.py` 在 Windows pytest 下打印超长 `X`、触发 `ValueError: the environment variable is longer than 32767 characters` 的回归：对 3 个无效 PDF 参数分别指定短 ID，`oversized_pdf` 只影响测试标识，不缩小实际 5 MiB 超限负向测试覆盖。
- 本版本为 **测试兼容性修复**，没有修改 PDF 处理/Guardrail/诊断/RAG/LLM 的业务实现，不预告其模型接受率或性能改善。
- 版本根目录改为 `telecom-netops-ai-agent-v3.1.1`；运行数据隔离为 `runtime_v3_1_1`；Guardrail 统计输出文件前缀为 `guardrail_v3_1_1_*`。
- 旧 V2、V3.1.0 文件不覆盖、旧 `.venv` 可复用、全部 Windows pytest 和 GPU/E2E 仍需用户环境验证。
- 详细差异与操作请查看 `docs/iterations/V3_1_1_HOTFIX.md`。

---

# V3.1.0 — Guardrail 可观测性与安全误拒修复

- V2 源码与文档作为基线复制到独立根目录，使用 `runtime_v3_1` 隔离运行数据。
- Guardrail 的“避免 / 切勿”等安全否定语句不再简单误报为修改建议；危险操作与方向反转仍被拒绝。
- 生成结果元数据采用敏感内容白名单摘要，增加结构化回退原因；E2E 逐条记录原因码。
- 新增 `scripts/analyze_guardrail_v3_1.py` 和文档 `docs/iterations/V3_1_CHANGELOG.md` / `.docx`。
- 原 `.env`、旧 venv、历史结果均不修改或覆盖；完整模型基准尚待 Windows 复测。

---

# Changelog

## v0.3.0

- 将 RAG 统一为 LangChain `OllamaEmbeddings + FAISS`，移除 TF-IDF 与 Scikit-learn 依赖。
- 使用 LangChain `ChatPromptTemplate` 组织受限 LLM 辅助说明提示。
- 新增 `langchain-mcp-adapters` 桥接层，可将 FastMCP 工具加载为 LangChain Tools。
- 保留 LangGraph 作为主工作流编排层，确定性解析器/规则引擎继续负责关键诊断结论。
- RAG 改为 fail-open：本地索引或 Ollama 不可用时，不影响确定性诊断主链路。
- 更新 README、架构文档、RAG 脚本和 GitHub 发布检查说明。
- 项目版本从 `0.2.0` 更新为 `0.3.0`。

## 2026-10-17 · Document-grounded test-case tooling integration

- Added read-only RAG test-case designer based **only** on the existing 34 provenance-annotated telecom queries and matched knowledge section labels.
- Added three MCP tools, three FastAPI routes and a CLI exporter (JSON / Markdown / CSV) with source/page/heading/Gold metadata.
- Added provenance validation and isolated offline regression tests, plus optional API and MCP stdio smoke tests.
- No third-party MCP credentials, unrelated business cases, source environment or executable Mac scripts from the uploaded `AI智能生成测试用例.zip` were included.
- Preserved the previously hardened PDF module, original Parser/Rule Engine, LangGraph, RAG, Qwen benchmark scripts and stored historical results.
- All generated test cases are explicitly marked **not_executed**. The source metadata does not constitute re-verification of the original telecom PDFs.
