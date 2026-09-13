"""Unit tests of the prediction core (backend/ml/prediction) and the prediction service — no server needed.

Covers sequence construction, temporal ordering, missing-data handling, the storm-level split of the
served data, baselines, model shapes, post-processing rules, track distance, real-model output ranges,
and the no-data / model-unavailable paths of the service.

    pytest tests/test_prediction_core.py
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ml.prediction.baseline import extrapolation, persistence
from ml.prediction.categories import imd_category
from ml.prediction.config import SequenceConfig
from ml.prediction.features import FEATURE_INDEX, FEATURE_NAMES, Normalizer, storm_fix_features, validate_observations
from ml.prediction.geo import haversine_km, wrap_lon
from ml.prediction.model import build_model
from ml.prediction.postprocess import PostprocessingError, postprocess
from ml.prediction.sequences import (
    INSUFFICIENT_HISTORY_MESSAGE, SequenceInputError, build_inference_window, build_samples, resolve_origin,
)

BACKEND = Path(__file__).resolve().parents[1]
MODEL_DIR = BACKEND / "models" / "prediction"
DATA_FILE = BACKEND / "app" / "data" / "cyclones" / "observations.csv.gz"
SPLITS_FILE = BACKEND.parent / "prediction_model" / "data" / "splits" / "storm_splits.csv"
CFG = SequenceConfig()
DLAT, DLON = 0.3, -0.2


def synthetic_storm(n: int = 10, sid: str = "2020122N10085", **overrides) -> pd.DataFrame:
    k = np.arange(n)
    df = pd.DataFrame({
        "storm_id": sid, "time": pd.date_range("2020-05-01T00:00:00Z", periods=n, freq="6h"),
        "lat": 10.0 + DLAT * k, "lon": 85.0 + DLON * k, "wind_kt": 30.0 + 5 * k, "pressure_hpa": 1000.0 - 3 * k,
        "nature": "TS", "dist2land_km": 500.0, "area": "bay_of_bengal", "region": "north_indian_ocean",
        "subregion": "bay_of_bengal", "basin": "NI",
    })
    for column, value in overrides.items():
        df[column] = value
    return validate_observations(df)[0]


# ---------------------------------------------------------------- sequences

def test_sequence_construction_shapes_and_targets():
    samples = build_samples(synthetic_storm(10), CFG)
    # T0 needs 4 earlier fixes (24 h) and 4 later ones (24 h): fixes 4 and 5 of 0..9.
    assert len(samples) == 2
    assert samples.X.shape == (2, CFG.steps, len(FEATURE_NAMES))
    assert samples.y.shape == (2, len(CFG.horizons_hours), 4)
    steps_ahead = np.array(CFG.horizon_steps)
    np.testing.assert_allclose(samples.y[0, :, 0], DLAT * steps_ahead, atol=1e-5)
    np.testing.assert_allclose(samples.y[0, :, 1], DLON * steps_ahead, atol=1e-5)
    np.testing.assert_allclose(samples.y[0, :, 2], 5 * steps_ahead, atol=1e-5)
    # Positions in the window are relative to T0; the first step is 24 h earlier.
    assert samples.X[0, -1, FEATURE_INDEX["rel_lat"]] == pytest.approx(0.0)
    assert samples.X[0, 0, FEATURE_INDEX["rel_lat"]] == pytest.approx(-4 * DLAT, abs=1e-5)


def test_temporal_ordering_and_timestamp_matching():
    storm = synthetic_storm(12)
    shuffled = validate_observations(storm.sample(frac=1.0, random_state=1))[0]
    assert shuffled["time"].is_monotonic_increasing
    a, b = build_samples(storm, CFG), build_samples(shuffled, CFG)
    np.testing.assert_array_equal(a.X, b.X)
    assert list(a.meta.t0) == sorted(a.meta.t0)
    # Remove one fix from a longer storm: no sample may bridge the gap, and targets are matched by
    # time, never by row position.
    storm = synthetic_storm(22)
    gapped = storm.drop(index=7).reset_index(drop=True)
    samples = build_samples(gapped, CFG)
    assert len(samples) > 0
    times = set(gapped["time"])
    missing = storm["time"].iloc[7]
    for t0 in samples.meta.t0:
        window = [t0 - pd.Timedelta(hours=h) for h in range(0, CFG.history_window_hours + 1, 6)]
        targets = [t0 + pd.Timedelta(hours=h) for h in CFG.horizons_hours]
        assert missing not in window + targets
        assert all(t in times for t in window + targets)
    assert samples.skipped.get("irregular_window", 0) > 0


def test_missing_data_handling():
    storm = synthetic_storm(10)
    storm.loc[3, "wind_kt"] = np.nan
    storm.loc[5, "pressure_hpa"] = np.nan
    feats = storm_fix_features(storm, CFG)
    assert feats[0, FEATURE_INDEX["motion_missing"]] == 1.0          # first fix has no previous one
    assert feats[3, FEATURE_INDEX["wind_missing"]] == 1.0 and np.isnan(feats[3, FEATURE_INDEX["wind_kt"]])
    assert np.isnan(feats[4, FEATURE_INDEX["dwind_prev"]])            # tendency needs both values
    assert feats[5, FEATURE_INDEX["pressure_missing"]] == 1.0
    samples = build_samples(storm, CFG)
    normalizer = Normalizer.fit(samples.X, samples.y)
    Z = normalizer.transform(samples.X)
    assert np.isfinite(Z).all()                                         # missing → training mean (0), flagged
    # Physically impossible values become missing, never clipped.
    bad = validate_observations(synthetic_storm(10).assign(wind_kt=250.0))[0]
    assert bad["wind_kt"].isna().all()


def test_insufficient_history_and_origin_resolution():
    storm = synthetic_storm(10)
    with pytest.raises(SequenceInputError) as exc:
        build_inference_window(storm, 2, CFG)
    assert exc.value.code == "INSUFFICIENT_HISTORY" and INSUFFICIENT_HISTORY_MESSAGE in exc.value.message
    assert resolve_origin(storm, None, CFG) == len(storm) - 1
    assert resolve_origin(storm, storm["time"].iloc[5] + pd.Timedelta(hours=2), CFG) == 5
    with pytest.raises(SequenceInputError) as before:
        resolve_origin(storm, storm["time"].iloc[0] - pd.Timedelta(hours=1), CFG)
    assert before.value.code == "OBSERVATION_NOT_FOUND"
    with pytest.raises(SequenceInputError):
        resolve_origin(storm, storm["time"].iloc[-1] + pd.Timedelta(hours=12), CFG)
    window, anchor = build_inference_window(storm, 6, CFG)
    assert window.shape == (CFG.steps, len(FEATURE_NAMES)) and anchor["t0"] == storm["time"].iloc[6]


def test_config_rejects_inconsistent_windows():
    with pytest.raises(ValueError):
        SequenceConfig(history_window_hours=20)
    with pytest.raises(ValueError):
        SequenceConfig(horizons_hours=(12, 6))
    assert SequenceConfig(horizons_hours=(6, 12, 18, 24, 36, 48)).horizon_steps == (1, 2, 3, 4, 6, 8)


# ---------------------------------------------------------------- baselines, geometry, model

def test_persistence_and_extrapolation_baselines():
    samples = build_samples(synthetic_storm(12), CFG)
    assert not persistence(len(samples), CFG).any()
    ext = extrapolation(samples.X, CFG)
    # A storm moving in a straight line at constant speed is forecast exactly by extrapolation.
    np.testing.assert_allclose(ext[..., :2], samples.y[..., :2], atol=1e-5)
    assert not ext[..., 2:].any()


def test_haversine_track_distance():
    one_degree = 2 * np.pi * 6371.0088 / 360
    assert haversine_km(0, 80, 1, 80) == pytest.approx(one_degree, rel=1e-6)
    assert haversine_km(0, 179.5, 0, -179.5) == pytest.approx(one_degree, rel=1e-6)   # across the antimeridian
    assert haversine_km(15, 88, 15, 88) == pytest.approx(0.0, abs=1e-9)
    assert haversine_km(10, 70, 20, 90) == pytest.approx(haversine_km(20, 90, 10, 70))
    assert wrap_lon(190) == pytest.approx(-170)


@pytest.mark.parametrize("architecture", ["gru", "lstm", "transformer"])
def test_model_forward_shapes(architecture):
    import torch

    model = build_model({"n_features": len(FEATURE_NAMES), "n_steps": CFG.steps, "n_horizons": 4, "architecture": architecture,
                         "hidden": 32, "layers": 2, "head_hidden": 16})
    out = model(torch.zeros(3, CFG.steps, len(FEATURE_NAMES)))
    assert tuple(out.shape) == (3, 4, 4)


# ---------------------------------------------------------------- post-processing

ANCHOR = {"t0": pd.Timestamp("2020-05-01T12:00:00Z"), "lat0": 15.0, "lon0": 179.0, "wind0": 60.0, "pres0": 985.0}


def test_postprocess_valid_forecast():
    deltas = np.array([[0.4, 0.8, 2, -1], [0.8, 1.6, 4, -2], [1.2, 2.4, 5, -3], [1.6, 3.2, 6, -4]], dtype=float)
    steps = postprocess(ANCHOR, deltas, CFG, {"track_radius_km": {"6": 40.0}, "wind_abs_error_kt": {"6": 5.0}})
    assert [s.hours for s in steps] == list(CFG.horizons_hours)
    assert [s.time for s in steps] == [ANCHOR["t0"] + pd.Timedelta(hours=h) for h in CFG.horizons_hours]
    assert all(-180 <= s.longitude < 180 for s in steps)            # 179 + 0.8 wraps to -180.2 → -179.2 range
    assert steps[0].uncertainty_radius_km == 40.0 and steps[0].wind_range_kt == (57.0, 67.0)
    assert steps[1].uncertainty_radius_km is None                     # radius only where provided
    assert steps[0].category == imd_category(62.0) == "Severe Cyclonic Storm"


def test_postprocess_rules_flag_or_reject():
    base = np.zeros((4, 4))
    floored = postprocess(ANCHOR, base + np.array([0, 0, -80, 0]), CFG)
    assert all(s.wind_kt == 0.0 and "wind_floored_at_zero" in s.flags for s in floored)
    fast = postprocess(ANCHOR, np.array([[10.0, 0, 0, 0]] * 4), CFG)
    assert "implausible_motion" in fast[0].flags                      # 1,100 km in 6 h is flagged, not changed
    with pytest.raises(PostprocessingError):
        postprocess(ANCHOR, base + np.array([80.0, 0, 0, 0]), CFG)    # latitude 95°
    with pytest.raises(PostprocessingError):
        postprocess(ANCHOR, base + np.array([0, 0, 0, -140.0]), CFG)  # 845 hPa
    with pytest.raises(PostprocessingError):
        postprocess(ANCHOR, np.full((4, 4), np.nan), CFG)


# ---------------------------------------------------------------- real artifacts

needs_model = pytest.mark.skipif(not (MODEL_DIR / "best_model.pth").exists() or not DATA_FILE.exists(),
                                 reason="prediction model or observation data not deployed")


@pytest.fixture(scope="module")
def engine():
    from ml.prediction.inference import PredictionInference

    return PredictionInference(MODEL_DIR, device="cpu")


@pytest.fixture(scope="module")
def served():
    return validate_observations(pd.read_csv(DATA_FILE, keep_default_na=False, na_values=[""]))[0]


@needs_model
def test_served_data_is_held_out_storm_level(served):
    assert set(served["split"]) == {"test"}
    if not SPLITS_FILE.exists():
        pytest.skip("training workspace not present")
    splits = pd.read_csv(SPLITS_FILE)
    assert splits["storm_id"].is_unique                               # every storm in exactly one split
    test_storms = set(splits.loc[splits.split == "test", "storm_id"])
    assert set(served["storm_id"]) <= test_storms


@needs_model
def test_real_model_output_ranges(engine, served):
    from services.prediction_service import forecast_origins

    checked = 0
    for _, storm in list(served.groupby("storm_id"))[:40]:
        storm = storm.sort_values("time").reset_index(drop=True)
        for t0 in forecast_origins(storm, engine.cfg)[::3]:
            result = engine.predict(storm, t0)
            times = [s.time for s in result.steps]
            assert times == sorted(times) and times[0] > t0
            for s in result.steps:
                assert -90 <= s.latitude <= 90 and -180 <= s.longitude < 180
                assert 0 <= s.wind_kt <= 200 and 870 <= s.pressure_hpa <= 1030
            checked += 1
    assert checked > 50


@needs_model
def test_inference_is_deterministic(engine, served):
    from services.prediction_service import forecast_origins

    storms = (g.sort_values("time").reset_index(drop=True) for _, g in served.groupby("storm_id"))
    storm, origins = next((s, o) for s in storms if (o := forecast_origins(s, engine.cfg)))
    t0 = origins[0]
    a, b = engine.predict(storm, t0), engine.predict(storm, t0)
    assert [(s.latitude, s.longitude, s.wind_kt) for s in a.steps] == [(s.latitude, s.longitude, s.wind_kt) for s in b.steps]


# ---------------------------------------------------------------- service error paths

@needs_model
def test_service_reports_model_unavailable(monkeypatch):
    from services import prediction_service
    from services.errors import MlServiceError

    monkeypatch.setattr(prediction_service.registry.prediction, "instance", None)
    with pytest.raises(MlServiceError) as exc:
        prediction_service.predict("2019300N12070", None)
    assert exc.value.status_code == 503 and exc.value.code == "MODEL_NOT_LOADED"


@needs_model
def test_service_no_data_cases(monkeypatch, engine):
    from repositories.cyclone_repository import FileCycloneRepository
    from services import prediction_service
    from services.errors import MlServiceError

    repo = FileCycloneRepository(DATA_FILE)
    repo.load()
    monkeypatch.setattr(prediction_service, "repository", repo)
    monkeypatch.setattr(prediction_service.registry.prediction, "instance", engine)
    storm = repo.list_storms()[0]
    with pytest.raises(MlServiceError) as short:
        prediction_service.predict(storm.storm_id, storm.first_time.isoformat())
    assert short.value.status_code == 422 and short.value.code == "INSUFFICIENT_HISTORY"
    assert INSUFFICIENT_HISTORY_MESSAGE in short.value.message
    # Not in the held-out table and MongoDB unreachable: the lookup cannot be completed, so it is reported, not a 404.
    from repositories.cyclone_repository import MongoCycloneRepository
    monkeypatch.setattr(MongoCycloneRepository, "_handle", staticmethod(lambda: None))  # independent of other tests' connection
    with pytest.raises(MlServiceError) as unchecked:
        prediction_service.predict("1999001N00000", None)
    assert unchecked.value.status_code == 503 and unchecked.value.code == "DATABASE_UNAVAILABLE"

    class EmptyDatabase:
        def get_observations(self, storm_id):
            return None

    monkeypatch.setattr(prediction_service, "mongo_repository", EmptyDatabase())
    with pytest.raises(MlServiceError) as unknown:
        prediction_service.predict("1999001N00000", None)
    assert unknown.value.status_code == 404 and unknown.value.code == "CYCLONE_NOT_FOUND"
    with pytest.raises(MlServiceError) as bad:
        prediction_service.predict("not-a-storm", None)
    assert bad.value.status_code == 400
