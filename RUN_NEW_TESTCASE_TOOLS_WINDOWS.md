# Windows 旧 `.venv` 环境：新测试设计工具的检查、运行、实验

> 本文适配原项目根目录和既有 `.venv`，不要求重建虚拟环境。原远程 API 已废弃，不要复制旧密钥；建议先 `RAG_ENABLED=false`、`LLM_ENABLED=false` 做离线验证。

## 0. 设置项目路径并检查基础环境

在 PowerShell 运行：

```powershell
$Project = 'C:\Users\Lenovo\Desktop\秋招\agent教学\telecom-netops-ai-agent_B7E78B8AE5BAAEE6B4BAE781\telecom-netops-ai-agent-hardened'
Set-Location -LiteralPath $Project
$Py = Join-Path $Project '.venv\Scripts\python.exe'
Test-Path -LiteralPath $Py
& $Py --version
& $Py -m pip check
```

请**先备份原项目目录**，再解压新版 ZIP 同名目录到此位置；请勿覆盖你本地的 `.venv`、`.env`、`runtime/checkpoints.sqlite3`。不要将上传的第三方 `mcp.json` 合并进项目。

## 1. 不需要 Ollama 的核心与测试用例验证

```powershell
& $Py -m pytest -q tests/test_grounded_testcase_tools.py tests/test_document_grounding.py
& $Py -m pytest -q tests/test_parsers.py tests/test_diagnosis.py tests/test_hardening_network.py tests/test_repository.py
& $Py -m scripts.export_document_grounded_cases --validate-only
& $Py -m scripts.export_document_grounded_cases --format markdown
& $Py -m scripts.export_document_grounded_cases --format csv
& $Py -m scripts.export_document_grounded_cases --format json --category vlan
```

导出默认在 `runtime/generated_testcases/`，均为**待执行测试设计**，不是命中率/诊断正确率。

## 2. FastAPI 接口验证

先确认 `.env` 的 `RAG_ENABLED=false`、`LLM_ENABLED=false`，若本机开发且暂未配置令牌，可以使用 `DEMO_AUTH_ENABLED=false`（**只能本机测试**）。

```powershell
& $Py -m scripts.seed_db
& $Py -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

在**新 PowerShell** 终端执行：

```powershell
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/testcases/document-grounded/categories'
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/testcases/document-grounded?category=vlan&limit=3'
Invoke-WebRequest 'http://127.0.0.1:8000/api/v1/testcases/document-grounded/export?format=markdown&limit=3' -OutFile '.\runtime\generated_testcases\downloaded_cases.md'
```

如果 `DEMO_AUTH_ENABLED=true`，须在请求中通过 `X-Demo-Token` 提供有效 Reader/Approver Token；没有令牌时会返回 401，不能通过关闭身份控制对外部署来规避。

## 3. MCP 实际工具发现与调用

在 `.env` 暂时设置 `RAG_ENABLED=false`（避免 Ollama 依赖影响离线工具测试）：

```powershell
& $Py -m scripts.test_documented_testcase_mcp_bridge
```

成功时会列出三个工具名并返回来源分类与用例片段。**MCP stdio 验证仅应在你本机现有环境运行**，交付构建环境未包含完整 LangGraph/MCP 依赖。

## 4. 继续原有实验（与新增工具互相独立）

有 Ollama 模型后：

```powershell
ollama list
& $Py -m scripts.build_vector_index
& $Py -m scripts.evaluate_rag_retrieval_150 --dataset data/rag_eval/queries_document_grounded.json --top-k 5 --repeats 1 --warmup 1
```

这条命令针对的是**34 条资料约束 Query**，脚本可能显示“不是 150 条”的警告，因为它默认服务于原 150 Query。新增测试用例生成不依赖运行此实验。原 150 条正式评测仍按原手册独立运行和比较，不要合并或替换旧报告。

完成以上环境与功能验证后，再运行原有 Qwen INT4 质量评测、MCP、LangGraph/HITL 与端到端并发实验。任何新量化表现都应重新实测，不应拿旧结果代替。

## 5. 常见问题

- `UnicodeDecodeError: gbk`：项目读取文本统一使用 `encoding='utf-8'`，该错误在上一版已经修复且本版保留。
- `PackageNotFoundError` / `ModuleNotFoundError`：记录缺失包名并根据 requirements 针对性安装，不要整体重建 `.venv`。
- `langchain-community` 弃用提示：是警告而非当前测试失败的直接原因。
- 34 条测试用例 ≠ 34 条真实电信工单，也 ≠ 34 条已通过测试。
- 当前只读测试设计功能不会调用外部 GitHub/Slack/搜索等服务，上传 ZIP 中携带的任何密钥都**不能**继续使用，应轮换。
