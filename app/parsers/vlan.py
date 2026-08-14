import re

from app.domain.models import ParsedVlan


def parse_vlan_output(text: str) -> ParsedVlan:
    if not text.strip():
        return ParsedVlan()

    link_match = re.search(r"port\s+link-type\s+(access|trunk|hybrid)", text, re.IGNORECASE)
    access_match = re.search(r"port\s+default\s+vlan\s+(\d+)", text, re.IGNORECASE)
    trunk_match = re.search(r"port\s+trunk\s+allow-pass\s+vlan\s+([^\r\n]+)", text, re.IGNORECASE)
    description_match = re.search(r"^\s*description\s+(.+)$", text, re.IGNORECASE | re.MULTILINE)

    trunk_vlans: list[int] = []
    if trunk_match:
        trunk_vlans = [int(value) for value in re.findall(r"\b\d{1,4}\b", trunk_match.group(1))]

    shutdown = None
    if re.search(r"^\s*shutdown\s*$", text, re.IGNORECASE | re.MULTILINE):
        shutdown = True
    elif re.search(r"^\s*undo\s+shutdown\s*$", text, re.IGNORECASE | re.MULTILINE):
        shutdown = False

    return ParsedVlan(
        link_type=link_match.group(1).lower() if link_match else None,
        access_vlan=int(access_match.group(1)) if access_match else None,
        trunk_vlans=trunk_vlans,
        interface_shutdown=shutdown,
        description=description_match.group(1).strip() if description_match else None,
    )
