from __future__ import annotations

from typing import TYPE_CHECKING

from app.domain.models import (
    DiagnosisResult,
    IncidentInput,
    InventoryRecord,
    KnowledgeHit,
    ParsedEvidence,
)

if TYPE_CHECKING:
    from app.core.config import Settings


class LangChainKnowledgeBase:
    """OllamaEmbeddings + FAISS retrieval through LangChain.

    RAG is deliberately fail-open by default because retrieved knowledge is only supporting
    context. A missing local index or Ollama outage must never replace or block the
    deterministic network diagnosis.
    """

    def __init__(self, settings: "Settings") -> None:
        self.settings = settings
        self.retriever = None
        self.load_error: str | None = None
        self.last_error: str | None = None

    def load(self) -> None:
        self.retriever = None
        self.load_error = None
        self.last_error = None
        if not self.settings.rag_enabled:
            return

        from app.rag.langchain_faiss import LangChainFaissRetriever

        try:
            self.retriever = LangChainFaissRetriever(
                index_path=self.settings.vector_index_path,
                metadata_path=self.settings.vector_metadata_path,
                embed_model=self.settings.ollama_embed_model,
                ollama_base_url=self.settings.ollama_base_url,
                top_k=self.settings.rag_top_k,
            )
        except (FileNotFoundError, RuntimeError, OSError, ValueError) as exc:
            self.load_error = f"{type(exc).__name__}: {exc}"
            if not self.settings.rag_fail_open:
                raise

    def search(self, query: str, top_k: int = 3) -> list[KnowledgeHit]:
        if not self.settings.rag_enabled:
            return []
        if self.retriever is None:
            if self.settings.rag_fail_open:
                return []
            raise RuntimeError(self.load_error or "LangChain RAG backend is not initialized")

        self.last_error = None
        try:
            raw_hits = self.retriever.search(query, top_k=top_k)
        except Exception as exc:  # integration boundary: RAG must remain non-fatal
            self.last_error = f"{type(exc).__name__}: {exc}"
            if self.settings.rag_fail_open:
                return []
            raise

        return [
            KnowledgeHit(
                title=str(item.get("section") or "知识片段"),
                source=str(item.get("source") or "unknown"),
                score=round(float(item.get("score", 0.0)), 4),
                content=str(item.get("content") or "")[:1200],
            )
            for item in raw_hits
        ]


# Backward-compatible name used by the graph/runtime and MCP server.
RoutedKnowledgeBase = LangChainKnowledgeBase


def build_retrieval_query(
    incident: IncidentInput,
    inventory: InventoryRecord | None,
    parsed: ParsedEvidence,
    diagnosis: DiagnosisResult,
) -> str:
    """Build a semantic Chinese query from structured diagnosis evidence."""

    parts = [
        f"故障现象：{incident.symptom}",
        f"诊断结论：{diagnosis.summary}",
        f"故障层级：{diagnosis.likely_layer.value}",
    ]

    if parsed.interface.status:
        parts.append(f"接口状态：{parsed.interface.status}")
    if parsed.interface.input_errors is not None or parsed.interface.output_errors is not None:
        parts.append(
            f"接口错误计数：输入{parsed.interface.input_errors or 0}，输出{parsed.interface.output_errors or 0}"
        )

    if parsed.mac.target_found is True:
        parts.append("目标MAC已学习")
    elif parsed.mac.target_found is False:
        parts.append("接口正常但未学习到目标MAC")

    if parsed.arp.target_found is True:
        parts.append("目标ARP存在")
    elif parsed.arp.target_found is False:
        parts.append("未发现目标ARP")

    if inventory is not None:
        parts.append(f"资源登记目标VLAN：{inventory.expected_vlan}")
        if parsed.mac.vlan is not None:
            parts.append(f"当前MAC学习VLAN：{parsed.mac.vlan}")
        if parsed.vlan.access_vlan is not None:
            parts.append(f"接口Access VLAN：{parsed.vlan.access_vlan}")

        if parsed.mac.learned_port and parsed.mac.learned_port != inventory.registered_port:
            parts.append(
                f"资源登记端口与实际MAC学习端口不一致：{inventory.registered_port} / {parsed.mac.learned_port}"
            )

    if parsed.terminal.gateway:
        parts.append(f"终端网关：{parsed.terminal.gateway}")
    if parsed.terminal.dns_success is False:
        parts.append("DNS解析异常")

    if diagnosis.hypotheses:
        parts.append("可能原因：" + "；".join(diagnosis.hypotheses[:3]))

    parts.append("检索相关排障流程、证据解释和继续核查方向")
    return "；".join(parts)
