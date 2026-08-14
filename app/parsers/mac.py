import re

from app.domain.models import ParsedMac
from app.parsers.common import normalize_mac


_MAC_PATTERN = re.compile(
    r"(?P<mac>(?:[0-9a-fA-F]{4}[-:.]){2}[0-9a-fA-F]{4}|(?:[0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2})"
)


def parse_mac_output(text: str, target_mac: str | None = None) -> ParsedMac:
    if not text.strip():
        return ParsedMac(target_mac=normalize_mac(target_mac))

    wanted = normalize_mac(target_mac)
    entries: list[dict] = []
    for line in text.splitlines():
        match = _MAC_PATTERN.search(line)
        if not match:
            continue
        normalized = normalize_mac(match.group("mac"))
        vlan_match = re.search(r"\b(\d{1,4})\b", line[: match.start()] + " " + line[match.end() :])
        port_match = re.search(
            r"\b((?:GigabitEthernet|GE|XGigabitEthernet|Eth-Trunk)[\w/.-]+)\b",
            line,
            flags=re.IGNORECASE,
        )
        type_match = re.search(r"\b(dynamic|static|blackhole|sticky)\b", line, flags=re.IGNORECASE)
        entries.append(
            {
                "mac": normalized,
                "vlan": int(vlan_match.group(1)) if vlan_match else None,
                "port": port_match.group(1) if port_match else None,
                "type": type_match.group(1).lower() if type_match else None,
            }
        )

    selected = None
    if wanted:
        selected = next((entry for entry in entries if entry["mac"] == wanted), None)
    elif len(entries) == 1:
        selected = entries[0]

    return ParsedMac(
        target_found=(selected is not None) if wanted else (True if selected else None),
        target_mac=wanted or (selected["mac"] if selected else None),
        learned_port=selected["port"] if selected else None,
        vlan=selected["vlan"] if selected else None,
        entry_type=selected["type"] if selected else None,
        total_entries=len(entries),
    )
