import re


_MAC_CLEAN_RE = re.compile(r"[^0-9a-fA-F]")


def normalize_mac(value: str | None) -> str | None:
    if not value:
        return None
    compact = _MAC_CLEAN_RE.sub("", value).lower()
    if len(compact) != 12:
        return None
    return ":".join(compact[i : i + 2] for i in range(0, 12, 2))


def normalize_port(value: str | None) -> str | None:
    if not value:
        return None
    return re.sub(r"\s+", "", value).lower().replace("gigabitethernet", "ge")


def parse_int(pattern: str, text: str) -> int | None:
    match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
    return int(match.group(1)) if match else None
