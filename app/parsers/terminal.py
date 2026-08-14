import re

from app.domain.models import ParsedTerminal
from app.parsers.common import normalize_mac


def _find_ip_after(label_pattern: str, text: str) -> str | None:
    match = re.search(r"(?:" + label_pattern + r")[^\r\n:]*[:：]\s*([0-9a-fA-F:.]+)", text, re.IGNORECASE)
    return match.group(1) if match else None


def parse_terminal_output(text: str) -> ParsedTerminal:
    if not text.strip():
        return ParsedTerminal()

    ip_value = _find_ip_after(r"IPv4(?: Address)?|IPv4 地址", text)
    mask = _find_ip_after(r"Subnet Mask|子网掩码", text)
    gateway = _find_ip_after(r"Default Gateway|默认网关", text)

    dns_servers = re.findall(
        r"(?:DNS Servers?|DNS 服务器)[^\r\n:]*[:：]\s*([0-9a-fA-F:.]+)",
        text,
        flags=re.IGNORECASE,
    )
    mac_match = re.search(
        r"(?:Physical Address|物理地址)[^\r\n:]*[:：]\s*([0-9a-fA-F:-]{12,20})",
        text,
        flags=re.IGNORECASE,
    )

    ping_success = None
    if re.search(r"Reply from|来自 .* 的回复|0%\s*loss|丢失\s*=\s*0", text, re.IGNORECASE):
        ping_success = True
    elif re.search(r"Request timed out|请求超时|100%\s*loss|无法访问目标主机", text, re.IGNORECASE):
        ping_success = False

    dns_success = None
    if re.search(r"^\s*(?:Address|地址):\s*[0-9a-fA-F:.]+", text, re.IGNORECASE | re.MULTILINE):
        dns_success = True
    elif re.search(r"Non-existent domain|server failed|timed out|找不到|超时", text, re.IGNORECASE):
        dns_success = False

    return ParsedTerminal(
        ip_address=ip_value,
        subnet_mask=mask,
        gateway=gateway,
        dns_servers=dns_servers,
        mac_address=normalize_mac(mac_match.group(1)) if mac_match else None,
        ping_success=ping_success,
        dns_success=dns_success,
    )
