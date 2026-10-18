"""Conservative MAC table parser: parse failure != a verified missing MAC."""
import re
from app.domain.models import ParsedMac
from app.parsers.common import normalize_mac

MAC_RE = re.compile(r"(?<![0-9a-fA-F])(?:[0-9a-fA-F]{4}[-:.]){2}[0-9a-fA-F]{4}(?![0-9a-fA-F])|(?<![0-9a-fA-F])(?:[0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}(?![0-9a-fA-F])")
PORT_RE = re.compile(r"\b(?:GigabitEthernet|GE|XGigabitEthernet|Eth-Trunk)[\w/.-]+\b", re.I)
EMPTY_RE = re.compile(r"(?:total\s+(?:mac\s+)?entries?\s*[:=]\s*0\b|0\s+(?:mac\s+)?entries?\b|no\s+mac\s+(?:address|entry)|没有(?:匹配|找到).*mac)", re.I)


def parse_mac_output(text: str, target_mac: str | None = None) -> ParsedMac:
    wanted = normalize_mac(target_mac)
    if not text.strip():
        return ParsedMac(target_mac=wanted)
    entries = []
    for line in text.splitlines():
        match = MAC_RE.search(line)
        if not match:
            continue
        port = PORT_RE.search(line)
        other = line[:match.start()] + ' ' + line[match.end():]
        vlan = re.search(r"(?<!\d)([1-9]\d{0,3})(?!\d)", other)
        typ = re.search(r"\b(dynamic|static|blackhole|sticky)\b", line, re.I)
        entries.append(dict(mac=normalize_mac(match.group()), vlan=int(vlan.group(1)) if vlan else None,
                            port=port.group() if port else None, type=typ.group().lower() if typ else None))
    if not entries and not EMPTY_RE.search(text):
        return ParsedMac(target_mac=wanted, parse_status='failed')
    matching = [e for e in entries if wanted and e['mac']==wanted]
    if not wanted and len(entries)==1:
        matching=[entries[0]]
    if len(matching)>1 and len({(e['vlan'],e['port']) for e in matching})>1:
        return ParsedMac(target_mac=wanted, total_entries=len(entries), parse_status='ambiguous')
    selected=matching[0] if matching else None
    return ParsedMac(target_found=(selected is not None) if wanted else (True if selected else None),
                     target_mac=wanted or (selected['mac'] if selected else None),
                     learned_port=selected['port'] if selected else None,
                     vlan=selected['vlan'] if selected else None,
                     entry_type=selected['type'] if selected else None,
                     total_entries=len(entries),parse_status='success')
