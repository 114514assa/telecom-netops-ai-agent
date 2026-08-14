from app.domain.enums import DiagnosisCode, FaultType, Layer, Severity
from app.domain.models import (
    DiagnosisResult,
    IncidentInput,
    InventoryRecord,
    ParsedEvidence,
    ParsedInterface,
    ParsedMac,
    ParsedVlan,
)
from app.services.knowledge import build_retrieval_query


def test_build_retrieval_query_contains_structured_evidence():
    incident = IncidentInput(
        ip_address="10.20.30.15",
        symptom="网络不通",
        fault_type=FaultType.OTHER,
    )
    inventory = InventoryRecord(
        ip_address="10.20.30.15",
        access_id="ACC-SIM-001",
        user_area="SIM",
        device_name="SW-SIM-01",
        device_role="access-switch",
        device_location="SIM",
        registered_port="GE0/0/15",
        expected_vlan=200,
        network_domain="OA-SIM",
    )
    parsed = ParsedEvidence(
        interface=ParsedInterface(status="UP"),
        mac=ParsedMac(target_found=False),
        vlan=ParsedVlan(access_vlan=200),
    )
    diagnosis = DiagnosisResult(
        code=DiagnosisCode.L2_NO_MAC,
        likely_layer=Layer.L2,
        severity=Severity.MEDIUM,
        confidence=0.88,
        summary="接口UP但未学习目标MAC",
        hypotheses=["终端未产生流量"],
    )

    query = build_retrieval_query(incident, inventory, parsed, diagnosis)
    assert "接口状态：UP" in query
    assert "未学习到目标MAC" in query
    assert "资源登记目标VLAN：200" in query
    assert "排障流程" in query
