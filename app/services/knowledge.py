from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.domain.models import (
    DiagnosisResult,
    IncidentInput,
    InventoryRecord,
    KnowledgeHit,
    ParsedEvidence,
)

if TYPE_CHECKING:
    from app.core.config import Settings


class KnowledgeBase:
    """TF-IDF baseline retriever."""

    def __init__(self, knowledge_dir: Path):
        self.knowledge_dir = Path(knowledge_dir)
        self.sections: list[dict[str, str]] = []
        self.vectorizer: TfidfVectorizer | None = None
        self.matrix = None

    def load(self) -> None:
        self.sections.clear()
        for path in sorted(self.knowledge_dir.glob("*.md")):
            if path.name == "00_README.md":
                continue
            text = path.read_text(encoding="utf-8")
            text = re.sub(r"^---\s*.*?\s*---", "", text, count=1, flags=re.DOTALL).strip()
            parts = re.split(r"(?m)^##\s+", text)
            preface = parts[0].strip()
            if preface:
                self.sections.append(
                    {"title": path.stem, "source": path.name, "content": preface}
                )
            for part in parts[1:]:
                lines = part.strip().splitlines()
                if not lines:
                    continue
                self.sections.append(
                    {
                        "title": lines[0].strip(),
                        "source": path.name,
                        "content": "\n".join(lines[1:]).strip(),
                    }
                )

        corpus = [f"{item['title']} {item['content']}" for item in self.sections]
        self.vectorizer = None
        self.matrix = None
        if corpus:
            self.vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(2, 4), min_df=1)
            self.matrix = self.vectorizer.fit_transform(corpus)

    def search(self, query: str, top_k: int = 3) -> list[KnowledgeHit]:
        if not self.sections or self.vectorizer is None or self.matrix is None:
            return []
        query_vector = self.vectorizer.transform([query])
        scores = cosine_similarity(query_vector, self.matrix).ravel()
        indexes = scores.argsort()[::-1][: max(1, min(top_k, 10))]
        hits: list[KnowledgeHit] = []
        for index in indexes:
            if scores[index] <= 0:
                continue
            item = self.sections[int(index)]
            hits.append(
                KnowledgeHit(
                    title=item["title"],
                    source=item["source"],
                    score=round(float(scores[index]), 4),
                    content=item["content"][:1200],
                )
            )
        return hits


class VectorKnowledgeBase:
    """Ollama embedding + FAISS retriever with the same KnowledgeHit output schema."""

    def __init__(self, settings: "Settings"):
        self.settings = settings
        self.retriever = None

    def load(self) -> None:
        from app.rag.faiss_retriever import FaissRetriever

        self.retriever = FaissRetriever(
            index_path=self.settings.vector_index_path,
            metadata_path=self.settings.vector_metadata_path,
            embed_model=self.settings.ollama_embed_model,
            ollama_base_url=self.settings.ollama_base_url,
            ollama_timeout=self.settings.ollama_timeout_seconds,
            top_k=self.settings.rag_top_k,
        )

    def search(self, query: str, top_k: int = 3) -> list[KnowledgeHit]:
        if self.retriever is None:
            raise RuntimeError("VectorKnowledgeBase.load() must be called before search()")

        raw_hits = self.retriever.search(query, top_k=top_k)
        hits: list[KnowledgeHit] = []
        for item in raw_hits:
            hits.append(
                KnowledgeHit(
                    title=str(item.get("section") or item.get("title") or "知识片段"),
                    source=str(item.get("source") or "unknown"),
                    score=round(float(item.get("score", 0.0)), 4),
                    content=str(item.get("content") or "")[:1200],
                )
            )
        return hits


class RoutedKnowledgeBase:
    """Select vector or TF-IDF at runtime.

    Vector retrieval may fall back to TF-IDF if Ollama/FAISS is unavailable.
    Core diagnosis is unaffected because RAG only supplies reference knowledge.
    """

    def __init__(self, settings: "Settings"):
        self.settings = settings
        self.tfidf = KnowledgeBase(settings.rag_knowledge_dir)
        self.vector: VectorKnowledgeBase | None = None

    def load(self) -> None:
        # Always load the baseline so vector mode can safely fall back.
        self.tfidf.load()
        if self.settings.rag_backend == "vector":
            self.vector = VectorKnowledgeBase(self.settings)
            self.vector.load()

    def search(self, query: str, top_k: int | None = None) -> list[KnowledgeHit]:
        k = top_k or self.settings.rag_top_k
        if self.settings.rag_backend != "vector":
            return self.tfidf.search(query, top_k=k)

        if self.vector is None:
            raise RuntimeError("Vector RAG backend is not initialized")

        try:
            return self.vector.search(query, top_k=k)
        except (RuntimeError, OSError, ValueError):
            if not self.settings.rag_vector_fallback_to_tfidf:
                raise
            return self.tfidf.search(query, top_k=k)


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
