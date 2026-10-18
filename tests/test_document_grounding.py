"""Provenance QA: explicitly sourced question prompts, not invented incidents."""
from pathlib import Path
import json

ROOT=Path(__file__).parents[1]


def test_queries_have_source_page_and_relevant_gold():
    rows=json.loads((ROOT/'data/rag_eval/queries_document_grounded.json').read_text(encoding='utf8'))
    assert len(rows)>=30
    assert len({c['case_id'] for c in rows})==len(rows)
    for c in rows:
        evidence=c['source_evidence']
        assert evidence['document'].endswith('pdf') or 'pdf（' in evidence['document']
        assert evidence['page']>=1
        assert len(evidence['support'])>=8
        assert '不代表实际发生' in evidence['interpretation']
        for ref in c['relevant']:
            text=(ROOT/'knowledge/sanitized'/ref['source']).read_text(encoding='utf8')
            assert any(section in text for section in ref['sections']), c['case_id']


def test_original_150_dataset_retained():
    legacy=json.loads((ROOT/'data/rag_eval/queries_150.json').read_text(encoding='utf8'))
    assert len(legacy)==150
