import json
from collections import Counter, defaultdict
from pathlib import Path


DATASET = Path("data/evaluation/quantization_cases_50.json")


def test_quantization_dataset_50_shape_and_fields():
    rows = json.loads(DATASET.read_text(encoding="utf-8"))
    assert len(rows) == 50
    assert len({row["case_id"] for row in rows}) == 50

    families = Counter(row["scenario_family"] for row in rows)
    assert len(families) == 10
    assert set(families.values()) == {5}

    by_family = defaultdict(set)
    for row in rows:
        assert row["diagnosis_code"]
        assert row["variant"] in {1, 2, 3, 4, 5}
        assert row["variant_type"]
        report = row["input_report"]
        assert "诊断代码：" in report
        assert "结论：" in report
        assert "建议：" in report
        assert "人工审批：" in report
        by_family[row["scenario_family"]].add(row["variant"])

    assert all(variants == {1, 2, 3, 4, 5} for variants in by_family.values())


def test_all_50_gold_conclusions_are_covered_by_direction_rules():
    from app.llm.report_guardrails import diagnosis_direction_signals, extract_constraints

    rows = json.loads(DATASET.read_text(encoding="utf-8"))
    failures = []
    for row in rows:
        constraints = extract_constraints(row["input_report"])
        conclusion = constraints.get("conclusion") or ""
        signals = diagnosis_direction_signals(row["diagnosis_code"], conclusion)
        if not signals["supported"] or signals["contradicted"]:
            failures.append((row["case_id"], row["diagnosis_code"], conclusion, signals))
    assert failures == []
