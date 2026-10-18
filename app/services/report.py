from app.core.config import Settings
from app.domain.models import (
    DiagnosisResult,
    IncidentInput,
    InventoryRecord,
    KnowledgeHit,
    ParsedEvidence,
    ReportResult,
)
from app.llm.factory import build_report_backend
from app.llm.langchain_report_chain import LangChainReportAssistant
from app.llm.report_guardrails import validate_auxiliary_output, safe_guardrail_metadata


DISCLAIMER = (
    "本报告由脱敏/模拟数据上的辅助诊断系统生成，仅用于学习、复盘和排障信息整理；"
    "不得替代授权维护人员判断，不得据此直接修改生产网络配置。"
)


class ReportComposer:
    """Compose a deterministic report and optionally append a guarded LLM note.

    The LLM never replaces the deterministic report. It may only append a short
    auxiliary explanation after the generated text passes strict guardrails.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.backend = build_report_backend(settings)
        self.assistant = LangChainReportAssistant(self.backend) if self.backend is not None else None

    def compose(
        self,
        incident: IncidentInput,
        inventory: InventoryRecord | None,
        parsed: ParsedEvidence,
        diagnosis: DiagnosisResult,
        knowledge_hits: list[KnowledgeHit],
    ) -> ReportResult:
        base = self._template_report(incident, inventory, parsed, diagnosis, knowledge_hits)
        title = f"终端网络故障辅助诊断报告 - {incident.ip_address}"
        if self.backend is None:
            return ReportResult(
                title=title,
                markdown=base,
                generated_by="deterministic-template",
                disclaimer=DISCLAIMER,
                generation_meta={"backend": "template", "quantization": "none"},
            )

        try:
            generation = self.assistant.generate(base)
        except (RuntimeError, ValueError, OSError) as exc:
            return ReportResult(
                title=title,
                markdown=base,
                generated_by="deterministic-template-fallback",
                disclaimer=DISCLAIMER,
                generation_meta={
                    "backend": self.settings.llm_backend,
                    "quantization": self.settings.local_llm_quantization
                    if self.settings.llm_backend == "local_hf"
                    else "none",
                    "fallback_reason": type(exc).__name__,
                    "guardrail_passed": False,
                    "guardrail_reasons": ["llm_backend_exception"],
                    "guardrail_revision": "v3.1.0",
                },
            )

        if not generation.text:
            meta = generation.as_meta()
            meta.update({"guardrail_passed": False, "fallback_reason": "empty_llm_output",
                         "guardrail_reasons": ["empty_llm_output"],
                         "guardrail_revision": "v3.1.0"})
            return ReportResult(
                title=title,
                markdown=base,
                generated_by="deterministic-template-fallback",
                disclaimer=DISCLAIMER,
                generation_meta=meta,
            )

        guard = validate_auxiliary_output(base, generation.text)
        truncated = bool(
            self.settings.llm_backend == "local_hf"
            and generation.output_tokens is not None
            and generation.output_tokens >= self.settings.local_llm_max_new_tokens
        )
        meta = generation.as_meta()
        meta.update(
            {
                "guardrail_passed": guard.passed,
                "guardrail": safe_guardrail_metadata(guard),
                "guardrail_reasons": list(guard.reasons),
                "guardrail_revision": "v3.1.0",
                "truncated": truncated,
            }
        )

        if not guard.passed or not guard.auxiliary_text:
            meta["fallback_reason"] = "llm_guardrail_rejected"
            return ReportResult(
                title=title,
                markdown=base,
                generated_by="deterministic-template-fallback",
                disclaimer=DISCLAIMER,
                generation_meta=meta,
            )

        enhanced = (
            base
            + "\n\n## 八、AI 辅助说明（非诊断依据）\n\n"
            + "> 本段仅对前述确定性诊断进行语言整理，不改变诊断结论。\n\n"
            + guard.auxiliary_text
            + "\n"
        )
        return ReportResult(
            title=title,
            markdown=enhanced,
            generated_by=f"{generation.backend}:{generation.quantization}:guarded",
            disclaimer=DISCLAIMER,
            generation_meta=meta,
        )

    def _template_report(
        self,
        incident: IncidentInput,
        inventory: InventoryRecord | None,
        parsed: ParsedEvidence,
        diagnosis: DiagnosisResult,
        knowledge_hits: list[KnowledgeHit],
    ) -> str:
        inventory_lines = ["- 未找到资源登记"]
        if inventory:
            inventory_lines = [
                f"- 接入号：`{inventory.access_id}`",
                f"- 登记设备：`{inventory.device_name}`（{inventory.device_role}）",
                f"- 设备位置：{inventory.device_location}",
                f"- 登记端口：`{inventory.registered_port}`",
                f"- 目标 VLAN：`{inventory.expected_vlan}`",
                f"- 网络域：{inventory.network_domain}",
            ]

        evidence_lines = [f"- {item}" for item in diagnosis.evidence] or ["- 暂无足够证据"]
        hypothesis_lines = [f"- {item}" for item in diagnosis.hypotheses]
        next_lines = [f"{idx}. {item}" for idx, item in enumerate(diagnosis.next_steps, start=1)]
        reference_lines = [
            f"- `{hit.source}` / {hit.title}（相关度 {hit.score:.4f}）"
            for hit in knowledge_hits
        ] or ["- 未检索到相关知识片段"]

        return f"""# 终端网络故障辅助诊断报告

> {DISCLAIMER}

## 一、报障信息

- 终端 IP：`{incident.ip_address}`
- 故障现象：{incident.symptom}
- 区域：{incident.area or '未提供'}
- 部门：{incident.department or '未提供'}
- OA 地址是否调整：{'是' if incident.oa_address_changed else '否'}
- OA 是否可访问：{incident.oa_accessible}
- 互联网是否可访问：{incident.internet_accessible}
- 是否间歇性异常：{'是' if incident.intermittent else '否'}

## 二、资源登记

{chr(10).join(inventory_lines)}

## 三、设备与终端证据摘要

- 接口状态：`{parsed.interface.status or '未知'}` / 协议：`{parsed.interface.protocol_status or '未知'}`
- 目标 MAC 是否学习：`{parsed.mac.target_found}`
- MAC 学习端口：`{parsed.mac.learned_port or '未知'}`
- MAC/VLAN：`{parsed.mac.vlan or '未知'}`
- 目标 ARP 是否存在：`{parsed.arp.target_found}`
- ARP MAC：`{parsed.arp.mac_address or '未知'}`
- 接口 Access VLAN：`{parsed.vlan.access_vlan or '未知'}`
- 终端网关：`{parsed.terminal.gateway or '未知'}`
- Ping 线索：`{parsed.terminal.ping_success}`
- DNS 线索：`{parsed.terminal.dns_success}`

## 四、辅助诊断结论

- 诊断代码：`{diagnosis.code.value}`
- 可能层级：**{diagnosis.likely_layer.value}**
- 严重程度：`{diagnosis.severity.value}`
- 置信度：`{diagnosis.confidence:.2f}`
- 结论：{diagnosis.summary}
- 是否建议升级处理：{'是' if diagnosis.escalation_required else '否'}

### 判断证据

{chr(10).join(evidence_lines)}

### 可能原因

{chr(10).join(hypothesis_lines)}

## 五、建议的只读核查与转交步骤

{chr(10).join(next_lines)}

## 六、知识依据

{chr(10).join(reference_lines)}

## 七、人工审批

本报告在归档前应由授权人员确认。任何 VLAN、端口或设备配置调整必须通过正式变更流程执行。
"""
