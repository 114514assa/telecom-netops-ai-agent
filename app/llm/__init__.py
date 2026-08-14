"""Optional LLM backends used only for report language organization."""

from app.llm.backends import GenerationResult, LocalHFBackend, OpenAICompatibleBackend
from app.llm.factory import build_report_backend

__all__ = [
    "GenerationResult",
    "LocalHFBackend",
    "OpenAICompatibleBackend",
    "build_report_backend",
]
