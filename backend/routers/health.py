"""GET /api/health — the API is up; which ML models are loaded is reported separately."""

import os
from datetime import datetime, timezone

from fastapi import APIRouter

from models.ml import HealthResponse, HealthServices
from services.ml_registry import registry

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="API and model health")
def health():
    """Answers 200 whenever the API process is up (`status: degraded` when a deployed model failed to load).
    A client that cannot reach this endpoint has lost the backend; a reachable backend with
    `services.prediction_model: false` has lost only the model (details: GET /api/ml/status)."""
    services = HealthServices(
        api=True,
        identification_model=registry.identification.ready,
        classification_model=registry.classification.ready,
        prediction_model=registry.prediction.ready,  # true only when the checkpoint is actually loaded
    )
    deployed_ok = services.identification_model and services.classification_model and services.prediction_model
    return HealthResponse(
        status="ok" if deployed_ok else "degraded",
        version=os.environ.get("APP_VERSION", "1.0"),
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        services=services,
    )
