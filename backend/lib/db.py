"""Shared Mongo handle — import `client`/`db` from here (server.py, routers, seed.py)."""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, DESCENDING, IndexModel

load_dotenv(Path(__file__).parent.parent / ".env")


def _env(*names: str) -> str:
    """First non-empty variable. MONGODB_URI / MONGODB_APP_DATABASE are the backend/.env names (shared with
    app/core/config.py); MONGO_URL / DB_NAME are the older names the hosted deployment still injects."""
    for name in names:
        if os.environ.get(name):
            return os.environ[name]
    raise RuntimeError(f"Set {names[0]} in backend/.env")


mongo_url = _env("MONGODB_URI", "MONGO_URL")
client = AsyncIOMotorClient(mongo_url)
db = client[_env("MONGODB_APP_DATABASE", "DB_NAME")]  # application DB: users, sessions, audit, analyst history

logger = logging.getLogger(__name__)

# One entry per collection: every field a route filters, sorts, or dedupes on. Applied by ensure_indexes() at startup.
INDEXES: dict[str, list[IndexModel]] = {
    "status_checks": [IndexModel([("timestamp", DESCENDING)], name="timestamp_desc")],
    "analyst_messages": [IndexModel([("session_id", ASCENDING), ("created_at", ASCENDING)], name="session_created")],
    "users": [IndexModel([("user_id", ASCENDING)], name="user_id_unique", unique=True), IndexModel([("email", ASCENDING)], name="email_unique", unique=True)],
    "user_sessions": [IndexModel([("session_token", ASCENDING)], name="session_token_unique", unique=True), IndexModel([("expires_at", ASCENDING)], name="expires_at"), IndexModel([("user_id", ASCENDING)], name="user_id")],
    "audit_events": [IndexModel([("created_at", DESCENDING)], name="created_desc"), IndexModel([("actor_user_id", ASCENDING), ("created_at", DESCENDING)], name="actor_created")],
}


async def ensure_indexes() -> None:
    for collection, models in INDEXES.items():
        for model in models:  # one at a time so a bad spec skips only itself
            try:
                await db[collection].create_indexes([model])
            except Exception as exc:  # never block boot on an index; the log line names what to fix
                logger.error("ensure_indexes(%s.%s): %s", collection, model.document["name"], exc)
