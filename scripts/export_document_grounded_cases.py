"""Export source-annotated RAG test-case designs, not verified test results.

Usage: python -m scripts.export_document_grounded_cases --format markdown
"""
from __future__ import annotations

import argparse
from pathlib import Path

from app.services.grounded_testcases import ROOT, generate_cases, render_cases, list_categories


def main() -> None:
    parser = argparse.ArgumentParser(description="只读生成带出处的 RAG 检索测试用例")
    parser.add_argument("--format", choices=["json", "markdown", "csv"], default="markdown")
    parser.add_argument("--category", default=None)
    parser.add_argument("--limit", type=int, default=34)
    parser.add_argument("--output", default=None, help="生成目标路径，默认 runtime/generated_testcases/...；不会修改原始 Query")
    parser.add_argument("--validate-only", action="store_true", help="仅验证源数据结构和知识标题，不运行 RAG")
    args = parser.parse_args()
    info = list_categories()
    if args.validate_only:
        print(f"VALID: {info['total']} 条资料约束 Query；知识文件/章节引用存在。原始电信 PDF 未独立复核。")
        return
    cases = generate_cases(category=args.category, limit=args.limit)
    path = Path(args.output) if args.output else ROOT / 'runtime' / 'generated_testcases' / ('document_grounded.' + {'markdown':'md','json':'json','csv':'csv'}[args.format])
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = render_cases(cases, format=args.format)
    path.write_text(payload, encoding='utf-8-sig' if args.format == 'csv' else 'utf-8')
    print(f"WROTE {len(cases)} UNEXECUTED tests -> {path.resolve()}")
    print("CAUTION: provenance metadata is curated; no claims of original document re-verification or live incident accuracy.")


if __name__ == '__main__':
    main()
