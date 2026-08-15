from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path

from app.core.config import get_settings
from app.services.knowledge import LangChainKnowledgeBase


def is_relevant(hit, relevant: list[dict]) -> bool:
    for target in relevant:
        if hit.source != target["source"]:
            continue
        sections = target.get("sections") or []
        if not sections:
            return True
        if any(keyword.lower() in hit.title.lower() for keyword in sections):
            return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="data/rag_eval/queries_30.json")
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()

    settings = get_settings()
    cases = json.loads(Path(args.dataset).read_text(encoding="utf-8"))

    retriever = LangChainKnowledgeBase(settings)
    retriever.load()
    if retriever.retriever is None:
        raise RuntimeError(
            "LangChain RAG is not available. Start Ollama, pull the embedding model, "
            "and run `python -m scripts.build_vector_index` first."
        )

    rows = []
    latencies = []
    hit1 = 0
    hit3 = 0

    for idx, case in enumerate(cases, 1):
        started = time.perf_counter()
        hits = retriever.search(case["query"], top_k=args.top_k)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        latencies.append(elapsed_ms)

        rank = None
        for r, hit in enumerate(hits, 1):
            if is_relevant(hit, case["relevant"]):
                rank = r
                break

        hit1 += int(rank == 1)
        hit3 += int(rank is not None and rank <= 3)
        rows.append(
            {
                "backend": "langchain-ollama-faiss",
                "case_id": case["case_id"],
                "query": case["query"],
                "first_relevant_rank": rank if rank is not None else "",
                "hit_at_1": int(rank == 1),
                "hit_at_3": int(rank is not None and rank <= 3),
                "latency_ms": round(elapsed_ms, 3),
                "top1_source": hits[0].source if hits else "",
                "top1_section": hits[0].title if hits else "",
                "top1_score": hits[0].score if hits else "",
            }
        )
        print(f"[{idx:02d}/{len(cases)}] {case['case_id']} rank={rank} latency={elapsed_ms:.1f}ms")

    count = len(cases)
    summary = {
        "backend": "langchain-ollama-faiss",
        "cases": count,
        "hit_at_1": round(hit1 / count, 4) if count else 0.0,
        "hit_at_3": round(hit3 / count, 4) if count else 0.0,
        "avg_latency_ms": round(sum(latencies) / len(latencies), 3) if latencies else 0.0,
    }

    out_dir = settings.runtime_dir / "rag_eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%S")
    detail_path = out_dir / f"rag_eval_detail_{stamp}.csv"
    summary_path = out_dir / f"rag_eval_summary_{stamp}.csv"
    json_path = out_dir / f"rag_eval_{stamp}.json"

    with detail_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    with summary_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary.keys()))
        writer.writeheader()
        writer.writerow(summary)

    json_path.write_text(
        json.dumps({"dataset": args.dataset, "top_k": args.top_k, "summary": summary, "detail": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("\n=== LangChain RAG retrieval summary ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("Saved:", summary_path)
    print("Saved:", detail_path)
    print("Saved:", json_path)


if __name__ == "__main__":
    main()
