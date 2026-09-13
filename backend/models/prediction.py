"""Pydantic contracts for /api/cyclones/* (track + prediction).

camelCase on the wire, matching frontend/src/types/model.ts (PredictionResourceResponse) and
frontend/src/types/track.ts (CycloneTrackResponse). Errors use models.ml.ErrorResponse.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, protected_namespaces=())


class PredictionRequest(_Camel):
    """POST /api/ml/predict. The model forecasts from the storm's own observed history (the last 24 h of
    best-track fixes the server holds), so `cyclone_id` + `timestamp` select the whole model input.
    Nothing else is fed to the network; unknown keys are rejected rather than silently ignored.
    snake_case and camelCase keys are both accepted."""
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, protected_namespaces=(), extra="forbid",
        json_schema_extra={"examples": [
            {"cyclone_id": "2020136N10088", "timestamp": "2020-05-18T18:00:00Z", "latitude": 14.9, "longitude": 86.6},
            {"cycloneId": "2020136N10088", "timestamp": "2020-05-18T18:00:00Z", "horizonsHours": [6, 12]},
        ]})

    cyclone_id: str = Field(min_length=1, max_length=32, description="IBTrACS storm id (SID), e.g. 2020136N10088 (AMPHAN)")
    timestamp: datetime | None = Field(
        None, description="Forecast time T0, ISO 8601 (UTC if no offset). The latest observation at or up to 3 h before it is the "
                          "forecast origin. Default: the storm's newest observation")
    latitude: float | None = Field(
        None, ge=-90, le=90, description="Optional consistency check, not a model input: where the client believes the storm was at T0. "
                                         "Rejected (400 POSITION_MISMATCH) when more than 50 km from the observed fix")
    longitude: float | None = Field(None, ge=-180, le=360, description="Pairs with `latitude`; degrees east")
    horizons_hours: list[int] | None = Field(
        None, min_length=1, description="Lead times to return, a subset of the model's [6, 12, 18, 24]. Default: all")

    @model_validator(mode="after")
    def _position_pair(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be given together")
        return self


class ForecastPointOut(_Camel):
    hours: int = Field(description="Lead time after the forecast time (T0), hours")
    forecast_time: str = Field(description="ISO 8601 UTC = issuedAt + hours")
    latitude: float
    longitude: float = Field(description="[-180, 180)")
    wind_speed: float = Field(description="km/h (model predicts 1-min sustained wind in kt)")
    wind_speed_kt: float
    pressure: float = Field(description="Central pressure, hPa")
    category: str | None = Field(description="IMD category of the predicted wind (1-min basis)")
    confidence: float | None = Field(None, description="Always null: the model has no calibrated per-forecast confidence")
    uncertainty_radius_km: float | None = Field(None, description="Empirical radius holding `uncertainty.confidenceLevel` of validation track errors at this lead")
    wind_speed_range: list[float] | None = Field(None, description="[low, high] km/h, empirical band from validation wind errors")
    flags: list[str] = Field(default_factory=list, description="Post-processing adjustments applied to this step")


class CurrentStateOut(_Camel):
    observed_at: str
    latitude: float
    longitude: float
    wind_kmh: float
    wind_kt: float
    pressure_hpa: float
    category: str | None
    nature: str | None = None
    movement_direction: str | None = None
    movement_speed_kmh: float | None = None


class PredictionModelOut(_Camel):
    name: str
    display_name: str
    version: str
    architecture: str
    trained_at: str | None = None
    dataset_version: str | None = None


class PredictionInputOut(_Camel):
    history_window_hours: int
    observation_interval_hours: int
    observations_used: int
    window_start: str
    window_end: str
    source: str = "IBTrACS v04r01 best track (USA_WIND / USA_PRES)"


class PredictionUncertaintyOut(_Camel):
    method: Literal["empirical"]
    confidence_level: float
    note: str


class TimingOut(_Camel):
    processing_time_ms: float
    preprocessing_ms: float
    model_ms: float


class PredictionResponse(_Camel):
    success: Literal[True] = True
    status: Literal["success"] = "success"
    cyclone_id: str
    name: str
    basin: str
    region: str
    subregion: str
    generated_at: str = Field(description="When this forecast was computed (server UTC)")
    issued_at: str = Field(description="Forecast time T0: the latest observation the forecast starts from")
    model_version: str
    model: PredictionModelOut
    horizons_hours: list[int]
    input: PredictionInputOut
    current: CurrentStateOut
    forecast: list[ForecastPointOut]
    confidence: None = Field(None, description="Null: no calibrated confidence is produced")
    uncertainty: PredictionUncertaintyOut | None = None
    disclaimer: str
    cached: bool = False
    inference: TimingOut


class TrackPointOut(_Camel):
    timestamp: str
    latitude: float
    longitude: float
    wind_kmh: float | None
    pressure_hpa: float | None
    category: str | None = None


class CycloneTrackOut(_Camel):
    cyclone_id: str
    observed_at: str | None = None
    points: list[TrackPointOut]


class PredictionCaseOut(_Camel):
    cyclone_id: str
    name: str
    season: int
    basin: str
    region: str
    subregion: str
    area: str
    first_observation: str
    last_observation: str
    observations: int
    peak_wind_kt: float | None
    split: str | None = Field(None, description="Dataset split of this storm; 'test' = never seen in training")
    forecast_origins: list[str] = Field(description="Times a forecast can start from (complete 24 h history + observed wind and pressure)")


class PredictionCasesResponse(_Camel):
    cases: list[PredictionCaseOut]
    total: int
    note: str
