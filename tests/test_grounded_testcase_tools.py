"""Offline test-design regression, independent of Ollama, CUDA and MCP runtime."""
import csv
import io
import json
from pathlib import Path

import pytest

from app.services.grounded_testcases import generate_cases, list_categories, render_cases


def test_original_source_and_source_links_are_kept():
    info = list_categories()
    assert info['total'] == 34
    cases = generate_cases()
    assert len(cases) == 34
    assert len({c['test_id'] for c in cases}) == 34
    assert all(c['verification_state'] == 'not_executed' for c in cases)
    source = json.loads((Path(__file__).parents[1] / 'data/rag_eval/queries_document_grounded.json').read_text(encoding='utf-8'))
    for c, raw in zip(cases, source):
        assert c['query'] == raw['query']
        assert c['provenance']['support'] == raw['source_evidence']['support']
        assert c['provenance']['page'] == raw['source_evidence']['page']
        assert c['gold'] == raw['relevant']
        assert c['type'] == 'rag_retrieval'


def test_three_export_formats_retaining_full_case_fields():
    cases = generate_cases(limit=2)
    out = json.loads(render_cases(cases, 'json'))
    assert out == cases
    md = render_cases(cases, 'markdown')
    assert '前置条件' in md and '测试步骤' in md and '预期结果' in md
    assert cases[0]['provenance']['document'] in md
    records = list(csv.DictReader(io.StringIO(render_cases(cases, 'csv'))))
    assert len(records) == 2
    assert records[0]['query'] == cases[0]['query']
    assert records[0]['verification_state'] == 'not_executed'


def test_category_filter_and_invalid_limits():
    out = generate_cases(category='vlan', limit=100)
    assert len(out) == 3 and all(c['category'] == 'vlan' for c in out)
    with pytest.raises(ValueError): generate_cases(category='fabricated')
    for x in (0, 101, True, -1):
        with pytest.raises(ValueError): generate_cases(limit=x)
    with pytest.raises(ValueError): render_cases([], format='xmind')


def test_docs_not_promoted_to_network_evidence():
    case = generate_cases(limit=1)[0]
    assert case['verification_state'] == 'not_executed'
    assert 'metadata_linked' in case['source_verification']
    assert not any(k in case for k in ('diagnosis', 'interface_state', 'target_mac_seen', 'observed_vlan'))
