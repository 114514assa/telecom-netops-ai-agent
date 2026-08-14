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


def test_build_request_does_not_delegate_protected_fields():
    request = build_auxiliary_request(SOURCE)
    assert "诊断类型（仅供理解，不要输出）：vlan_mismatch" in request
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
