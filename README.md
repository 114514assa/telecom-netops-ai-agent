# Telecom NetOps AI Agent — V3.1.0

**V3.1 第一步：Guardrail 可观测性 + 否定安全建议误判修复。**

请先读：[版本改进说明](docs/iterations/V3_1_CHANGELOG.md) 与 [Windows 独立启动](RUN_V3_1_WINDOWS.md)。

本版本由上一版 **测试用例工具集成完整加固版** 源码原样复制并做有限改动；不连接真实生产网。
V2 原工程目录、`.env`、`.venv`、运行数据库、历史实验均不覆盖。

- 原有 LangGraph / 规则诊断 / 9 个 MCP / PDF / RAG / 150+34 Query / Qwen 量化脚本全部保留。
- 新增版本化的报告生成拒绝原因审计与分析脚本，不将原始候选文本、IP/MAC/VLAN 具体标识写入新的 Guardrail 元数据。
- 修正“避免直接调整/切勿直接修改”类禁止生产操作表述的误拒，保留对积极修改建议和诊断方向反转的拒绝。
- 使用 `RUN_V3_1_ENV.ps1` 隔离 SQLite、报告、审计和 FAISS 文件到 `runtime_v3_1`。

**验收边界：** 离线 Guardrail/部分核心测试已经运行；完整本地 Qwen、端到端、GPU 和全部集成测试仍需在有原 `.venv` 的 Windows 主机运行。不要在未复测时宣称回退率和性能已改善。
