# 资料溯源测试用例工具：设计、边界与来源

## 1. 本次新增什么

在 `app/services/grounded_testcases.py` 中新增**只读**测试设计工具，供 CLI、FastAPI、MCP 共用。原始 `AI智能生成测试用例.zip` 经过审查后，选择性采纳了“测试用例 ID、前置条件、测试步骤、预期结果、优先级、需求追溯”和 Markdown/JSON 转换的设计思路。

本工具**不是**自动生成真实网络故障的 LLM，也不让模型自己编写预期诊断结论。当前 34 条 Query 的语义和人工标注 Gold 不改写。此模块所做的是**自动形成可执行的检索验收测试设计**，而不是创建网络工单。对于没有可验证来源的情况，必须明确标记。

## 2. 原工具分析及取舍

| 上传资料里的能力 | 处理 | 理由 |
| --- | --- | --- |
| `.trae/skills/case_design/SKILL.md` 测试用例设计规范 | 借鉴字段/测试方法 | 可用于独立测试设计，未照搬非网络业务数据 |
| `markdown_to_json_parser.py` / XMind 转换脚本 | 将格式能力重构为 JSON/Markdown/CSV | 原工具含硬编码路径、业务标题、可选依赖；不适合直接注入服务 |
| PDF 解析脚本 | 复用项目原有受限 pypdf 解析服务 | 避免两个不同 PDF 读取系统造成不一致 |
| 图片 OCR、PPT、外部浏览器工具 | 不默认启用 | 无法保证出处与诊断真实性，且会增加额外执行权限和依赖 |
| `mcp.json` 里的 GitHub、Slack、搜索等外部 MCP | 不导入配置、令牌或外部权限 | 上传配置含敏感凭证、Mac 专用路径及无关服务，必须撤销/轮换凭证 |

## 3. 使用的数据以及验证边界

- 数据唯一来源：`data/rag_eval/queries_document_grounded.json`（34 条由既有电信运维资料标注出处的受控 Query）。
- 可核实：每条 ID 唯一，包含来源文档名、页码、章节、人工支持摘要；所有 Gold 知识文件与 Markdown 章节存在。
- **不能独立核实：** 原始电信 PDF 并未保存在当前项目包内，运行时无法验证支持摘要是否逐字精确描述原始 PDF。需要有权限的人对照上传原件复核。
- 生成的所有用例 `verification_state=not_executed`，仅表示测试**计划**。其 `expected` 是待检验的目标，不是已测结果。
- `priority=P1` 只是工程默认优先级，不是原始电信文档事实。
- `Query + Gold` 检索测试不应被误写成故障分类准确率，也不应被混入原有 150 Query 历史测评后改变简历口径。
- 原来的 150 条 Query、源码、历史实验结果保持不变。

## 4. 三类使用方式

**命令行**：`python -m scripts.export_document_grounded_cases --format markdown`。也支持 `--format csv/json`、`--category vlan`、`--validate-only`。

**REST 接口**（使用现有 Demo 读权限）：

- `GET /api/v1/testcases/document-grounded/categories`
- `GET /api/v1/testcases/document-grounded?category=vlan&limit=3`
- `GET /api/v1/testcases/document-grounded/export?format=csv&limit=3`

**只读 MCP**：

- `list_document_grounded_testcases`
- `generate_document_grounded_testcases(category, limit)`
- `export_document_grounded_testcases(format, category, limit)`

所有工具只对经过版本管理的本地资料约束 JSON 和 `knowledge/sanitized/` 读取；MCP 不接受任意文件路径，永远不自动登录网络设备，也不会写配置或执行用户传来的脚本。

## 5. 为什么仍不叫“真实故障自动生成”

当前运维资料更适合支撑**排障 SOP 和 RAG 检索评测设计**。如果未来要真正生成可评价“诊断准确率”的新案例，应取得具有合法访问权限、脱敏、包含采集时间和人工复核标签的工单与 CLI 证据。没有这些条件，不应让 LLM 凭空合成真实工单。

## 6. 独立测试方法

`python -m pytest -q tests/test_grounded_testcase_tools.py tests/test_document_grounding.py`

有完整依赖后再执行：

`python -m pytest -q tests/test_grounded_testcase_api.py`

MCP stdio 真实联调：

`python -m scripts.test_documented_testcase_mcp_bridge`

环境变量 `RAG_ENABLED=false` 可以避免 MCP Server 启动时尝试加载 Ollama 索引。CLI 生成测试用例不依赖 RAG/LLM/GPU。
