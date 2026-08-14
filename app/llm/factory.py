from __future__ import annotations

from app.core.config import Settings
from app.llm.backends import LocalHFBackend, OpenAICompatibleBackend


def build_report_backend(settings: Settings):
    if not settings.llm_enabled:
        return None

    backend = settings.llm_backend.lower().strip()
    if backend == "openai":
        return OpenAICompatibleBackend(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            timeout_seconds=settings.llm_timeout_seconds,
        )
    if backend == "local_hf":
        return LocalHFBackend(
            model_id=settings.local_llm_model_id,
            quantization=settings.local_llm_quantization,
            device_map=settings.local_llm_device_map,
            max_new_tokens=settings.local_llm_max_new_tokens,
            temperature=settings.local_llm_temperature,
            trust_remote_code=settings.local_llm_trust_remote_code,
            cache_dir=str(settings.local_llm_cache_dir) if settings.local_llm_cache_dir else None,
        )
    raise ValueError("LLM_BACKEND must be one of: openai, local_hf")
