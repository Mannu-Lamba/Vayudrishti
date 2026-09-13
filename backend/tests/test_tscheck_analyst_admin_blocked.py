"""API-bearing check: analyst is blocked from all administration endpoints."""

import os

import httpx

API_URL = f"{os.environ.get('BACKEND_URL', 'http://localhost:8001')}/api"


def api_url(path: str = "") -> str:
    return f"{API_URL}{path}"


ANALYST_TOKEN = "test_session_analyst_2001"
HEADERS_ANALYST = {"Authorization": f"Bearer {ANALYST_TOKEN}"}


def test_analyst_forbidden_from_access_policy():
    resp = httpx.get(api_url("/admin/access-policy"), headers=HEADERS_ANALYST, timeout=30.0)
    assert resp.status_code == 403, resp.text


def test_analyst_forbidden_from_users_list():
    resp = httpx.get(api_url("/admin/users"), headers=HEADERS_ANALYST, timeout=30.0)
    assert resp.status_code == 403, resp.text


def test_analyst_role_is_analyst_via_me():
    resp = httpx.get(api_url("/auth/me"), headers=HEADERS_ANALYST, timeout=30.0)
    assert resp.status_code == 200, resp.text
    assert resp.json().get("role") == "analyst", resp.json()
