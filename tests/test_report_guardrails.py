from app.llm.report_guardrails import build_auxiliary_request, validate_auxiliary_output

SOURCE = """# 报告
- 终端 IP：10.20.30.15
- 登记设备：SW-SIM-03
- 目标 VLAN：200
- MAC 学习 VLAN：210
- 诊断代码：vlan_mismatch
- 置信度：0.96
- 结论：设备侧 VLAN 与资源登记目标 VLAN 不一致。
- 建议：人工核对资源台账与正式变更记录，不得自动修改生产配置。
"""


def test_build_request_does_not_expose_protected_fields():
    request = build_auxiliary_request(SOURCE)
    assert "vlan_mismatch" not in request
    assert "10.20.30.15" not in request
    assert "0.96" not in request
    assert "结论：设备侧 VLAN 与资源登记目标 VLAN 不一致。" in request
    assert "只输出一行：辅助说明" in request


def test_valid_auxiliary_output_passes():
    output = "辅助说明：建议人工核对资源台账与正式变更记录，确认接入信息后再由授权人员处理。"
    result = validate_auxiliary_output(SOURCE, output)
    assert result.passed is True
    assert result.auxiliary_text


def test_extra_model_text_is_ignored_if_safe_auxiliary_exists():
    output = "说明如下\n辅助说明：建议人工核对资源台账与变更记录，并由授权人员确认后继续处理。\n谢谢"
    result = validate_auxiliary_output(SOURCE, output)
    assert result.passed is True
    assert result.ignored_extra_lines == 2


def test_identifier_in_auxiliary_is_rejected():
    output = "辅助说明：建议继续核对 VLAN 300，并由授权人员确认。"
    result = validate_auxiliary_output(SOURCE, output)
    assert result.passed is False
    assert "identifier_or_numeric_fact_in_auxiliary" in result.reasons


def test_confidence_recalculation_is_rejected():
    output = "辅助说明：当前置信度为99%，建议人工复核。"
    result = validate_auxiliary_output(SOURCE, output)
    assert result.passed is False
    assert "identifier_or_numeric_fact_in_auxiliary" in result.reasons


def test_unsafe_reboot_is_rejected():
    output = "辅助说明：建议重启交换机后再次观察。"
    result = validate_auxiliary_output(SOURCE, output)
    assert result.passed is False
    assert "unsafe_operation_suggestion" in result.reasons


def test_unresolved_case_cannot_claim_no_issue():
    output = "辅助说明：未发现明显异常，无需进一步核查。"
    result = validate_auxiliary_output(SOURCE, output)
    assert result.passed is False
    assert "semantic_contradiction" in result.reasons


def test_normal_access_allows_no_further_access_check_wording():
    source = """# 报告
- 诊断代码：access_side_normal
- 结论：资源关系、接口、MAC 与 VLAN 证据一致，接入侧未发现明显异常。
- 建议：若业务仍不可用，将现有证据转交上层网络或业务维护人员继续分析。
"""
    output = "辅助说明：资源关系与接口证据一致，无需进一步核查接入侧。"
    result = validate_auxiliary_output(source, output)
    assert result.passed is True
    assert result.semantic_relevant is True


def test_semantically_unrelated_but_safe_sentence_is_rejected():
    output = "辅助说明：建议人工查看相关资料并做好记录。"
    result = validate_auxiliary_output(SOURCE, output)
    assert result.passed is False
    assert result.semantic_relevant is False
    assert "semantic_irrelevance" in result.reasons


def test_rejected_output_keeps_candidate_for_audit():
    output = "辅助说明：建议重启交换机后再次观察。"
    result = validate_auxiliary_output(SOURCE, output)
    assert result.passed is False
    assert result.auxiliary_text is None
    assert result.candidate_text == "建议重启交换机后再次观察。"


def test_diagnosis_code_echo_is_rejected():
    output = "辅助说明：根据已确认的诊断类型 vlan_mismatch，建议人工核对资源台账。"
    result = validate_auxiliary_output(SOURCE, output)
    assert result.passed is False
    assert result.diagnosis_code_free is False
    assert "diagnosis_code_echo" in result.reasons


def test_policy_adjustment_suggestion_is_rejected():
    source = """# 报告
- 诊断代码：uplink_policy_or_application
- 结论：接入侧未见明显异常，需继续核查上层网络或业务链路。
- 建议：仅做只读核查并转交相关维护人员。
"""
    output = "辅助说明：可能需要进一步的只读检查和策略调整。"
    result = validate_auxiliary_output(source, output)
    assert result.passed is False
    assert "unsafe_operation_suggestion" in result.reasons


def test_human_confirm_and_correct_is_rejected():
    source = """# 报告
- 诊断代码：terminal_config
- 结论：终端地址配置与正式资源登记不一致。
- 建议：人工核对终端地址与网关信息，不自动修改配置。
"""
    output = "辅助说明：终端地址与正式资源配置不符，需由人工确认并修正。"
    result = validate_auxiliary_output(source, output)
    assert result.passed is False
    assert "unsafe_operation_suggestion" in result.reasons


def test_interface_down_physical_connection_wording_is_relevant():
    source = """# 报告
- 诊断代码：physical_or_terminal_link
- 结论：登记端口未建立有效链路，优先核查物理连接或终端侧。
- 建议：仅做只读核查并由授权人员继续处理。
"""
    output = "辅助说明：在确认诊断信息后，仅需检查并确认物理连接或端口状态。"
    result = validate_auxiliary_output(source, output)
    assert result.passed is True
    assert result.semantic_relevant is True


def test_negated_manual_modify_is_not_false_positive():
    source = """# 报告
- 诊断代码：resource_inconsistency
- 结论：实际学习位置与资源台账登记不一致。
- 建议：人工复核接入点、资源记录和近期迁移情况，不自动修改台账。
"""
    output = "辅助说明：当前学习的位置与台账记录的端口不匹配，建议复核接入点和资源记录，无需手动修改台账信息。"
    result = validate_auxiliary_output(source, output)
    assert result.passed is True
    assert result.unsafe_free is True


def test_reconfigure_action_is_rejected():
    source = """# 报告
- 诊断代码：terminal_config
- 结论：终端地址配置与正式资源登记不一致。
- 建议：人工核对终端地址与网关信息，不自动修改配置。
"""
    output = "辅助说明：终端地址配置与正式资源不一致，需人工确认地址参数并重新配置。"
    result = validate_auxiliary_output(source, output)
    assert result.passed is False
    assert "unsafe_operation_suggestion" in result.reasons


def test_negated_config_change_statement_is_allowed():
    output = "辅助说明：建议人工核对资源台账与正式变更记录，不得自动修改生产配置。"
    result = validate_auxiliary_output(SOURCE, output)
    assert result.passed is True
    assert result.unsafe_free is True


def test_abnormal_case_rejects_premature_no_other_action_claim():
    output = "辅助说明：建议人工核对资源台账与变更记录，无需进行其他操作。"
    result = validate_auxiliary_output(SOURCE, output)
    assert result.passed is False
    assert "semantic_contradiction" in result.reasons


def test_new_root_cause_expansion_is_rejected():
    output = "辅助说明：可能的原因是配置错误，建议人工核对资源台账。"
    result = validate_auxiliary_output(SOURCE, output)
    assert result.passed is False
    assert "unsupported_root_cause_expansion" in result.reasons


def _source_for(code: str, conclusion: str, recommendation: str = "建议仅进行只读核查并由授权人员人工复核。") -> str:
    return f"""# 报告
- 诊断代码：{code}
- 结论：{conclusion}
- 建议：{recommendation}
"""


def test_vlan_direction_reversal_is_rejected():
    source = _source_for("vlan_mismatch", "当前接入 VLAN 与登记 VLAN 不一致。")
    output = "辅助说明：目标终端 MAC 学习 VLAN 与资源目标 VLAN 一致，建议只读核查。"
    result = validate_auxiliary_output(source, output)
    assert result.passed is False
    assert result.direction_contradicted is True
    assert result.contradiction_free is False
    assert "semantic_contradiction" in result.reasons


def test_vlan_negative_wording_is_not_misread_as_consistent():
    source = _source_for("vlan_mismatch", "当前接入 VLAN 与登记 VLAN 不一致。")
    output = "辅助说明：当前接入 VLAN 未与登记 VLAN 一致，建议进行只读核查并人工复核。"
    result = validate_auxiliary_output(source, output)
    assert result.direction_supported is True
    assert result.direction_contradicted is False
    assert result.contradiction_free is True


def test_no_mac_direction_reversal_is_rejected():
    source = _source_for("l2_no_mac", "接口已 UP，但未观察到目标终端 MAC 学习证据。")
    output = "辅助说明：目标终端 MAC 已学习，建议继续只读核查。"
    result = validate_auxiliary_output(source, output)
    assert result.passed is False
    assert result.direction_contradicted is True


def test_interface_down_direction_reversal_is_rejected():
    source = _source_for("physical_or_terminal_link", "登记端口当前无有效链路。")
    output = "辅助说明：当前接口状态正常且链路已建立，建议人工复核。"
    result = validate_auxiliary_output(source, output)
    assert result.passed is False
    assert result.direction_contradicted is True


def test_resource_inconsistency_reversal_is_rejected():
    source = _source_for("resource_inconsistency", "实际学习端口与资源登记端口不一致。")
    output = "辅助说明：实际学习端口与资源登记端口一致，建议人工复核。"
    result = validate_auxiliary_output(source, output)
    assert result.passed is False
    assert result.direction_contradicted is True


def test_terminal_config_reversal_is_rejected():
    source = _source_for("terminal_config", "终端默认网关与资源登记不一致。")
    output = "辅助说明：终端网关配置与登记信息一致，建议人工复核。"
    result = validate_auxiliary_output(source, output)
    assert result.passed is False
    assert result.direction_contradicted is True


def test_link_quality_reversal_is_rejected():
    source = _source_for("link_quality_issue", "接口错误计数较高，存在链路质量异常线索。")
    output = "辅助说明：当前链路质量正常且接口无异常，建议人工复核。"
    result = validate_auxiliary_output(source, output)
    assert result.passed is False
    assert result.direction_contradicted is True


def test_evidence_insufficient_reversal_is_rejected():
    source = _source_for("evidence_insufficient", "当前证据不足以定位故障层级。")
    output = "辅助说明：当前证据已经充分并已确定故障层级，建议人工复核。"
    result = validate_auxiliary_output(source, output)
    assert result.passed is False
    assert result.direction_contradicted is True


def test_access_side_normal_reversal_is_rejected():
    source = _source_for("access_side_normal", "接入侧未发现明显异常。", "若业务仍不可用，转交上层继续分析。")
    output = "辅助说明：接入侧存在明显故障，建议继续核查。"
    result = validate_auxiliary_output(source, output)
    assert result.passed is False
    assert result.direction_contradicted is True


def test_uplink_case_does_not_allow_claiming_access_side_fault():
    source = _source_for("uplink_policy_or_application", "接入侧关键证据未见明显异常，应继续核查上层网络或业务系统。")
    output = "辅助说明：接入侧存在故障，建议人工复核。"
    result = validate_auxiliary_output(source, output)
    assert result.passed is False
    assert result.direction_contradicted is True


def test_obvious_mixed_language_and_template_echo_are_rejected():
    source = _source_for("vlan_mismatch", "当前接入 VLAN 与登记 VLAN 不一致。")
    output = "辅助说明：已确认结论：VLAN 不一致，仅做只Read确认。"
    result = validate_auxiliary_output(source, output)
    assert result.passed is False
    assert result.text_quality_ok is False
    assert "text_quality_violation" in result.reasons
