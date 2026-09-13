from fastapi import APIRouter

from app.db.mongo import (
    check_database_connection,
    get_cyclone_database,
    get_app_database,
)

router = APIRouter(
    prefix="/api/database",
    tags=["Database"],
)


@router.get("/health")
def database_health():

    connected = check_database_connection()

    if not connected:
        return {
            "status": "error",
            "mongodb": False,
        }

    cyclone_db = get_cyclone_database()
    app_db = get_app_database()

    return {
        "status": "ok",
        "mongodb": True,
        "databases": {
            "cyclone_database": {
                "connected": cyclone_db is not None,
            },
            "vayudrishti_local": {
                "connected": app_db is not None,
            },
        },
    }