# LangChain / LangGraph / MCP 集成说明

## 1. 为什么同时使用三个组件

三者在本项目中职责不同：

- **LangGraph**：工作流编排、状态传递、条件分支、Interrupt/Resume、SQLite Checkpoint。
- **LangChain**：RAG 的 Document/VectorStore/Embedding 抽象，以及受限报告生成的 `ChatPromptTemplate`。
- **MCP**：把资源查询、证据解析、规则诊断和知识检索封装成标准只读工具。

项目没有把核心排障链路改成完全由 LLM 自主选择工具的 ReAct Agent。关键故障结论仍由解析器和确定性规则生成，这样更符合网络运维场景对可解释性和安全边界的要求。

## 2. LangChain RAG

```text
Markdown Demo Knowledge
        ↓
LangChain Document
        ↓
OllamaEmbeddings
        ↓
FAISS VectorStore
        ↓
KnowledgeHit
        ↓
LangGraph retrieve node
```

对应代码：

- `scripts/build_vector_index.py`
- `app/rag/langchain_faiss.py`
- `app/services/knowledge.py`

## 3. LangChain Prompt

`ReportComposer` 先生成完整确定性报告；只有启用 LLM 时，才由 `LangChainReportAssistant` 使用 `ChatPromptTemplate` 构造受限提示。

模型只能生成一条辅助说明，输出随后还要经过 `report_guardrails.py` 校验。Guardrail 失败时直接回退到确定性报告。

对应代码：

- `app/llm/langchain_report_chain.py`
- `app/llm/backends.py`
- `app/services/report.py`

## 4. MCP → LangChain Tool

`app.mcp_server` 使用 FastMCP 提供：

- `query_access_relation`
- `parse_switch_evidence`
- `diagnose_access_issue`
- `search_netops_runbook`
- `get_readonly_boundary`

`LangChainMCPBridge` 使用 `langchain-mcp-adapters` 通过 stdio 启动本地 MCP Server，并把这些工具加载为 LangChain Tools。

验证：

```powershell
python -m scripts.test_langchain_mcp_bridge
```

这个桥接层用于展示工具协议互操作；主 LangGraph 排障流程仍直接调用本地确定性服务，避免不必要的子进程开销和 LLM 自主路由风险。
