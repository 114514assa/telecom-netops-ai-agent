from scripts.benchmark_agent_e2e import extract_state_metadata


def test_e2e_csv_metadata_contains_only_guardrail_reasons():
    report = {
        'state': {
            'diagnosis': {'code': 'vlan_mismatch'},
            'knowledge_hits': [{}, {}, {}],
            'report': {
                'generated_by': 'deterministic-template-fallback',
                'generation_meta': {
                    'latency_ms': 123.5,
                    'guardrail_passed': False,
                    'guardrail_reasons': ['unsafe_operation_suggestion'],
                    'fallback_reason': 'llm_guardrail_rejected',
                    'guardrail': {'candidate_sha256': 'abcdef', 'reasons': ['unsafe_operation_suggestion']},
                },
            },
        },
    }
    meta = extract_state_metadata(report)
    assert meta['diagnosis_code'] == 'vlan_mismatch'
    assert meta['guardrail_passed'] is False
    assert meta['guardrail_reasons'] == 'unsafe_operation_suggestion'
    assert meta['fallback_reason'] == 'llm_guardrail_rejected'
    assert 'candidate_sha256' not in meta
    assert 'candidate_text' not in meta
