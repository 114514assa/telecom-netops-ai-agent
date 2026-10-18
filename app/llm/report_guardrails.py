from __future__ import annotations

import re
from dataclasses import dataclass, field


AUX_SYSTEM_PROMPT = """你是网络运维诊断系统的受限语言整理器，不是诊断器。
核心诊断、事实和处理边界已经由确定性程序给出，你不得重新判断或修改。

只做一件事：把已确认结论和只读处理方向整理成一句简短辅助说明。
严格要求：
1. 只输出一行，格式必须为“辅助说明：...” 。
2. 最多 80 个中文字符，句末使用句号。
3. 必须保持原结论的状态方向不变；“不一致、未学习、DOWN、证据不足、未见异常”等含义不得改成相反含义。
4. 不得输出或复述任何 IP、MAC 地址、端口号、VLAN 编号、置信度、百分比或其他具体数值。
5. 不得输出诊断代码，不得新增输入中没有的故障原因、设备状态、修复结果或网络事实。
6. 只能建议只读核查、人工复核、补充证据或转交授权维护人员；不得建议任何配置修改、设备操作或生产变更。
7. 不得使用“无需其他操作”“已经完全确认”“可以排除其他问题”等超出已有证据的绝对化表述。
8. 使用自然、完整的中文；VLAN、MAC、ARP、Interface 等标准网络缩写可保留，不输出字段名、列表、标题或额外段落。
"""

IP_RE = re.compile(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)")
PORT_RE = re.compile(r"(?i)\b(?:GigabitEthernet|GE)\s*\d+/\d+/\d+\b")
MAC_RE = re.compile(
    r"(?i)(?:\b(?:[0-9a-f]{2}(?::|-)){5}[0-9a-f]{2}\b|\b[0-9a-f]{4}(?:-[0-9a-f]{4}){2}\b)"
)
VLAN_RE = re.compile(r"(?i)vlan[^0-9\r\n]{0,12}(\d{1,4})\b")
CONFIDENCE_RE = re.compile(r"(?i)(?:置信度\s*(?:为|是|[：:])?\s*\d|\b0\.\d+\b|\b\d+(?:\.\d+)?\s*%)")

NEGATED_UNSAFE_ACTION_PATTERNS = [
    re.compile(
        r"(?i)(?:无需|不需|不需要|不得|禁止|不应|不可|不要|不必|严禁|不建议|避免|切勿)"
        r"\s*(?:人工|手动|自动|直接|擅自|自行|立即)?\s*(?:进行\s*)?(?:任何\s*)?"
        r"(?:修改|调整|修正|下发|写入|删除|新增|重启|关闭|复位|重新配置|重配|改配)"
    ),
]

UNSAFE_PATTERNS = [
    re.compile(r"(?im)^\s*(?:port\s+default\s+vlan|undo\s+shutdown|shutdown|reboot|reset)\b"),
    re.compile(
        r"(?i)(?:建议|应当|可以|请|需|需要|可能需要).{0,28}"
        r"(?:修改|调整|修正|下发|写入|删除|新增|重启|关闭|复位|重新配置|重配|改配)"
    ),
    re.compile(
        r"(?i)(?:vlan|策略|路由|配置|设备|交换机|端口|接口|网关|地址|参数|资源|台账)"
        r".{0,12}(?:修改|调整|修正|下发|写入|删除|新增|重新配置|重配|改配)"
    ),
    re.compile(
        r"(?i)(?:配置变更|变更配置|策略变更|变更策略|路由变更|变更路由|"
        r"地址变更|变更地址|资源变更操作|台账变更操作)"
    ),
]

ABNORMAL_CONTRADICTIONS = [
    re.compile(r"(?:未发现|没有|不存在)(?:明显)?异常"),
    re.compile(r"(?:无需|不需要|不必).{0,10}(?:其他|额外|进一步)?(?:操作|处理|核查|复核|转交|排查)"),
    re.compile(r"(?:已经|已)(?:恢复|修复|解决)"),
    re.compile(r"(?:可以|可).{0,6}排除.{0,12}(?:其他|其余)?(?:问题|故障|原因)"),
]

NORMAL_CONTRADICTIONS = [
    re.compile(r"(?:确认|表明|说明).{0,8}(?:存在|发现).{0,8}(?:故障|异常)"),
    re.compile(r"接入侧.{0,8}(?:存在|发现|确认|属于).{0,8}(?:故障|异常)"),
    re.compile(r"接入侧(?:故障|异常)"),
]

UNSUPPORTED_ROOT_CAUSE_PATTERNS = [
    re.compile(r"(?:可能|疑似|推测).{0,6}(?:原因|根因).{0,6}(?:是|为|包括|涉及)"),
    re.compile(r"(?:原因|根因).{0,4}(?:可能)?(?:是|为|包括|涉及)"),
    re.compile(r"(?:可能由于|可能由|疑似由).{1,24}(?:导致|引起|造成)"),
]

# Hard text-quality failures. These are intentionally narrow and only catch obvious
# malformed/template-echo output; they do not try to judge writing style in general.
TEXT_QUALITY_PATTERNS = [
    re.compile(r"(?i)只\s*read"),
    re.compile(r"(?:已确认结论|允许参考的处理方向)\s*[：:]"),
    re.compile(r"(?:学学习|核核查|复复核|确确认|登登记|资资源|端端口|变变更)"),
    re.compile(r"(?:核查|复核|确认|转交)\s*/\s*(?:核查|复核|确认|转交)"),
]

DIAGNOSIS_RELEVANCE_TERMS: dict[str, tuple[str, ...]] = {
    "vlan_mismatch": ("vlan", "台账", "登记", "资源", "变更", "一致", "核对"),
    "physical_or_terminal_link": ("终端", "网卡", "线缆", "链路", "接入", "接口", "端口", "物理", "连接", "状态", "核查"),
    "l2_no_mac": ("mac", "学习", "终端", "流量", "接入", "二层", "核查"),
    "resource_inconsistency": ("资源", "台账", "接入", "迁移", "位置", "设备", "端口", "核对"),
    "uplink_policy_or_application": ("上层", "业务", "dns", "路由", "策略", "转交", "继续"),
    "terminal_config": ("终端", "地址", "网关", "配置", "分配", "核对"),
    "link_quality_issue": ("链路", "线缆", "网卡", "接口", "错误", "统计", "质量", "核查"),
    "evidence_insufficient": ("证据", "补充", "网关", "arp", "上层", "进一步", "核查"),
    "access_side_normal": ("正常", "一致", "未见", "无异常", "上层", "业务", "转交", "接入侧"),
}


def _compile_many(*patterns: str) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(pattern, re.I) for pattern in patterns)


# Diagnosis-specific direction rules are used for both safety and experiment scoring.
# Expected patterns express the diagnosis direction; opposite patterns capture explicit
# reversals. Expected spans are masked before opposite scanning so “不一致” is never
# misread as the substring “一致”.
DIAGNOSIS_DIRECTION_RULES: dict[str, dict[str, tuple[re.Pattern[str], ...]]] = {
    "vlan_mismatch": {
        "expected": _compile_many(
            r"vlan.{0,20}(?:不一致|不匹配|不相同|存在.{0,6}差异|有.{0,6}差异)",
            r"(?:不一致|不匹配|差异).{0,20}vlan",
            r"vlan.{0,12}(?:未与|没有与).{0,12}(?:一致|匹配|相同)",
            r"vlan.{0,8}一致性异常",
        ),
        "opposite": _compile_many(
            r"vlan.{0,20}(?:一致|匹配|相同)(?!性)",
            r"(?:无|没有|不存在).{0,10}vlan.{0,6}(?:差异|异常)",
        ),
    },
    "physical_or_terminal_link": {
        "expected": _compile_many(
            r"(?:接口|端口|链路).{0,14}(?:down|未建立|无有效链路|断开|异常)",
            r"(?:核查|检查|复核).{0,12}(?:物理连接|终端|网卡|线缆|链路|接口状态|端口状态)",
        ),
        "opposite": _compile_many(
            r"(?:接口|端口|链路).{0,12}(?:up|正常|已建立有效链路|连接正常|无异常)",
        ),
    },
    "l2_no_mac": {
        "expected": _compile_many(
            r"mac.{0,14}(?:未学习|没有|未见|缺失|无记录|未观察到)",
            r"(?:未学习|没有|未见|缺失|缺少|未观察到).{0,14}mac",
        ),
        "opposite": _compile_many(
            r"mac.{0,14}(?:已学习|正常学习|已存在|存在|有记录)",
            r"(?:已学习|已观察到|已发现).{0,12}mac",
        ),
    },
    "resource_inconsistency": {
        "expected": _compile_many(
            r"(?:资源|台账|登记|学习位置|接入位置|设备|端口).{0,22}(?:不一致|不匹配|不相符|存在.{0,6}差异|不同)",
            r"(?:不一致|不匹配|差异|不同).{0,22}(?:资源|台账|登记|学习位置|接入位置|设备|端口)",
        ),
        "opposite": _compile_many(
            r"(?:资源|台账|登记|学习位置|接入位置|设备|端口).{0,20}(?:一致|匹配|相同)(?!性)",
            r"(?:无|没有|不存在).{0,8}(?:资源|台账|登记|接入).{0,8}(?:差异|异常)",
        ),
    },
    "uplink_policy_or_application": {
        "expected": _compile_many(
            r"(?:上层|业务|dns|路由|策略).{0,20}(?:核查|排查|继续|转交|待确认|异常线索|进一步分析|继续分析)",
            r"(?:上层网络|业务链路).{0,12}(?:问题|异常线索|待核查)",
            r"(?:问题|风险).{0,10}(?:位于|转向).{0,10}(?:上层|业务)",
            r"接入侧.{0,18}(?:正常|未见.{0,6}异常|未发现.{0,12}(?:异常|证据)|证据一致|无明显异常)",
        ),
        "opposite": _compile_many(
            r"接入侧.{0,10}(?:存在|确认|属于).{0,8}(?:故障|异常)",
            r"(?:已确认|确定).{0,10}(?:dns|路由|策略|上层|业务).{0,8}(?:故障|异常)",
        ),
    },
    "terminal_config": {
        "expected": _compile_many(
            r"(?:终端|地址|网关|配置|分配记录).{0,20}(?:不一致|不匹配|不相符|存在.{0,6}差异|不同)",
            r"(?:不一致|不匹配|差异|不同).{0,20}(?:终端|地址|网关|配置|分配记录)",
        ),
        "opposite": _compile_many(
            r"(?:终端|地址|网关|配置).{0,18}(?:一致|匹配|相同|正常)(?!性)",
            r"(?:无|没有|不存在).{0,8}(?:地址|网关|终端配置).{0,8}(?:差异|异常)",
        ),
    },
    "link_quality_issue": {
        "expected": _compile_many(
            r"(?:链路质量|接口质量).{0,10}(?:(?<!无)异常|不稳定|较差|存在问题)",
            r"(?:错误计数|错误统计|input errors|output errors).{0,18}(?:增加|偏高|异常|持续|风险|问题)",
            r"(?:输入输出错误|接口错误|丢弃统计).{0,18}(?:异常|风险|链路质量问题)",
            r"(?:核查|复核).{0,12}(?:链路质量|接口统计|错误计数|线缆|网卡)",
        ),
        "opposite": _compile_many(
            r"(?:链路|接口).{0,12}(?:正常|无异常|质量正常)",
            r"(?:错误计数|错误统计).{0,10}(?:正常|为零|无异常)",
            r"(?:无|没有).{0,8}(?:错误|丢包)",
        ),
    },
    "evidence_insufficient": {
        "expected": _compile_many(
            r"(?:证据|arp|信息).{0,14}(?:不足|缺少|缺失|未找到|不完整)",
            r"(?:需|需要|建议).{0,10}(?:补充|继续核查|进一步核查)",
            r"(?:暂不能|无法|不能).{0,12}(?:确定|定位|确认)",
        ),
        "opposite": _compile_many(
            r"(?:证据|信息).{0,10}(?:充分|完整|已齐全)",
            r"(?:已经|已)(?:确认|确定).{0,12}(?:故障|层级|原因|位置)",
        ),
    },
    "access_side_normal": {
        "expected": _compile_many(
            r"接入侧.{0,16}(?:正常|未见.{0,6}异常|未发现.{0,6}异常|无明显异常|没有明显异常)",
            r"(?:未发现|未见).{0,10}接入侧.{0,6}异常",
            r"(?:资源|接口|mac|vlan|证据).{0,20}(?:一致|正常)(?!性)",
            r"(?:转交|继续核查).{0,12}(?:上层|业务)",
        ),
        "opposite": _compile_many(
            r"接入侧.{0,10}(?:存在|发现|确认|属于).{0,8}(?:故障|异常)",
            r"接入侧(?:故障|异常)",
        ),
    },
}


def normalize_text(text: str) -> str:
    text = text.lower().replace("`", "")
    text = text.replace("：", ":").replace("，", ",").replace("｜", "|")
    text = re.sub(r"[\t ]+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text)
    return text.strip()


def diagnosis_relevance(diagnosis_code: str, auxiliary_text: str | None) -> bool:
    if not auxiliary_text:
        return False
    text = normalize_text(auxiliary_text)
    terms = DIAGNOSIS_RELEVANCE_TERMS.get(diagnosis_code, ("核查", "复核", "确认", "转交", "证据"))
    return any(normalize_text(term) in text for term in terms)


def diagnosis_direction_signals(diagnosis_code: str, auxiliary_text: str | None) -> dict[str, object]:
    """Return diagnosis-direction evidence without using another LLM.

    `supported` is intentionally stricter than generic relevance. A sentence may be safe
    and relevant yet still fail to restate the diagnostic direction. `contradicted`
    catches explicit reversals and is used by the application guardrail.
    """
    if not auxiliary_text:
        return {"supported": False, "contradicted": False, "support_hits": [], "opposite_hits": []}

    rules = DIAGNOSIS_DIRECTION_RULES.get(diagnosis_code)
    if not rules:
        return {"supported": diagnosis_relevance(diagnosis_code, auxiliary_text), "contradicted": False, "support_hits": [], "opposite_hits": []}

    text = normalize_text(auxiliary_text)
    support_patterns = rules["expected"]
    opposite_patterns = rules["opposite"]
    support_hits = [p.pattern for p in support_patterns if p.search(text)]

    # Remove spans expressing the expected direction before searching for the opposite.
    # This prevents “不一致” from triggering a naive “一致” match.
    opposite_scan_text = text
    for pattern in support_patterns:
        opposite_scan_text = pattern.sub("<EXPECTED_DIRECTION>", opposite_scan_text)
    opposite_hits = [p.pattern for p in opposite_patterns if p.search(opposite_scan_text)]

    return {
        "supported": bool(support_hits),
        "contradicted": bool(opposite_hits),
        "support_hits": support_hits,
        "opposite_hits": opposite_hits,
    }


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
        line = raw_line.strip().lstrip("-*>").strip().replace("`", "")
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
    conclusion = constraints.get("conclusion") or "当前证据不足，需要继续核查。"
    recommendation = constraints.get("recommendation") or "仅进行只读核查、人工复核、补充证据或转交授权维护人员。"
    return f"""请把以下内容改写成一句自然中文辅助说明。

结论：{conclusion}
处理方向：{recommendation}

保持结论的状态方向不变，不新增原因或事实；只给出只读核查、人工复核、补充证据或转交建议。
不要输出具体标识、数值、诊断代码、配置修改命令，也不要复述“结论”“处理方向”等字段名。
只输出一行：辅助说明：<最多80个中文字符>。
"""


def _extract_auxiliary(raw_output: str) -> tuple[str | None, int]:
    nonempty = [line.strip() for line in raw_output.splitlines() if line.strip()]
    for line in nonempty:
        match = re.match(r"^辅助说明\s*[：:]\s*(.+?)\s*$", line)
        if match:
            return match.group(1).strip(), max(0, len(nonempty) - 1)
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
    direction_supported: bool = False
    direction_contradicted: bool = False
    text_quality_ok: bool = True
    auxiliary_text: str | None = None
    candidate_text: str | None = None
    ignored_extra_lines: int = 0
    unsafe_patterns: list[str] = field(default_factory=list)
    contradiction_patterns: list[str] = field(default_factory=list)
    direction_support_patterns: list[str] = field(default_factory=list)
    direction_opposite_patterns: list[str] = field(default_factory=list)
    text_quality_patterns: list[str] = field(default_factory=list)
    unsupported_root_cause_patterns: list[str] = field(default_factory=list)
    identifiers_in_auxiliary: dict[str, list[str]] = field(default_factory=dict)
    confidence_like_values: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
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
            "direction_supported": self.direction_supported,
            "direction_contradicted": self.direction_contradicted,
            "text_quality_ok": self.text_quality_ok,
            "auxiliary_text": self.auxiliary_text,
            "candidate_text": self.candidate_text,
            "ignored_extra_lines": self.ignored_extra_lines,
            "unsafe_patterns": self.unsafe_patterns,
            "contradiction_patterns": self.contradiction_patterns,
            "direction_support_patterns": self.direction_support_patterns,
            "direction_opposite_patterns": self.direction_opposite_patterns,
            "text_quality_patterns": self.text_quality_patterns,
            "unsupported_root_cause_patterns": self.unsupported_root_cause_patterns,
            "identifiers_in_auxiliary": self.identifiers_in_auxiliary,
            "confidence_like_values": self.confidence_like_values,
            "reasons": self.reasons,
            "diagnosis_code_ok": self.diagnosis_code_ok,
            "conclusion_ok": self.conclusion_ok,
        }


def safe_guardrail_metadata(result: GuardrailResult) -> dict[str, object]:
    """Return structured outcomes WITHOUT persisting raw candidate text.

    Reports and SQLite checkpoints must not become unreviewed storage for
    LLM-echoed addresses, user data, or raw document contents. The returned
    fields are suitable for local, access-controlled audit and metrics.
    """
    import hashlib

    # An allow-list is intentional: as_dict() includes concrete extracted IP,
    # MAC, VLAN identifiers as well as full candidate text. Neither belongs in
    # checkpoints or metadata-based telemetry.
    fields = (
        "passed", "format_ok", "identifier_free", "unsafe_free",
        "contradiction_free", "semantic_relevant", "diagnosis_code_free",
        "length_ok", "complete_sentence", "direction_supported",
        "direction_contradicted", "text_quality_ok", "ignored_extra_lines",
        "reasons", "diagnosis_code_ok", "conclusion_ok",
    )
    raw = result.as_dict()
    summary = {key: raw[key] for key in fields}
    candidate = result.candidate_text or ""
    summary["candidate_sha256"] = hashlib.sha256(candidate.encode("utf-8")).hexdigest() if candidate else None
    summary["candidate_char_count"] = len(candidate)
    summary["guardrail_revision"] = "v3.1.0"
    return summary


def _mask_negated_unsafe_actions(text: str) -> str:
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
            direction_supported=False,
            direction_contradicted=False,
            text_quality_ok=False,
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

    generic_patterns = NORMAL_CONTRADICTIONS if diagnosis_code == "access_side_normal" else ABNORMAL_CONTRADICTIONS
    generic_contradiction_hits = [pattern.pattern for pattern in generic_patterns if pattern.search(auxiliary)]
    direction = diagnosis_direction_signals(diagnosis_code, auxiliary)
    direction_opposite_hits = list(direction["opposite_hits"])
    contradiction_hits = generic_contradiction_hits + direction_opposite_hits
    contradiction_free = not contradiction_hits

    semantic_relevant = diagnosis_relevance(diagnosis_code, auxiliary)
    unsupported_root_cause_hits = [
        pattern.pattern for pattern in UNSUPPORTED_ROOT_CAUSE_PATTERNS if pattern.search(auxiliary)
    ]
    normalized_code = diagnosis_code.lower().strip()
    diagnosis_code_free = not normalized_code or normalized_code not in auxiliary.lower()

    text_quality_hits = [pattern.pattern for pattern in TEXT_QUALITY_PATTERNS if pattern.search(auxiliary)]
    text_quality_ok = not text_quality_hits

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
    if unsupported_root_cause_hits:
        reasons.append("unsupported_root_cause_expansion")
    if not diagnosis_code_free:
        reasons.append("diagnosis_code_echo")
    if not text_quality_ok:
        reasons.append("text_quality_violation")
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
        direction_supported=bool(direction["supported"]),
        direction_contradicted=bool(direction["contradicted"]),
        text_quality_ok=text_quality_ok,
        auxiliary_text=auxiliary if passed else None,
        candidate_text=auxiliary,
        ignored_extra_lines=ignored_extra_lines,
        unsafe_patterns=unsafe_hits,
        contradiction_patterns=contradiction_hits,
        direction_support_patterns=list(direction["support_hits"]),
        direction_opposite_patterns=direction_opposite_hits,
        text_quality_patterns=text_quality_hits,
        unsupported_root_cause_patterns=unsupported_root_cause_hits,
        identifiers_in_auxiliary=identifiers_flat,
        confidence_like_values=confidence_hits,
        reasons=reasons,
    )
