from app.domain.models import EvidenceInput, ParsedEvidence
from app.parsers.arp import parse_arp_output
from app.parsers.interface import parse_interface_output
from app.parsers.mac import parse_mac_output
from app.parsers.terminal import parse_terminal_output
from app.parsers.vlan import parse_vlan_output


def parse_all_evidence(evidence: EvidenceInput, target_mac: str | None, target_ip: str | None = None) -> ParsedEvidence:
    terminal = parse_terminal_output(evidence.terminal_output)
    effective_mac = target_mac or terminal.mac_address
    return ParsedEvidence(
        interface=parse_interface_output(evidence.interface_output),
        mac=parse_mac_output(evidence.mac_output, effective_mac),
        arp=parse_arp_output(evidence.arp_output, target_ip=target_ip),
        vlan=parse_vlan_output(evidence.vlan_output),
        terminal=terminal,
        observed_device=evidence.observed_device,
        observed_port=evidence.observed_port,
    )
