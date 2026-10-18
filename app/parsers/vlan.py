"""Bind per-interface VLAN fields to the intended port; never cross interface blocks."""
import re
from app.domain.models import ParsedVlan
from app.parsers.common import normalize_port

HEAD = re.compile(r"^\s*interface\s+((?:GigabitEthernet|GE|XGigabitEthernet|Eth-Trunk)[\w/ .-]+?)\s*$", re.I | re.M)

def parse_vlan_output(text: str, target_port: str | None = None) -> ParsedVlan:
    if not text.strip():
        return ParsedVlan()
    blocks=list(HEAD.finditer(text))
    port=None
    if blocks:
        options=[]
        for i,m in enumerate(blocks):
            end=blocks[i+1].start() if i+1<len(blocks) else len(text)
            options.append((m.group(1).strip(), text[m.end():end]))
        if target_port:
            options=[b for b in options if normalize_port(b[0])==normalize_port(target_port)]
        if len(options)!=1:
            return ParsedVlan(parse_status='ambiguous' if len(options)>1 else 'failed')
        port, text=options[0]
    elif target_port:
        # A single interface-configuration fragment is valid if scope is provided externally.
        port=target_port
    link=re.search(r"^\s*port\s+link-type\s+(access|trunk|hybrid)\b",text,re.I|re.M)
    access=re.search(r"^\s*port\s+default\s+vlan\s+(\d+)\b",text,re.I|re.M)
    trunk=re.search(r"^\s*port\s+trunk\s+allow-pass\s+vlan\s+([^\r\n]+)",text,re.I|re.M)
    description=re.search(r"^\s*description\s+(.+)$",text,re.I|re.M)
    shut=re.search(r"^\s*shutdown\s*$",text,re.I|re.M)
    unshut=re.search(r"^\s*undo\s+shutdown\s*$",text,re.I|re.M)
    recognized=any((link,access,trunk,shut,unshut))
    if not recognized:
        return ParsedVlan(port=port,parse_status='failed')
    return ParsedVlan(link_type=link.group(1).lower() if link else None,
                      access_vlan=int(access.group(1)) if access else None,
                      trunk_vlans=[int(v) for v in re.findall(r"\b\d{1,4}\b",trunk.group(1))] if trunk else [],
                      interface_shutdown=True if shut else False if unshut else None,
                      description=description.group(1).strip() if description else None,
                      port=port, parse_status='success')
