# V3.1.0 版本改进说明（2026-10-17）

## 版本谱系与定位

- V1：简历初始项目——LangGraph、Parser/Rules、MCP、Ollama+FAISS RAG、Qwen 量化。
- V2：工程加固，PDF/MCP、证据质量、模拟采集、资料溯源测试用例，用户侧完成 84 项 pytest 和本地 E2E 实验。
- **V3.1：本轮只处理 Guardrail 误拒与模型有效生成结果可观测性**；V3.2 计划定位并发资源等待，V3.3 计划 RAG 数据标注与 Chunk 对照，V3.4 计划可靠性与权限故障注入。后续版本尚未交付。

## 为什么做这一步

V2 的本地 INT4 完整 Agent 端到端压测为 180/180 工作流完成，但候选输出 72/180 通过 Guardrail、108/180 回退模板。50 Case 质量评测的 INT4 接受率为 84%。这两组样本分布不同，不能直接认为回退率恶化了 44%。它们表明应先取得 **拒绝原因分布** 再调整模型/规则。

另外，旧的 `GuardrailResult.as_dict()` 包含 `candidate_text` 与提取出来的具体 IP/MAC/VLAN，直接保存到 Checkpoint/报告元数据存在隐私风险；V3.1 引入白名单摘要，只保留布尔检查结果、原因代码、候选长度与 SHA-256 摘要。

## 修改一：只处理禁止性语言误判

源文件 `app/llm/report_guardrails.py`：在 `_mask_negated_unsafe_actions` 的否定前缀范围新增「避免」「切勿」，对应“避免直接调整生产 VLAN 配置”属于禁止修改，而不是建议修改；不会改变“请修改/重启/下发”等主动危险建议的拒绝规则。新回归测试覆盖正确否定句、直接危险命令、否定后另有危险操作、诊断方向反转。


## 修改二：结构化 Guardrail 审计

- `app/services/report.py`：原 `guard.as_dict()` 替换为 `safe_guardrail_metadata()`，禁止候选原文与具体标识出现在报告元数据/Checkpoint。
- `app/graph/builder.py`：`report_composed` 的审计数据新增诊断代码、LLM 通过情况、原因代码、回退原因、LLM 延迟/输出 tokens；不增加任何网络设备动作。
- `scripts/analyze_guardrail_v3_1.py`：分析 `runtime_v3_1/audit.jsonl`，输出三个带 `guardrail_v3_1_0_时间戳` 前缀的 JSON/CSV，包括按诊断代码统计接受/回退、原因频次。**不导出候选全文。**
- `scripts/benchmark_agent_e2e.py`：`agent_perf_detail.csv` 新增 `guardrail_passed`、`guardrail_reasons`、`fallback_reason` 三列，不变更 E2E 请求方式或原有性能统计公式。

## 修改三：启动和结果隔离

- 整包解压根目录 `telecom-netops-ai-agent-v3.1.0`，不与 V2 同名。
- `RUN_V3_1_ENV.ps1` 可以指向 V2 的 `.venv\Scripts\python.exe`，不需复制或重建旧环境。
- `runtime_v3_1` 下独立保存 SQLite Checkpoint、inventory、report、audit、FAISS index、测试结果；
- 新版 `app/core/config.py` 默认知识目录由无文件的 `knowledge/demo` 修正为随项目存在的 `knowledge/sanitized`；覆盖环境变量仍优先。

## 保持原样

原 7 份知识文档、41 Chunk 逻辑、150/34 Query、Gold、Qwen 模型/量化脚本、9 个 MCP 工具、PDF 接口、模拟采集、确定性规则、LangGraph 工作流和原历史实验文件都不变。

## 可验证的结果与尚未验证的内容

- 仅离线 Guardrail/Parser/规则及相关测试在构建环境运行通过，完整集成及 GPU 实验因没有全部 LangGraph、LangChain、FAISS、Ollama/CUDA 依赖无法执行。
- V3.1 引入的日志观察功能需由用户 Windows 上开启 `LLM_ENABLED=true` 且真实运行后才能形成拒绝原因分布。
- 未来主要验收指标：相同 5 类模拟 E2E 用例上的接受率、拒绝原因频次、安全违规漏检率、P50/P95、吞吐量。质量、安全和延迟必须同时比较。

