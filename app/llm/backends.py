from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

import httpx


from app.llm.report_guardrails import AUX_SYSTEM_PROMPT


SYSTEM_PROMPT = AUX_SYSTEM_PROMPT


@dataclass(slots=True)
class GenerationResult:
    text: str | None
    backend: str
    model: str
    quantization: str = "none"
    latency_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    tokens_per_second: float | None = None
    memory_footprint_mb: float | None = None
    peak_gpu_memory_mb: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def as_meta(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "model": self.model,
            "quantization": self.quantization,
            "latency_ms": self.latency_ms,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "tokens_per_second": self.tokens_per_second,
            "memory_footprint_mb": self.memory_footprint_mb,
            "peak_gpu_memory_mb": self.peak_gpu_memory_mb,
            **self.extra,
        }


class OpenAICompatibleBackend:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: int = 30,
    ) -> None:
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    def generate(self, report: str) -> GenerationResult:
        if not (self.api_key and self.model):
            return GenerationResult(
                text=None,
                backend="openai-compatible",
                model=self.model or "unconfigured",
                extra={"fallback_reason": "missing_api_key_or_model"},
            )

        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": report},
            ],
        }
        started = time.perf_counter()
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(
                    self.base_url.rstrip("/") + "/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
            elapsed_ms = (time.perf_counter() - started) * 1000
            usage = data.get("usage") or {}
            output_tokens = usage.get("completion_tokens")
            tokens_per_second = None
            if output_tokens and elapsed_ms > 0:
                tokens_per_second = output_tokens / (elapsed_ms / 1000)
            return GenerationResult(
                text=data["choices"][0]["message"]["content"],
                backend="openai-compatible",
                model=self.model,
                latency_ms=round(elapsed_ms, 2),
                input_tokens=usage.get("prompt_tokens"),
                output_tokens=output_tokens,
                tokens_per_second=round(tokens_per_second, 3) if tokens_per_second else None,
            )
        except (httpx.HTTPError, KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            return GenerationResult(
                text=None,
                backend="openai-compatible",
                model=self.model,
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                extra={"fallback_reason": type(exc).__name__},
            )


class LocalHFBackend:
    """Lazy local Hugging Face causal-LM backend with optional bitsandbytes quantization.

    The backend is intentionally optional. Importing the main application does not require
    torch/transformers/bitsandbytes; those packages are imported only when local generation
    is actually requested.
    """

    SUPPORTED_QUANTIZATION = {"none", "fp16", "int8", "int4"}

    def __init__(
        self,
        *,
        model_id: str,
        quantization: str = "int4",
        device_map: str = "auto",
        max_new_tokens: int = 384,
        temperature: float = 0.0,
        trust_remote_code: bool = False,
        cache_dir: str | None = None,
    ) -> None:
        quantization = quantization.lower().strip()
        if quantization not in self.SUPPORTED_QUANTIZATION:
            raise ValueError(
                f"unsupported quantization={quantization!r}; "
                f"choose from {sorted(self.SUPPORTED_QUANTIZATION)}"
            )
        self.model_id = model_id
        self.quantization = quantization
        self.device_map = device_map
        self.max_new_tokens = max_new_tokens
        self.temperature = temperature
        self.trust_remote_code = trust_remote_code
        self.cache_dir = cache_dir or None
        self._tokenizer = None
        self._model = None
        self._torch = None
        self._load_seconds: float | None = None

    @property
    def loaded(self) -> bool:
        return self._model is not None and self._tokenizer is not None

    def _load(self) -> None:
        if self.loaded:
            return
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
        except ImportError as exc:  # pragma: no cover - depends on optional environment
            raise RuntimeError(
                "Local LLM backend requires optional dependencies. "
                "Install them with: pip install -r requirements-llm.txt"
            ) from exc

        model_kwargs: dict[str, Any] = {
            "device_map": self.device_map,
            "trust_remote_code": self.trust_remote_code,
            "low_cpu_mem_usage": True,
        }
        if self.cache_dir:
            model_kwargs["cache_dir"] = self.cache_dir

        if self.quantization == "int8":
            model_kwargs["quantization_config"] = BitsAndBytesConfig(load_in_8bit=True)
        elif self.quantization == "int4":
            compute_dtype = torch.bfloat16 if torch.cuda.is_available() and torch.cuda.is_bf16_supported() else torch.float16
            model_kwargs["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True,
                bnb_4bit_compute_dtype=compute_dtype,
            )
        elif self.quantization == "fp16":
            if not torch.cuda.is_available():
                raise RuntimeError("FP16 local inference is configured for CUDA in this project demo.")
            model_kwargs["torch_dtype"] = torch.float16

        started = time.perf_counter()
        tokenizer_kwargs = {"trust_remote_code": self.trust_remote_code}
        if self.cache_dir:
            tokenizer_kwargs["cache_dir"] = self.cache_dir
        tokenizer = AutoTokenizer.from_pretrained(self.model_id, **tokenizer_kwargs)
        model = AutoModelForCausalLM.from_pretrained(self.model_id, **model_kwargs)
        model.eval()
        self._tokenizer = tokenizer
        self._model = model
        self._torch = torch
        self._load_seconds = time.perf_counter() - started

    def _build_prompt(self, report: str) -> str:
        assert self._tokenizer is not None
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": report},
        ]
        if getattr(self._tokenizer, "chat_template", None):
            return self._tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
        return f"[SYSTEM]\n{SYSTEM_PROMPT}\n\n[USER]\n{report}\n\n[ASSISTANT]\n"

    def generate(self, report: str) -> GenerationResult:
        self._load()
        assert self._tokenizer is not None
        assert self._model is not None
        assert self._torch is not None
        torch = self._torch

        prompt = self._build_prompt(report)
        inputs = self._tokenizer(prompt, return_tensors="pt")
        try:
            input_device = self._model.device
            inputs = {key: value.to(input_device) for key, value in inputs.items()}
        except (AttributeError, RuntimeError):
            pass

        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
            torch.cuda.synchronize()

        generation_kwargs: dict[str, Any] = {
            "max_new_tokens": self.max_new_tokens,
            "do_sample": self.temperature > 0,
            "pad_token_id": self._tokenizer.eos_token_id,
            "eos_token_id": self._tokenizer.eos_token_id,
            "repetition_penalty": 1.05,
            "no_repeat_ngram_size": 4,
        }
        if self.temperature > 0:
            generation_kwargs["temperature"] = self.temperature

        started = time.perf_counter()
        with torch.inference_mode():
            generated = self._model.generate(**inputs, **generation_kwargs)
        if torch.cuda.is_available():
            torch.cuda.synchronize()
        elapsed = time.perf_counter() - started

        input_tokens = int(inputs["input_ids"].shape[-1])
        output_ids = generated[0][input_tokens:]
        output_tokens = int(output_ids.shape[-1])
        text = self._tokenizer.decode(output_ids, skip_special_tokens=True).strip()

        footprint_mb = None
        if hasattr(self._model, "get_memory_footprint"):
            try:
                footprint_mb = float(self._model.get_memory_footprint()) / 1024 / 1024
            except (TypeError, RuntimeError):
                footprint_mb = None
        peak_gpu_mb = None
        if torch.cuda.is_available():
            peak_gpu_mb = float(torch.cuda.max_memory_allocated()) / 1024 / 1024

        return GenerationResult(
            text=text or None,
            backend="local-hf",
            model=self.model_id,
            quantization=self.quantization,
            latency_ms=round(elapsed * 1000, 2),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            tokens_per_second=round(output_tokens / elapsed, 3) if elapsed > 0 else None,
            memory_footprint_mb=round(footprint_mb, 2) if footprint_mb is not None else None,
            peak_gpu_memory_mb=round(peak_gpu_mb, 2) if peak_gpu_mb is not None else None,
            extra={"load_seconds": round(self._load_seconds, 3) if self._load_seconds else None},
        )
