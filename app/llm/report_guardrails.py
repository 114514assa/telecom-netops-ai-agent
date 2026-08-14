from __future__ import annotations

import re
from dataclasses import dataclass, field


AUX_SYSTEM_PROMPT = """你是网络运维诊断系统的受限语言整理器，不是诊断器。
核心诊断、事实、置信度和处理边界已经由确定性程序给出，你不得重新判断或修改。

只做一件事：生成一句简短的“辅助说明”。
严格要求：
1. 只输出一行，格式必须为“辅助说明：...” 。
2. 最多 80 个中文字符，句末使用句号。
3. 不得输出或复述任何 IP、MAC、端口号、VLAN 编号、置信度、百分比或其他具体数值。
4. 不得输出诊断代码，不得重新计算或改变诊断结论。
5. 不得新增输入中没有的故障原因、设备状态、修复结果或网络事实。
6. 只能建议只读核查、人工复核、补充证据或转交授权维护人员；不得建议任何修改、调整、修正、变更、下发或写入操作。
7. 禁止建议修改配置、调整策略/VLAN/路由、修正地址或资源、shutdown/undo shutdown、reboot/reset、重启/关闭/复位设备或端口。
8. 不输出标题、表格、原始报告、推导、编号列表或额外段落。
"""

IP_RE = re.compile(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)")
PORT_RE = re.compile(r"(?i)\b(?:GigabitEthernet|GE)\s*\d+/\d+/\d+\b")
MAC_RE = re.compile(
    r"(?i)(?:\b(?:[0-9a-f]{2}(?::|-)){5}[0-9a-f]{2}\b|\b[0-9a-f]{4}(?:-[0-9a-f]{4}){2}\b)"
)
VLAN_RE = re.compile(r"(?i)vlan[^0-9\r\n]{0,12}(\d{1,4})\b")
CONFIDENCE_RE = re.compile(r"(?i)(?:置信度\s*(?:为|是|[：:])?\s*\d|\b0\.\d+\b|\b\d+(?:\.\d+)?\s*%)")

# Explicitly negated change operations are safe statements, e.g.
# “无需手动修改台账信息” or “不得自动修改生产配置”.  They are
# masked before unsafe-action matching so the guardrail does not reject a
# sentence merely because it contains a forbidden verb in a negative scope.
NEGATED_UNSAFE_ACTION_PATTERNS = [
    re.compile(
        r"(?i)(?:无需|不需|不需要|不得|禁止|不应|不可|不要|不必|严禁|不建议)"
        r"\s*(?:人工|手动|自动|直接|擅自|自行|立即)?\s*(?:进行\s*)?(?:任何\s*)?"
        r"(?:修改|调整|修正|下发|写入|删除|新增|重启|关闭|复位|重新配置|重配|改配)"
    ),
]

UNSAFE_PATTERNS = [
    re.compile(r"(?im)^\s*(?:port\s+default\s+vlan|undo\s+shutdown|shutdown|reboot|reset)\b"),
    # Explicit action recommendations, even when the object is omitted later in the sentence.
    re.compile(
        r"(?i)(?:建议|应当|可以|请|需|需要|可能需要).{0,28}"
        r"(?:修改|调整|修正|下发|写入|删除|新增|重启|关闭|复位|重新配置|重配|改配)"
    ),
    # Network/configuration objects followed by a change verb, e.g. “策略调整”
    # or “地址参数并重新配置”.
    re.compile(
        r"(?i)(?:vlan|策略|路由|配置|设备|交换机|端口|接口|网关|地址|参数|资源|台账)"
        r".{0,12}(?:修改|调整|修正|下发|写入|删除|新增|重新配置|重配|改配)"
    ),
    # More explicit change phrases.  Avoid a bare “变更” token because safe
    # phrases such as “核对正式变更记录” use it as a noun.
    re.compile(
        r"(?i)(?:配置变更|变更配置|策略变更|变更策略|路由变更|变更路由|"
        r"地址变更|变更地址|资源变更操作|台账变更操作)"
    ),
]

# These phrases are incompatible with an unresolved/abnormal diagnosis. They are
# checked only against the auxiliary sentence that would actually be appended.
ABNORMAL_CONTRADICTIONS = [
    re.compile(r"(?:未发现|没有|不存在)(?:明显)?异常"),
    re.compile(r"(?:无需|不需要)(?:处理|核查|复核|转交|排查)"),
    re.compile(r"(?:已经|已)(?:恢复|修复|解决)"),
]
NORMAL_CONTRADICTIONS = [
    re.compile(r"(?:确认|表明|说明).{0,8}(?:存在|发现).{0,8}(?:故障|异常)"),
]

# Lightweight diagnosis-aware relevance guard.  It is intentionally conservative:
# a false rejection only falls back to the deterministic report, while an unrelated
# LLM sentence must never be appended merely because it is syntactically safe.
DIAGNOSIS_RELEVANCE_TERMS: dict[str, tuple[str, ...]] = {
    "vlan_mismatch": ("vlan", "台账", "登记", "资源", "变更", "一致", "核对"),
    "physical_or_terminal_link": ("终端", "网卡", "线缆", "链路", "接入", "接口", "端口", "物理", "连接", "状态", "核查"),
    "l2_no_mac": ("mac", "学习", "终端", "流量", "接入", "二层", "核查"),
    "resource_inconsistency": ("资源", "台账", "接入", "迁移", "位置", "设备", "端口", "核对"),
    "uplink_policy_or_application": ("上层", "业务", "dns", "路由", "策略", "转交", "继续"),
    "terminal_config": ("终端", "地址", "网关", "配置", "分配", "核对"),
    "link_quality_issue": ("链路", "线缆", "网卡", "接口", "错误", "统计", "质量", "核查"),
    "evidence_insufficient": ("证据", "补充", "网关", "上层", "进一步", "核查"),
    "access_side_normal": ("正常", "一致", "未见", "无异常", "上层", "业务", "转交", "无需进一步核查"),
}


def diagnosis_relevance(diagnosis_code: str, auxiliary_text: str | None) -> bool:
    if not auxiliary_text:
        return False
    text = normalize_text(auxiliary_text)
    terms = DIAGNOSIS_RELEVANCE_TERMS.get(
        diagnosis_code,
        ("核查", "复核", "确认", "转交", "证据"),
    )
    return any(normalize_text(term) in text for term in terms)


def normalize_text(text: str) -> str:
    text = text.lower().replace("`", "")
    text = text.replace("：", ":").replace("，", ",").replace("｜", "|")
    text = re.sub(r"[\t ]+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text)
    return text.strip()


def canonical_port(value: str) -> str:
    compact = re.sub(r"\s+", "", value).lower()
    return compact.replace("gigabitethernet", "ge")


def canonical_mac(value: str) -> str:
    return re.sub(r"[^0-9a-f]", "", value.lower())


def identifiers(text: str) -> dict[str, set[str]]:
    return {
        "ips": set(IP_RE.findall(text)),
        "macs": {canonical_mac(v) for v in MAC_RE.findall(text)},
        "ports": {canonical_port(v) for v in PORT_RE.findall(text)},
        "vlans": set(VLAN_RE.findall(text)),
    }


def unexpected_identifiers(source: str, output: str) -> dict[str, list[str]]:
    src = identifiers(source)
    out = identifiers(output)
    return {key: sorted(out[key] - src[key]) for key in src}


def _extract_line_value(report: str, labels: tuple[str, ...]) -> str | None:
    for raw_line in report.splitlines():
        line = raw_line.strip().lstrip("-*>").strip()
        line = line.replace("`", "")
        for label in labels:
            match = re.match(rf"(?i)^{re.escape(label)}\s*[：:]\s*(.+?)\s*$", line)
            if match:
                return match.group(1).strip()
    return None


def extract_constraints(source_report: str) -> dict[str, str | None]:
    return {
        "diagnosis_code": _extract_line_value(source_report, ("诊断代码",)),
        "conclusion": _extract_line_value(source_report, ("结论", "诊断结论")),
        "recommendation": _extract_line_value(source_report, ("建议",)),
        "confidence": _extract_line_value(source_report, ("置信度",)),
    }


def build_auxiliary_request(source_report: str) -> str:
    constraints = extract_constraints(source_report)
    code = constraints.get("diagnosis_code") or "未提供"
    conclusion = constraints.get("conclusion") or "未提供"
    recommendation = constraints.get("recommendation") or "仅进行只读核查并转交授权人员"
    return f"""根据下面已经确认的诊断信息生成一句辅助说明。

诊断类型（仅供理解，不要输出）：{code}
已确认结论：{conclusion}
允许参考的处理方向：{recommendation}

不要复述具体地址、设备编号、端口、VLAN编号、MAC、置信度或诊断代码。
不要重新判断原因，不要给出任何配置修改或设备操作命令。
只输出一行：辅助说明：<最多80个中文字符的只读核查/人工复核/转交说明>。
"""


def _extract_auxiliary(raw_output: str) -> tuple[str | None, int]:
    """Extract only the content that can ever reach the application report.

    Small local models sometimes add headers or extra paragraphs. Those extra lines are
    discarded rather than treated as part of the final report. Guardrails validate the
    extracted sentence, while the raw output remains available in audit/evaluation logs.
    """
    nonempty = [line.strip() for line in raw_output.splitlines() if line.strip()]
    for line in nonempty:
        match = re.match(r"^辅助说明\s*[：:]\s*(.+?)\s*$", line)
        if match:
            return match.group(1).strip(), max(0, len(nonempty) - 1)

    # Conservative fallback for weak local models: accept a single short plain sentence
    # only when there is no extra multi-line content. The prefix itself is optional here.
    if len(nonempty) == 1:
        candidate = re.sub(r"^(?:说明|建议)\s*[：:]\s*", "", nonempty[0]).strip()
        if candidate:
            return candidate, 0
    return None, len(nonempty)


@dataclass(slots=True)
class GuardrailResult:
    passed: bool
    format_ok: bool
    identifier_free: bool
    unsafe_free: bool
    contradiction_free: bool
    semantic_relevant: bool
    diagnosis_code_free: bool
    length_ok: bool
    complete_sentence: bool
    auxiliary_text: str | None = None
    candidate_text: str | None = None
    ignored_extra_lines: int = 0
    unsafe_patterns: list[str] = field(default_factory=list)
    contradiction_patterns: list[str] = field(default_factory=list)
    identifiers_in_auxiliary: dict[str, list[str]] = field(default_factory=dict)
    confidence_like_values: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    # Backward-compatible metadata fields. Protected diagnosis fields are no longer
    # delegated to the model in V3, so they remain true by construction.
    diagnosis_code_ok: bool = True
    conclusion_ok: bool = True

    def as_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "format_ok": self.format_ok,
            "identifier_free": self.identifier_free,
            "unsafe_free": self.unsafe_free,
            "contradiction_free": self.contradiction_free,
            "semantic_relevant": self.semantic_relevant,
            "diagnosis_code_free": self.diagnosis_code_free,
            "length_ok": self.length_ok,
            "complete_sentence": self.complete_sentence,
            "auxiliary_text": self.auxiliary_text,
            "candidate_text": self.candidate_text,
            "ignored_extra_lines": self.ignored_extra_lines,
            "unsafe_patterns": self.unsafe_patterns,
            "contradiction_patterns": self.contradiction_patterns,
            "identifiers_in_auxiliary": self.identifiers_in_auxiliary,
            "confidence_like_values": self.confidence_like_values,
            "reasons": self.reasons,
            "diagnosis_code_ok": self.diagnosis_code_ok,
            "conclusion_ok": self.conclusion_ok,
        }


def _mask_negated_unsafe_actions(text: str) -> str:
    """Mask only directly-negated write/change actions before unsafe scanning.

    This prevents false positives such as “无需手动修改台账信息”, while
    keeping positive recommendations like “需人工确认并重新配置” visible to
    the unsafe patterns.
    """
    masked = text
    for pattern in NEGATED_UNSAFE_ACTION_PATTERNS:
        masked = pattern.sub("<NEGATED_SAFE_ACTION>", masked)
    return masked


def validate_auxiliary_output(source_report: str, output: str) -> GuardrailResult:
    constraints = extract_constraints(source_report)
    diagnosis_code = (constraints.get("diagnosis_code") or "").strip()
    auxiliary, ignored_extra_lines = _extract_auxiliary(output)
    format_ok = auxiliary is not None

    if auxiliary is None:
        return GuardrailResult(
            passed=False,
            format_ok=False,
            identifier_free=False,
            unsafe_free=False,
            contradiction_free=False,
            semantic_relevant=False,
            diagnosis_code_free=False,
            length_ok=False,
            complete_sentence=False,
            candidate_text=None,
            ignored_extra_lines=ignored_extra_lines,
            reasons=["auxiliary_line_missing"],
        )

    ids = identifiers(auxiliary)
    identifiers_flat = {key: sorted(values) for key, values in ids.items()}
    identifier_free = all(not values for values in ids.values())
    confidence_hits = CONFIDENCE_RE.findall(auxiliary)
    if confidence_hits:
        identifier_free = False

    unsafe_scan_text = _mask_negated_unsafe_actions(auxiliary)
    unsafe_hits = [pattern.pattern for pattern in UNSAFE_PATTERNS if pattern.search(unsafe_scan_text)]
    unsafe_free = not unsafe_hits

    contradiction_patterns = NORMAL_CONTRADICTIONS if diagnosis_code == "access_side_normal" else ABNORMAL_CONTRADICTIONS
    contradiction_hits = [pattern.pattern for pattern in contradiction_patterns if pattern.search(auxiliary)]
    contradiction_free = not contradiction_hits
    semantic_relevant = diagnosis_relevance(diagnosis_code, auxiliary)
    normalized_code = diagnosis_code.lower().strip()
    diagnosis_code_free = not normalized_code or normalized_code not in auxiliary.lower()

    # 100 characters is a hard application guardrail; prompt target remains <=80.
    length_ok = 1 <= len(auxiliary) <= 100
    complete_sentence = auxiliary.endswith(("。", "！", "？", ".", "!", "?"))

    reasons: list[str] = []
    if not identifier_free:
        reasons.append("identifier_or_numeric_fact_in_auxiliary")
    if not unsafe_free:
        reasons.append("unsafe_operation_suggestion")
    if not contradiction_free:
        reasons.append("semantic_contradiction")
    if not semantic_relevant:
        reasons.append("semantic_irrelevance")
    if not diagnosis_code_free:
        reasons.append("diagnosis_code_echo")
    if not length_ok:
        reasons.append("auxiliary_text_too_long_or_empty")
    if not complete_sentence:
        reasons.append("auxiliary_sentence_incomplete")

    passed = not reasons
    return GuardrailResult(
        passed=passed,
        format_ok=format_ok,
        identifier_free=identifier_free,
        unsafe_free=unsafe_free,
        contradiction_free=contradiction_free,
        semantic_relevant=semantic_relevant,
        diagnosis_code_free=diagnosis_code_free,
        length_ok=length_ok,
        complete_sentence=complete_sentence,
        auxiliary_text=auxiliary if passed else None,
        candidate_text=auxiliary,
        ignored_extra_lines=ignored_extra_lines,
        unsafe_patterns=unsafe_hits,
        contradiction_patterns=contradiction_hits,
        identifiers_in_auxiliary=identifiers_flat,
        confidence_like_values=confidence_hits,
        reasons=reasons,
    )
