from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

from app.llm.report_guardrails import AUX_SYSTEM_PROMPT, extract_constraints


class LangChainReportAssistant:
    """Generate one tightly-scoped auxiliary sentence from deterministic results."""

    SAFE_FALLBACK_DIRECTION = "仅进行只读核查、人工复核、补充证据或转交授权维护人员。"

    def __init__(self, backend) -> None:
        self.backend = backend
        self.prompt = ChatPromptTemplate.from_messages(
            [
                ("system", AUX_SYSTEM_PROMPT),
                (
                    "human",
                    """请将下面两项整理成一句自然中文辅助说明。

结论：{conclusion}
处理方向：{recommendation}

规则：
- 保持结论语义和状态方向不变；不一致、未学习、DOWN、证据不足、未见异常等含义不能改成相反含义。
- 只转述已有结论和处理方向，不新增原因、事实或修复结果。
- 只建议只读核查、人工复核、补充证据或转交授权人员。
- 不输出具体标识、数值、诊断代码、字段名、配置修改命令或额外段落。
- 使用自然完整中文，标准缩写 VLAN、MAC、ARP、Interface 可保留。

只输出：辅助说明：<最多80个中文字符的完整句子>。""",
                ),
            ]
        )

    def generate(self, source_report: str):
        constraints = extract_constraints(source_report)
        prompt_value = self.prompt.invoke(
            {
                "conclusion": constraints.get("conclusion") or "当前证据不足，需要继续核查。",
                "recommendation": constraints.get("recommendation") or self.SAFE_FALLBACK_DIRECTION,
            }
        )
        messages: list[dict[str, str]] = []
        for message in prompt_value.to_messages():
            role = "system" if message.type == "system" else "user"
            messages.append({"role": role, "content": str(message.content)})
        result = self.backend.generate_chat(messages)
        result.extra["prompt_framework"] = "langchain-chat-prompt-template"
        result.extra["llm_input_scope"] = "confirmed-conclusion-and-readonly-direction-only"
        result.extra["prompt_version"] = "netops-aux-v4-final-quant"
        return result
