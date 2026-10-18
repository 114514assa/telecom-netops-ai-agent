# Telecom NetOps AI Agent

**工程加固版 + 只读 PDF 输入（原始源码与历史评测保留）**：先阅读 [RUN_AND_START.md](RUN_AND_START.md)、[加固变更](docs/HARDENING_CHANGELOG.md)、[原始资料映射](docs/SOURCE_PROVENANCE.md) 和 [测试状态](docs/TEST_STATUS.md)。新增加 34 条文档来源标注 Query，但未声称测出新的检索分数；原 150 Query / 模型量化 / DeepSeek 测试均为历史实验记录。


面向接入网终端故障排查场景搭建的只读型 AI Agent。项目使用模拟资源和网络数据，将资源查询、网络状态解析、确定性故障判断、RAG 知识检索和诊断结果整理串成可恢复工作流。

> 公开仓库仅包含模拟数据与 Demo 知识，不连接运营商生产系统，不包含真实 IP、设备标识、账号密钥或内部资料。

## 主要功能

- **LangGraph 工作流**：编排资源查询、证据解析、规则诊断、RAG、报告生成、人工确认和归档，SQLite Checkpoint 支持恢复。
- **LangChain 应用组件**：使用 `ChatPromptTemplate` 组织受限 LLM 提示，使用 LangChain FAISS VectorStore 与 OllamaEmbeddings 完成本地 RAG。
- **MCP 只读工具**：通过 FastMCP 封装资源查询、Interface/MAC/ARP/VLAN 解析、规则诊断和知识检索，并提供 `langchain-mcp-adapters` 兼容桥接。
- **确定性诊断优先**：关键网络事实由解析器和规则引擎判断，LLM 只负责辅助说明，不直接修改诊断结论。
- **本地轻量推理**：支持 Qwen2.5-0.5B-Instruct 的 FP16 / INT8 / INT4(NF4) 推理实践。
- **安全兜底**：RAG fail-open、LLM Guardrail、Human-in-the-loop、审计日志和只读边界。

## 架构

```mermaid
flowchart TD
    A[FastAPI / Web UI] --> B[LangGraph Workflow]
    B --> C[Simulated Inventory]
    B --> D[Interface/MAC/ARP/VLAN Parsers]
    B --> E[Deterministic Diagnosis Rules]
    B --> F[LangChain RAG]
    F --> F1[OllamaEmbeddings]
    F1 --> F2[FAISS VectorStore]
    B --> G[Report Composer]
    G --> H[LangChain ChatPromptTemplate]
    H --> I{Optional LLM}
    I --> I1[OpenAI-compatible API]
    I --> I2[Local Qwen FP16/INT8/INT4]
    I1 --> J[Guardrail]
    I2 --> J
    J --> K[HITL Approval]
    B --> L[SQLite Checkpoint / Audit]
    M[LangChain MCP Bridge] --> N[Read-only FastMCP Server]
    N --> C
    N --> D
    N --> E
    N --> F
```

## 技术栈

| 模块 | 技术 |
|---|---|
| Agent / Workflow | LangGraph, LangChain |
| Tool Protocol | MCP, FastMCP, langchain-mcp-adapters |
| API | FastAPI, Pydantic |
| RAG | OllamaEmbeddings, FAISS |
| LLM | OpenAI-compatible API, Hugging Face Transformers |
| Quantization | bitsandbytes, FP16, INT8, INT4/NF4 |
| Storage | SQLite, CSV, JSONL |
| Engineering | Docker, pytest, Ruff, GitHub Actions |

## 快速开始

Python 3.10+：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m scripts.seed_db
```

准备本地 RAG：

```powershell
ollama pull qwen3-embedding:0.6b
python -m scripts.build_vector_index
```

启动：

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- Web Demo: `http://127.0.0.1:8000/`
- Swagger: `http://127.0.0.1:8000/docs`

如果暂时不运行 Ollama，可在 `.env` 中设置 `RAG_ENABLED=false`；确定性诊断流程仍可正常运行。

## RAG

当前版本仅保留 LangChain 向量检索链路：

```text
knowledge/demo/*.md
        ↓
LangChain Document
        ↓
OllamaEmbeddings
        ↓
FAISS
        ↓
Retriever
        ↓
LangGraph retrieve node
```

配置示例：

```env
RAG_ENABLED=true
RAG_KNOWLEDGE_DIR=knowledge/demo
RAG_TOP_K=3
RAG_FAIL_OPEN=true
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_EMBED_MODEL=qwen3-embedding:0.6b
```

重新构建索引：

```powershell
python -m scripts.build_vector_index
python -m scripts.test_vector_retrieval
```

## MCP / LangChain 工具桥接

启动独立 MCP Server：

```powershell
python -m app.mcp_server
```

验证 MCP 工具能够被转换为 LangChain Tools：

```powershell
python -m scripts.test_langchain_mcp_bridge
```

主诊断工作流仍直接调用本地确定性解析器和规则，不让 LLM 自主选择写操作或决定故障结论；MCP Bridge 用于展示标准工具协议和 LangChain/LangGraph 生态互操作。

## 本地模型量化

可选安装：

```powershell
python -m pip install -r requirements-llm.txt
```

配置：

```env
LLM_ENABLED=true
LLM_BACKEND=local_hf
LOCAL_LLM_MODEL_ID=Qwen/Qwen2.5-0.5B-Instruct
LOCAL_LLM_QUANTIZATION=int4
LOCAL_LLM_MAX_NEW_TOKENS=96
```

## Demo

项目内置接口 DOWN、无目标 MAC、VLAN 不一致、接入侧正常需继续核查上层、端口登记不一致等模拟场景。

```powershell
python -m scripts.run_demo --case vlan_mismatch
```

## 项目边界

该仓库用于学习和展示网络运维场景下的 Agent 开发流程。资源数据、交换机状态和知识库均为模拟内容，不连接真实生产网络，也不会执行网络配置修改操作。

详细说明见 `docs/`。

## License

MIT


## 新增：PDF 文件上传与 MCP 文本提取

- FastAPI `POST /api/v1/documents/pdf/extract`：上传 PDF，只读解析分页文本，不触发诊断。
- FastAPI `POST /api/v1/incidents/from-pdf`：仅当文档实际包含单一种类的已脱敏 CLI 输出、并由调用者明确指定 `evidence_kind` 后，才作为**用户提供的未经验证证据**进入原 LangGraph 工作流。
- MCP `extract_pdf_document(pdf_base64)`：同一解析能力的只读 MCP 工具。不允许任意路径读取/写入，不自动调用 LLM，也不自动修改规则结果。
- 本功能**不自动入库 RAG**；需要人工审查、脱敏与索引重建才能成为知识材料。
- 仅支持带文本层的 PDF，扫描 PDF 没有 OCR 支持；5 MiB / 20 页 / 30,000 字符限额；不支持加密文件。上传来源/时间不可凭 PDF 自证。
- 上传的 PDF 文本会进入工作流 State 并可能被 SQLite Checkpoint 持久化。**只允许使用脱敏测试材料**。

运行及 PowerShell 接口验证详见 `docs/PDF_MCP_WINDOWS_GUIDE.md`。
提供的 `mcp-local.zip` 中 filesystem MCP 并不具备 PDF 解析能力且带写工具，故此版本未直接启动该服务器；其相关源码仅作隔离参考，不作为 Agent 默认工具。

### Document-grounded RAG test-case tools (2026-10-17)

Optional, read-only test **design** tooling from the provenance-annotated telecom Query dataset, not a diagnosis model or a real-ticket generator.

- `python -m scripts.export_document_grounded_cases --validate-only`
- `python -m scripts.export_document_grounded_cases --format markdown`
- `python -m scripts.export_document_grounded_cases --format json --category vlan`
- `GET /api/v1/testcases/document-grounded/categories`
- `GET /api/v1/testcases/document-grounded?category=vlan&limit=3`
- `GET /api/v1/testcases/document-grounded/export?format=csv&limit=3`
- MCP tools: `list_document_grounded_testcases`, `generate_document_grounded_testcases`, `export_document_grounded_testcases`.

See [Windows commands](RUN_NEW_TESTCASE_TOOLS_WINDOWS.md) and [provenance / limitations](docs/TESTCASE_TOOL_DESIGN.md). Original 150-Query benchmark numbers are unchanged.
