from __future__ import annotations

import json
import re

import faiss
import numpy as np
from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings

from app.core.config import get_settings


def split_markdown(path) -> list[Document]:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"^---\s*.*?\s*---", "", text, count=1, flags=re.DOTALL).strip()
    sections = re.split(r"(?=^##\s+)", text, flags=re.MULTILINE)

    documents: list[Document] = []
    for i, section in enumerate(sections):
        section = section.strip()
        if len(section) < 30:
            continue

        first_line = section.splitlines()[0]
        section_name = first_line.lstrip("#").strip() if first_line.startswith("##") else "文档概述"
        documents.append(
            Document(
                page_content=section,
                metadata={
                    "chunk_id": f"{path.stem}_{i:03d}",
                    "source": path.name,
                    "section": section_name,
                },
            )
        )
    return documents


def main() -> None:
    settings = get_settings()
    settings.vector_index_path.parent.mkdir(parents=True, exist_ok=True)
    settings.vector_metadata_path.parent.mkdir(parents=True, exist_ok=True)

    documents: list[Document] = []
    knowledge_files = [
        path
        for path in sorted(settings.rag_knowledge_dir.glob("*.md"))
        if path.name not in {"00_README.md", "README.md"}
    ]
    for path in knowledge_files:
        documents.extend(split_markdown(path))

    if not documents:
        raise RuntimeError(f"No knowledge chunks found under {settings.rag_knowledge_dir}")

    print(f"Knowledge directory: {settings.rag_knowledge_dir}")
    print(f"Knowledge files: {len(knowledge_files)}")
    print(f"Chunks: {len(documents)}")
    print(f"LangChain embedding model: {settings.ollama_embed_model}")

    embeddings = OllamaEmbeddings(
        model=settings.ollama_embed_model,
        base_url=settings.ollama_base_url.rstrip("/"),
    )

    print("Generating embeddings through LangChain OllamaEmbeddings...")
    vectors = np.asarray(
        embeddings.embed_documents([doc.page_content for doc in documents]),
        dtype=np.float32,
    )
    if vectors.ndim != 2 or vectors.shape[0] != len(documents):
        raise RuntimeError(f"Unexpected embedding shape: {vectors.shape}")

    # Normalize once so IndexFlatL2 is cosine-equivalent at retrieval time.
    faiss.normalize_L2(vectors)
    index = faiss.IndexFlatL2(vectors.shape[1])
    index.add(vectors)

    metadata = [
        {
            "chunk_id": str(doc.metadata["chunk_id"]),
            "source": str(doc.metadata["source"]),
            "section": str(doc.metadata["section"]),
            "content": doc.page_content,
        }
        for doc in documents
    ]

    faiss.write_index(index, str(settings.vector_index_path))
    settings.vector_metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("Embedding shape:", vectors.shape)
    print("Saved:")
    print(settings.vector_index_path)
    print(settings.vector_metadata_path)


if __name__ == "__main__":
    main()
