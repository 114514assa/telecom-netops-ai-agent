# 加固版变更记录（对照原完整版）

本版本在用户确认的 `telecom-netops-ai-agent.zip` 完整版源码上做增量改造。**不覆盖、不修改原有实验结论**，所有新增测试都属于离线/模拟环境验证。

## 保持不变的关键内容

- LangGraph 的 normalize / inventory / parse / diagnose / retrieve / compose / approval / finalize 八节点与 SQLite Checkpoint、HITL。
- FastMCP 五个既有只读工具及 LangChain MCP Bridge（仍不作为主工作流必经路径）。
- 原有 `knowledge/sanitized/` 知识库、`data/rag_eval/queries_150.json`、RAG 150 Query 实验数据、原量化脚本与历史结果。
- Qwen2.5-0.5B FP16/INT8/INT4(NF4) 本地实验及远程 DeepSeek 端到端历史测试材料。
- 原有 `data/sample_requests/` 五个模拟网络现象案例，不宣称为真实工单。

## 新增与修复

1. `app/parsers/`: 非空但不可识别的 MAC/ARP/Interface/VLAN 不再误判为“目标不存在”；不同接口 CLI 不能串读；MAC 重复且观察冲突标记 ambiguous。
2. `ParsedEvidence`: 原始输入可带 collected_at、vendor、source_system、evidence_mode；解析结果携带 parse_status、quality_issues。
3. `app/services/diagnosis.py`: 关键证据解析失败、过期或同端口 Access VLAN 与 MAC VLAN 冲突时返回 `insufficient_evidence`；不将 Trunk PVID 当成用户 VLAN；VLAN 明确异常优先于无 MAC 的宽泛现象。
4. `app/services/collection.py`: 提供受限本地样例 `FixtureEvidenceCollector`，新增可选 collect 节点。**没有真实设备连接、没有 SSH/网管写配置**。
5. `app/core/auth.py`: Demo 用只读与审批角色令牌；审批前验证任务处于 interrupt 等待态，重复恢复拒绝；生产环境模式拒绝无令牌启动。这并非企业级 IAM。
6. `app/api/routes.py`: 同步 graph.invoke 使用线程池避免阻塞 FastAPI 主事件循环；尚未在完整依赖/负载环境复测并发提升。
7. `app/graph/builder.py`: 每节点输出耗时审计事件；finalize 使用临时文件加原子替换减小半写入风险。
8. `data/rag_eval/queries_document_grounded.json`: 新增 34 条标注精确来源页码/章节的“基于资料的查询问句”，**不是34条真实工单，也未声称已有检索分数**。
9. `historical_results/`: 整理原 ZIP 评测记录与鲁棒性测试资产（排除运行中的 SQLite/WAL、审计日志和中间归档报告）。

## 仍未解决的生产级问题

- 当前未接真实 MSE/交换机，只能切换人工提供 CLI 与固定模拟采集；数据必须继续脱敏。
- 令牌认证仅供单租户演示，缺少 OIDC、完整用户/任务归属、分布式幂等锁、多实例 HA。
- 当前没有运行真实 Ollama/FAISS/DeepSeek/GPU 测试；不能从旧指标推出加固后的新性能。
- 当前仍缺真实匿名生产故障数据及经独立专家标注的诊断准确率；不得把 Query 检索命中率当作诊断准确率。
- Graph State Schema 已增加字段，不能默认兼容旧 checkpoint；推荐启动一个全新的 runtime 目录。


## 2026-10-17：PDF/MCP 文本输入及 Windows 编码修复

- 修复 `tests/test_hardening_network.py` 读取 UTF-8 中文 JSON 时未指定编码，在 Windows 默认 GBK 环境中报错的问题。
- 新增只读 PDF 提取器 `app/services/pdf_ingest.py`，支持文本型 PDF 页面、摘要哈希与容量限制。
- 新增 `extract_pdf_document` FastMCP 工具；原有五个只读 MCP 工具保持不变。
- 新增 `POST /api/v1/documents/pdf/extract` 和 `POST /api/v1/incidents/from-pdf`；后者仅接收明确标记种类的用户 PDF CLI 文本；不自动入库 RAG 或自动判定其真实性。
- 独立附带用户上传的 filesystem MCP 源码参考，但**不**启用其写/移动文件工具。
- 新增来源映射明确的 PDF 测试样本、单元测试、API 合约测试及 Windows 命令文档。
- 这次没有覆盖 `historical_results/`、已有 RAG 150 Query、量化与 DeepSeek 历史评测记录。
