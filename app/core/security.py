from ipaddress import ip_address
from pathlib import Path


class SecurityError(ValueError):
    pass


def validate_demo_ip(value: str) -> str:
    """Only allow non-public addresses in the demonstration project."""
    parsed = ip_address(value)
    if not (parsed.is_private or parsed.is_loopback or parsed.is_link_local):
        raise SecurityError("演示系统仅允许私网、环回或链路本地地址")
    return str(parsed)


def safe_report_path(report_dir: Path, thread_id: str) -> Path:
    if not thread_id or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for ch in thread_id):
        raise SecurityError("非法 thread_id")
    base = report_dir.resolve()
    target = (base / f"{thread_id}.md").resolve()
    if base not in target.parents:
        raise SecurityError("报告路径越界")
    return target
