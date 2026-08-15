from __future__ import annotations

import json
from pathlib import Path

import faiss
from langchain_community.docstore.in_memory import InMemoryDocstore
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings


class LangChainFaissRetriever:
    """LangChain FAISS retriever backed by a locally generated, non-committed index.

    The persisted artifacts intentionally stay as a raw FAISS index + JSON metadata rather
    than LangChain's pickle-based ``save_local`` format. Runtime retrieval still uses the
    LangChain vector-store abstraction and ``OllamaEmbeddings``.
    """

    def __init__(
        self,
        index_path: str | Path,
        metadata_path: str | Path,
        *,
        embed_model: str = "qwen3-embedding:0.6b",
        ollama_base_url: str = "http://localhost:11434",
        top_k: int = 3,
    ) -> None:
        self.index_path = Path(index_path)
        self.metadata_path = Path(metadata_path)
        if not self.index_path.exists():
            raise FileNotFoundError(
                f"FAISS index not found: {self.index_path}. "
                "Run `python -m scripts.build_vector_index` first."
            )
        if not self.metadata_path.exists():
            raise FileNotFoundError(
                f"Vector metadata not found: {self.metadata_path}. "
                "Run `python -m scripts.build_vector_index` first."
            )

        index = faiss.read_index(str(self.index_path))
        if getattr(index, "metric_type", None) != faiss.METRIC_L2:
            raise RuntimeError(
                "FAISS index metric is not L2. This repository version changed the vector index format; "
                "run `python -m scripts.build_vector_index` to rebuild it."
            )
        metadata = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        if len(metadata) != index.ntotal:
            raise RuntimeError(
                f"Metadata count ({len(metadata)}) does not match FAISS index size ({index.ntotal})"
            )

        embeddings = OllamaEmbeddings(
            model=embed_model,
            base_url=ollama_base_url.rstrip("/"),
        )

        documents: dict[str, Document] = {}
        index_to_docstore_id: dict[int, str] = {}
        for idx, item in enumerate(metadata):
            chunk_id = str(item.get("chunk_id") or f"chunk_{idx:04d}")
            documents[chunk_id] = Document(
                page_content=str(item.get("content") or ""),
                metadata={
                    "chunk_id": chunk_id,
                    "source": str(item.get("source") or "unknown"),
                    "section": str(item.get("section") or "知识片段"),
                },
            )
            index_to_docstore_id[idx] = chunk_id

        # The index is built from L2-normalized embeddings and uses IndexFlatL2.
        # normalize_L2=True keeps query vectors on the same cosine-equivalent geometry.
        self.vectorstore = FAISS(
            embedding_function=embeddings,
            index=index,
            docstore=InMemoryDocstore(documents),
            index_to_docstore_id=index_to_docstore_id,
            normalize_L2=True,
        )
        self.top_k = top_k

    def search(self, query: str, top_k: int | None = None) -> list[dict]:
        query = query.strip()
        if not query or self.vectorstore.index.ntotal == 0:
            return []

        k = max(1, min(top_k or self.top_k, self.vectorstore.index.ntotal))
        rows = self.vectorstore.similarity_search_with_score(query, k=k)

        results: list[dict] = []
        for document, distance in rows:
            # With normalized vectors, squared L2 distance d = 2 - 2*cos(theta).
            # Convert it to a cosine-like score so larger is more relevant.
            score = 1.0 - float(distance) / 2.0
            score = max(-1.0, min(1.0, score))
            results.append(
                {
                    "chunk_id": document.metadata.get("chunk_id"),
                    "source": document.metadata.get("source", "unknown"),
                    "section": document.metadata.get("section", "知识片段"),
                    "content": document.page_content,
                    "score": score,
                }
            )
        return results
