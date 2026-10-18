---
doc_id: kb_switch_readonly
category: switch_evidence
sensitivity: sanitized
source: 交换机查询与故障定位资料（脱敏整理）
---

# 交换机只读证据说明

## 1. Interface 状态

常见只读查询示例：

```text
display interface brief
display interface GigabitEthernet 0/0/15
```

重点关注：

- Physical 状态
- Protocol 状态
- 输入/输出流量
- 错误包
- 丢包或异常计数
- 接口描述

### 状态解释

**UP/UP**

说明设备检测到物理链路且链路协议正常，但不能单独证明业务正常。

**DOWN**

优先核查终端、网卡、线缆、物理连接及实际接入位置。

**UP 且错误计数持续增加**

可能存在链路质量问题，应继续核查线缆、模块、物理连接和错误计数变化趋势。

## 2. MAC 地址表

常见只读查询示例：

```text
display mac-address
display mac-address interface GigabitEthernet 0/0/15
display mac-address 0011-2233-4415
```

重点关注：

- 是否存在目标 MAC
- MAC 所在接口
- MAC 所属 VLAN
- MAC 是否与登记终端一致

### 证据解释

接口 UP 且存在目标 MAC：

- 终端与交换机之间通常已经具备基本二层连接
- 仍需结合 VLAN、ARP 和终端配置判断业务状态

接口 UP 但没有目标 MAC：

- 不能直接判定设备故障
- 应检查终端流量、网卡、实际端口、VLAN 和 MAC 老化情况

## 3. ARP 表

常见只读查询示例：

```text
display arp
display arp 10.20.30.15
```

ARP 表可用于核对 IP 与 MAC 的映射关系。

### 典型情况

**MAC 存在，ARP 也存在**

说明当前二层与三层邻接证据较完整，但仍不能保证应用层业务正常。

**MAC 存在，ARP 缺失**

可能是：

- 终端近期未进行三层通信
- ARP 表项老化
- 查询设备或网络位置不正确
- 上层三层关系仍需继续核查

不能仅凭 ARP 缺失直接判定终端或交换机故障。

## 4. VLAN 证据

建议只读取接口当前配置或状态，不执行配置变更。

常见只读查询示例：

```text
display current-configuration interface GigabitEthernet 0/0/15
```

重点识别：

- Access / Trunk 等接口类型
- 当前 VLAN
- 接口描述
- 是否存在关闭状态
- 与资源登记目标 VLAN 是否一致

### 示例

资源登记：

```text
目标 VLAN = 200
```

当前证据：

```text
MAC VLAN = 210
```

可形成结论：

> 当前设备侧 VLAN 证据与资源登记目标 VLAN 不一致，需要人工核对接入关系和网络配置。

不能自动生成配置修改命令。

## 5. 证据优先级

建议按照以下顺序理解证据：

1. 资源登记关系
2. 实际设备
3. 实际端口
4. Interface 状态
5. MAC 学习
6. VLAN
7. ARP
8. 终端 IP / 网关 / DNS
9. 上层业务状态

单项证据只能缩小范围，多项证据一致时再形成较强结论。

## 6. 只读安全边界

知识库允许出现：

- `display`
- `show`
- `ping`
- `nslookup`
- `tracert`
- `ipconfig`

知识库不向 Agent 提供用于自动执行的：

- VLAN 修改
- 端口关闭/开启
- 设备重启
- 配置保存
- 路由下发
- 业务删除或恢复

如确需执行生产变更，应由授权维护人员按照正式流程完成。
