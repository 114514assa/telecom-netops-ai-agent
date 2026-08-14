from app.core.config import get_settings
from app.rag.faiss_retriever import FaissRetriever


def main():
    settings = get_settings()
    retriever = FaissRetriever(
        index_path=settings.vector_index_path,
        metadata_path=settings.vector_metadata_path,
        embed_model=settings.ollama_embed_model,
        ollama_base_url=settings.ollama_base_url,
        ollama_timeout=settings.ollama_timeout_seconds,
        top_k=settings.rag_top_k,
    )

    queries = [
        "接口UP但是没有学习到目标MAC应该怎么排查？",
        "资源登记VLAN和当前交换机VLAN不一致怎么办？",
        "接入侧正常但是业务还是访问不了应该继续检查什么？",
    ]

    for query in queries:
        print("=" * 80)
        print("QUERY:", query)
        for i, item in enumerate(retriever.search(query, top_k=settings.rag_top_k), 1):
            print()
            print(f"[{i}] score={item['score']:.4f}")
            print("source :", item["source"])
            print("section:", item["section"])
            print(item["content"][:300])


if __name__ == "__main__":
    main()
