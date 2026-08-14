from __future__ import annotations

from typing import Sequence

import numpy as np
import requests


class OllamaEmbedder:
    def __init__(
        self,
        model: str = "qwen3-embedding:0.6b",
        base_url: str = "http://localhost:11434",
        timeout: int = 120,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        values = [str(item).strip() for item in texts if str(item).strip()]
        if not values:
            return np.empty((0, 0), dtype=np.float32)

        try:
            response = requests.post(
                f"{self.base_url}/api/embed",
                json={"model": self.model, "input": values},
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(
                f"Ollama embedding request failed: {type(exc).__name__}"
            ) from exc

        data = response.json()
        raw_vectors = data.get("embeddings")
        if not raw_vectors:
            raise RuntimeError("Ollama embedding response did not contain embeddings")

        vectors = np.asarray(raw_vectors, dtype=np.float32)
        if vectors.ndim != 2:
            raise RuntimeError(f"Unexpected embedding shape: {vectors.shape}")
        return vectors

    def embed_query(self, text: str) -> np.ndarray:
        vectors = self.embed([text])
        if vectors.shape[0] != 1:
            raise RuntimeError("Expected exactly one query embedding")
        return vectors[0]
