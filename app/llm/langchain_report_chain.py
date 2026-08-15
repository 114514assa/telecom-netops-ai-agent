from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

from app.llm.report_guardrails import AUX_SYSTEM_PROMPT, extract_constraints


class LangChainReportAssistant:
    """Compose the auxiliary-generation prompt with LangChain.

    The chain receives only already-confirmed diagnostic fields. It does not expose any API
    that can replace ``DiagnosisResult``; the generated sentence still has to pass the
    application guardrail before it can be appended to a report.
    """

    def __init__(self, backend) -> None:
        self.backend = backend
        self.prompt = ChatPromptTemplate.from_messages(
            [
                ("system", AUX_SYSTEM_PROMPT),
                (
                    "human",
                    """根据下面已经确认的诊断信息生成一句辅助说明。

诊断类型（仅供理解，不要输出）：{diagnosis_code}
已确认结论：{conclusion}
允许参考的处理方向：{recommendation}

不要复述具体地址、设备编号、端口、VLAN编号、MAC、置信度或诊断代码。
不要重新判断原因，不要给出任何配置修改或设备操作命令。
只输出一行：辅助说明：<最多80个中文字符的只读核查/人工复核/转交说明>。""",
                ),
            ]
        )

    def generate(self, source_report: str):
        constraints = extract_constraints(source_report)
        prompt_value = self.prompt.invoke(
            {
                "diagnosis_code": constraints.get("diagnosis_code") or "未提供",
                "conclusion": constraints.get("conclusion") or "未提供",
                "recommendation": constraints.get("recommendation") or "仅进行只读核查并转交授权人员",
            }
        )
        messages: list[dict[str, str]] = []
        for message in prompt_value.to_messages():
            role = "system" if message.type == "system" else "user"
            messages.append({"role": role, "content": str(message.content)})
        result = self.backend.generate_chat(messages)
        result.extra["prompt_framework"] = "langchain-chat-prompt-template"
        return result
