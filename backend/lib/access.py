"""Domain access policy: which email domains may enter the console. Seeded once from ALLOWED_EMAIL_DOMAINS."""

import os

from lib.db import db
from models.auth import AccessPolicy, utc_now


POLICY_ID = "default"


def _env_domains() -> list[str]:
    raw = os.environ.get("ALLOWED_EMAIL_DOMAINS", "")
    return sorted({part.strip().lower().lstrip("@") for part in raw.split(",") if part.strip()})


def email_domain(email: str) -> str:
    return email.rsplit("@", 1)[-1].lower() if "@" in email else ""


def _to_policy(document: dict) -> AccessPolicy:
    domains = sorted(document.get("allowed_domains", []))
    return AccessPolicy(allowed_domains=domains, open_access=not domains, updated_at=document.get("updated_at"), updated_by=document.get("updated_by"))


async def get_access_policy() -> AccessPolicy:
    document = await db.access_policy.find_one({"_id": POLICY_ID})
    if document is None:
        document = {"_id": POLICY_ID, "allowed_domains": _env_domains(), "updated_at": utc_now(), "updated_by": "environment"}
        await db.access_policy.update_one({"_id": POLICY_ID}, {"$setOnInsert": document}, upsert=True)
    return _to_policy(document)


async def save_domains(domains: list[str], updated_by: str) -> AccessPolicy:
    document = {"allowed_domains": sorted(set(domains)), "updated_at": utc_now(), "updated_by": updated_by}
    await db.access_policy.update_one({"_id": POLICY_ID}, {"$set": document}, upsert=True)
    return _to_policy(document)


async def is_email_allowed(email: str) -> bool:
    policy = await get_access_policy()
    return policy.open_access or email_domain(email) in policy.allowed_domains
