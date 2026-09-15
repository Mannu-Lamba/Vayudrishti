"""Pydantic contracts for the cyclone registry, regions, events and satellite endpoints (camelCase on the wire).

They mirror frontend/src/types/{cyclone,region,satellite,track}.ts. Fields the real data cannot provide (detection
confidence, Dvorak T-number, risk level, landfall, casualties, imagery) are null — never filled with invented values.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, protected_namespaces=())


class LocationOut(_Camel):
    latitude: float
    longitude: float
    label: str


class CycloneOut(_Camel):
    id: str = Field(description="IBTrACS storm id (SID)")
    code: str
    name: str
    status: Literal["active", "historical"] = Field(description="active = last observed within 24 h; otherwise historical")
    category: str | None = Field(description="IMD category of the wind at observedAt (1-min wind, IMD thresholds); null when no wind was observed")
    region: str = Field(description="Area label, e.g. Bay of Bengal")
    basin: str
    wind_kmh: float | None
    pressure_hpa: float | None
    movement_direction: str | None = Field(description="From the last two fixes")
    movement_speed_kmh: float | None
    detection_confidence: float | None = Field(None, description="Not in the database: null")
    dvorak_t_number: str | None = Field(None, description="Not in the database: null")
    risk_level: str | None = Field(None, description="No risk model is deployed: null")
    location: LocationOut
    observed_at: str = Field(description="Time of the latest observation, ISO 8601 UTC")
    first_observed_at: str
    season: int
    fixes: int
    peak_wind_kmh: float | None
    peak_category: str | None
    source: str = Field(description="cyclone_database, the held-out IBTrACS best track the API serves, or both")
    forecast_available: bool = Field(description="True when at least one fix has a complete 24 h history and observed wind + "
                                                 "pressure, so the prediction model can run")
    forecast_origin: str | None = Field(None, description="Latest fix a forecast can start from (the default `at` of "
                                                          "GET /cyclones/{id}/prediction); null when none")


class TrackFixOut(_Camel):
    id: str
    label: str
    offset_hours: float
    timestamp: str
    latitude: float
    longitude: float
    wind_kmh: float | None
    pressure_hpa: float | None
    category: str | None
    forecast: Literal[False] = False


class HistoryPage(_Camel):
    items: list[TrackFixOut]
    page: int
    page_size: int
    total: int


class HistoricalCycloneOut(_Camel):
    id: str
    name: str
    year: int
    basin: str
    area: str
    category: str | None = Field(description="IMD category of the peak observed wind")
    peak_wind_kmh: float | None
    landfall: str | None = Field(None, description="Not in the database: null")
    casualties: int | None = Field(None, description="Not in the database: null")
    first_observed_at: str
    last_observed_at: str
    source: str


class ArchivePage(_Camel):
    items: list[HistoricalCycloneOut]
    page: int
    page_size: int
    total: int


class SeasonCount(_Camel):
    season: str
    storms: int


class ArchiveSummaryOut(_Camel):
    indexed_systems: int
    first_year: int
    last_year: int
    coverage: str
    seasons: list[SeasonCount]


class ObservedSystemOut(_Camel):
    cyclone_id: str
    code: str
    name: str
    category: str | None
    status: Literal["active", "historical"]
    risk_level: str | None = None
    basin: str
    region_id: str
    subregion_id: str | None
    latitude: float
    longitude: float
    wind_kmh: float | None
    pressure_hpa: float | None
    confidence: float | None = None
    observed_at: str


class RegionalObservationOut(_Camel):
    region_id: str
    subregion_id: str | None
    timestamp: str
    active_systems: int = Field(description="Systems with a fix within ±3 h of `timestamp` in this sector")
    systems: list[ObservedSystemOut]
    strongest: ObservedSystemOut | None


class EventOut(_Camel):
    id: str
    kind: Literal["record"] = Field("record", description="record = the latest observation of a storm in the database")
    priority: Literal["info"] = "info"
    title: str
    source: str
    timestamp: str
    cyclone_id: str | None = None
