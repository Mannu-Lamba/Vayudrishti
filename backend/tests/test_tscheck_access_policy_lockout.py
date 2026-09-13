"""API-bearing check: domain allowlist add/remove with lockout guards.

Starts from open access (allowed_domains empty), adds a domain, verifies the
admin's own domain (example.com) gets auto-included, verifies the lockout
guard rejects removing the last domain that keeps the admin in, verifies
invalid domain format is rejected, and finally restores the policy to fully
open access so later tests/iterations start clean.
"""

import os

import httpx

API_URL = f"{os.environ.get('BACKEND_URL', 'http://localhost:8001')}/api"


def api_url(path: str = "") -> str:
    return f"{API_URL}{path}"


ADMIN_TOKEN = "test_session_1788885621_agent"
ANALYST_TOKEN = "test_session_analyst_2001"
HEADERS_ADMIN = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
HEADERS_ANALYST = {"Authorization": f"Bearer {ANALYST_TOKEN}"}


def _get_policy():
    return httpx.get(api_url("/admin/access-policy"), headers=HEADERS_ADMIN, timeout=30.0)


def _restore_open_access():
    """Best-effort: delete every domain currently on the policy."""
    resp = _get_policy()
    if resp.status_code != 200:
        return
    for domain in list(resp.json().get("allowed_domains", [])):
        httpx.delete(
            api_url(f"/admin/access-policy/domains/{domain}"),
            headers=HEADERS_ADMIN,
            timeout=30.0,
        )


def test_domain_allowlist_lockout_guards():
    # Sanity: confirm starting state is open access (per seed facts).
    start = _get_policy()
    assert start.status_code == 200, start.text
    assert start.json()["open_access"] is True

    try:
        # Add a new domain -> admin's own domain (example.com) is auto-included.
        add = httpx.post(
            api_url("/admin/access-policy/domains"),
            headers=HEADERS_ADMIN,
            json={"domain": "sih-team.ac.in"},
            timeout=30.0,
        )
        assert add.status_code == 200, add.text
        domains = set(add.json()["allowed_domains"])
        assert "sih-team.ac.in" in domains, domains
        assert "example.com" in domains, domains

        # Admin must still be able to authenticate under the new restricted policy.
        me = httpx.get(api_url("/auth/me"), headers=HEADERS_ADMIN, timeout=30.0)
        assert me.status_code == 200, me.text

        # Removing the admin's OWN domain (example.com) is guarded even though
        # sih-team.ac.in still remains -> would lock the admin out.
        lockout = httpx.delete(
            api_url("/admin/access-policy/domains/example.com"),
            headers=HEADERS_ADMIN,
            timeout=30.0,
        )
        assert lockout.status_code == 400, lockout.text
        assert "lock" in lockout.json().get("detail", "").lower()

        # Invalid domain format is rejected.
        bad = httpx.post(
            api_url("/admin/access-policy/domains"),
            headers=HEADERS_ADMIN,
            json={"domain": "not a domain"},
            timeout=30.0,
        )
        assert bad.status_code == 422, bad.text

        # Analyst cannot touch the policy at all.
        forbidden = httpx.get(api_url("/admin/access-policy"), headers=HEADERS_ANALYST, timeout=30.0)
        assert forbidden.status_code == 403, forbidden.text

        # Proper unwind order: remove sih-team.ac.in first (200), then example.com (200).
        remove_first = httpx.delete(
            api_url("/admin/access-policy/domains/sih-team.ac.in"),
            headers=HEADERS_ADMIN,
            timeout=30.0,
        )
        assert remove_first.status_code == 200, remove_first.text
        assert "sih-team.ac.in" not in remove_first.json()["allowed_domains"]

        remove_last = httpx.delete(
            api_url("/admin/access-policy/domains/example.com"),
            headers=HEADERS_ADMIN,
            timeout=30.0,
        )
        assert remove_last.status_code == 200, remove_last.text
        assert remove_last.json()["open_access"] is True
    finally:
        _restore_open_access()
        final = _get_policy()
        assert final.status_code == 200
        assert final.json()["open_access"] is True, final.json()
