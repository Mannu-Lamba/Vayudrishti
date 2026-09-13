"""Regions (/api/regions), events (/api/events) and satellite frame records (/api/satellite).

Router → services/registry_service → repositories/registry_repository (MongoDB cyclone_database, read-only) and the
reference geography in app/data/reference. Errors follow {success: false, status: "error", error: {code, message}}.
"""

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from models.ml import ErrorDetail, ErrorResponse
from models.registry import EventOut
from services import registry_service
from services.errors import MlServiceError

DB_ERRORS = {503: {"model": ErrorResponse, "description": "DATABASE_UNAVAILABLE"}}

regions_router = APIRouter(tags=["regions"])
events_router = APIRouter(tags=["events"])
satellite_router = APIRouter(tags=["satellite"])


def _error(exc: MlServiceError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=ErrorResponse(error=ErrorDetail(code=exc.code, message=exc.message)).model_dump())


def _call(fn, *args):
    try:
        return fn(*args)
    except MlServiceError as exc:
        return _error(exc)


# ---------------------------------------------------------------- /api/regions

@regions_router.get("", summary="Region taxonomy (UI regions → IBTrACS basins, RSMCs, map bounds)")
def list_regions():
    return registry_service.regions()


@regions_router.get("/coastal-districts", summary="Coastal districts (approximate centroids) for the risk-zone impact popup")
def coastal_districts():
    return registry_service.coastal_districts()


@regions_router.get("/{region_id}", summary="One region", responses={404: {"model": ErrorResponse}})
def get_region(region_id: str):
    return _call(registry_service.region, region_id)


# ---------------------------------------------------------------- /api/events

@events_router.get("/events", response_model=list[EventOut], responses=DB_ERRORS,
                   summary="Latest storm observations recorded in cyclone_database")
def events(limit: int = Query(10, ge=1, le=100)):
    return _call(registry_service.events, limit)


# ---------------------------------------------------------------- /api/satellite

@satellite_router.get("/sources", responses=DB_ERRORS, summary="Sources with frame records in a region/subregion")
def satellite_sources(region: str = Query(...), subregion: str | None = Query(None)):
    return _call(registry_service.satellite_sources, region, subregion)


@satellite_router.get("/latest", responses={**DB_ERRORS, 404: {"model": ErrorResponse}}, summary="Latest satellite frame record in a region")
def latest_frame(region: str | None = Query(None)):
    return _call(registry_service.latest_frame, region)


@satellite_router.get("", responses=DB_ERRORS,
                      summary="Satellite frame records (metadata; imageUrl is null when cyclone_database stores no image)")
def satellite_frames(region: str = Query(...), subregion: str | None = Query(None), source: str | None = Query(None),
                     channel: str | None = Query(None), start: str | None = Query(None), end: str | None = Query(None),
                     page: int = Query(1, ge=1), page_size: int = Query(500, ge=1, le=1000, alias="pageSize")):
    """Without `start`/`end`, the latest 24 frame records of the selection."""
    return _call(registry_service.satellite_frames, region, subregion, source, channel, start, end, page, page_size)


@satellite_router.get("/{frame_id}", responses={**DB_ERRORS, 404: {"model": ErrorResponse}}, summary="One satellite frame record")
def satellite_frame(frame_id: str):
    return _call(registry_service.satellite_frame, frame_id)
