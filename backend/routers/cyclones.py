"""Cyclone track + prediction endpoints (mounted at /api/cyclones).

Router → services/prediction_service → repository + ml/prediction. Every error follows
{success: false, error: {code, message}}; no stack traces reach the client.
"""

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from models.ml import ErrorDetail, ErrorResponse
from models.prediction import CycloneTrackOut, PredictionCasesResponse, PredictionResponse
from models.registry import ArchivePage, ArchiveSummaryOut, CycloneOut, HistoryPage, RegionalObservationOut
from services import prediction_service, registry_service
from services.errors import MlServiceError

router = APIRouter(tags=["cyclones"])

ERROR_RESPONSES = {
    400: {"model": ErrorResponse, "description": "Invalid cyclone id or timestamp"},
    404: {"model": ErrorResponse, "description": "Unknown cyclone, or no observation at the requested time"},
    422: {"model": ErrorResponse, "description": "Insufficient history, or wind/pressure not observed at the forecast time"},
    500: {"model": ErrorResponse, "description": "Inference failed or the output failed post-processing checks"},
    503: {"model": ErrorResponse, "description": "Prediction model or observation data not loaded"},
}


def _error(exc: MlServiceError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=ErrorResponse(error=ErrorDetail(code=exc.code, message=exc.message)).model_dump())


@router.get("/prediction-cases", response_model=PredictionCasesResponse, responses={503: ERROR_RESPONSES[503]},
            summary="Storms a forecast can be run for, with their valid forecast times")
def prediction_cases(region: str | None = Query(None, description="UI region id, e.g. north_indian_ocean"),
                     subregion: str | None = Query(None, description="UI subregion id, e.g. bay_of_bengal"),
                     basin: str | None = Query(None, description="IBTrACS basin code, e.g. NI")):
    try:
        return prediction_service.list_cases(region, subregion, basin)
    except MlServiceError as exc:
        return _error(exc)


# ---------------------------------------------------------------- registry (MongoDB cyclone_database, read-only)
# Static paths are declared before /{cyclone_id} so they are not taken for a cyclone id.

REGISTRY_ERRORS = {400: ERROR_RESPONSES[400], 503: {"model": ErrorResponse, "description": "DATABASE_UNAVAILABLE"}}


@router.get("", response_model=list[CycloneOut], responses=REGISTRY_ERRORS,
            summary="Storms in cyclone_database, newest first, optionally by region / basin / date / active")
def list_cyclones(region: str | None = Query(None, description="UI region id, e.g. north_indian_ocean"),
                  subregion: str | None = Query(None, description="UI subregion id, e.g. bay_of_bengal"),
                  basin: str | None = Query(None, description="IBTrACS basin code, e.g. NI"),
                  start_date: str | None = Query(None, alias="startDate"), end_date: str | None = Query(None, alias="endDate"),
                  active: bool | None = Query(None, description="true = last observed within 24 h"),
                  limit: int = Query(50, ge=1, le=1000)):
    """Real storms only (the class-0 `SYS_…` samples are not storms). `category`, wind and pressure are those of the latest
    fix (null when not observed); detection confidence, Dvorak T-number and risk level are not in the data and are null."""
    try:
        return registry_service.list_cyclones(region, subregion, basin, start_date, end_date, active, limit)
    except MlServiceError as exc:
        return _error(exc)


@router.get("/archive", response_model=ArchivePage, responses=REGISTRY_ERRORS, summary="Paged storm archive (peak intensity per storm)")
def cyclone_archive(region: str | None = Query(None), subregion: str | None = Query(None), year: int | None = Query(None),
                    page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=500, alias="pageSize")):
    try:
        return registry_service.archive(region, subregion, year, page, page_size)
    except MlServiceError as exc:
        return _error(exc)


@router.get("/archive/summary", response_model=ArchiveSummaryOut, responses=REGISTRY_ERRORS, summary="Archive coverage and storms per season")
def cyclone_archive_summary():
    try:
        return registry_service.archive_summary()
    except MlServiceError as exc:
        return _error(exc)


@router.get("/regional-observation", response_model=RegionalObservationOut, responses=REGISTRY_ERRORS,
            summary="Storms observed in a sector within ±3 h of a time")
def regional_observation(region: str = Query(...), subregion: str | None = Query(None), at: str = Query(..., description="ISO 8601")):
    try:
        return registry_service.regional_observation(region, subregion, at)
    except MlServiceError as exc:
        return _error(exc)


@router.get("/{cyclone_id}/track", response_model=CycloneTrackOut, responses=ERROR_RESPONSES, summary="Observed best-track fixes")
def cyclone_track(cyclone_id: str, start: str | None = Query(None, description="ISO 8601 lower bound"),
                  end: str | None = Query(None, description="ISO 8601 upper bound")):
    try:
        return prediction_service.track(cyclone_id, start, end)
    except MlServiceError as exc:
        return _error(exc)


@router.get("/{cyclone_id}/prediction", response_model=PredictionResponse, responses=ERROR_RESPONSES,
            summary="Track / intensity / pressure forecast for T+6 … T+24 h")
def cyclone_prediction(cyclone_id: str, at: str | None = Query(None, description="Forecast time (ISO 8601); default = the newest observation")):
    """Forecast from the storm's own observation history ending at `at`. `confidence` is always null;
    `uncertaintyRadiusKm` is an empirical radius from validation errors, not a calibrated probability."""
    try:
        return prediction_service.predict(cyclone_id, at)
    except MlServiceError as exc:
        return _error(exc)


@router.get("/{cyclone_id}/history", response_model=HistoryPage, responses={**REGISTRY_ERRORS, 404: ERROR_RESPONSES[404]},
            summary="Observed fixes of one storm, paged")
def cyclone_history(cyclone_id: str, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=1000, alias="pageSize"),
                    start: str | None = Query(None), end: str | None = Query(None)):
    try:
        return registry_service.history(cyclone_id, page, page_size, start, end)
    except MlServiceError as exc:
        return _error(exc)


@router.get("/{cyclone_id}", response_model=CycloneOut, responses={**REGISTRY_ERRORS, 404: ERROR_RESPONSES[404]}, summary="One storm of the registry")
def get_cyclone(cyclone_id: str):
    try:
        return registry_service.get_cyclone(cyclone_id)
    except MlServiceError as exc:
        return _error(exc)
