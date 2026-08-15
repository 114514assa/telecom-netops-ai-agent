# Changelog

## v0.3.0

- 将 RAG 统一为 LangChain `OllamaEmbeddings + FAISS`，移除 TF-IDF 与 Scikit-learn 依赖。
- 使用 LangChain `ChatPromptTemplate` 组织受限 LLM 辅助说明提示。
- 新增 `langchain-mcp-adapters` 桥接层，可将 FastMCP 工具加载为 LangChain Tools。
- 保留 LangGraph 作为主工作流编排层，确定性解析器/规则引擎继续负责关键诊断结论。
- RAG 改为 fail-open：本地索引或 Ollama 不可用时，不影响确定性诊断主链路。
- 更新 README、架构文档、RAG 脚本和 GitHub 发布检查说明。
- 项目版本从 `0.2.0` 更新为 `0.3.0`。
