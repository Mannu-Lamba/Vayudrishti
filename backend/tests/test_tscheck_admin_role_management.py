"""API-bearing check: admin role management (promote/demote, self-patch guard)."""

import contextlib
import fcntl
import os

import httpx

API_URL = f"{os.environ.get('BACKEND_URL', 'http://localhost:8001')}/api"


def api_url(path: str = "") -> str:
    return f"{API_URL}{path}"


@contextlib.contextmanager
def role_mutation_lock():
    """Cross-process lock guarding the shared analyst-role critical section
    (see test_tscheck_audit_events.py for the counterpart)."""
    with open("/tmp/tscheck_role_mutation.lock", "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


ADMIN_TOKEN = "test_session_1788885621_agent"
ADMIN_USER_ID = "test-user-1788885621"
ANALYST_TOKEN = "test_session_analyst_2001"
ANALYST_USER_ID = "test-analyst-2001"
HEADERS_ADMIN = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
HEADERS_ANALYST = {"Authorization": f"Bearer {ANALYST_TOKEN}"}


def test_admin_users_list_shape():
    resp = httpx.get(api_url("/admin/users"), headers=HEADERS_ADMIN, timeout=30.0)
    assert resp.status_code == 200, resp.text
    users = resp.json()
    by_id = {u["user_id"]: u for u in users}
    assert ADMIN_USER_ID in by_id
    assert ANALYST_USER_ID in by_id
    assert "role" in by_id[ADMIN_USER_ID]
    assert "active_sessions" in by_id[ADMIN_USER_ID]


def test_promote_and_restore_analyst_role():
    with role_mutation_lock():
        try:
            promote = httpx.patch(
                api_url(f"/admin/users/{ANALYST_USER_ID}/role"),
                headers=HEADERS_ADMIN,
                json={"role": "admin"},
                timeout=30.0,
            )
            assert promote.status_code == 200, promote.text
            assert promote.json()["role"] == "admin", promote.json()
        finally:
            restore = httpx.patch(
                api_url(f"/admin/users/{ANALYST_USER_ID}/role"),
                headers=HEADERS_ADMIN,
                json={"role": "analyst"},
                timeout=30.0,
            )
            assert restore.status_code == 200, restore.text
            assert restore.json()["role"] == "analyst", restore.json()


def test_admin_cannot_patch_own_role():
    resp = httpx.patch(
        api_url(f"/admin/users/{ADMIN_USER_ID}/role"),
        headers=HEADERS_ADMIN,
        json={"role": "analyst"},
        timeout=30.0,
    )
    assert resp.status_code == 400, resp.text


def test_analyst_cannot_patch_roles():
    resp = httpx.patch(
        api_url(f"/admin/users/{ADMIN_USER_ID}/role"),
        headers=HEADERS_ANALYST,
        json={"role": "analyst"},
        timeout=30.0,
    )
    assert resp.status_code == 403, resp.text
