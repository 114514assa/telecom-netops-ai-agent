---
doc_id: kb_endpoint_connectivity
category: endpoint_check
sensitivity: sanitized
source: 终端网络核查资料（脱敏整理）
---

# 终端网络连通性核查

## 1. Windows 网络信息

常见只读命令：

```text
ipconfig
ipconfig /all
route print
```

重点检查：

- IPv4 地址
- 子网掩码
- 默认网关
- DNS
- DHCP 状态
- 网卡 MAC
- 默认路由

## 2. 默认网关测试

示例：

```text
ping 10.20.30.1
```

结果解释：

- 网关可达：说明本地终端到三层网关具备基本可达性
- 网关不可达：需要继续结合 IP 配置、VLAN、ARP、接口和链路状态判断

一次 Ping 结果不能单独作为最终故障结论。

## 3. DNS 测试

示例：

```text
nslookup example.internal
```

若：

- IP 网络连通正常
- 直接访问 IP 正常
- 域名解析失败

则应重点核查 DNS 配置或 DNS 服务。

## 4. 路径测试

示例：

```text
tracert 203.0.113.10
```

路径结果可辅助判断异常发生在：

- 本地接入
- 网关之后
- 上层路由
- 目标网络

但中间节点不回应探测报文并不一定等于该节点故障。

## 5. 地址调整后的检查顺序

1. `ipconfig /all`
2. 核对 IP / 掩码 / 网关 / DNS
3. Ping 默认网关
4. 检查域名解析
5. 验证内部业务
6. 验证互联网或目标业务
7. 必要时查看路径
8. 将终端结果与交换机 Interface / MAC / VLAN / ARP 证据关联

## 6. 典型场景

### 地址与网关不匹配

若终端地址已经调整，但默认网关仍属于旧网络，可能造成网络不可达。

### DNS 配置异常

可能表现为：

- 网关可达
- IP 可访问
- 域名无法解析

### 接入侧正常、业务仍失败

若 Interface、MAC、VLAN、网关均正常，应将排障范围继续上移至：

- DNS
- 路由
- 访问策略
- 业务系统
