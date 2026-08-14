from __future__ import annotations

import argparse
import csv
import json
import time
from collections import defaultdict
from pathlib import Path

from app.core.config import get_settings
from app.services.knowledge import KnowledgeBase, VectorKnowledgeBase


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


def run_backend(name, retriever, cases, top_k):
    rows = []
    latencies = []
    hit1 = 0
    hit3 = 0

    for idx, case in enumerate(cases, 1):
        start = time.perf_counter()
        hits = retriever.search(case["query"], top_k=top_k)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        latencies.append(elapsed_ms)

        rank = None
        for r, hit in enumerate(hits, 1):
            if is_relevant(hit, case["relevant"]):
                rank = r
                break

        if rank == 1:
            hit1 += 1
        if rank is not None and rank <= 3:
            hit3 += 1

        rows.append(
            {
                "backend": name,
                "case_id": case["case_id"],
                "query": case["query"],
                "first_relevant_rank": rank if rank is not None else "",
                "hit_at_1": int(rank == 1),
                "hit_at_3": int(rank is not None and rank <= 3),
                "latency_ms": round(elapsed_ms, 3),
                "top1_source": hits[0].source if hits else "",
                "top1_section": hits[0].title if hits else "",
                "top1_score": hits[0].score if hits else "",
                "top3": json.dumps(
                    [
                        {
                            "source": hit.source,
                            "section": hit.title,
                            "score": hit.score,
                        }
                        for hit in hits[:3]
                    ],
                    ensure_ascii=False,
                ),
            }
        )
        print(
            f"[{name}] {idx:02d}/{len(cases)} {case['case_id']} "
            f"rank={rank} latency={elapsed_ms:.1f}ms"
        )

    count = len(cases)
    summary = {
        "backend": name,
        "cases": count,
        "hit_at_1": round(hit1 / count, 4) if count else 0.0,
        "hit_at_3": round(hit3 / count, 4) if count else 0.0,
        "avg_latency_ms": round(sum(latencies) / len(latencies), 3) if latencies else 0.0,
    }
    return rows, summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="data/rag_eval/queries_30.json")
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()

    settings = get_settings()
    cases = json.loads(Path(args.dataset).read_text(encoding="utf-8"))

    tfidf = KnowledgeBase(settings.rag_knowledge_dir)
    tfidf.load()

    vector = VectorKnowledgeBase(settings)
    vector.load()

    all_rows = []
    summaries = []

    rows, summary = run_backend("tfidf", tfidf, cases, args.top_k)
    all_rows.extend(rows)
    summaries.append(summary)

    rows, summary = run_backend("vector", vector, cases, args.top_k)
    all_rows.extend(rows)
    summaries.append(summary)

    out_dir = settings.runtime_dir / "rag_eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%S")

    detail_path = out_dir / f"rag_eval_detail_{stamp}.csv"
    summary_path = out_dir / f"rag_eval_summary_{stamp}.csv"
    json_path = out_dir / f"rag_eval_{stamp}.json"

    with detail_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
        writer.writeheader()
        writer.writerows(all_rows)

    with summary_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(summaries[0].keys()))
        writer.writeheader()
        writer.writerows(summaries)

    json_path.write_text(
        json.dumps(
            {
                "dataset": args.dataset,
                "top_k": args.top_k,
                "summary": summaries,
                "detail": all_rows,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\n=== RAG retrieval summary ===")
    print(json.dumps(summaries, ensure_ascii=False, indent=2))
    print("Saved:", summary_path)
    print("Saved:", detail_path)
    print("Saved:", json_path)


if __name__ == "__main__":
    main()
