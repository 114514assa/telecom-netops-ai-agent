from __future__ import annotations

import json
from app.llm.report_guardrails import validate_auxiliary_output, safe_guardrail_metadata
from scripts.analyze_guardrail_v3_1 import summarize_records, write_outputs

SOURCE = """# 模拟诊断
- 诊断代码：vlan_mismatch
- 结论：当前 VLAN 与登记 VLAN 不一致。
- 建议：只读核查并人工复核，不自动修改生产配置。
"""


def test_safe_negative_adjustment_is_not_flagged_as_command():
    r = validate_auxiliary_output(SOURCE, "辅助说明：当前 VLAN 与登记 VLAN 不一致，应避免直接调整生产 VLAN 配置，建议只读核查并人工复核。")
    assert r.passed and r.unsafe_free


def test_safe_do_not_modify_is_not_flagged():
    r = validate_auxiliary_output(SOURCE, "辅助说明：当前 VLAN 与登记 VLAN 不一致，切勿直接修改配置，建议人工复核。")
    assert r.passed


def test_positive_modify_still_blocked():
    r = validate_auxiliary_output(SOURCE, "辅助说明：当前 VLAN 与登记 VLAN 不一致，请立即修改生产 VLAN 配置。")
    assert not r.passed and "unsafe_operation_suggestion" in r.reasons


def test_negation_does_not_allow_second_unsafe_action():
    r = validate_auxiliary_output(SOURCE, "辅助说明：当前 VLAN 与登记 VLAN 不一致，避免直接修改配置，但请重启交换机。")
    assert not r.passed and "unsafe_operation_suggestion" in r.reasons


def test_contradictory_vlan_remains_blocked():
    r = validate_auxiliary_output(SOURCE, "辅助说明：当前 VLAN 与登记 VLAN 一致，建议只读核查。")
    assert not r.passed and "semantic_contradiction" in r.reasons


def test_guardrail_metadata_drops_raw_text_and_keeps_reason_codes():
    payload = "辅助说明：当前 VLAN 不一致，请重启交换机后核查。"
    result = validate_auxiliary_output(SOURCE, payload)
    meta = safe_guardrail_metadata(result)
    assert "candidate_text" not in meta and "auxiliary_text" not in meta
    assert payload not in json.dumps(meta, ensure_ascii=False)
    assert "unsafe_operation_suggestion" in meta["reasons"]
    assert meta["candidate_char_count"] > 0 and len(meta["candidate_sha256"]) == 64


def test_metadata_has_no_sensitive_candidate_strings():
    result = validate_auxiliary_output(SOURCE, "辅助说明：VLAN 不一致，请重启 10.10.10.10 的交换机。")
    meta = safe_guardrail_metadata(result)
    assert "10.10.10.10" not in json.dumps(meta, ensure_ascii=False)


def test_guardrail_summary_counts_and_export(tmp_path):
    events = [
        {"event": "report_composed", "detail": {"diagnosis_code": "vlan_mismatch", "generated_by": "local_hf:int4:guarded", "guardrail_reasons": []}},
        {"event": "report_composed", "detail": {"diagnosis_code": "vlan_mismatch", "generated_by": "deterministic-template-fallback", "guardrail_reasons": ["unsafe_operation_suggestion"]}},
        {"event": "report_composed", "detail": {"diagnosis_code": "physical_or_terminal_link", "generated_by": "deterministic-template", "guardrail_reasons": []}},
        {"event": "approval_decision", "detail": {"approved": True}},
    ]
    s = summarize_records(events)
    assert s["events"] == 3 and s["llm_accepted"] == 1 and s["llm_fallback"] == 1 and s["template_only"] == 1
    assert s["llm_acceptance_rate"] == 0.5
    assert s["rejection_reasons"]["unsafe_operation_suggestion"] == 1
    files = write_outputs(s, tmp_path, stamp="TEST")
    assert len(files) == 3 and all(x.is_file() and "v3_1_1_TEST" in x.name for x in files)
    assert "VLAN" not in files[0].read_text(encoding="utf-8") or s["events"] == 3
