from __future__ import annotations

import json
import re

import faiss
import numpy as np

from app.core.config import get_settings
from app.rag.ollama_embedder import OllamaEmbedder


def split_markdown(path):
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"^---\s*.*?\s*---", "", text, count=1, flags=re.DOTALL).strip()
    sections = re.split(r"(?=^##\s+)", text, flags=re.MULTILINE)

    chunks = []
    for i, section in enumerate(sections):
        section = section.strip()
        if len(section) < 30:
            continue

        first_line = section.splitlines()[0]
        section_name = (
            first_line.lstrip("#").strip()
            if first_line.startswith("##")
            else "文档概述"
        )
        chunks.append(
            {
                "chunk_id": f"{path.stem}_{i:03d}",
                "source": path.name,
                "section": section_name,
                "content": section,
            }
        )
    return chunks


def main():
    settings = get_settings()
    settings.vector_index_path.parent.mkdir(parents=True, exist_ok=True)
    settings.vector_metadata_path.parent.mkdir(parents=True, exist_ok=True)

    chunks = []
    knowledge_files = [
        path
        for path in sorted(settings.rag_knowledge_dir.glob("*.md"))
        if path.name != "00_README.md"
    ]
    for path in knowledge_files:
        chunks.extend(split_markdown(path))

    if not chunks:
        raise RuntimeError(f"No knowledge chunks found under {settings.rag_knowledge_dir}")

    print(f"Knowledge directory: {settings.rag_knowledge_dir}")
    print(f"Knowledge files: {len(knowledge_files)}")
    print(f"Chunks: {len(chunks)}")
    print(f"Embedding model: {settings.ollama_embed_model}")

    embedder = OllamaEmbedder(
        model=settings.ollama_embed_model,
        base_url=settings.ollama_base_url,
        timeout=settings.ollama_timeout_seconds,
    )

    print("Generating embeddings...")
    vectors = embedder.embed([item["content"] for item in chunks]).astype("float32")
    print("Embedding shape:", vectors.shape)

    faiss.normalize_L2(vectors)
    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(vectors)

    faiss.write_index(index, str(settings.vector_index_path))
    settings.vector_metadata_path.write_text(
        json.dumps(chunks, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("Saved:")
    print(settings.vector_index_path)
    print(settings.vector_metadata_path)


if __name__ == "__main__":
    main()
