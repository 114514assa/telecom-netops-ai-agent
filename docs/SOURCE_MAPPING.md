# 文档内容到系统实现的映射

| 文档中的工作内容 | 系统实现 |
|---|---|
| 收集 IP、区域、故障现象、OA 地址调整和访问情况 | `IncidentInput` |
| IP 查询接入号 | `InventoryRepository.find_by_ip` |
| MSE/资源界面核对设备、位置、端口、VLAN | 模拟 `inventory.csv` 与只读查询工具 |
| 查看接口 UP/DOWN、流量、错误包 | `parse_interface_output` |
| 查询目标 MAC、端口和 VLAN | `parse_mac_output` |
| 查看目标 IP—MAC 邻接 | `parse_arp_output` |
| 查看接口 Access/Trunk、VLAN、shutdown | `parse_vlan_output` |
| 对比资源登记与设备实时状态 | `diagnose` 中的资源一致性规则 |
| 接口 DOWN、UP 无 MAC、UP 有 MAC 但业务不通 | 分层诊断规则 |
| ping、tracert、nslookup、ipconfig 等终端核查 | `parse_terminal_output` 与报告建议 |
| 记录与复测 | Checkpoint、审计 JSONL、Markdown 报告 |

城域网与云网培训中涉及的 CR、MSE、OLT、SW、PON、交换机接入和不同承载网络，仅用于知识背景和设备角色说明。当前原型不覆盖 PON 光猫注册、OLT 下发、专线开通、MSE 配置和生产资源编排。
