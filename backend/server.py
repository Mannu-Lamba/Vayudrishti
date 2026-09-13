import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, APIRouter, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
import os
import logging
import sys
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List
from urllib.parse import urlparse
import uuid
from datetime import datetime


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

for _stream in (sys.stdout, sys.stderr):  # the ✅/❌ startup lines must not crash a cp1252 console or a redirected log
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(errors="backslashreplace")

# MongoDB connection
from lib.db import client, db, ensure_indexes
from app.db.mongo import check_database_connection, close_mongodb, connect_to_mongodb
from routers.admin import router as admin_router
from routers.analyst import router as analyst_router
from routers.audit import router as audit_router
from routers.auth import router as auth_router
from routers.cyclones import router as cyclones_router
from routers.database import router as database_router
from routers.registry import events_router, regions_router, satellite_router
from routers.health import router as health_router
from routers.ml import router as ml_router
from routers.sessions import router as sessions_router
from models.ml import ErrorDetail, ErrorResponse
from repositories.cyclone_repository import load_cyclone_data, repository
from services.ml_registry import load_models, registry


def connect_databases() -> None:
    """cyclone_database + the app DB (app/db/mongo.py). A MongoDB that is down is logged, not fatal: the ML routes
    work without it and GET /api/database/health reports the failure."""
    try:
        connect_to_mongodb()
    except Exception:
        logging.getLogger(__name__).exception("MongoDB not connected (MONGODB_URI in backend/.env)")


def log_startup_summary() -> None:
    """One line that shows at a glance whether the API started complete or degraded (a missing model or database
    degrades it; the API still starts, and /api/health and /api/ml/status report the same)."""
    slots = (registry.identification, registry.classification, registry.prediction)
    unavailable = [f"{slot.key} ({slot.error_code or 'not loaded'})" for slot in slots if not slot.ready]
    mongo_ok = check_database_connection()
    parts = [
        f"MongoDB {'connected' if mongo_ok else 'NOT connected'}",
        f"models ready: {', '.join(slot.key for slot in slots if slot.ready) or 'none'}",
        f"held-out observations: {len(repository.list_storms())} storms" if repository.ready else "held-out observations NOT loaded",
    ]
    if unavailable:
        parts.append(f"unavailable: {', '.join(unavailable)}")
    complete = mongo_ok and not unavailable and repository.ready
    logging.getLogger("startup").log(logging.INFO if complete else logging.WARNING, "%s Startup %s: %s",
                                     "✅" if complete else "⚠️", "complete" if complete else "degraded", " · ".join(parts))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. database → 2-6. model registry (load + validate each model once) → observations → 7. report
    app.state.index_task = asyncio.create_task(ensure_indexes())  # background: a big index build must not block boot
    await asyncio.to_thread(connect_databases)  # blocking ping, up to 5 s when MongoDB is down
    await asyncio.to_thread(load_models)  # ML models load once here, never per request; failures are reported, not raised
    await asyncio.to_thread(load_cyclone_data)  # observation histories the prediction service reads (repository)
    log_startup_summary()
    yield
    client.close()
    close_mongodb()


app = FastAPI(
    title="VayuDrishti API",
    version=os.environ.get("APP_VERSION", "1.0"),
    description="Tropical cyclone identification, IMD intensity classification and track / intensity forecasting (PS-70). "
                "AI-assisted decision support — not an official forecast; refer to IMD / the responsible RSMC for warnings.",
    lifespan=lifespan,
)

# The ML / prediction routes answer malformed requests with their own {success, status, error: {code, message}}
# contract. Every other route keeps FastAPI's default {detail: [...]} body, which the auth screens read.
ML_CONTRACT_PREFIXES = ("/api/ml/", "/api/cyclones", "/api/regions", "/api/satellite", "/api/events")


def _validation_message(exc: RequestValidationError) -> str:
    parts = []
    for err in exc.errors()[:3]:
        if err.get("type") == "json_invalid":
            parts.append("the request body is not valid JSON")
            continue
        field = ".".join(str(p) for p in err.get("loc", ()) if p not in ("body", "query", "path"))
        message = str(err.get("msg", "invalid value")).removeprefix("Value error, ")
        parts.append(f"{field}: {message}" if field else message)
    return f"Invalid request: {'; '.join(parts)}."


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    if not request.url.path.startswith(ML_CONTRACT_PREFIXES):
        return await request_validation_exception_handler(request, exc)
    body = ErrorResponse(error=ErrorDetail(code="VALIDATION_ERROR", message=_validation_message(exc)))
    return JSONResponse(status_code=422, content=body.model_dump())

api_router = APIRouter(prefix="/api")
api_router.include_router(analyst_router, prefix="/analyst")
api_router.include_router(auth_router, prefix="/auth")
api_router.include_router(sessions_router, prefix="/sessions")
api_router.include_router(audit_router, prefix="/audit")
api_router.include_router(admin_router, prefix="/admin")
api_router.include_router(ml_router, prefix="/ml")
api_router.include_router(cyclones_router, prefix="/cyclones")
api_router.include_router(regions_router, prefix="/regions")
api_router.include_router(satellite_router, prefix="/satellite")
api_router.include_router(events_router)
api_router.include_router(health_router)


# Define Models
class StatusCheck(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class StatusCheckCreate(BaseModel):
    client_name: str

# Add your routes to the router instead of directly to app
@api_router.get("/")
async def root():
    return {"message": "Hello World"}

@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_dict = input.model_dump()
    status_obj = StatusCheck(**status_dict)
    _ = await db.status_checks.insert_one(status_obj.model_dump())
    return status_obj

@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    status_checks = await db.status_checks.find().to_list(1000)
    return [StatusCheck(**status_check) for status_check in status_checks]

# Cross-origin browser access. The default frontend setup is same-origin (VITE_API_BASE_URL=/api through the
# Vite dev proxy or the ingress), so this only matters when the frontend calls the API on another origin.
LOCAL_DEV_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:5173", "http://127.0.0.1:5173"]


def _is_local(origin: str) -> bool:
    return urlparse(origin).hostname in ("localhost", "127.0.0.1")


def cors_origins() -> list[str]:
    """CORS_ORIGINS (comma-separated) plus FRONTEND_URL. While every configured origin is local (a dev machine, e.g.
    FRONTEND_URL=http://localhost:3000) the other local Vite origins are allowed too; a deployment that names its real
    origin gets exactly that list."""
    raw = f"{os.environ.get('CORS_ORIGINS', '')},{os.environ.get('FRONTEND_URL', '')}"
    configured = [origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip()]
    if all(_is_local(origin) for origin in configured):
        return list(dict.fromkeys(configured + LOCAL_DEV_ORIGINS))
    return configured


CORS_ALLOWED = cors_origins()
CORS_WILDCARD = "*" in CORS_ALLOWED
app.add_middleware(
    CORSMiddleware,
    # "*" together with credentials would let any website make cookie-authenticated calls, so a wildcard drops credentials.
    allow_origins=["*"] if CORS_WILDCARD else CORS_ALLOWED,
    allow_credentials=not CORS_WILDCARD,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Accept", "Content-Type", "Authorization"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
logger.info("CORS: %s", "any origin, without credentials" if CORS_WILDCARD else ", ".join(CORS_ALLOWED))

# Include the router in the main app last so every route remains under /api.
app.include_router(api_router)
app.include_router(database_router)  # carries its own /api/database prefix
