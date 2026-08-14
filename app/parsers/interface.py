import re

from app.domain.models import ParsedInterface
from app.parsers.common import parse_int


def parse_interface_output(text: str) -> ParsedInterface:
    if not text.strip():
        return ParsedInterface()

    status = None
    protocol = None
    port = None

    detailed = re.search(
        r"(?P<port>(?:GigabitEthernet|GE|XGigabitEthernet|Eth-Trunk)[\w/.-]+).*?"
        r"current state\s*:\s*(?P<status>UP|DOWN|Administratively DOWN).*?"
        r"Line protocol current state\s*:\s*(?P<protocol>UP|DOWN)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if detailed:
        port = detailed.group("port")
        status = detailed.group("status").upper()
        protocol = detailed.group("protocol").upper()
    else:
        brief = re.search(
            r"(?P<port>(?:GigabitEthernet|GE|XGigabitEthernet|Eth-Trunk)[\w/.-]+)\s+"
            r"(?P<status>up|down|adm(?:in)?down)\s+(?P<protocol>up|down)",
            text,
            flags=re.IGNORECASE,
        )
        if brief:
            port = brief.group("port")
            raw_status = brief.group("status").lower()
            status = "ADMINISTRATIVELY DOWN" if raw_status.startswith("adm") else raw_status.upper()
            protocol = brief.group("protocol").upper()

    return ParsedInterface(
        status=status,
        protocol_status=protocol,
        port=port,
        input_errors=parse_int(r"input\s+errors?\s*[:=]?\s*(\d+)", text),
        output_errors=parse_int(r"output\s+errors?\s*[:=]?\s*(\d+)", text),
        input_drops=parse_int(r"input\s+(?:drops?|discard)\s*[:=]?\s*(\d+)", text),
        output_drops=parse_int(r"output\s+(?:drops?|discard)\s*[:=]?\s*(\d+)", text),
    )
