# 接入网故障诊断 Agent 加固版｜运行与启动指令

> 对象：Windows PowerShell / Linux 或 macOS，推荐 Python 3.11 或 3.12。请在解压后的项目根目录执行。


## 1. 安装依赖

### Windows PowerShell

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

### Linux / macOS

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt
cp .env.example .env
```

请使用虚拟环境。无 Py3.11 时也可尝试 3.12。依赖版本由原项目 `requirements.txt` 管理，首次安装需要联网。

## 2. 最小核心诊断模式（无需 Ollama / GPU / 远程模型）

编辑 `.env` 为：

```dotenv
APP_ENV=development
RAG_ENABLED=false
LLM_ENABLED=false
DEMO_AUTH_ENABLED=false
REQUIRE_APPROVAL=true
```

初始化模拟资源库并启动：

```bash
python -m scripts.seed_db
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

访问 `http://127.0.0.1:8000/`、`http://127.0.0.1:8000/docs` 或 `http://127.0.0.1:8000/health`。

## 3. 运行两种证据模式

### A. 保留原模式：人工提供 CLI

Windows PowerShell：

```powershell
$body = Get-Content 'data/sample_requests/vlan_mismatch.json' -Raw -Encoding UTF8
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/v1/incidents' -Method Post -ContentType 'application/json' -Body ([System.Text.Encoding]::UTF8.GetBytes($body))
```

Linux/macOS：

```bash
curl -sS -X POST http://127.0.0.1:8000/api/v1/incidents \
  -H 'Content-Type: application/json' \
  --data-binary @data/sample_requests/vlan_mismatch.json
```

### B. 新增可选的模拟只读采集模式

复制 `data/sample_requests/vlan_mismatch.json` 的 `incident`，将 `evidence` 改为：

```json
{"evidence": {"evidence_mode": "simulated_collection"}}
```

如用 Python 生成演示请求：

```bash
python -m scripts.prepare_mock_collection_request
curl -sS -X POST http://127.0.0.1:8000/api/v1/incidents -H 'Content-Type: application/json' --data-binary @runtime/mock_collection_request.json
```

`collect` 仅从 `data/sample_requests` 的固定白名单读取演示文本，不登录真实交换机，也不会发起任意 HTTP、SSH、SNMP 请求。不存在匹配模拟样例时会报采集失败/证据不足，不能自动捏造实时设备证据。

## 4. 审批与查询

POST 创建任务后读取响应中的 `thread_id`，工作流会在 `approval` 节点暂停。

```bash
curl -sS http://127.0.0.1:8000/api/v1/incidents/<thread_id>
# 人工确认后批准归档（将 <thread_id> 替换为实际值）
curl -sS -X POST http://127.0.0.1:8000/api/v1/incidents/<thread_id>/resume \
  -H 'Content-Type: application/json' \
  -d '{"approved":true,"comment":"复核后同意归档"}'
```

如果 `approved=false`，保留 Checkpoint 和审计结果，不生成最终归档报告。重复 resume 将返回 HTTP 409（需要完整环境集成复测）。查看历史状态可使用 GET 接口。

## 5. 演示令牌保护（建议开启）

在 `.env` 中使用两个**不相同的高熵测试令牌**：

```dotenv
DEMO_AUTH_ENABLED=true
DEMO_READER_TOKEN=替换为安全随机生成的只读令牌
DEMO_APPROVER_TOKEN=替换为独立的审批令牌
```

访问 `/api/v1/*` 要在 HTTP Header 中携带 `X-Demo-Token`。查询/创建任务可用 Reader 或 Approver 令牌；`/resume` 必须使用 Approver 令牌。Web 静态演示页未实现令牌输入 UI，启用鉴权后请使用 Swagger 自定义请求客户端或 curl/PowerShell 提交 Header。

```bash
curl -H 'X-Demo-Token: <reader-token>' http://127.0.0.1:8000/api/v1/inventory
```

这是单用户 Demo token 校验，**不等于生产级 OIDC、企业 IAM、操作审计的完整体系**。不要在公网以未鉴权配置暴露服务。

## 6. 开启本地 RAG（需要 Ollama）

```bash
ollama pull qwen3-embedding:0.6b
```

确认本机 Ollama 服务已经运行；修改 `.env`：

```dotenv
RAG_ENABLED=true
RAG_KNOWLEDGE_DIR=knowledge/sanitized
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_EMBED_MODEL=qwen3-embedding:0.6b
LLM_ENABLED=false
```

首次构建索引：

```bash
python -m scripts.build_vector_index
```

重启 uvicorn；FAISS 保存 `runtime/vector_index/knowledge.faiss`，知识映射存 `metadata.json`。

### 评测旧的 150 Query 与新的来源约束 Query

```bash
python -m scripts.evaluate_rag_retrieval_150 --dataset data/rag_eval/queries_150.json --repeats 1 --warmup 1
python -m scripts.evaluate_rag_retrieval_150 --dataset data/rag_eval/queries_document_grounded.json --repeats 1 --warmup 1
```

原 150 条评测属于历史模拟集；新 34 条是有源文档页码/章节的提问，**新增集必须重新运行后才能报告 Hit@K/MRR**。

## 7. 本地 Qwen 与远程 LLM（可选）

核心规则诊断不依赖 LLM。要复现模型量化，请在有合适 GPU 和驱动环境下额外安装：

```bash
python -m pip install -r requirements-llm.txt
```

然后参照 `RUN_QUANTIZATION_50.txt`、`docs/QUANTIZATION_FINAL.md` 原始脚本。启用可选模型需在 `.env` 设置 `LLM_ENABLED=true` 及相应 Backend 参数；仅使用你有权限的 API/模型，不要在 ZIP 或 Git 中存放密钥。

既有 FP16/INT8/INT4 与 DeepSeek 评测归档在 `historical_results/`，本版本并未重新执行 GPU 或远程模型性能测试。

## 8. 测试与排错

```bash
python -m compileall -q app
pytest -q
pytest -q tests/test_hardening_network.py tests/test_document_grounding.py tests/test_auth_boundaries.py
```

常见问题：

- `ModuleNotFoundError: langgraph`/`langchain_core`：先安装 `requirements.txt`；不要误以为系统已测试通过。
- RAG 检索为空：检查 Ollama、Embedding 模型与向量索引是否存在，必要时重新构建。`RAG_ENABLED=false` 可先验证确定性主流程。
- 无法 resume：先确认返回了 `awaiting_approval`，并使用同一 `thread_id`，不要重复提交。
- 模拟采集未找到资源：只支持已提供的白名单样例，不能对任意 IP 执行真实采集。
- 升级后旧任务无法恢复：State Schema 已变化，使用全新的 `runtime/`，不要直接搬运历史 SQLite/WAL。
- Docker 启动：`docker compose up --build`；已将端口绑定到本机回环地址；若开启 RAG 需要另行处理容器访问 Ollama 的网络地址。


