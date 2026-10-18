from __future__ import annotations

import argparse
import csv
import json
import statistics
import time
from collections import defaultdict
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


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    pos = (len(xs) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    frac = pos - lo
    return xs[lo] * (1 - frac) + xs[hi] * frac


def aggregate(rows: list[dict]) -> dict:
    n = len(rows)
    if not n:
        return {
            "cases": 0, "hit_at_1": 0.0, "hit_at_3": 0.0, "hit_at_5": 0.0,
            "mrr": 0.0, "avg_latency_ms": 0.0, "p95_latency_ms": 0.0,
            "empty_rate": 0.0, "error_rate": 0.0,
        }
    lats = [float(r["latency_ms"]) for r in rows]
    return {
        "cases": n,
        "hit_at_1": round(sum(int(r["hit_at_1"]) for r in rows) / n, 4),
        "hit_at_3": round(sum(int(r["hit_at_3"]) for r in rows) / n, 4),
        "hit_at_5": round(sum(int(r["hit_at_5"]) for r in rows) / n, 4),
        "mrr": round(sum(float(r["reciprocal_rank"]) for r in rows) / n, 4),
        "avg_latency_ms": round(sum(lats) / n, 3),
        "p95_latency_ms": round(percentile(lats, 0.95), 3),
        "empty_rate": round(sum(int(r["empty_result"]) for r in rows) / n, 4),
        "error_rate": round(sum(int(bool(r["retrieval_error"])) for r in rows) / n, 4),
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="data/rag_eval/queries_150.json")
    parser.add_argument("--top-k", type=int, default=5, help="Retrieve once at K=5, then compute Hit@1/3/5 from the ranking.")
    parser.add_argument("--repeats", type=int, default=3, help="Repeat each query for more stable latency; ranking uses the final repeat.")
    parser.add_argument("--warmup", type=int, default=3, help="Warm-up retrieval calls before timing.")
    args = parser.parse_args()

    if args.top_k < 5:
        raise ValueError("For this experiment use --top-k 5 so Hit@5 is measurable.")
    if args.repeats < 1:
        raise ValueError("--repeats must be >= 1")

    settings = get_settings()
    cases = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    if len(cases) != 150:
        print(f"WARNING: dataset has {len(cases)} cases, expected 150.")

    kb = LangChainKnowledgeBase(settings)
    kb.load()
    if kb.retriever is None:
        raise RuntimeError(
            "LangChain RAG is not available. Check RAG_KNOWLEDGE_DIR, start Ollama, "
            "pull the embedding model, and rebuild the vector index first."
        )

    # Warm-up avoids measuring model/index cold-start in the main latency statistics.
    warm_query = cases[0]["query"] if cases else "网络故障排查"
    for _ in range(max(0, args.warmup)):
        kb.search(warm_query, top_k=args.top_k)

    rows: list[dict] = []
    for idx, case in enumerate(cases, 1):
        hits = []
        run_latencies = []
        retrieval_error = ""
        for _ in range(args.repeats):
            started = time.perf_counter()
            hits = kb.search(case["query"], top_k=args.top_k)
            run_latencies.append((time.perf_counter() - started) * 1000.0)
            if kb.last_error:
                retrieval_error = kb.last_error
        elapsed_ms = statistics.median(run_latencies)

        rank = None
        for r, hit in enumerate(hits, 1):
            if is_relevant(hit, case["relevant"]):
                rank = r
                break

        def h(k: int) -> int:
            return int(rank is not None and rank <= k)

        top = []
        for r, hit in enumerate(hits[:5], 1):
            top.append(f"{r}:{hit.source}::{hit.title}::{hit.score}")

        rows.append({
            "backend": "langchain-ollama-faiss",
            "case_id": case["case_id"],
            "category": case.get("category", ""),
            "category_name": case.get("category_name", ""),
            "expression_type": case.get("expression_type", ""),
            "expression_name": case.get("expression_name", ""),
            "difficulty": case.get("difficulty", ""),
            "query": case["query"],
            "first_relevant_rank": rank if rank is not None else "",
            "hit_at_1": h(1),
            "hit_at_3": h(3),
            "hit_at_5": h(5),
            "reciprocal_rank": round(1.0 / rank, 6) if rank else 0.0,
            "latency_ms": round(elapsed_ms, 3),
            "empty_result": int(not hits),
            "retrieval_error": retrieval_error,
            "top5": " || ".join(top),
        })
        print(
            f"[{idx:03d}/{len(cases)}] {case['case_id']} "
            f"rank={rank} H1={h(1)} H3={h(3)} H5={h(5)} latency={elapsed_ms:.1f}ms"
        )

    overall = aggregate(rows)
    summary = {
        "backend": "langchain-ollama-faiss",
        "dataset": args.dataset,
        "top_k": args.top_k,
        "repeats": args.repeats,
        "knowledge_dir": str(settings.rag_knowledge_dir),
        "embedding_model": settings.ollama_embed_model,
        **overall,
    }

    def grouped(field: str) -> list[dict]:
        groups = defaultdict(list)
        for row in rows:
            groups[row.get(field, "")].append(row)
        output = []
        for key in sorted(groups):
            metric = aggregate(groups[key])
            name_field = "category_name" if field == "category" else "expression_name"
            display_name = next((r.get(name_field, "") for r in groups[key] if r.get(name_field)), "")
            output.append({field: key, name_field: display_name, **metric})
        return output

    per_category = grouped("category")
    per_expression = grouped("expression_type")
    errors = [r for r in rows if not int(r["hit_at_1"])]

    out_dir = settings.runtime_dir / "rag_eval_150"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%S")
    detail_path = out_dir / f"rag150_detail_{stamp}.csv"
    summary_path = out_dir / f"rag150_summary_{stamp}.csv"
    category_path = out_dir / f"rag150_per_category_{stamp}.csv"
    expression_path = out_dir / f"rag150_per_expression_{stamp}.csv"
    errors_path = out_dir / f"rag150_hit1_errors_{stamp}.csv"
    json_path = out_dir / f"rag150_full_{stamp}.json"

    write_csv(detail_path, rows)
    write_csv(summary_path, [summary])
    write_csv(category_path, per_category)
    write_csv(expression_path, per_expression)
    write_csv(errors_path, errors)
    json_path.write_text(json.dumps({
        "summary": summary,
        "per_category": per_category,
        "per_expression": per_expression,
        "detail": rows,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== RAG-150 summary ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("\n=== Per-category ===")
    for row in per_category:
        print(
            f"{row['category']:<10} n={row['cases']:>3} "
            f"H1={row['hit_at_1']:.4f} H3={row['hit_at_3']:.4f} "
            f"H5={row['hit_at_5']:.4f} MRR={row['mrr']:.4f}"
        )
    print("\nSaved:")
    for p in [summary_path, detail_path, category_path, expression_path, errors_path, json_path]:
        print(p)


if __name__ == "__main__":
    main()
