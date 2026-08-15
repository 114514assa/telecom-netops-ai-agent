# 业务流程与系统实现映射

| 通用排障步骤 | 系统实现 |
|---|---|
| 收集 IP、故障现象与终端信息 | `IncidentInput` / Pydantic |
| 查询模拟接入资源 | `InventoryRepository.find_by_ip` |
| 解析接口状态 | `parse_interface_output` |
| 解析 MAC、端口和 VLAN | `parse_mac_output` |
| 解析 IP—MAC 邻接 | `parse_arp_output` |
| 解析接口 VLAN 信息 | `parse_vlan_output` |
| 比对资源登记与当前证据 | `diagnose` 确定性规则 |
| 构造 RAG 查询 | `build_retrieval_query` |
| Embedding | LangChain `OllamaEmbeddings` |
| 向量检索 | LangChain `FAISS` VectorStore |
| LLM Prompt | LangChain `ChatPromptTemplate` |
| MCP 工具暴露 | `FastMCP` / `app.mcp_server` |
| MCP → LangChain Tool | `langchain-mcp-adapters` / `LangChainMCPBridge` |
| 生成可追溯报告 | `ReportComposer` + Guardrail |
| 人工确认与恢复 | LangGraph HITL + SQLite Checkpoint |
