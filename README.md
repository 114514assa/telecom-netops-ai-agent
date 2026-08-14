# Telecom NetOps AI Agent

面向接入网终端故障排查场景搭建的 AI Agent 项目。项目使用模拟资源和网络数据，将资源查询、网络状态解析、故障判断、知识检索和诊断结果整理串成一个完整流程。

公开仓库仅包含模拟数据和 Demo 知识，不连接真实运营商生产系统，也不包含真实 IP、设备信息或内部资料。

## 主要功能

* 基于 **LangGraph** 搭建故障诊断工作流；
* 查询终端 IP 对应的接入资源和交换机信息；
* 解析 Interface、MAC、ARP、VLAN 等网络状态；
* 使用规则完成常见接入故障判断；
* 使用 **RAG** 检索相关排障知识；
* 支持 LLM 辅助整理诊断结果和排障建议；
* 使用 **MCP** 封装只读查询和诊断工具；
* 使用 SQLite 保存工作流状态和诊断记录；
* 支持人工确认后完成结果归档。

## 工作流程

```mermaid
flowchart LR
    A[输入终端 IP] --> B[资源查询]
    B --> C[网络状态解析]
    C --> D[故障规则判断]
    D --> E[RAG 知识检索]
    E --> F[生成诊断结果]
    F --> G[人工确认]
    G --> H[结果归档]
```

## 技术栈

| 模块        | 技术                                               |
| --------- | ------------------------------------------------ |
| Agent 工作流 | LangGraph, LangChain Core                        |
| 工具调用      | MCP / FastMCP                                    |
| API       | FastAPI, Pydantic                                |
| RAG       | TF-IDF, FAISS, Ollama Embedding                  |
| LLM       | OpenAI-compatible API, Hugging Face Transformers |
| 数据存储      | SQLite, CSV, JSONL                               |
| 工程工具      | Docker, pytest, GitHub Actions                   |

## 项目结构

```text
telecom-netops-ai-agent/
├── app/                # Agent、API 和核心业务逻辑
├── knowledge/demo/     # 模拟排障知识
├── scripts/            # 初始化和运行脚本
├── tests/              # 基础测试
├── docs/               # 项目说明和实验记录
├── requirements.txt
└── README.md
```

## 快速开始

环境要求：

```text
Python 3.10+
```

创建环境并安装依赖：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

初始化模拟数据：

```powershell
python -m scripts.seed_db
```

启动服务：

```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

浏览器访问：

```text
http://127.0.0.1:8000/
```

API 文档：

```text
http://127.0.0.1:8000/docs
```

## RAG

项目默认使用 TF-IDF 检索 Demo 知识库：

```env
RAG_BACKEND=tfidf
RAG_KNOWLEDGE_DIR=knowledge/demo
```

也可以切换到 Ollama Embedding + FAISS：

```powershell
ollama pull qwen3-embedding:0.6b
python -m scripts.build_vector_index
```

对应配置：

```env
RAG_BACKEND=vector
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_EMBED_MODEL=qwen3-embedding:0.6b
RAG_KNOWLEDGE_DIR=knowledge/demo
```

## LLM

LLM 为可选模块，主要用于整理诊断说明，不直接决定关键网络故障结论。

项目支持 OpenAI-compatible API，也可以使用本地 Hugging Face 模型。

示例配置：

```env
LLM_ENABLED=true
LLM_BACKEND=local_hf
LOCAL_LLM_MODEL_ID=Qwen/Qwen2.5-0.5B-Instruct
LOCAL_LLM_QUANTIZATION=int4
```

## Demo 场景

项目内置了几种模拟故障，包括：

* 接口 DOWN；
* 接口正常但未学习到目标 MAC；
* VLAN 配置与资源记录不一致；
* 端口登记信息不一致；
* 接入侧状态正常，需要继续排查上层网络。

例如：

```powershell
python -m scripts.run_demo --case vlan_mismatch
```

## 项目说明

该仓库用于学习和展示网络运维场景下的 Agent 开发流程。

项目中的资源数据、交换机状态和知识库内容均为模拟数据，不接入真实生产网络，也不会执行交换机配置修改等操作。

更详细的实现和实验记录见 `docs/`。

## License

MIT
