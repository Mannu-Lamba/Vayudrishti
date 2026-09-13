"""Phase 7 — ML inference for all three trained models, in process (no server needed).

Real inputs only: held-out test-split images (tests/fixtures/ml), held-out best-track storms
(backend/app/data/cyclones) and real cyclone ids read from MongoDB cyclone_database (those tests are skipped
when it is not reachable). Covers the load-time artifact checks, output validation, the MISSING_FEATURES guard,
the MongoDB-backed lookup, the unified /api/ml/analyze pipeline and the truthful /api/ml/status.

    .venv/Scripts/python.exe -m pytest tests/test_ml_phase7.py
"""

import io
import json
import math
import os
import re
import shutil
from collections import OrderedDict
from pathlib import Path

import pandas as pd
import pytest
import torch
from PIL import Image
from torch import nn

os.environ.setdefault("MONGODB_URI", "mongodb://127.0.0.1:27017")  # lib/db + app/core/config read these at import
os.environ.setdefault("MONGODB_APP_DATABASE", "vayudrishti_test")  # never the real app DB

from fastapi.testclient import TestClient  # noqa: E402

import server  # noqa: E402
from ml.architecture import self_check  # noqa: E402
from ml.prediction.sequences import SequenceInputError  # noqa: E402
from repositories import cyclone_repository  # noqa: E402
from repositories.cyclone_repository import FileCycloneRepository, mongo_repository  # noqa: E402
from services import prediction_service  # noqa: E402
from services.ml_registry import MlRegistry, ModelSlot, registry  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]
MODELS = BACKEND / "models"
DATA_FILE = BACKEND / "app" / "data" / "cyclones" / "observations.csv.gz"
FIXTURES = Path(__file__).parent / "fixtures" / "ml"
EXPECTED = json.loads((FIXTURES / "expected.json").read_text(encoding="utf-8"))
CLASS_MAPPING = json.loads((MODELS / "classification" / "class_mapping.json").read_text(encoding="utf-8"))
CLASS_NAMES = [CLASS_MAPPING[k]["name"] for k in sorted(CLASS_MAPPING, key=int)]
AMPHAN, AMPHAN_T0 = "2020136N10088", "2020-05-18T18:00:00Z"  # held-out test storm
SID = re.compile(r"^\d{7}[NS]\d{5}$")
CYCLONE_IMAGE, CLEAR_IMAGE = EXPECTED["analyze"]["cyclone"], EXPECTED["analyze"]["no_cyclone"]


def iso(ts: pd.Timestamp) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def upload(name: str) -> dict:
    return {"file": (name, (FIXTURES / name).read_bytes(), "image/png")}


def assert_error(resp, status: int, code: str) -> dict:
    assert resp.status_code == status, resp.text
    body = resp.json()
    assert body["success"] is False and body["status"] == "error"
    assert body["error"]["code"] == code and body["error"]["message"]
    assert "Traceback" not in resp.text and ".py" not in resp.text and "\\" not in body["error"]["message"]
    return body


class ConstantNet(nn.Module):
    """Stands in for a network that emits a fixed output (e.g. NaN), to test that outputs are validated."""

    def __init__(self, tail: tuple[int, ...], value: float):
        super().__init__()
        self.tail, self.value = tail, value

    def forward(self, x):
        return torch.full((x.shape[0], *self.tail), self.value)


# ---------------------------------------------------------------- fixtures

@pytest.fixture(scope="module")
def engines() -> MlRegistry:
    """The three real models, loaded once exactly as the FastAPI startup loads them."""
    loaded = MlRegistry()
    loaded.load(models_dir=MODELS, device="cpu")
    for slot in (loaded.identification, loaded.classification, loaded.prediction):
        assert slot.ready, f"{slot.key}: {slot.error_code} {slot.error_message}"
    return loaded


@pytest.fixture(scope="module")
def held_out() -> FileCycloneRepository:
    repo = FileCycloneRepository(DATA_FILE)
    repo.load()
    assert repo.ready, repo.error
    return repo


@pytest.fixture
def client(monkeypatch, engines, held_out):
    for key in ("identification", "classification", "prediction"):
        monkeypatch.setattr(registry, key, getattr(engines, key))
    monkeypatch.setattr(prediction_service, "repository", held_out)
    monkeypatch.setattr(prediction_service, "_cache", OrderedDict())  # every test runs the model afresh
    return TestClient(server.app)  # without `with`: the lifespan (index build, model loading) does not run


@pytest.fixture(scope="module")
def mongo():
    from app.db.mongo import connect_to_mongodb, mongodb
    try:
        connect_to_mongodb()
    except Exception as exc:
        pytest.skip(f"MongoDB cyclone_database not reachable: {exc}")
    return mongodb.cyclone_db


@pytest.fixture(scope="module")
def database_ids(mongo) -> dict:
    """Real ids from cyclone_database that are NOT in the held-out table, so MongoDB is their only source."""
    held = set(pd.read_csv(DATA_FILE, usecols=["storm_id"])["storm_id"])
    counts = list(mongo.cyclone_positions.aggregate([{"$group": {"_id": "$cyclone_id", "n": {"$sum": 1}}}, {"$sort": {"n": -1}}]))
    sid = next(c for c in counts if SID.fullmatch(c["_id"]) and c["_id"] not in held)
    sys_id = next(c for c in counts if c["_id"].startswith("SYS_"))
    return {"sid": sid["_id"], "sys": sys_id["_id"]}


# ---------------------------------------------------------------- artifact verification (load time)

def test_every_model_loads_and_passes_its_checks(engines):
    assert engines.identification.instance.info["architecture"] == "efficientnet_b0"
    classes = engines.classification.instance.classes
    assert [c["name"] for c in classes] == CLASS_NAMES and [c["id"] for c in classes] == list(range(len(CLASS_NAMES)))
    assert engines.prediction.instance.info["horizons_hours"] == [6, 12, 18, 24]
    assert {str(slot.instance.device) for slot in (engines.identification, engines.classification, engines.prediction)} == {"cpu"}


def test_self_check_rejects_a_wrong_output_shape():
    with pytest.raises(ValueError, match="expected"):
        self_check(nn.Linear(4, 3).eval(), (1, 4), (1, 2), torch.device("cpu"))


def test_checkpoint_that_disagrees_with_its_config_is_never_ready(tmp_path):
    target = tmp_path / "prediction"
    shutil.copytree(MODELS / "prediction", target)
    config = json.loads((target / "model_config.json").read_text(encoding="utf-8"))
    config["sequence"]["horizons_hours"] = [6, 12, 18, 24, 30]  # the checkpoint has 4 output horizons
    (target / "model_config.json").write_text(json.dumps(config), encoding="utf-8")
    fresh = MlRegistry()
    fresh.load(models_dir=tmp_path, device="cpu")
    assert not fresh.prediction.ready and fresh.prediction.state == "error" and fresh.prediction.error_code == "INVALID_MODEL_CONFIG"
    assert fresh.identification.state == "unavailable"  # simply not deployed in tmp_path


def test_app_main_serves_the_same_app():
    from app.main import app
    assert app is server.app


# ---------------------------------------------------------------- identification

@pytest.mark.parametrize("case", EXPECTED["identification"], ids=lambda c: c["file"])
def test_identify_real_images(client, case):
    resp = client.post("/api/ml/identify", files=upload(case["file"]))
    assert resp.status_code == 200, resp.text
    ident = resp.json()["identification"]
    assert ident["class_name"] == case["class_name"] and ident["detected"] is (case["class_name"] == "CYCLONE")
    assert set(ident["probabilities"]) == {"CYCLONE", "NO_CYCLONE"}
    assert math.isclose(sum(ident["probabilities"].values()), 1.0, abs_tol=1e-5)
    assert ident["confidence"] == pytest.approx(ident["probabilities"][ident["class_name"]])


def test_identify_rejects_bad_files(client):
    gif = io.BytesIO()
    Image.new("L", (256, 256), 128).save(gif, format="GIF")
    assert_error(client.post("/api/ml/identify"), 400, "NO_FILE")
    assert_error(client.post("/api/ml/identify", files={"file": ("x.png", b"not an image", "image/png")}), 415, "INVALID_FILE_TYPE")
    assert_error(client.post("/api/ml/identify", files={"file": ("x.gif", gif.getvalue(), "image/gif")}), 415, "INVALID_FILE_TYPE")


@pytest.mark.parametrize("path", ["/api/ml/identify", "/api/ml/analyze"])
def test_identification_model_unavailable(client, monkeypatch, path):
    monkeypatch.setattr(registry, "identification", ModelSlot("identification", error_code="MODEL_FILE_MISSING"))
    assert_error(client.post(path, files=upload(CYCLONE_IMAGE)), 503, "MODEL_NOT_LOADED")


# ---------------------------------------------------------------- classification

@pytest.mark.parametrize("case", EXPECTED["classification"], ids=lambda c: c["file"])
def test_classify_real_labelled_images(client, case):
    resp = client.post("/api/ml/classify", files=upload(case["file"]))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    probs = body["probabilities"]
    assert list(probs) == CLASS_NAMES  # the artifact's class mapping, in id order
    assert math.isclose(sum(probs.values()), 1.0, abs_tol=1e-5) and all(0.0 <= p <= 1.0 for p in probs.values())
    top = max(probs, key=probs.get)
    pred = body["prediction"]
    assert pred["class_name"] == top and CLASS_MAPPING[str(pred["class_id"])]["code"] == pred["class_code"] == case["class_code"]
    assert pred["confidence"] == pytest.approx(probs[top])


def test_classification_model_unavailable(client, monkeypatch):
    monkeypatch.setattr(registry, "classification", ModelSlot("classification", error_code="MODEL_LOAD_FAILED"))
    assert_error(client.post("/api/ml/classify", files=upload(CYCLONE_IMAGE)), 503, "MODEL_NOT_LOADED")
    body = client.post("/api/ml/analyze", files=upload(CYCLONE_IMAGE)).json()
    assert body["classification"] is None and body["classification_skipped_reason"] == "Classification model is not available."


@pytest.mark.parametrize("key,path,tail", [("identification", "/api/ml/identify", (2,)), ("classification", "/api/ml/classify", (4,))])
def test_non_finite_image_model_output_is_rejected(client, monkeypatch, engines, key, path, tail):
    monkeypatch.setattr(getattr(engines, key).instance, "model", ConstantNet(tail, float("nan")))
    assert_error(client.post(path, files=upload(CYCLONE_IMAGE)), 500, "INVALID_MODEL_OUTPUT")


# ---------------------------------------------------------------- prediction

def test_predict_real_held_out_storm(client):
    resp = client.post("/api/ml/predict", json={"cyclone_id": AMPHAN, "timestamp": AMPHAN_T0})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "success" and body["issuedAt"] == AMPHAN_T0
    assert [step["hours"] for step in body["forecast"]] == [6, 12, 18, 24]
    t0 = pd.Timestamp(AMPHAN_T0)
    for step in body["forecast"]:
        assert pd.Timestamp(step["forecastTime"]) == t0 + pd.Timedelta(hours=step["hours"])
        assert -90 <= step["latitude"] <= 90 and -180 <= step["longitude"] < 180
        assert all(math.isfinite(step[k]) for k in ("latitude", "longitude", "windSpeedKt", "pressure"))
        assert step["confidence"] is None  # the model produces no calibrated confidence
    assert body["confidence"] is None and body["uncertainty"]["method"] == "empirical"


def test_prediction_error_states(client, held_out, monkeypatch):
    first = held_out.get_observations(AMPHAN)["time"].iloc[0]
    assert_error(client.post("/api/ml/predict", json={"cyclone_id": AMPHAN, "timestamp": iso(first)}), 422, "INSUFFICIENT_HISTORY")
    before = first - pd.Timedelta(days=2)
    assert_error(client.post("/api/ml/predict", json={"cyclone_id": AMPHAN, "timestamp": iso(before)}), 404, "OBSERVATION_NOT_FOUND")
    assert_error(client.get(f"/api/cyclones/{AMPHAN}/prediction", params={"at": "not-a-time"}), 400, "INVALID_TIME")
    assert_error(client.post("/api/ml/predict", json={"cyclone_id": AMPHAN, "timestamp": "not-a-time"}), 422, "VALIDATION_ERROR")
    assert_error(client.post("/api/ml/predict", json={"cyclone_id": "not-a-storm"}), 400, "INVALID_CYCLONE_ID")
    monkeypatch.setattr(registry, "prediction", ModelSlot("prediction", error_code="MODEL_FILE_MISSING"))
    assert_error(client.post("/api/ml/predict", json={"cyclone_id": AMPHAN, "timestamp": AMPHAN_T0}), 503, "MODEL_NOT_LOADED")


@pytest.mark.parametrize("column,blank", [("dist2land_km", float("nan")), ("nature", "")])
def test_required_inputs_are_never_imputed(engines, held_out, column, blank):
    engine = engines.prediction.instance
    t0 = pd.Timestamp(AMPHAN_T0)
    storm = held_out.get_observations(AMPHAN)
    end = int(storm.index[storm["time"] == t0][0])
    storm.loc[end - 2, column] = blank  # one fix inside the 24 h window
    with pytest.raises(SequenceInputError) as info:
        engine.predict(storm, t0)
    assert info.value.code == "MISSING_FEATURES" and info.value.status_code == 422
    assert len(engine.predict(held_out.get_observations(AMPHAN), t0).steps) == 4  # the untouched record forecasts


@pytest.mark.parametrize("value,code", [(float("nan"), "INVALID_MODEL_OUTPUT"), (1e6, "PREDICTION_OUT_OF_RANGE")])
def test_impossible_forecast_is_rejected_not_repaired(client, monkeypatch, engines, value, code):
    monkeypatch.setattr(engines.prediction.instance, "model", ConstantNet((4, 4), value))
    assert_error(client.post("/api/ml/predict", json={"cyclone_id": AMPHAN, "timestamp": AMPHAN_T0}), 500, code)


# ---------------------------------------------------------------- MongoDB cyclone_database (read-only)

def test_database_repository_reads_a_real_storm(mongo, database_ids):
    storm = mongo_repository.get_observations(database_ids["sid"])
    assert storm is not None and len(storm) >= 1
    assert storm["dist2land_km"].isna().all() and (storm["nature"] == "").all()  # absent in the collection: never invented
    assert storm["time"].is_monotonic_increasing and storm["time"].is_unique
    assert mongo_repository.get_observations("1999001N00000") is None


def test_database_storms_get_a_truthful_no_forecast(client, mongo, database_ids):
    assert_error(client.post("/api/ml/predict", json={"cyclone_id": database_ids["sys"]}), 422, "INSUFFICIENT_HISTORY")
    body = client.post("/api/ml/predict", json={"cyclone_id": database_ids["sid"]}).json()
    assert body["success"] is False and body["error"]["code"] in {"INSUFFICIENT_HISTORY", "MISSING_FEATURES"}
    for cyclone_id in (database_ids["sid"], database_ids["sys"]):
        track = client.get(f"/api/cyclones/{cyclone_id}/track")
        assert track.status_code == 200 and track.json()["points"], track.text
    assert_error(client.post("/api/ml/predict", json={"cyclone_id": "1999001N00000"}), 404, "CYCLONE_NOT_FOUND")


def test_database_unavailable_is_reported_not_hidden(client, monkeypatch):
    monkeypatch.setattr(cyclone_repository.MongoCycloneRepository, "_handle", staticmethod(lambda: None))
    assert_error(client.post("/api/ml/predict", json={"cyclone_id": "1999001N00000"}), 503, "DATABASE_UNAVAILABLE")
    assert client.post("/api/ml/predict", json={"cyclone_id": AMPHAN, "timestamp": AMPHAN_T0}).status_code == 200  # no DB needed
    database = next(c for c in client.get("/api/ml/status").json()["components"] if c["id"] == "cyclone-database")
    assert database["status"] == "unavailable"


# ---------------------------------------------------------------- unified POST /api/ml/analyze

def test_analyze_no_cyclone_stops_after_identification(client):
    body = client.post("/api/ml/analyze", files=upload(CLEAR_IMAGE)).json()
    assert body["identification"]["class_name"] == "NO_CYCLONE" and body["classification"] is None
    assert body["prediction"]["available"] is False and body["prediction"]["reason"] == "NO_CYCLONE_DETECTED"
    assert body["prediction"]["forecast"] is None and "prediction" not in body["models"]


def test_analyze_cyclone_without_storm_id(client):
    body = client.post("/api/ml/analyze", files=upload(CYCLONE_IMAGE)).json()
    assert body["classification"]["class_code"] and body["prediction"]["reason"] == "STORM_ID_REQUIRED"
    assert body["prediction"]["forecast"] is None


def test_analyze_full_pipeline_with_history(client):
    form = {"storm_id": AMPHAN, "timestamp": AMPHAN_T0}
    resp = client.post("/api/ml/analyze", files=upload(CYCLONE_IMAGE), data=form)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["identification"]["class_name"] == "CYCLONE" and body["classification"]["class_code"]
    prediction = body["prediction"]
    assert prediction["available"] is True and prediction["reason"] is None
    forecast = prediction["forecast"]
    assert forecast["cycloneId"] == AMPHAN and forecast["issuedAt"] == AMPHAN_T0 and len(forecast["forecast"]) == 4
    direct = client.post("/api/ml/predict", json={"cyclone_id": AMPHAN, "timestamp": AMPHAN_T0}).json()
    assert forecast["forecast"] == direct["forecast"]  # the same service and model output as POST /api/ml/predict
    assert set(body["models"]) == {"identification", "classification", "prediction"}


def test_analyze_cyclone_with_insufficient_history(client, held_out):
    first = held_out.get_observations(AMPHAN)["time"].iloc[0]
    body = client.post("/api/ml/analyze", files=upload(CYCLONE_IMAGE), data={"storm_id": AMPHAN, "timestamp": iso(first)}).json()
    assert body["classification"] is not None
    assert body["prediction"]["available"] is False and body["prediction"]["reason"] == "INSUFFICIENT_HISTORY"
    assert body["prediction"]["forecast"] is None


def test_analyze_database_storm(client, mongo, database_ids):
    body = client.post("/api/ml/analyze", files=upload(CYCLONE_IMAGE), data={"storm_id": database_ids["sys"]}).json()
    assert body["prediction"]["available"] is False and body["prediction"]["reason"] == "INSUFFICIENT_HISTORY"


# ---------------------------------------------------------------- GET /api/ml/status + Swagger

def test_status_is_read_from_the_registry(client, monkeypatch):
    body = client.get("/api/ml/status").json()
    assert body["status"] == "ok"
    for key in ("identification", "classification", "prediction"):
        assert body[key]["status"] == "ready" and body[key]["modelLoaded"] is True
        assert body[key]["device"] == "cpu" and body[key]["modelVersion"] and body[key]["modelName"]
    monkeypatch.setattr(registry, "classification", ModelSlot("classification", loading=True))
    monkeypatch.setattr(registry, "prediction", ModelSlot("prediction", error_code="MODEL_SELF_CHECK_FAILED", error_message="shape"))
    body = client.get("/api/ml/status").json()
    assert body["status"] == "degraded" and body["identification"]["status"] == "ready"
    assert body["classification"]["status"] == "loading" and body["classification"]["modelLoaded"] is False
    assert body["prediction"]["status"] == "error" and body["prediction"]["errorCode"] == "MODEL_SELF_CHECK_FAILED"
    assert body["prediction"]["message"] == "Model failed its load-time self-check."


def test_swagger_documents_the_ml_endpoints(client):
    spec = client.get("/openapi.json").json()
    for path, method in (("/api/ml/identify", "post"), ("/api/ml/classify", "post"), ("/api/ml/predict", "post"),
                         ("/api/ml/analyze", "post"), ("/api/ml/status", "get")):
        operation = spec["paths"][path][method]
        assert operation["summary"] and "200" in operation["responses"], path
    assert {"AnalysisPrediction", "ModelStatus", "PredictionRequest"} <= set(spec["components"]["schemas"])
