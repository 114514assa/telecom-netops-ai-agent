from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Telecom NetOps AI Agent"
    app_env: str = "development"
    host: str = "127.0.0.1"
    port: int = 8000

    data_dir: Path = Path("data")
    runtime_dir: Path = Path("runtime")
    checkpoint_db: Path = Path("runtime/checkpoints.sqlite3")
    inventory_db: Path = Path("runtime/inventory.sqlite3")
    report_dir: Path = Path("runtime/reports")
    audit_log: Path = Path("runtime/audit.jsonl")

    require_approval: bool = True
    # Development can run locally without authentication; set true for access-controlled demos.
    demo_auth_enabled: bool = False
    demo_reader_token: str = ""
    demo_approver_token: str = ""
    evidence_max_age_seconds: int = Field(default=1800, ge=60, le=86400)


    # LangChain RAG: OllamaEmbeddings + FAISS. RAG is supporting evidence only;
    # deterministic diagnosis must still work when the local vector service is unavailable.
    rag_enabled: bool = True
    rag_knowledge_dir: Path = Path("knowledge/sanitized")
    rag_top_k: int = Field(default=3, ge=1, le=10)
    rag_fail_open: bool = True

    ollama_base_url: str = "http://localhost:11434"
    ollama_embed_model: str = "qwen3-embedding:0.6b"

    vector_index_path: Path = Path("runtime/vector_index/knowledge.faiss")
    vector_metadata_path: Path = Path("runtime/vector_index/metadata.json")

    # Optional LLM. The diagnosis result is always produced by deterministic parsers/rules.
    llm_enabled: bool = False
    llm_backend: Literal["openai", "local_hf"] = "openai"

    # OpenAI-compatible remote backend.
    llm_base_url: str = "https://example.invalid/v1"
    llm_api_key: str = ""
    llm_model: str = ""
    llm_timeout_seconds: int = Field(default=30, ge=5, le=120)

    # Local Hugging Face backend for portfolio/demo quantization experiments.
    local_llm_model_id: str = "Qwen/Qwen2.5-0.5B-Instruct"
    local_llm_quantization: Literal["none", "fp16", "int8", "int4"] = "int4"
    local_llm_device_map: str = "auto"
    local_llm_max_new_tokens: int = Field(default=96, ge=32, le=512)
    local_llm_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    local_llm_trust_remote_code: bool = False
    local_llm_cache_dir: Path | None = None

    def ensure_directories(self) -> None:
        for directory in (self.runtime_dir, self.report_dir):
            directory.mkdir(parents=True, exist_ok=True)
        self.checkpoint_db.parent.mkdir(parents=True, exist_ok=True)
        self.inventory_db.parent.mkdir(parents=True, exist_ok=True)
        self.audit_log.parent.mkdir(parents=True, exist_ok=True)
        self.vector_index_path.parent.mkdir(parents=True, exist_ok=True)
        self.vector_metadata_path.parent.mkdir(parents=True, exist_ok=True)
        if self.local_llm_cache_dir:
            self.local_llm_cache_dir.mkdir(parents=True, exist_ok=True)

    def public_model_config(self) -> dict[str, object]:
        return {
            "llm_enabled": self.llm_enabled,
            "llm_backend": self.llm_backend,
            "remote_model": self.llm_model if self.llm_backend == "openai" else None,
            "local_model_id": self.local_llm_model_id if self.llm_backend == "local_hf" else None,
            "quantization": self.local_llm_quantization if self.llm_backend == "local_hf" else "none",
            "device_map": self.local_llm_device_map if self.llm_backend == "local_hf" else None,
            "max_new_tokens": self.local_llm_max_new_tokens if self.llm_backend == "local_hf" else None,
            "diagnosis_mode": "deterministic-parsers-and-rules",
            "llm_usage": "langchain-prompted-report-language-organization-only",
            "rag_enabled": self.rag_enabled,
            "rag_backend": "langchain-ollama-faiss" if self.rag_enabled else "disabled",
            "rag_top_k": self.rag_top_k,
            "rag_embedding_model": self.ollama_embed_model if self.rag_enabled else None,
            "rag_knowledge_dir": str(self.rag_knowledge_dir),
        }


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings
