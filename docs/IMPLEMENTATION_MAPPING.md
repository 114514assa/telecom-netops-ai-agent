# 业务流程与系统实现映射

| 通用排障步骤 | 系统实现 |
|---|---|
| 收集 IP、故障现象与终端信息 | `IncidentInput` |
| 查询模拟接入资源 | `InventoryRepository.find_by_ip` |
| 解析接口状态 | `parse_interface_output` |
| 解析 MAC、端口和 VLAN | `parse_mac_output` |
| 解析 IP—MAC 邻接 | `parse_arp_output` |
| 解析接口 VLAN 信息 | `parse_vlan_output` |
| 比对资源登记与当前证据 | `diagnose` 确定性规则 |
| 检索相关知识 | TF-IDF / Ollama Embedding + FAISS |
| 生成可追溯报告 | Report Composer + KnowledgeHit |
| 人工确认与恢复 | LangGraph HITL + SQLite Checkpoint |
