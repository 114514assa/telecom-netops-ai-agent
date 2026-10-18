import json
from collections import Counter
from pathlib import Path


def test_final_quality_dataset_has_30_balanced_variants():
    path = Path('data/evaluation/quality_cases_30.json')
    cases = json.loads(path.read_text(encoding='utf-8'))
    assert len(cases) == 30
    assert len({case['case_id'] for case in cases}) == 30
    counts = Counter(case['scenario_family'] for case in cases)
    assert len(counts) == 10
    assert set(counts.values()) == {3}
    assert all(case['diagnosis_code'] in case['input_report'] for case in cases)
