"""API-bearing check: unauthenticated requests are rejected on protected endpoints."""

import os

import httpx

API_URL = f"{os.environ.get('BACKEND_URL', 'http://localhost:8001')}/api"


def api_url(path: str = "") -> str:
    return f"{API_URL}{path}"


def test_sessions_requires_auth():
    resp = httpx.get(api_url("/sessions"), timeout=30.0)
    assert resp.status_code == 401, resp.text


def test_audit_events_requires_auth():
    resp = httpx.get(api_url("/audit/events"), timeout=30.0)
    assert resp.status_code == 401, resp.text


def test_admin_users_requires_auth():
    resp = httpx.get(api_url("/admin/users"), timeout=30.0)
    assert resp.status_code == 401, resp.text
