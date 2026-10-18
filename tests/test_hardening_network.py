"""Synthetic CLI fixtures exercising failure *patterns documented in the source*.
Not production records. Numeric MAC/IP/VLAN values are from existing Demo fixtures.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json

from app.domain.enums import DiagnosisCode
from app.domain.models import EvidenceInput, IncidentInput, InventoryRecord
from app.parsers.aggregate import parse_all_evidence
from app.parsers.interface import parse_interface_output
from app.parsers.mac import parse_mac_output
from app.parsers.vlan import parse_vlan_output
from app.services.collection import FixtureEvidenceCollector, CollectionUnavailable
from app.services.diagnosis import diagnose

ROOT=Path(__file__).parents[1]
INVENTORY=InventoryRecord(ip_address='10.20.30.15',access_id='ACC-SIM-003',user_area='B',
    device_name='SW-SIM-03',device_role='SW',device_location='模拟机房B',registered_port='GE0/0/15',
    expected_vlan=200,network_domain='OA-SIM')
INCIDENT=IncidentInput(ip_address='10.20.30.15',symptom='地址调整后无法接入',target_mac='00:11:22:33:44:15')


def test_unrecognized_mac_is_unknown_not_absent():
    parsed=parse_mac_output('VendorXYZ malformed interface line',INCIDENT.target_mac)
    assert parsed.parse_status=='failed' and parsed.target_found is None


def test_explicit_mac_table_zero_supports_absence():
    parsed=parse_mac_output('Total MAC entries: 0',INCIDENT.target_mac)
    assert parsed.parse_status=='success' and parsed.target_found is False


def test_two_interfaces_do_not_mix_vlan_fields():
    raw='interface GigabitEthernet0/0/15\n port link-type access\n port default vlan 200\n' \
        'interface GigabitEthernet0/0/16\n port link-type access\n port default vlan 210\n'
    p=parse_vlan_output(raw,'GE0/0/15')
    assert p.parse_status=='success' and p.access_vlan==200
    assert parse_vlan_output(raw).parse_status=='ambiguous'


def test_unrelated_interface_status_is_not_accepted():
    raw='GigabitEthernet0/0/16 current state : DOWN\nLine protocol current state : DOWN'
    assert parse_interface_output(raw,'GE0/0/15').parse_status=='failed'


def test_wrong_format_cannot_trigger_no_mac_rule():
    evidence=EvidenceInput(interface_output='GigabitEthernet0/0/15 current state : UP\nLine protocol current state : UP',
        mac_output='unrecognized vendor CLI',observed_port='GE0/0/15')
    parsed=parse_all_evidence(evidence,INCIDENT.target_mac,INCIDENT.ip_address,target_port='GE0/0/15')
    assert diagnose(INCIDENT,INVENTORY,parsed).code==DiagnosisCode.INSUFFICIENT_EVIDENCE


def test_vlan_evidence_conflict_does_not_silently_choose_access_vlan():
    evidence=EvidenceInput(interface_output='GigabitEthernet0/0/15 current state : UP\nLine protocol current state : UP',
        mac_output='210 0011-2233-4415 dynamic GE0/0/15',
        vlan_output='interface GigabitEthernet0/0/15\nport link-type access\nport default vlan 200',
        observed_port='GE0/0/15')
    parsed=parse_all_evidence(evidence,INCIDENT.target_mac,INCIDENT.ip_address,target_port='GE0/0/15')
    assert 'vlan:interface_mac_conflict' in parsed.quality_issues
    assert diagnose(INCIDENT,INVENTORY,parsed).code==DiagnosisCode.INSUFFICIENT_EVIDENCE


def test_stale_evidence_returns_insufficient():
    evidence=EvidenceInput(interface_output='GigabitEthernet0/0/15 current state : DOWN\nLine protocol current state : DOWN',
        collected_at=datetime.now(timezone.utc)-timedelta(hours=2),observed_port='GE0/0/15')
    parsed=parse_all_evidence(evidence,INCIDENT.target_mac,INCIDENT.ip_address,'GE0/0/15')
    assert diagnose(INCIDENT,INVENTORY,parsed).code==DiagnosisCode.INSUFFICIENT_EVIDENCE


def test_historical_documented_vlan_pattern_remains_classified():
    raw=json.loads((ROOT/'data/sample_requests/vlan_mismatch.json').read_text(encoding='utf-8'))
    inc=IncidentInput.model_validate(raw['incident'])
    evidence=EvidenceInput.model_validate(raw['evidence'])
    parsed=parse_all_evidence(evidence,inc.target_mac,inc.ip_address,'GE0/0/15')
    assert parsed.quality_issues==[]
    assert diagnose(inc,INVENTORY,parsed).code==DiagnosisCode.VLAN_MISMATCH


def test_collector_only_uses_allowlisted_fixtures():
    collector=FixtureEvidenceCollector(ROOT/'data/sample_requests')
    evidence=collector.collect(INVENTORY)
    assert evidence.evidence_mode=='simulated_collection'
    assert evidence.collected_at is not None
    assert evidence.mac_output.strip()
    assert 'sample' not in evidence.source_system
    other=INVENTORY.model_copy(update={'ip_address':'10.10.10.101'})
    try:collector.collect(other)
    except CollectionUnavailable:pass
    else:assert False, 'unknown IP should never map to a random file or network host'
