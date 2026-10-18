from app.domain.enums import DiagnosisCode, Layer, Severity
from app.domain.models import DiagnosisResult, IncidentInput, InventoryRecord, ParsedEvidence
from app.parsers.common import normalize_mac, normalize_port


def _has_link_errors(parsed: ParsedEvidence) -> bool:
    values = [
        parsed.interface.input_errors,
        parsed.interface.output_errors,
        parsed.interface.input_drops,
        parsed.interface.output_drops,
    ]
    return any(value is not None and value >= 10 for value in values)


def diagnose(
    incident: IncidentInput,
    inventory: InventoryRecord | None,
    parsed: ParsedEvidence,
) -> DiagnosisResult:
    evidence: list[str] = []

    if inventory is None:
        return DiagnosisResult(
            code=DiagnosisCode.RESOURCE_NOT_FOUND,
            likely_layer=Layer.RESOURCE,
            severity=Severity.MEDIUM,
            confidence=0.92,
            summary="未在演示资源台账中找到该 IP 对应的接入关系。",
            evidence=[f"查询 IP：{incident.ip_address}"],
            hypotheses=["资源台账缺失或未同步", "输入 IP 不在当前演示范围"],
            next_steps=["核对 IP 是否正确", "由正式维护人员在授权资源系统中查询接入号"],
            escalation_required=True,
        )

    # Fail safely when evidence is stale, ambiguous, or demonstrably unparseable.
    critical = [x for x in parsed.quality_issues if x.startswith((
        "collection_time:", "interface:", "mac:", "vlan:"))]
    if critical:
        return DiagnosisResult(
            code=DiagnosisCode.INSUFFICIENT_EVIDENCE,
            likely_layer=Layer.UNKNOWN,
            severity=Severity.MEDIUM,
            confidence=0.35,
            summary="关键设备证据无法可靠核验，需要补充或重新采集。",
            evidence=["证据质量问题：" + ", ".join(critical)],
            hypotheses=[],
            next_steps=["核对采集时间、设备/接口及命令格式", "重新采集对应只读状态并复核原文"],
            escalation_required=True,
        )

    expected_port = normalize_port(inventory.registered_port)
    observed_port = normalize_port(parsed.observed_port or (parsed.mac.learned_port if parsed.mac.target_found else None) or parsed.interface.port)
    if parsed.observed_device and parsed.observed_device.lower() != inventory.device_name.lower():
        evidence.append(f"登记设备={inventory.device_name}，观察设备={parsed.observed_device}")
        return DiagnosisResult(
            code=DiagnosisCode.RESOURCE_INCONSISTENCY,
            likely_layer=Layer.RESOURCE,
            severity=Severity.MEDIUM,
            confidence=0.90,
            summary="资源登记设备与当前核查设备不一致。",
            evidence=evidence,
            hypotheses=["终端接入位置发生变化", "资源数据未及时更新", "核查设备选择错误"],
            next_steps=["记录设备差异", "由资源管理或正式维护人员核实并更新台账"],
            escalation_required=True,
        )

    if observed_port and expected_port and observed_port != expected_port:
        evidence.append(f"登记端口={inventory.registered_port}，实际学习端口={parsed.observed_port or parsed.mac.learned_port or parsed.interface.port}")
        return DiagnosisResult(
            code=DiagnosisCode.RESOURCE_INCONSISTENCY,
            likely_layer=Layer.RESOURCE,
            severity=Severity.MEDIUM,
            confidence=0.91,
            summary="资源登记端口与设备实时证据不一致。",
            evidence=evidence,
            hypotheses=["终端已迁移端口", "资源登记滞后", "目标 MAC 出现在非预期端口"],
            next_steps=["保留 MAC—端口证据", "请正式维护人员核对接入关系"],
            escalation_required=True,
        )

    interface_status = (parsed.interface.status or "").upper()
    if interface_status in {"DOWN", "ADMINISTRATIVELY DOWN"} or parsed.vlan.interface_shutdown is True:
        evidence.append(f"接口状态={parsed.interface.status or '未知'}")
        if parsed.vlan.interface_shutdown is True:
            evidence.append("接口配置包含 shutdown")
        return DiagnosisResult(
            code=DiagnosisCode.PHYSICAL_OR_TERMINAL_LINK,
            likely_layer=Layer.PHYSICAL,
            severity=Severity.HIGH,
            confidence=0.94,
            summary="目标接口未建立正常物理链路，应优先检查终端与物理连接。",
            evidence=evidence,
            hypotheses=["终端关机或网卡异常", "网线/光电转换链路异常", "接口被管理性关闭"],
            next_steps=["现场确认终端电源、网卡与线缆", "由授权人员核查接口是否应处于关闭状态"],
            escalation_required=True,
        )

    if _has_link_errors(parsed) and (incident.intermittent or incident.fault_type.value == "intermittent"):
        evidence.append("接口错误包或丢弃计数达到演示阈值")
        return DiagnosisResult(
            code=DiagnosisCode.LINK_QUALITY,
            likely_layer=Layer.PHYSICAL,
            severity=Severity.MEDIUM,
            confidence=0.82,
            summary="接口存在较多错误/丢弃统计，可能与间歇性链路质量有关。",
            evidence=evidence,
            hypotheses=["线缆或光电转换器质量问题", "双工/速率协商或端口质量异常"],
            next_steps=["分时段复测错误计数变化", "由授权人员现场核查链路质量"],
            escalation_required=True,
        )

    # Access VLAN is only comparable when the interface is explicitly access-type.
    # For trunk/hybrid, a PVID does not identify the unique user VLAN.
    observed_vlan = parsed.vlan.access_vlan if parsed.vlan.link_type == "access" else None
    if observed_vlan is None and parsed.mac.target_found is True and parsed.mac.parse_status == "success":
        observed_vlan = parsed.mac.vlan
    if observed_vlan is not None and observed_vlan != inventory.expected_vlan:
        evidence.extend([
            f"登记 VLAN={inventory.expected_vlan}",
            f"设备证据 VLAN={observed_vlan}",
        ])
        return DiagnosisResult(
            code=DiagnosisCode.VLAN_MISMATCH,
            likely_layer=Layer.L2,
            severity=Severity.HIGH,
            confidence=0.96,
            summary="接口/MAC 所属 VLAN 与资源台账的目标 VLAN 不一致。",
            evidence=evidence,
            hypotheses=["地址调整后端口 VLAN 未同步", "资源登记与现网配置不一致"],
            next_steps=["保留当前接口配置证据", "由授权维护人员核对变更单和目标 VLAN，禁止由本系统自动修改"],
            escalation_required=True,
        )

    if interface_status == "UP" and parsed.mac.target_found is False and parsed.mac.parse_status == "success":
        evidence.extend(["接口状态=UP", "未在输入的 MAC 表证据中找到目标 MAC"])
        return DiagnosisResult(
            code=DiagnosisCode.L2_NO_MAC,
            likely_layer=Layer.L2,
            severity=Severity.MEDIUM,
            confidence=0.86,
            summary="接口已 UP，但缺少目标终端 MAC 学习证据。",
            evidence=evidence,
            hypotheses=["终端未发送二层流量", "实际接入端口不一致", "MAC 表项老化", "VLAN 配置不匹配"],
            next_steps=["确认终端网卡启用并产生流量", "按目标 MAC 扩大查询范围", "再次核对登记端口与 VLAN"],
            escalation_required=False,
        )


    terminal = parsed.terminal
    if terminal.ip_address and terminal.ip_address != incident.ip_address:
        evidence.append(f"报障 IP={incident.ip_address}，终端输出 IP={terminal.ip_address}")
        return DiagnosisResult(
            code=DiagnosisCode.TERMINAL_CONFIG,
            likely_layer=Layer.TERMINAL,
            severity=Severity.MEDIUM,
            confidence=0.90,
            summary="报障 IP 与终端实际配置不一致。",
            evidence=evidence,
            hypotheses=["终端地址未按计划调整", "采集了错误网卡信息"],
            next_steps=["重新执行 ipconfig /all 并确认目标网卡", "核对地址整改台账"],
            escalation_required=False,
        )

    if inventory.expected_gateway and terminal.gateway and terminal.gateway != inventory.expected_gateway:
        evidence.extend([f"预期网关={inventory.expected_gateway}", f"终端网关={terminal.gateway}"])
        return DiagnosisResult(
            code=DiagnosisCode.TERMINAL_CONFIG,
            likely_layer=Layer.TERMINAL,
            severity=Severity.MEDIUM,
            confidence=0.93,
            summary="终端默认网关与台账预期不一致。",
            evidence=evidence,
            hypotheses=["静态地址配置错误", "地址迁移后网关未同步"],
            next_steps=["核对终端 IP、掩码与默认网关", "修改前应走正式终端配置流程"],
            escalation_required=False,
        )

    if (interface_status == "UP" and parsed.mac.target_found is True
            and parsed.mac.parse_status == "success" and observed_vlan == inventory.expected_vlan):
        evidence.extend(["接口已建立链路", "目标 MAC 已学习", f"VLAN={inventory.expected_vlan} 与台账一致"])
        if parsed.arp.target_found is False:
            evidence.append("设备 ARP 证据中未找到目标 IP")
        elif parsed.arp.target_found is True:
            evidence.append("目标 IP 已存在 ARP 映射")
        if terminal.ping_success is False or terminal.dns_success is False or incident.oa_accessible is False or incident.internet_accessible is False:
            return DiagnosisResult(
                code=DiagnosisCode.UPLINK_POLICY_OR_APPLICATION,
                likely_layer=Layer.L3,
                severity=Severity.MEDIUM,
                confidence=0.78,
                summary="接入侧二层证据基本正常，问题可能位于终端三层配置、上层路径、访问策略或业务系统。",
                evidence=evidence,
                hypotheses=["默认网关或路由异常", "DNS 解析异常", "上层网络路径或访问策略异常", "业务系统自身异常"],
                next_steps=["依次核查 ping 网关、route print、nslookup、tracert", "将证据提交上层网络或业务系统维护人员"],
                escalation_required=True,
            )

    return DiagnosisResult(
        code=DiagnosisCode.INSUFFICIENT_EVIDENCE,
        likely_layer=Layer.UNKNOWN,
        severity=Severity.LOW,
        confidence=0.45,
        summary="当前证据不足以形成可靠的分层判断。",
        evidence=evidence,
        hypotheses=["缺少接口状态、目标 MAC 或 VLAN 配置证据"],
        next_steps=["补充 display interface、display mac-address 和接口配置的脱敏输出", "补充终端 ipconfig、网关连通性与 DNS 测试结果"],
        escalation_required=False,
    )
