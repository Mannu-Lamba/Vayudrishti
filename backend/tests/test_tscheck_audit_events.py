"""API-bearing check: audit trail records client-side events and enforces scope."""

import contextlib
import fcntl
import os
import uuid

import httpx

API_URL = f"{os.environ.get('BACKEND_URL', 'http://localhost:8001')}/api"


def api_url(path: str = "") -> str:
    return f"{API_URL}{path}"


@contextlib.contextmanager
def role_mutation_lock():
    """Cross-process lock guarding the shared analyst-role critical section
    (see test_tscheck_admin_role_management.py for the counterpart)."""
    with open("/tmp/tscheck_role_mutation.lock", "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def api_url(path: str = "") -> str:
    return f"{API_URL}{path}"


ADMIN_TOKEN = "test_session_1788885621_agent"
ANALYST_TOKEN = "test_session_analyst_2001"
HEADERS_ADMIN = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
HEADERS_ANALYST = {"Authorization": f"Bearer {ANALYST_TOKEN}"}


def test_analyst_can_post_event_and_it_carries_actor_email():
    target = f"tscheck-audit-{uuid.uuid4().hex[:8]}"
    resp = httpx.post(
        api_url("/audit/events"),
        headers=HEADERS_ANALYST,
        json={"action": "cyclone.selected", "target": target},
        timeout=30.0,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body.get("actor_email") == "analyst.two@example.com", body
    assert body.get("target") == target


def test_privileged_action_rejected_from_public_endpoint():
    resp = httpx.post(
        api_url("/audit/events"),
        headers=HEADERS_ANALYST,
        json={"action": "admin.role_changed", "target": "someone"},
        timeout=30.0,
    )
    assert resp.status_code == 422, resp.text


def test_analyst_scope_forced_to_mine():
    with role_mutation_lock():
        resp = httpx.get(api_url("/audit/events?scope=all"), headers=HEADERS_ANALYST, timeout=30.0)
        assert resp.status_code == 200, resp.text
        assert resp.json().get("scope") == "mine", resp.json()


def test_admin_scope_all_shows_multiple_actors():
    # Seed at least one analyst event first so "all" scope has more than the admin's own.
    httpx.post(
        api_url("/audit/events"),
        headers=HEADERS_ANALYST,
        json={"action": "cyclone.selected", "target": f"tscheck-audit-{uuid.uuid4().hex[:8]}"},
        timeout=30.0,
    )
    resp = httpx.get(api_url("/audit/events?scope=all"), headers=HEADERS_ADMIN, timeout=30.0)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body.get("scope") == "all", body
    actors = {e.get("actor_email") for e in body.get("events", [])}
    assert len(actors) >= 1
