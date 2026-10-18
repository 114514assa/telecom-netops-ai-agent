"""Single-tenant demonstration bearer tokens. NOT enterprise IAM or production RBAC."""
import secrets
from fastapi import Header, HTTPException
from app.core.config import get_settings


def _authorized(provided: str | None, candidates: list[str]) -> bool:
    return bool(provided) and any(secrets.compare_digest(provided, c) for c in candidates if c)


def require_reader(x_demo_token: str | None = Header(default=None)) -> None:
    settings=get_settings()
    if not settings.demo_auth_enabled:
        if settings.app_env != 'development':
            raise HTTPException(503,'Non-development environment requires DEMO_AUTH_ENABLED=true')
        return
    if not _authorized(x_demo_token,[settings.demo_reader_token,settings.demo_approver_token]):
        raise HTTPException(401,'Valid read token required')


def require_approver(x_demo_token: str | None = Header(default=None)) -> None:
    settings=get_settings()
    if not settings.demo_auth_enabled:
        if settings.app_env != 'development':
            raise HTTPException(503,'Non-development environment requires DEMO_AUTH_ENABLED=true')
        return
    if not _authorized(x_demo_token,[settings.demo_approver_token]):
        raise HTTPException(403,'Approver token required')
