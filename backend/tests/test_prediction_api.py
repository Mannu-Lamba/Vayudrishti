"""Prediction endpoints (/api/cyclones/*) and model status against the live backend.

    BACKEND_URL=http://127.0.0.1:8001 pytest tests/test_prediction_api.py

The parity test recomputes one forecast in-process with the same PredictionInference class and the
same held-out observation file, and requires the API to return the same numbers.
"""

import os
from pathlib import Path

import httpx
import numpy as np
import pandas as pd
import pytest

API_URL = f"{os.environ.get('BACKEND_URL', 'http://localhost:8001')}/api"
BACKEND = Path(__file__).resolve().parents[1]
HORIZONS = [6, 12, 18, 24]


def api_url(path: str = "") -> str:
    return f"{API_URL}{path}"


def get(path: str, **params) -> httpx.Response:
    return httpx.get(api_url(path), params={k: v for k, v in params.items() if v is not None}, timeout=60.0)


def post_predict(payload) -> httpx.Response:
    return httpx.post(api_url("/ml/predict"), json=payload, timeout=60.0)


def assert_error(resp: httpx.Response, status: int, code: str) -> dict:
    assert resp.status_code == status, resp.text
    body = resp.json()
    assert body["success"] is False and body["status"] == "error"
    assert body["error"]["code"] == code and body["error"]["message"]
    assert "Traceback" not in resp.text
    return body


@pytest.fixture(scope="module")
def cases() -> list[dict]:
    resp = get("/cyclones/prediction-cases")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == len(body["cases"]) > 0
    return body["cases"]


@pytest.fixture(scope="module")
def case(cases) -> dict:
    return max((c for c in cases if len(c["forecastOrigins"]) >= 3), key=lambda c: c["peakWindKt"] or 0)


# ---------------------------------------------------------------- health / status

def test_health_reports_prediction_model_loaded():
    body = get("/health").json()
    assert body["services"]["prediction_model"] is True


def test_status_lists_prediction_model_and_dataset():
    body = get("/ml/status").json()
    components = {c["id"]: c for c in body["components"]}
    assert components["prediction-model"]["status"] == "ready"
    assert components["cyclone-observations"]["status"] == "ready"
    track = next(m for m in body["models"] if m["task"] == "track")
    assert track["inputWindowHours"] == 24 and track["forecastHorizonHours"] == 24
    prediction = body["prediction"]
    assert prediction["status"] == "ready" and prediction["modelLoaded"] is True
    assert prediction["modelName"] == "cyclone-track-prediction" and prediction["modelVersion"] and prediction["errorCode"] is None


# ---------------------------------------------------------------- cases / track

def test_prediction_cases_are_held_out(cases):
    assert all(c["split"] == "test" for c in cases)
    assert all(c["cycloneId"] and c["observations"] >= 1 for c in cases)
    regional = get("/cyclones/prediction-cases", subregion="bay_of_bengal").json()["cases"]
    assert regional and all(c["subregion"] == "bay_of_bengal" for c in regional)


def test_track_endpoint_bounds(case):
    full = get(f"/cyclones/{case['cycloneId']}/track").json()
    assert len(full["points"]) == case["observations"]
    times = [p["timestamp"] for p in full["points"]]
    assert times == sorted(times)
    origin = case["forecastOrigins"][1]
    bounded = get(f"/cyclones/{case['cycloneId']}/track", end=origin).json()
    assert bounded["points"][-1]["timestamp"] == origin and bounded["observedAt"] == origin


# ---------------------------------------------------------------- prediction

def test_prediction_schema_and_ranges(case):
    origin = case["forecastOrigins"][len(case["forecastOrigins"]) // 2]
    resp = get(f"/cyclones/{case['cycloneId']}/prediction", at=origin)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True and body["cycloneId"] == case["cycloneId"]
    assert body["issuedAt"] == origin and body["current"]["observedAt"] == origin
    assert body["model"]["version"] and body["modelVersion"] and body["generatedAt"]
    assert body["confidence"] is None                                    # never fabricated
    assert body["disclaimer"] and "not an official forecast" in body["disclaimer"].lower()
    assert [step["hours"] for step in body["forecast"]] == HORIZONS == body["horizonsHours"]
    t0 = pd.Timestamp(origin)
    for step in body["forecast"]:
        assert pd.Timestamp(step["forecastTime"]) == t0 + pd.Timedelta(hours=step["hours"])
        assert -90 <= step["latitude"] <= 90 and -180 <= step["longitude"] < 180
        assert step["windSpeed"] == pytest.approx(step["windSpeedKt"] * 1.852, abs=0.2)
        assert 870 <= step["pressure"] <= 1030
        assert step["confidence"] is None
        assert step["uncertaintyRadiusKm"] > 0
    radii = [step["uncertaintyRadiusKm"] for step in body["forecast"]]
    assert radii == sorted(radii)                                        # error grows with lead time
    assert body["uncertainty"]["method"] == "empirical" and 0 < body["uncertainty"]["confidenceLevel"] < 1


def test_prediction_matches_in_process_inference(case):
    from ml.prediction.features import validate_observations
    from ml.prediction.inference import PredictionInference

    origin = case["forecastOrigins"][-1]
    api = get(f"/cyclones/{case['cycloneId']}/prediction", at=origin).json()
    engine = PredictionInference(BACKEND / "models" / "prediction", device="cpu")
    obs = validate_observations(pd.read_csv(BACKEND / "app" / "data" / "cyclones" / "observations.csv.gz", keep_default_na=False, na_values=[""]))[0]
    storm = obs[obs.storm_id == case["cycloneId"]].reset_index(drop=True)
    local = engine.predict(storm, pd.Timestamp(origin))
    for step, expected in zip(api["forecast"], local.steps):
        assert step["latitude"] == pytest.approx(expected.latitude, abs=2e-3)
        assert step["longitude"] == pytest.approx(expected.longitude, abs=2e-3)
        assert step["windSpeedKt"] == pytest.approx(expected.wind_kt, abs=0.1)
        assert step["pressure"] == pytest.approx(expected.pressure_hpa, abs=0.1)


def test_repeated_prediction_is_cached(case):
    origin = case["forecastOrigins"][0]
    first = get(f"/cyclones/{case['cycloneId']}/prediction", at=origin).json()
    second = get(f"/cyclones/{case['cycloneId']}/prediction", at=origin).json()
    assert second["cached"] is True
    assert first["forecast"] == second["forecast"] and first["generatedAt"] == second["generatedAt"]


# ---------------------------------------------------------------- no-data / errors

def test_insufficient_history_returns_no_prediction(case):
    body = assert_error(get(f"/cyclones/{case['cycloneId']}/prediction", at=case["firstObservation"]), 422, "INSUFFICIENT_HISTORY")
    assert "Insufficient historical observations for the selected cyclone." in body["error"]["message"]


def test_prediction_error_codes(case):
    assert_error(get("/cyclones/not-a-storm/prediction"), 400, "INVALID_CYCLONE_ID")
    assert_error(get("/cyclones/1999001N00000/prediction"), 404, "CYCLONE_NOT_FOUND")
    assert_error(get(f"/cyclones/{case['cycloneId']}/prediction", at="yesterday-ish"), 400, "INVALID_TIME")
    before = (pd.Timestamp(case["firstObservation"]) - pd.Timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert_error(get(f"/cyclones/{case['cycloneId']}/prediction", at=before), 404, "OBSERVATION_NOT_FOUND")
    assert_error(get("/cyclones/1999001N00000/track"), 404, "CYCLONE_NOT_FOUND")


# ---------------------------------------------------------------- POST /api/ml/predict (frontend endpoint)

def test_post_predict_equals_get_prediction(case):
    origin = case["forecastOrigins"][len(case["forecastOrigins"]) // 2]
    fix = get(f"/cyclones/{case['cycloneId']}/track", start=origin, end=origin).json()["points"][0]
    resp = post_predict({"cyclone_id": case["cycloneId"], "timestamp": origin, "latitude": fix["latitude"], "longitude": fix["longitude"]})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True and body["status"] == "success" and body["cycloneId"] == case["cycloneId"]
    assert body["issuedAt"] == origin and body["current"]["latitude"] == pytest.approx(fix["latitude"])
    assert body["confidence"] is None and all(step["confidence"] is None for step in body["forecast"])
    reference = get(f"/cyclones/{case['cycloneId']}/prediction", at=origin).json()
    assert body["forecast"] == reference["forecast"] and body["model"] == reference["model"]


def test_post_predict_camel_case_and_horizon_subset(case):
    origin = case["forecastOrigins"][0]
    body = post_predict({"cycloneId": case["cycloneId"], "timestamp": origin, "horizonsHours": [6, 12]}).json()
    assert [step["hours"] for step in body["forecast"]] == [6, 12] == body["horizonsHours"]


def test_post_predict_error_contract(case):
    origin = case["forecastOrigins"][0]
    assert_error(post_predict({}), 422, "VALIDATION_ERROR")
    assert_error(post_predict({"cyclone_id": case["cycloneId"], "latitude": 91, "longitude": 0}), 422, "VALIDATION_ERROR")
    assert_error(post_predict({"cyclone_id": "not-a-storm"}), 400, "INVALID_CYCLONE_ID")
    assert_error(post_predict({"cyclone_id": "1999001N00000"}), 404, "CYCLONE_NOT_FOUND")
    assert_error(post_predict({"cyclone_id": case["cycloneId"], "timestamp": origin, "horizons_hours": [48]}), 400, "UNSUPPORTED_HORIZON")
    fix = get(f"/cyclones/{case['cycloneId']}/track", start=origin, end=origin).json()["points"][0]
    far = {"cyclone_id": case["cycloneId"], "timestamp": origin, "latitude": fix["latitude"] - 5 if fix["latitude"] > 0 else fix["latitude"] + 5,
           "longitude": fix["longitude"]}
    assert_error(post_predict(far), 400, "POSITION_MISMATCH")
    body = assert_error(post_predict({"cyclone_id": case["cycloneId"], "timestamp": case["firstObservation"]}), 422, "INSUFFICIENT_HISTORY")
    assert "Insufficient historical observations for the selected cyclone." in body["error"]["message"]


def test_cors_preflight_for_local_frontend():
    for origin in ("http://localhost:5173", "http://127.0.0.1:3000"):
        resp = httpx.options(api_url("/ml/predict"), headers={"Origin": origin, "Access-Control-Request-Method": "POST",
                                                                "Access-Control-Request-Headers": "content-type"})
        assert resp.status_code == 200 and resp.headers["access-control-allow-origin"] == origin
    denied = httpx.options(api_url("/ml/predict"), headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in denied.headers


def test_no_fabricated_values_in_any_origin(case):
    for origin in case["forecastOrigins"][:6]:
        body = get(f"/cyclones/{case['cycloneId']}/prediction", at=origin).json()
        assert body["confidence"] is None and all(step["confidence"] is None for step in body["forecast"])
        assert np.all(np.isfinite([step["latitude"] for step in body["forecast"]]))
