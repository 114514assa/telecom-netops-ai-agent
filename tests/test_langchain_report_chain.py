from app.llm.backends import GenerationResult
from app.llm.langchain_report_chain import LangChainReportAssistant


SOURCE = """# 报告
- 终端 IP：10.20.30.15
- 登记设备：SW-SIM-03
- 登记端口：GE0/0/12
- 目标 VLAN：200
- 诊断代码：vlan_mismatch
- 置信度：0.96
- 结论：设备侧 VLAN 与资源登记目标 VLAN 不一致。
- 建议：人工核对资源台账与正式变更记录，仅做只读确认。
"""


class CaptureBackend:
    def __init__(self):
        self.messages = None

    def generate_chat(self, messages):
        self.messages = messages
        return GenerationResult(
            text="辅助说明：设备侧 VLAN 与资源登记信息不一致，建议进行只读核查并由授权人员复核。",
            backend="test",
            model="capture",
        )


def test_langchain_prompt_uses_minimum_safe_context_only():
    backend = CaptureBackend()
    assistant = LangChainReportAssistant(backend)
    result = assistant.generate(SOURCE)

    joined = "\n".join(message["content"] for message in backend.messages)
    assert "设备侧 VLAN 与资源登记目标 VLAN 不一致" in joined
    assert "人工核对资源台账与正式变更记录" in joined
    assert "vlan_mismatch" not in joined
    assert "10.20.30.15" not in joined
    assert "SW-SIM-03" not in joined
    assert "GE0/0/12" not in joined
    assert "0.96" not in joined
    assert result.extra["llm_input_scope"] == "confirmed-conclusion-and-readonly-direction-only"
    assert result.extra["prompt_version"] == "netops-aux-v4-final-quant"


def test_langchain_prompt_explicitly_preserves_diagnosis_direction():
    backend = CaptureBackend()
    assistant = LangChainReportAssistant(backend)
    assistant.generate(SOURCE)

    joined = "\n".join(message["content"] for message in backend.messages)
    assert "状态方向不变" in joined
    assert "不一致、未学习、DOWN、证据不足、未见异常" in joined
    assert "只Read" not in joined
    assert "正确输出" not in joined
    assert "不输出具体标识、数值、诊断代码、字段名" in joined
