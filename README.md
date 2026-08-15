# Telecom NetOps AI Agent

一个用于接入网故障排查练习的 AI Agent 项目。

项目根据常见的终端接入故障排查流程，将资源查询、交换机信息解析、规则判断、知识检索和结果整理串成一个可执行流程。当前仓库使用的资源、设备状态和知识库均为模拟数据，不连接真实生产网络。

## 功能

目前实现了以下内容：

* 根据终端 IP 查询模拟接入资源
* 解析 Interface、MAC、ARP、VLAN 等交换机信息
* 根据端口状态、MAC 学习和 VLAN 配置进行基础故障判断
* 使用 LangGraph 编排完整诊断流程
* 使用 Ollama Embedding + FAISS 检索排障知识
* 使用 LangChain 组织 RAG、Prompt 和 MCP Tool 接入
* 使用 FastMCP 提供只读网络查询与诊断工具
* 可选使用本地 Qwen 模型整理诊断说明
* 支持人工确认、SQLite Checkpoint 和诊断记录保存

整体流程：

```text
终端 IP
   ↓
资源查询
   ↓
网络信息解析
   ↓
规则诊断
   ↓
RAG 检索
   ↓
结果整理
   ↓
人工确认
   ↓
归档
```

关键故障判断由解析器和规则完成，大模型主要用于整理已有诊断结果和补充排障说明。

## 技术栈

* Python
* LangGraph / LangChain
* MCP / FastMCP
* FastAPI
* Ollama
* FAISS
* Transformers / bitsandbytes
* SQLite
* Docker

## 项目结构

```text
.
├── app/
│   ├── graph/          # LangGraph 工作流
│   ├── llm/            # LLM 与 LangChain 报告生成
│   ├── rag/            # Ollama + FAISS 检索
│   ├── services/       # 资源查询、诊断、知识检索等业务逻辑
│   ├── mcp_server.py   # MCP Server
│   └── mcp_bridge.py   # LangChain MCP Bridge
│
├── knowledge/
│   └── demo/           # Demo 知识库
├── scripts/            # 初始化、测试和 Demo 脚本
├── tests/
├── docs/
└── requirements.txt
```

## 运行

要求 Python 3.10+。

### 1. 安装依赖

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

### 2. 初始化模拟数据

```powershell
python -m scripts.seed_db
```

### 3. 准备 RAG

本地安装并启动 Ollama 后：

```powershell
ollama pull qwen3-embedding:0.6b
python -m scripts.build_vector_index
```

当前 RAG 使用：

```text
Markdown Knowledge
      ↓
Ollama Embedding
      ↓
FAISS
      ↓
Retriever
```

### 4. 启动项目

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

## Demo

项目中准备了几种模拟故障，例如：

* 接口 DOWN
* 接口 UP 但没有学习到目标 MAC
* VLAN 配置与资源记录不一致
* 端口登记信息不一致
* 接入侧正常，需要继续检查上层网络

运行 VLAN 不一致示例：

```powershell
python -m scripts.run_demo --case vlan_mismatch
```

## MCP

MCP Server：

```powershell
python -m app.mcp_server
```

目前提供的工具主要用于：

```text
资源查询
网络信息解析
故障判断
知识检索
只读边界查询
```

也可以通过 `langchain-mcp-adapters` 将 MCP Tool 接入 LangChain：

```powershell
python -m scripts.test_langchain_mcp_bridge
```

## 本地 LLM

LLM 不是运行主诊断流程的必要条件。

如果需要测试本地模型，可以安装额外依赖：

```powershell
python -m pip install -r requirements-llm.txt
```

示例：

```env
LLM_ENABLED=true
LLM_BACKEND=local_hf
LOCAL_LLM_MODEL_ID=Qwen/Qwen2.5-0.5B-Instruct
LOCAL_LLM_QUANTIZATION=int4
```

项目中保留了 FP16、INT8 和 INT4 的本地推理测试脚本，相关实验记录见：

```text
docs/EXPERIMENT_RESULTS.md
```

## 测试

```powershell
pytest -q
```

RAG 和 MCP 可以单独测试：

```powershell
python -m scripts.test_vector_retrieval
python -m scripts.test_langchain_mcp_bridge
```

## 说明

这个项目主要用于学习和整理 AI Agent 在网络运维场景中的实现方式。

仓库中的 IP、设备、交换机状态和知识内容均为模拟数据，不包含真实客户数据、生产配置或运营商内部资料，也不会执行网络配置修改操作。

其他实现说明放在 `docs/` 目录中。

## License

MIT
