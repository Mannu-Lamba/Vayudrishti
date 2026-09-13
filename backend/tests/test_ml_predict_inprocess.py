"""POST /api/ml/predict, GET /api/ml/status, request validation and CORS, in-process (no server needed).

    pytest tests/test_ml_predict_inprocess.py

Covers the states a running server cannot be put into on demand: model not loaded, model loading and a
model that is deployed but fails to load. Where the trained model is present it is loaded for real (CPU)
and the forecast comes from it; nothing here fabricates a prediction.
"""

import os
import shutil
from pathlib import Path

import pytest

os.environ.setdefault("MONGODB_URI", "mongodb://127.0.0.1:27017")  # lib/db + app/core/config read these at import
os.environ.setdefault("MONGODB_APP_DATABASE", "vayudrishti_test")  # never the real app DB

from fastapi.testclient import TestClient  # noqa: E402

import server  # noqa: E402
from repositories.cyclone_repository import FileCycloneRepository  # noqa: E402
from services import prediction_service  # noqa: E402
from services.ml_registry import MlRegistry, ModelSlot, registry  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]
MODEL_DIR = BACKEND / "models" / "prediction"
DATA_FILE = BACKEND / "app" / "data" / "cyclones" / "observations.csv.gz"
AMPHAN = {"cyclone_id": "2020136N10088", "timestamp": "2020-05-18T18:00:00Z", "latitude": 14.9, "longitude": 86.6}
needs_model = pytest.mark.skipif(not ((MODEL_DIR / "best_model.pth").exists() and DATA_FILE.exists()),
                                 reason="trained prediction model or held-out data not deployed")


@pytest.fixture(scope="module")
def client():
    return TestClient(server.app)  # used without `with`: the lifespan (Mongo indexes, model loading) does not run


@pytest.fixture(scope="module")
def engine():
    from ml.prediction.inference import PredictionInference
    return PredictionInference(MODEL_DIR, device="cpu")


@pytest.fixture
def loaded(monkeypatch, engine):
    """The real model and the held-out observation table, as the lifespan would load them."""
    repo = FileCycloneRepository(DATA_FILE)
    repo.load()
    monkeypatch.setattr(prediction_service, "repository", repo)
    monkeypatch.setattr(registry, "prediction", ModelSlot("prediction", instance=engine, loaded_at="2026-01-01T00:00:00+00:00"))


def assert_error(resp, status: int, code: str) -> dict:
    assert resp.status_code == status, resp.text
    body = resp.json()
    assert body["success"] is False and body["status"] == "error"
    assert body["error"]["code"] == code and body["error"]["message"]
    assert "detail" not in body and "Traceback" not in resp.text and ".py" not in resp.text
    return body


# ---------------------------------------------------------------- model states

@needs_model
def test_status_ready_and_valid_prediction(client, loaded):
    status = client.get("/api/ml/status").json()["prediction"]
    assert status["status"] == "ready" and status["modelLoaded"] is True
    assert status["modelName"] == "cyclone-track-prediction" and status["modelVersion"]

    resp = client.post("/api/ml/predict", json=AMPHAN)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True and body["status"] == "success" and body["cycloneId"] == AMPHAN["cyclone_id"]
    assert body["issuedAt"] == AMPHAN["timestamp"] and body["current"]["latitude"] == pytest.approx(14.9)
    assert [step["hours"] for step in body["forecast"]] == [6, 12, 18, 24]
    assert body["confidence"] is None and all(step["confidence"] is None for step in body["forecast"])


def test_model_not_loaded(client, monkeypatch):
    monkeypatch.setattr(registry, "prediction", ModelSlot("prediction"))
    status = client.get("/api/ml/status").json()["prediction"]
    assert status["status"] == "unavailable" and status["modelLoaded"] is False and status["modelName"] is None
    assert_error(client.post("/api/ml/predict", json=AMPHAN), 503, "MODEL_NOT_LOADED")
    health = client.get("/api/health").json()
    assert health["services"]["api"] is True and health["services"]["prediction_model"] is False and health["status"] == "degraded"


def test_model_loading_state(client, monkeypatch):
    monkeypatch.setattr(registry, "prediction", ModelSlot("prediction", loading=True))
    status = client.get("/api/ml/status").json()["prediction"]
    assert status["status"] == "loading" and status["modelLoaded"] is False
    assert_error(client.post("/api/ml/predict", json=AMPHAN), 503, "MODEL_NOT_LOADED")


@needs_model
def test_model_load_error_is_not_reported_ready(client, monkeypatch, tmp_path):
    broken = tmp_path / "prediction"
    broken.mkdir()
    shutil.copy(MODEL_DIR / "model_config.json", broken / "model_config.json")
    (broken / "best_model.pth").write_bytes(b"not a checkpoint")
    fresh = MlRegistry()
    fresh.load(models_dir=tmp_path, device="cpu")
    assert fresh.prediction.state == "error" and fresh.prediction.error_code == "MODEL_LOAD_FAILED"
    assert fresh.identification.state == "unavailable"          # files simply not deployed there

    monkeypatch.setattr(registry, "prediction", fresh.prediction)
    body = client.get("/api/ml/status").json()
    assert body["prediction"]["status"] == "error" and body["prediction"]["modelLoaded"] is False
    assert body["prediction"]["errorCode"] == "MODEL_LOAD_FAILED" and str(tmp_path) not in body["prediction"]["message"]
    assert next(c for c in body["components"] if c["id"] == "prediction-model")["status"] == "error"
    assert_error(client.post("/api/ml/predict", json=AMPHAN), 503, "MODEL_NOT_LOADED")


# ---------------------------------------------------------------- request validation (422, structured)

@pytest.mark.parametrize("payload", [
    {},                                                                    # cyclone_id missing
    {"cyclone_id": "2020136N10088", "latitude": 95.0, "longitude": 86.6},  # latitude out of range
    {"cyclone_id": "2020136N10088", "latitude": 14.9},                     # position half given
    {"cyclone_id": "2020136N10088", "timestamp": "yesterday-ish"},         # not ISO 8601
    {"cyclone_id": "2020136N10088", "sea_surface_temp": 29.5},             # not a model input: rejected, not ignored
    {"cyclone_id": "2020136N10088", "horizons_hours": []},
])
def test_invalid_payload_is_a_structured_422(client, payload):
    body = assert_error(client.post("/api/ml/predict", json=payload), 422, "VALIDATION_ERROR")
    assert body["error"]["message"].startswith("Invalid request:")


def test_malformed_json_is_a_structured_422(client):
    resp = client.post("/api/ml/predict", content=b"{not json", headers={"Content-Type": "application/json"})
    assert "not valid JSON" in assert_error(resp, 422, "VALIDATION_ERROR")["error"]["message"]


def test_other_routes_keep_the_default_validation_body(client):
    resp = client.post("/api/status", json={})                           # legacy route, validated before any DB call
    assert resp.status_code == 422 and isinstance(resp.json()["detail"], list)


class _EmptyDatabase:
    """cyclone_database stand-in that holds no storms (the lifespan, which connects MongoDB, does not run here)."""

    def get_observations(self, storm_id):
        return None


@needs_model
def test_semantic_errors(client, loaded, monkeypatch):
    monkeypatch.setattr(prediction_service, "mongo_repository", _EmptyDatabase())
    assert_error(client.post("/api/ml/predict", json={"cyclone_id": "not-a-storm"}), 400, "INVALID_CYCLONE_ID")
    assert_error(client.post("/api/ml/predict", json={"cyclone_id": "1999001N00000"}), 404, "CYCLONE_NOT_FOUND")
    assert_error(client.post("/api/ml/predict", json={**AMPHAN, "latitude": 20.0}), 400, "POSITION_MISMATCH")
    assert_error(client.post("/api/ml/predict", json={**AMPHAN, "horizons_hours": [6, 48]}), 400, "UNSUPPORTED_HORIZON")
    first = prediction_service.repository.get_summary(AMPHAN["cyclone_id"]).first_time.isoformat()
    body = assert_error(client.post("/api/ml/predict", json={"cyclone_id": AMPHAN["cyclone_id"], "timestamp": first}), 422, "INSUFFICIENT_HISTORY")
    assert "Insufficient historical observations" in body["error"]["message"]


# ---------------------------------------------------------------- CORS

@pytest.mark.parametrize("origin", ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"])
def test_cors_allows_the_local_frontend(client, origin):
    resp = client.options("/api/ml/predict", headers={"Origin": origin, "Access-Control-Request-Method": "POST",
                                                      "Access-Control-Request-Headers": "content-type"})
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == origin and resp.headers["access-control-allow-credentials"] == "true"


def test_cors_rejects_unknown_origins(client):
    resp = client.options("/api/ml/predict", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
    assert resp.status_code == 400 and "access-control-allow-origin" not in resp.headers
    simple = client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert simple.status_code == 200 and "access-control-allow-origin" not in simple.headers
