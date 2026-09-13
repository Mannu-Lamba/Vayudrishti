"""API-bearing check: Session Center lists the admin's devices (read-only).

The actual revoke+recreate flow is exercised end-to-end in the browser check
`session-center-revoke` (which also validates the UI). This test only asserts
the GET /api/sessions contract so we never double-revoke the seeded mobile
session from two different lanes.
"""

import os

import httpx

API_URL = f"{os.environ.get('BACKEND_URL', 'http://localhost:8001')}/api"


def api_url(path: str = "") -> str:
    return f"{API_URL}{path}"


ADMIN_TOKEN = "test_session_1788885621_agent"
HEADERS_ADMIN = {"Authorization": f"Bearer {ADMIN_TOKEN}"}


def test_admin_sessions_lists_two_devices_with_current_flag():
    resp = httpx.get(
        api_url("/sessions"),
        headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
        timeout=30.0,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    sessions = body["sessions"]
    assert len(sessions) == 2, f"expected 2 sessions, got {sessions}"

    by_id = {s["session_id"]: s for s in sessions}
    assert "sess_test_admin_primary" in by_id
    assert "sess_test_admin_mobile" in by_id

    primary = by_id["sess_test_admin_primary"]
    mobile = by_id["sess_test_admin_mobile"]

    assert primary["current"] is True, primary
    assert primary["browser"] == "Chrome" and primary["os"] == "Linux"

    assert mobile["current"] is False, mobile
    assert mobile["browser"] == "Safari" and mobile["os"] == "iOS"


def test_sessions_requires_auth():
    resp = httpx.get(api_url("/sessions"), timeout=30.0)
    assert resp.status_code == 401, resp.text
