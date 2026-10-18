import re

from app.domain.models import ParsedArp
from app.parsers.common import normalize_mac


def parse_arp_output(text: str, target_ip: str | None = None) -> ParsedArp:
    if not text.strip():
        return ParsedArp(ip_address=target_ip)

    entries: list[dict] = []
    for line in text.splitlines():
        ip_match = re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", line)
        mac_match = re.search(
            r"(?:[0-9a-fA-F]{4}[-:.]){2}[0-9a-fA-F]{4}|(?:[0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}",
            line,
        )
        if not ip_match or not mac_match:
            continue
        port_match = re.search(
            r"\b((?:GigabitEthernet|GE|XGigabitEthernet|Eth-Trunk|Vlanif)[\w/.-]+)\b",
            line,
            flags=re.IGNORECASE,
        )
        type_match = re.search(r"\b(dynamic|static|reachable|stale|incomplete)\b", line, re.IGNORECASE)
        entries.append({
            "ip": ip_match.group(0),
            "mac": normalize_mac(mac_match.group(0)),
            "interface": port_match.group(1) if port_match else None,
            "type": type_match.group(1).lower() if type_match else None,
        })

    if not entries and not re.search(r"(?:total\s+(?:arp\s+)?entries?\s*[:=]\s*0|0\s+entries|no\s+arp\s+entry)", text, re.I):
        return ParsedArp(ip_address=target_ip, parse_status="failed")

    selected = next((entry for entry in entries if target_ip and entry["ip"] == target_ip), None)
    if not target_ip and len(entries) == 1:
        selected = entries[0]

    return ParsedArp(
        target_found=(selected is not None) if target_ip else (True if selected else None),
        ip_address=target_ip or (selected["ip"] if selected else None),
        mac_address=selected["mac"] if selected else None,
        interface=selected["interface"] if selected else None,
        entry_type=selected["type"] if selected else None,
        total_entries=len(entries),
        parse_status="success",
    )
