from datetime import datetime, timezone
from app.domain.models import EvidenceInput, ParsedEvidence
from app.parsers.arp import parse_arp_output
from app.parsers.interface import parse_interface_output
from app.parsers.mac import parse_mac_output
from app.parsers.terminal import parse_terminal_output
from app.parsers.vlan import parse_vlan_output
from app.parsers.common import normalize_port


def parse_all_evidence(evidence: EvidenceInput,target_mac: str|None,target_ip: str|None=None,target_port: str|None=None,max_age_seconds: int=1800)->ParsedEvidence:
    terminal=parse_terminal_output(evidence.terminal_output)
    effective_mac=target_mac or terminal.mac_address
    # Prefer the port explicitly identified by inventory or the caller.
    mac=parse_mac_output(evidence.mac_output,effective_mac)
    # A positively matched target MAC on another port is evidence of a changed
    # attachment point, not a parsing error to be forced into inventory scope.
    scoped_port=(evidence.observed_port or
                 (mac.learned_port if mac.target_found is True and mac.parse_status=='success' else None) or
                 target_port)
    interface=parse_interface_output(evidence.interface_output,scoped_port)
    vlan=parse_vlan_output(evidence.vlan_output,scoped_port)
    arp=parse_arp_output(evidence.arp_output,target_ip)
    issues=[]
    for key,raw,parsed in [("interface",evidence.interface_output,interface),
                           ("mac",evidence.mac_output,mac),("vlan",evidence.vlan_output,vlan),
                           ("arp",evidence.arp_output,arp)]:
        if raw.strip() and parsed.parse_status in ("failed","ambiguous"):
            issues.append(f"{key}:{parsed.parse_status}")
    if scoped_port:
        for name,port in (("interface",interface.port),("vlan",vlan.port)):
            if port and normalize_port(port)!=normalize_port(scoped_port):issues.append(f"{name}:wrong_port")
    if vlan.link_type=='access' and vlan.access_vlan is not None and mac.target_found and mac.vlan is not None:
        if vlan.access_vlan != mac.vlan and normalize_port(mac.learned_port)==normalize_port(scoped_port):
            issues.append('vlan:interface_mac_conflict')
    if evidence.collected_at:
        stamp=evidence.collected_at
        if stamp.tzinfo is None:issues.append('collection_time:missing_timezone')
        else:
            age=(datetime.now(timezone.utc)-stamp.astimezone(timezone.utc)).total_seconds()
            if age < -300:issues.append('collection_time:future')
            if age > max_age_seconds:issues.append('collection_time:stale')
    return ParsedEvidence(interface=interface,mac=mac,arp=arp,vlan=vlan,terminal=terminal,
        observed_device=evidence.observed_device,observed_port=evidence.observed_port,
        collected_at=evidence.collected_at,source_system=evidence.source_system,
        vendor=evidence.vendor,evidence_mode=evidence.evidence_mode,quality_issues=issues)
