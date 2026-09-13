"""ML endpoints (/api/ml/*) and /api/health against the live backend.

Like the other suites here, this hits a running uvicorn process (BACKEND_URL), not an in-process app:

    BACKEND_URL=http://127.0.0.1:8002 pytest tests/test_classification_api.py

tests/fixtures/ml/ holds real held-out TEST-split images; expected.json records the probabilities the
training pipeline (identification_model evaluation) produced for them. The parity tests therefore check
that the backend's preprocessing and weights reproduce training — not just that the endpoint answers.
Regenerate the fixtures with identification_model/scripts/classification/make_backend_fixtures.py.
"""

import io
import json
import math
import os
from pathlib import Path

import httpx
import pytest
from PIL import Image

API_URL = f"{os.environ.get('BACKEND_URL', 'http://localhost:8001')}/api"
FIXTURES = Path(__file__).parent / "fixtures" / "ml"
EXPECTED = json.loads((FIXTURES / "expected.json").read_text(encoding="utf-8"))
TOLERANCE = float(EXPECTED["tolerance"])
CLASS_CODES = {"D-DD", "CS-SCS", "VSCS", "ESCS-SuCS"}
ENDPOINTS = ["/ml/identify", "/ml/classify", "/ml/analyze"]


def api_url(path: str = "") -> str:
    return f"{API_URL}{path}"


def post(path: str, files=None, data=None) -> httpx.Response:
    return httpx.post(api_url(path), files=files, data=data, timeout=60.0)


def fixture_upload(name: str) -> dict:
    return {"file": (name, (FIXTURES / name).read_bytes(), "image/png")}


def png_bytes(size=(256, 256), fmt="PNG") -> bytes:
    buf = io.BytesIO()
    Image.new("L", size, 128).save(buf, format=fmt)
    return buf.getvalue()


def assert_error(resp: httpx.Response, status: int, code: str) -> None:
    assert resp.status_code == status, resp.text
    body = resp.json()
    assert body["success"] is False
    assert body["error"]["code"] == code
    assert body["error"]["message"]
    assert "Traceback" not in resp.text and 'File "' not in resp.text


@pytest.fixture(scope="module")
def services() -> dict:
    resp = httpx.get(api_url("/health"), timeout=30.0)
    assert resp.status_code == 200, resp.text
    return resp.json()["services"]


@pytest.fixture(scope="module")
def classifier_ready(services) -> None:
    if not services["classification_model"]:
        pytest.fail("Classification model is not loaded on the backend under test")


# ---------------------------------------------------------------- health / status

def test_health_reports_every_service(services):
    body = httpx.get(api_url("/health"), timeout=30.0).json()
    assert set(body["services"]) == {"api", "identification_model", "classification_model", "prediction_model"}
    assert body["services"]["api"] is True
    assert isinstance(body["services"]["prediction_model"], bool)
    deployed = services["identification_model"] and services["classification_model"] and services["prediction_model"]
    assert body["status"] == ("ok" if deployed else "degraded")


def test_status_lists_components_without_server_paths():
    resp = httpx.get(api_url("/ml/status"), timeout=30.0)
    assert resp.status_code == 200, resp.text
    components = {c["id"]: c for c in resp.json()["components"]}
    assert {"identification-model", "classification-model", "prediction-model"} <= set(components)
    for c in components.values():
        assert "\\" not in (c["detail"] or "") and ".pth" not in (c["detail"] or "")


# ---------------------------------------------------------------- classification

@pytest.mark.parametrize("case", EXPECTED["classification"], ids=lambda c: c["file"])
def test_classify_matches_training_pipeline(classifier_ready, case):
    resp = post("/ml/classify", files=fixture_upload(case["file"]))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["prediction"]["class_code"] == case["class_code"]
    for name, expected in case["probabilities"].items():
        assert body["probabilities"][name] == pytest.approx(expected, abs=TOLERANCE), name


def test_classify_response_is_a_consistent_distribution(classifier_ready):
    body = post("/ml/classify", files=fixture_upload(EXPECTED["classification"][0]["file"])).json()
    probs = body["probabilities"]
    assert len(probs) == 4
    assert math.isclose(sum(probs.values()), 1.0, abs_tol=1e-4)
    top = max(probs, key=probs.get)
    assert body["prediction"]["class_name"] == top
    assert body["prediction"]["confidence"] == pytest.approx(probs[top], abs=1e-6)
    assert body["prediction"]["class_code"] in CLASS_CODES
    assert body["prediction"]["imd_categories"]
    assert body["model"]["architecture"] == "efficientnet_b0"
    assert body["inference"]["processing_time_ms"] > 0


def test_classify_is_deterministic(classifier_ready):
    name = EXPECTED["classification"][1]["file"]
    first = post("/ml/classify", files=fixture_upload(name)).json()["probabilities"]
    second = post("/ml/classify", files=fixture_upload(name)).json()["probabilities"]
    assert first == second


def test_metadata_is_echoed_not_inferred(classifier_ready):
    form = {"region": "bay_of_bengal", "basin": "NI", "storm_id": "TEST-1", "timestamp": "2020-05-20T00:00:00Z"}
    body = post("/ml/classify", files=fixture_upload(EXPECTED["classification"][0]["file"]), data=form).json()
    assert body["metadata"] == form


# ---------------------------------------------------------------- identification + pipeline

@pytest.mark.parametrize("case", EXPECTED["identification"], ids=lambda c: c["file"])
def test_identify_matches_training_pipeline(case):
    resp = post("/ml/identify", files=fixture_upload(case["file"]))
    assert resp.status_code == 200, resp.text
    ident = resp.json()["identification"]
    assert ident["class_name"] == case["class_name"]
    assert ident["cyclone_probability"] == pytest.approx(case["cyclone_probability"], abs=TOLERANCE)


def test_analyze_cyclone_runs_classification(classifier_ready):
    resp = post("/ml/analyze", files=fixture_upload(EXPECTED["analyze"]["cyclone"]))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["identification"]["class_name"] == "CYCLONE"
    assert body["classification"] is not None
    assert body["classification"]["class_code"] in CLASS_CODES
    assert body["classification_skipped_reason"] is None
    # no storm_id → no observation history → no forecast (never one fabricated from the image)
    assert body["prediction"] == {"available": False, "reason": "STORM_ID_REQUIRED", "message": body["prediction"]["message"], "forecast": None}
    assert set(body["models"]) == {"identification", "classification"}


def test_analyze_no_cyclone_skips_classification():
    resp = post("/ml/analyze", files=fixture_upload(EXPECTED["analyze"]["no_cyclone"]))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["identification"]["class_name"] == "NO_CYCLONE"
    assert body["classification"] is None
    assert body["classification_skipped_reason"]
    assert body["prediction"]["available"] is False and body["prediction"]["reason"] == "NO_CYCLONE_DETECTED"
    assert body["prediction"]["forecast"] is None


# ---------------------------------------------------------------- upload validation

@pytest.mark.parametrize("path", ENDPOINTS)
def test_missing_file_is_rejected(path):
    assert_error(post(path), 400, "NO_FILE")


@pytest.mark.parametrize("path", ENDPOINTS)
def test_empty_file_is_rejected(path):
    assert_error(post(path, files={"file": ("empty.png", b"", "image/png")}), 400, "EMPTY_FILE")


def test_text_file_is_rejected():
    assert_error(post("/ml/classify", files={"file": ("notes.png", b"not an image", "image/png")}), 415, "INVALID_FILE_TYPE")


def test_unsupported_image_format_is_rejected():
    assert_error(post("/ml/classify", files={"file": ("anim.gif", png_bytes(fmt="GIF"), "image/gif")}), 415, "INVALID_FILE_TYPE")


def test_truncated_image_is_rejected():
    data = (FIXTURES / EXPECTED["classification"][0]["file"]).read_bytes()
    assert_error(post("/ml/classify", files={"file": ("cut.png", data[: len(data) // 2], "image/png")}), 400, "CORRUPTED_IMAGE")


def test_tiny_image_is_rejected():
    assert_error(post("/ml/classify", files={"file": ("tiny.png", png_bytes((32, 32)), "image/png")}), 400, "UNSUPPORTED_DIMENSIONS")


def test_oversized_upload_is_rejected():
    data = b"\x89PNG\r\n\x1a\n" + b"\0" * (10 * 1024 * 1024)
    assert_error(post("/ml/classify", files={"file": ("big.png", data, "image/png")}), 413, "FILE_TOO_LARGE")
