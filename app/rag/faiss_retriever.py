from __future__ import annotations

import json
from pathlib import Path

import faiss
import numpy as np

from app.rag.ollama_embedder import OllamaEmbedder


class FaissRetriever:
    def __init__(
        self,
        index_path: str | Path,
        metadata_path: str | Path,
        *,
        embed_model: str = "qwen3-embedding:0.6b",
        ollama_base_url: str = "http://localhost:11434",
        ollama_timeout: int = 120,
        top_k: int = 3,
    ):
        self.index_path = Path(index_path)
        self.metadata_path = Path(metadata_path)
        if not self.index_path.exists():
            raise FileNotFoundError(
                f"FAISS index not found: {self.index_path}. Run `python -m scripts.build_vector_index` first."
            )
        if not self.metadata_path.exists():
            raise FileNotFoundError(
                f"Vector metadata not found: {self.metadata_path}. Run `python -m scripts.build_vector_index` first."
            )

        self.index = faiss.read_index(str(self.index_path))
        with self.metadata_path.open("r", encoding="utf-8") as f:
            self.metadata = json.load(f)

        if len(self.metadata) < self.index.ntotal:
            raise RuntimeError(
                f"Metadata count ({len(self.metadata)}) is smaller than FAISS index size ({self.index.ntotal})"
            )

        self.embedder = OllamaEmbedder(
            model=embed_model,
            base_url=ollama_base_url,
            timeout=ollama_timeout,
        )
        self.top_k = top_k

    def search(self, query: str, top_k: int | None = None) -> list[dict]:
        query = query.strip()
        if not query or self.index.ntotal == 0:
            return []

        k = max(1, min(top_k or self.top_k, self.index.ntotal))
        vector = np.asarray([self.embedder.embed_query(query)], dtype=np.float32)

        if vector.shape[1] != self.index.d:
            raise RuntimeError(
                f"Embedding dimension mismatch: query={vector.shape[1]}, index={self.index.d}. "
                "Rebuild the vector index with the configured embedding model."
            )

        faiss.normalize_L2(vector)
        scores, indices = self.index.search(vector, k)

        results: list[dict] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:
                continue
            item = dict(self.metadata[int(idx)])
            item["score"] = float(score)
            results.append(item)
        return results
