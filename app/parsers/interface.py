"""Parse interface status without mixing two distinct interface sections."""
import re
from app.domain.models import ParsedInterface
from app.parsers.common import normalize_port, parse_int

NAME=r"(?:GigabitEthernet|GE|XGigabitEthernet|Eth-Trunk)[\w/.-]+"
DETAIL=re.compile(rf"(?P<port>{NAME})\s+current state\s*:\s*(?P<status>UP|DOWN|Administratively DOWN)",re.I)
BRIEF=re.compile(rf"(?P<port>{NAME})\s+(?P<status>up|down|adm(?:in)?down)\s+(?P<protocol>up|down)",re.I)
PROTOCOL=re.compile(r"Line protocol current state\s*:\s*(UP|DOWN)",re.I)

def parse_interface_output(text: str,target_port: str|None=None)->ParsedInterface:
    if not text.strip():return ParsedInterface()
    matches=list(DETAIL.finditer(text)); detailed=bool(matches)
    if not matches:matches=list(BRIEF.finditer(text))
    if target_port:matches=[m for m in matches if normalize_port(m.group('port'))==normalize_port(target_port)]
    if len(matches)!=1:
        return ParsedInterface(parse_status='ambiguous' if len(matches)>1 else 'failed')
    m=matches[0]
    portion=text[m.end():matches[1].start()] if False else text[m.end():]
    # A detailed line is only trusted for protocol state until the next interface block.
    if detailed:
        next_entry=DETAIL.search(text,m.end())
        if next_entry:portion=text[m.end():next_entry.start()]
        pm=PROTOCOL.search(portion)
        if not pm:return ParsedInterface(port=m.group('port'),parse_status='failed')
        protocol=pm.group(1).upper()
    else:protocol=m.group('protocol').upper()
    raw=m.group('status').lower()
    status='ADMINISTRATIVELY DOWN' if raw.startswith('adm') else raw.upper()
    return ParsedInterface(status=status,protocol_status=protocol,port=m.group('port'),
        input_errors=parse_int(r"input\s+errors?\s*[:=]?\s*(\d+)",portion),
        output_errors=parse_int(r"output\s+errors?\s*[:=]?\s*(\d+)",portion),
        input_drops=parse_int(r"input\s+(?:drops?|discard)\s*[:=]?\s*(\d+)",portion),
        output_drops=parse_int(r"output\s+(?:drops?|discard)\s*[:=]?\s*(\d+)",portion),
        parse_status='success')
