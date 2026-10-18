# 加固版 Agent：PDF 输入与 MCP 只读工具集成／Windows 启动步骤

## 0. 先讲清楚能力边界

- `mcp-local.zip` 包含 **filesystem MCP、Allure MCP、XMind MCP**。其中 filesystem MCP 仅支持 UTF-8 文本文件的读写等操作，**不支持直接解析 PDF 正文**，而且包含写文件、移动文件的工具。
- 为了保持网络诊断项目“只读”约束，新版**没有启动**原来的宽权限 filesystem MCP Server。它的相关源码位于 `third_party/filesystem-mcp-server-reference/`，仅留作审计/参考。
- 在原 FastMCP 中增加第六个只读工具 `extract_pdf_document(pdf_base64)`：基于 pypdf 提取**文本型 PDF** 正文，返回页码与 SHA-256，不访问本机任意路径。
- HTTP API 提供 `POST /api/v1/documents/pdf/extract`（仅提取，不启动诊断）和 `POST /api/v1/incidents/from-pdf`（需要显式给出 `evidence_kind`，才作为用户提交的 CLI 证据进入原图）。
- 扫描件／图像 PDF 无 OCR；加密 PDF 不接受；大小 5 MiB、页数 20、提取字符 30,000 上限。截断文本禁止用于诊断。
- **PDF 来自用户输入，数据未经验证**。PDF 本身既不能证明设备命令真的执行过，也不能证明采集时间；上传 PDF 中的恶意文字不能被视作模型指令。PDF 解析代码依然运行在进程内，并非生产级安全沙箱。
- PDF 上传的文本若进入 LangGraph State，可能被 SQLite Checkpoint 保存。**仅使用脱敏的模拟或授权材料。** PDF 不会自动变成 RAG 知识，也不修改原来的 150 Query 与历史评测数据。

## 1. 在你的目录中切换项目，并验证旧 venv

在 **Windows PowerShell** 打开以下内容（整段复制，不需重新创建 venv）：

```powershell
$Project = 'C:\Users\Lenovo\Desktop\秋招\agent教学\telecom-netops-ai-agent_B7E78B8AE5BAAEE6B4BAE781\telecom-netops-ai-agent-hardened'
Set-Location -LiteralPath $Project
$Py = Join-Path $Project '.venv\Scripts\python.exe'
& $Py --version
& $Py -m pip check
```

备份原目录，再将本 ZIP 的 `telecom-netops-ai-agent-hardened/` 中更新文件合并到该项目。**不要覆盖本机 `.venv`、本地 `.env`、模型缓存以及已生成的 `runtime/` 数据**；不要从 ZIP 中导入旧的历史 checkpoint。当环境运行在新分支时，推荐在专用目录测试。

## 2. 本次新增依赖（不升级 torch/transformers）

```powershell
& $Py -m pip show pypdf python-multipart
& $Py -m pip install 'pypdf>=5,<7' 'python-multipart>=0.0.20,<1'
& $Py -m pip check
```

若两项已安装且兼容，可跳过安装。无需 Node.js，PDF MCP 是 Python FastMCP 的新增工具；附带的 TypeScript filesystem MCP 仅作参考。

## 3. 先回归 Windows UTF-8 错误与 PDF 功能

```powershell
& $Py -m pytest -q tests/test_hardening_network.py::test_historical_documented_vlan_pattern_remains_classified
& $Py -m pytest -q tests/test_pdf_ingest.py tests/test_pdf_upload_api.py
& $Py -m pytest -q tests/test_parsers.py tests/test_diagnosis.py tests/test_hardening_network.py tests/test_auth_boundaries.py tests/test_repository.py
& $Py -m pytest -q
```

本次在 Linux 的离线环境已执行 PDF 纯解析测试与核心单测。API 合约测试使用假工作流验证入参绑定，不等于在 Windows 的完整 LangGraph 环境中已经执行端到端测试；上述命令需你本机复核。

## 4. 最小配置优先：不启用 LLM / RAG

保留原本 `.env` 的其他配置，只临时设置：

```dotenv
APP_ENV=development
HOST=127.0.0.1
PORT=8000
RAG_ENABLED=false
LLM_ENABLED=false
DEMO_AUTH_ENABLED=false
```

禁用 Demo 鉴权仅限可信的本机 `127.0.0.1`，不要绑定公网。生产场景需要更严格的鉴权、隔离与文件解析安全设计。原来废弃的 API 密钥不要复制到新包。

```powershell
& $Py -m scripts.seed_db
& $Py -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

检查浏览器 `http://127.0.0.1:8000/docs`，或新开 PowerShell：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

## 5. 验证 PDF 提取（不进入故障诊断）

在项目根目录新开 PowerShell，重新设置 `$Project` 和 `$Py`，然后执行：

```powershell
& $Py -m scripts.demo_pdf_input --pdf tests/fixtures/documented_interface_excerpt.pdf
```

期望输出 PDF 解析文本、页码、`sha256`。测试 PDF 文本由仓库已有 `vlan_mismatch.json` 的 `interface_output` 制作，**不是另外构造的真实电信工单**。

## 6. 通过 PDF 启动诊断（谨慎）

测试样例只含 Interface CLI，而不是完整的 MAC/VLAN/ARP 组合。因此如下命令会将 PDF 当作 **Interface 证据**输入，不能凭这一页 PDF 期待一定输出 VLAN mismatch。

```powershell
& $Py -m scripts.demo_pdf_input --start `
  --pdf tests/fixtures/documented_interface_excerpt.pdf `
  --incident data/sample_requests/vlan_mismatch.json `
  --kind interface `
  --port GE0/0/15
```

`--incident` 支持 `{ "incident": {...}, "evidence": {...} }` 样例，也支持独立的 Incident JSON。**此命令只使用所选 PDF 内容，不会偷偷拼接 JSON 样例中其他证据。** 输出中记录 `thread_id`，审批流程按原有 `/api/v1/incidents/{thread_id}/resume` 继续；不要把批准理解为允许网络配置写入。

若在 `.env` 中启用 Demo Reader/Approver 令牌，提取与启动调用需增加 `--token <reader-token>`；审批使用 Approver 令牌。不要将真实令牌放进 Git 或测试记录。

## 7. 验证新增 PDF MCP 工具

```powershell
& $Py -m scripts.test_pdf_mcp_bridge
```

这个脚本使用 `LangChainMCPBridge` 经 `stdio` 启动原 FastMCP Server、列出工具并调用新 `extract_pdf_document`。运行时必须保证 MCP 服务依赖可用。PDF 工具只提取用户传来的 Base64 文档，不读用户指定的任意磁盘路径。

## 8. 恢复 RAG、Qwen 与原实验

核心端到端验证完成后，再开启：

```dotenv
RAG_ENABLED=true
RAG_FAIL_OPEN=true
LLM_ENABLED=true
LLM_BACKEND=local_hf
LOCAL_LLM_MODEL_ID=Qwen/Qwen2.5-0.5B-Instruct
LOCAL_LLM_QUANTIZATION=int4
```

```powershell
ollama list
ollama pull qwen3-embedding:0.6b
& $Py -m scripts.build_vector_index
& $Py -m scripts.test_vector_retrieval
& $Py -m scripts.evaluate_rag_retrieval_150 --help
& $Py -m scripts.benchmark_quantization_v2 --help
```

**先查看 `--help` 后依照原评测脚本运行**。原 150 Query 与历史量化记录未改写；PDF 输入功能的效果需要独立测试，不能把历史指标当作本次集成的验证结果。

## 9. 故障定位

- `UnicodeDecodeError: gbk`：此次已修复 `tests/test_hardening_network.py` 中 `read_text(encoding='utf-8')`。其它新文件也统一用 UTF-8 读取。
- `ModuleNotFoundError: pypdf`：只安装缺少的 `pypdf`，不要先大规模升级依赖。
- `ModuleNotFoundError: multipart`：安装 `python-multipart`。
- HTTP 422 `no_extractable_text`：PDF 是扫描件或没有文本层；不自动 OCR。
- HTTP 422 `encrypted_pdf` / `file_size` / `page_count`：PDF 不符合解析限制。
- `RAG` 索引或 Ollama 未准备好：先保持 `RAG_ENABLED=false` 完成核心测试。
- MCP 验证失败：先确认 `& $Py -m scripts.test_langchain_mcp_bridge`，再验证 PDF MCP 工具。
