from app.domain.enums import DiagnosisCode
from app.domain.models import IncidentInput, InventoryRecord, ParsedEvidence, ParsedInterface, ParsedMac, ParsedVlan
from app.services.diagnosis import diagnose


INVENTORY = InventoryRecord(
    ip_address="10.20.30.15",
    access_id="ACC-SIM-003",
    user_area="B",
    device_name="SW-SIM-03",
    device_role="SW",
    device_location="模拟机房B",
    registered_port="GE0/0/15",
    expected_vlan=200,
    network_domain="OA-SIM",
    expected_gateway="10.20.30.1",
    expected_dns="10.20.0.53",
    registered_mac="00:11:22:33:44:15",
)


def test_vlan_mismatch_has_priority():
    incident = IncidentInput(ip_address="10.20.30.15", symptom="迁移后不通", target_mac="00:11:22:33:44:15")
    parsed = ParsedEvidence(
        interface=ParsedInterface(status="UP", protocol_status="UP", port="GE0/0/15"),
        mac=ParsedMac(target_found=True, target_mac=incident.target_mac, learned_port="GE0/0/15", vlan=210),
        vlan=ParsedVlan(link_type="access", access_vlan=210, interface_shutdown=False),
        observed_device="SW-SIM-03",
    )
    result = diagnose(incident, INVENTORY, parsed)
    assert result.code == DiagnosisCode.VLAN_MISMATCH
    assert result.confidence >= 0.9


def test_resource_port_mismatch():
    incident = IncidentInput(ip_address="10.20.30.15", symptom="端口不明")
    parsed = ParsedEvidence(
        interface=ParsedInterface(status="UP", port="GE0/0/18"),
        mac=ParsedMac(target_found=True, learned_port="GE0/0/18", vlan=200),
        vlan=ParsedVlan(access_vlan=200),
        observed_device="SW-SIM-03",
    )
    result = diagnose(incident, INVENTORY, parsed)
    assert result.code == DiagnosisCode.RESOURCE_INCONSISTENCY
