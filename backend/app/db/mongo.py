import logging

from pymongo import MongoClient
from pymongo.errors import PyMongoError

from app.core.config import settings

# logging, not print(); server.py makes the console streams emoji-safe (a cp1252 console or redirected log).
logger = logging.getLogger(__name__)


class MongoDB:
    client: MongoClient | None = None
    cyclone_db = None
    app_db = None


mongodb = MongoDB()


def connect_to_mongodb():
    if mongodb.client is not None:
        return

    try:
        mongodb.client = MongoClient(
            settings.MONGODB_URI,
            serverSelectionTimeoutMS=5000,
        )

        # Verify that the MongoDB server/cluster is reachable
        mongodb.client.admin.command("ping")

        # Scientific / cyclone database
        mongodb.cyclone_db = mongodb.client[
            settings.MONGODB_CYCLONE_DATABASE
        ]

        # Application / authentication database
        mongodb.app_db = mongodb.client[
            settings.MONGODB_APP_DATABASE
        ]

        logger.info(
            "✅ MongoDB connected - cyclone DB: %s, app DB: %s",
            settings.MONGODB_CYCLONE_DATABASE,
            settings.MONGODB_APP_DATABASE,
        )

    except PyMongoError as exc:
        mongodb.client = None
        mongodb.cyclone_db = None
        mongodb.app_db = None

        logger.error("❌ MongoDB connection failed: %s", exc)
        raise


def close_mongodb():
    if mongodb.client is not None:
        mongodb.client.close()

    mongodb.client = None
    mongodb.cyclone_db = None
    mongodb.app_db = None

    logger.info("MongoDB connection closed")


def get_cyclone_database():
    if mongodb.cyclone_db is None:
        raise RuntimeError(
            "Cyclone database is not connected"
        )

    return mongodb.cyclone_db


def get_app_database():
    if mongodb.app_db is None:
        raise RuntimeError(
            "Application database is not connected"
        )

    return mongodb.app_db


def check_database_connection() -> bool:
    try:
        if mongodb.client is None:
            return False

        mongodb.client.admin.command("ping")
        return True

    except PyMongoError:
        return False