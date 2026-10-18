"""Identity handling in DEMO mode; production SSO remains out of scope."""
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
import app.core.auth as auth


def test_demo_role_separation(monkeypatch):
    monkeypatch.setattr(auth,'get_settings',lambda:SimpleNamespace(
        demo_auth_enabled=True,app_env='development',
        demo_reader_token='reader-test-token',demo_approver_token='approver-test-token'))
    auth.require_reader('reader-test-token')
    auth.require_reader('approver-test-token')
    auth.require_approver('approver-test-token')
    with pytest.raises(HTTPException) as exc:auth.require_approver('reader-test-token')
    assert exc.value.status_code==403
    with pytest.raises(HTTPException) as exc:auth.require_reader('bad-token')
    assert exc.value.status_code==401


def test_non_development_cannot_disable_auth(monkeypatch):
    monkeypatch.setattr(auth,'get_settings',lambda:SimpleNamespace(
        demo_auth_enabled=False,app_env='production',
        demo_reader_token='',demo_approver_token=''))
    with pytest.raises(HTTPException) as exc:auth.require_reader(None)
    assert exc.value.status_code==503
