# VayuDrishti backend

FastAPI app (`server.py`), mounted under `/api`. The existing routers (auth, analyst, sessions, audit,
admin, …) are unchanged. This document covers the ML services added for PS-70:

| stage | model | endpoint |
|---|---|---|
| 1. identification | CYCLONE / NO_CYCLONE on an IR scene | `POST /api/ml/identify` |
| 2. intensity classification | 4 IMD intensity groups | `POST /api/ml/classify` |
| 1 → 2 pipeline | classification runs only when stage 1 finds a cyclone | `POST /api/ml/analyze` |
| 3. track / intensity / pressure forecast | GRU on the storm's last 24 h of best track → T+6 … 24 h | `POST /api/ml/predict` (frontend) · `GET /api/cyclones/{id}/prediction` |

Training code: the image models live in `../identification_model/`, the prediction model in `../prediction_model/`.
The backend loads the exported artifacts. The prediction core (`ml/prediction/`) is shared with that
training workspace, so serving and training use the same features, sequences and post-processing.

## Layout

```
backend/
  server.py                     app + lifespan: loads both models ONCE at startup (asyncio.to_thread)
  routers/ml.py                 POST /ml/identify | /ml/classify | /ml/analyze | /ml/predict, GET /ml/status
  routers/health.py             GET /health
  routers/cyclones.py           GET /cyclones/prediction-cases | /cyclones/{id}/track | /cyclones/{id}/prediction
  services/prediction_service.py  repository → sequence → inference → post-processing → response (+ cache)
  repositories/cyclone_repository.py  storm histories (file-backed today; the model never touches storage)
  ml/prediction/                config, features, sequences, baseline, model, postprocess, inference
  services/ml_registry.py       loads models once; a failed load is recorded, never crashes the API
  services/*_service.py         validate upload → run engine → Pydantic response (no torch in routers)
  services/errors.py            MlServiceError → {success: false, error: {code, message}}
  ml/imaging.py                 upload validation + the evaluation transform used in training
  ml/architecture.py            EfficientNet-B0 + head; torch.load(weights_only=True), strict=True
  ml/identification/, ml/classification/   inference engines
  models/ml.py                  Pydantic contracts (mirrored by hand in frontend/src/types/model.ts)
  models/identification/        best_model.pth, model_config.json
  models/classification/        best_model.pth, model_config.json, class_mapping.json
  models/prediction/            best_model.pth, last_model.pth, model_config.json
  app/data/cyclones/            observations.csv.gz + manifest.json (held-out IBTrACS test storms)
  tests/test_classification_api.py, tests/fixtures/ml/   endpoint + training-parity tests
```

## Classification classes

Labels are **IMD (RSMC New Delhi) intensity categories** applied to the IBTrACS v04r01 `USA_WIND`
(JTWC/NHC 1-minute sustained wind), grouped into 4 classes. No class is invented: each is a set of IMD
categories with IMD's knot thresholds. `USA_WIND` is used because it is the only wind reported on one
averaging basis in every basin.

| id | code | name | IMD categories | USA_WIND |
|---|---|---|---|---|
| 0 | `D-DD` | Depression / Deep Depression | Depression, Deep Depression | 17–33 kt |
| 1 | `CS-SCS` | Cyclonic Storm / Severe Cyclonic Storm | Cyclonic Storm, Severe Cyclonic Storm | 34–63 kt |
| 2 | `VSCS` | Very Severe Cyclonic Storm | Very Severe Cyclonic Storm | 64–89 kt |
| 3 | `ESCS-SuCS` | Extremely Severe / Super Cyclonic Storm | Extremely Severe Cyclonic Storm, Super Cyclonic Storm | ≥ 90 kt |

IMD itself uses a 3-minute wind. On the 3,563 North Indian Ocean fixes that carry both winds, the IMD wind
gives the same class 69.6 % of the time; the 1-minute label is one class higher in 25.6 % and lower in 4.8 %.
Expect disagreement with official IMD bulletins near class boundaries.

## Dataset (cls-v1.0)

Full report: `identification_model/reports/classification/classification_dataset_report.md`.

- **Fixes:** Dataset A (PS-70 finalized IBTrACS metadata, 139,829 fixes) → main track, `NATURE = TS`,
  3-hourly synoptic, `USA_WIND` ≥ 17 kt → 86,063 labelled fixes from 1,954 storms, basins NI SI WP EP SP, 2000+.
- **Candidates:** 5,600 (1,400 per class) from 1,768 storms, at most 6 fixes per storm, ≥ 12 h apart,
  spread round-robin over the 6 UI areas and over storms.
- **Imagery:** NOAA GridSat-B1 v02r01 IRWIN CDR (~11 µm), 18°×18° crop centred on the fix, exact 3-hourly
  slot, rendered 180–310 K → 8-bit with cold cloud tops bright, 256×256, north up — the same rendering as
  the identification model.
- **Download shortfall:** NOAA's OPeNDAP server stopped answering (HTTP 503 / dropped connections) after
  4,899 crops; the remaining 701 candidates — all ESCS/SuCS — were not fetched (661 never attempted, 40 failed
  after retries). The fetch script is resumable; see *Retraining*.
- **Cleaning:** 82 crops rejected for > 2 % missing pixels; 0 exact duplicates; 0 near-duplicate pairs
  (dHash + thumbnail correlation); 0 corrupted files. Clean pool 4,817.
- **Final:** **4,438 images** from 1,704 storms — D-DD 1,250 · CS-SCS 1,250 · VSCS 1,250 · ESCS-SuCS 688.
- **Split (storm/event grouped):** 1,608 leakage groups (union of same storm, crops overlapping within 12 h,
  near-duplicates) → `StratifiedGroupKFold` on label|area → train 3,105 / val 666 / test 667 images
  (1,192 / 259 / 253 storms). **Leakage check: PASS** — no storm, group, identical pixels, near-duplicate or
  overlapping crop is shared between splits; training refuses to start unless this check passes.

## Preprocessing (identical in training and serving)

`decode → single channel ('L') → 3 identical channels → resize 224×224 (bilinear, antialiased) → [0, 1] →
ImageNet mean/std`. No augmentation at inference. `ml/imaging.py` mirrors the evaluation transform in
`identification_model/src/preprocessing.py`; `tests/test_classification_api.py` checks that the backend
reproduces the training pipeline's probabilities on held-out test images.

## Training configuration (classification)

EfficientNet-B0 (ImageNet weights) → global average pool → FC 256 → ReLU → Dropout 0.3 → 4-way linear →
softmax. AdamW (lr 3e-4, weight decay 1e-4), cosine schedule, batch 32, up to 40 epochs, early stopping after
8 epochs without a validation macro-F1 improvement, class-weighted cross-entropy (ESCS-SuCS is the smaller
class), mixed precision, seed 42. Train-split-only augmentation: rotation ±15°, scale 0.9–1.0, horizontal and
vertical flips, brightness/contrast ±5 % (kept small — cloud-top temperature is itself an intensity cue),
Gaussian noise σ 0.01. Config: `identification_model/configs/classification.yaml`.

## Test-set results (classification v1)

Held-out test split: 667 images from 253 storms that appear in neither training nor validation. Best epoch
17 of 25 (early stopping; validation macro-F1 0.639). Full outputs in
`identification_model/reports/classification/` (metrics JSON, per-class report, confusion matrix, ROC/PR,
calibration, region metrics, error analysis) and `identification_model/results/classification/test_predictions.csv`.

| metric | value |
|---|---|
| accuracy | 0.628 (95 % CI 0.590–0.662, storm-group bootstrap) |
| macro F1 | 0.628 (95 % CI 0.590–0.664) |
| balanced accuracy | 0.626 |
| adjacent accuracy (within one class) | 0.964 (95 % CI 0.950–0.977) |
| top-2 accuracy | 0.915 |
| macro ROC-AUC (one-vs-rest) | 0.868 |
| expected calibration error | 0.253 (mean confidence 0.875 vs accuracy 0.628) |

| class | precision | recall | F1 | test images |
|---|---|---|---|---|
| D-DD | 0.697 | 0.674 | 0.685 | 184 |
| CS-SCS | 0.545 | 0.411 | 0.468 | 190 |
| VSCS | 0.581 | 0.816 | 0.678 | 190 |
| ESCS-SuCS | 0.785 | 0.602 | 0.681 | 103 |

Confusion matrix (rows actual, columns predicted, order D-DD · CS-SCS · VSCS · ESCS-SuCS):
`[124 42 18 0] [53 78 58 1] [0 19 155 16] [1 4 36 62]` — 224 of the 248 errors land in an adjacent class.
North Indian Ocean (106 test images): accuracy 0.670, adjacent accuracy 0.953, but only 4 of them are ESCS-SuCS.

**Limitations**

- Intensity from a single IR snapshot is inherently limited (operational Dvorak analysis uses the storm's
  recent history). Training accuracy reached 0.95 while validation stayed near 0.62: the model overfits.
- Overconfident: 60 % of test predictions have confidence ≥ 0.9 and 117 of those are wrong. Treat
  `confidence` as a ranking score, not a probability.
- CS-SCS (34–63 kt) is the hardest class; it is confused with both neighbours.
- ESCS-SuCS has 688 images (NOAA outage, see *Dataset*), only 16 of them in the North Indian Ocean.
- Labels are 1-minute `USA_WIND` with IMD thresholds, not IMD's official 3-minute category.
- Inputs outside the training domain (not GridSat-style 18°×18°, north-up, 180–310 K with cold = bright)
  give unreliable answers; the API cannot detect that.
- `/api/ml/*` do not require sign-in yet.

## API

All ML endpoints take `multipart/form-data`:

| field | required | notes |
|---|---|---|
| `file` | yes | PNG, JPEG, TIFF, BMP or WebP; ≤ 10 MB; each side 64–8192 px |
| `region`, `basin`, `storm_id`, `timestamp` | no | echoed back in `metadata`; never inferred from the image. On `/api/ml/analyze`, `storm_id` (+ `timestamp`) also selects the storm history for stage 3 |

| method | path | returns |
|---|---|---|
| POST | `/api/ml/identify` | `IdentificationResponse` |
| POST | `/api/ml/classify` | `ClassificationResponse` — stage 2 alone; assumes the image shows a cyclone |
| POST | `/api/ml/analyze` | `AnalysisResponse` — identification; classification only if `CYCLONE`; a track forecast only if `storm_id`'s history supports one (`prediction: {available, reason, message, forecast}`) |
| POST | `/api/ml/predict` | `PredictionResponse` — JSON body, see [Track prediction](#track-prediction-stage-3) |
| GET | `/api/ml/status` | `status` (ok · degraded), per-model `identification` / `classification` / `prediction` (ready · loading · unavailable · error, device, version), components + model metadata |
| GET | `/api/health` | `{status: "ok" \| "degraded", version, timestamp, services: {api, identification_model, classification_model, prediction_model}}` |

`confidence` is the maximum softmax probability — a model score, not a calibrated probability.

```bash
curl -F "file=@ir_crop.png" -F "basin=NI" http://127.0.0.1:8001/api/ml/analyze
```

```python
import requests

with open("ir_crop.png", "rb") as fh:
    r = requests.post("http://127.0.0.1:8001/api/ml/classify",
                      files={"file": ("ir_crop.png", fh, "image/png")}, data={"basin": "NI"}, timeout=60)
body = r.json()
if body["success"]:
    print(body["prediction"]["class_code"], body["prediction"]["confidence"], body["probabilities"])
else:
    print(r.status_code, body["error"]["code"], body["error"]["message"])
```

A real response (`POST /api/ml/analyze` with `tests/fixtures/ml/ident_cyclone_IMG1856.png` and `basin=WP`):

```json
{
  "success": true,
  "identification": {
    "detected": true, "class_name": "CYCLONE",
    "confidence": 0.9999998807907104, "cyclone_probability": 0.9999998807907104,
    "probabilities": {"NO_CYCLONE": 7.542726621068141e-08, "CYCLONE": 0.9999998807907104}
  },
  "classification": {
    "class_id": 2, "class_name": "Very Severe Cyclonic Storm", "class_code": "VSCS",
    "confidence": 0.987916111946106, "imd_categories": ["Very Severe Cyclonic Storm"],
    "probabilities": {
      "Depression / Deep Depression": 4.5998258428880945e-05,
      "Cyclonic Storm / Severe Cyclonic Storm": 0.00022864087077323347,
      "Very Severe Cyclonic Storm": 0.987916111946106,
      "Extremely Severe / Super Cyclonic Storm": 0.01180924754589796
    }
  },
  "classification_skipped_reason": null,
  "prediction": {
    "available": false, "reason": "STORM_ID_REQUIRED", "forecast": null,
    "message": "A track forecast is computed from the storm's observation history, not from the image. Send storm_id (and the image's timestamp) to run it."
  },
  "metadata": {"region": null, "basin": "WP", "storm_id": null, "timestamp": null},
  "models": {
    "identification": {"name": "cyclone-identification", "version": "v1", "architecture": "efficientnet_b0"},
    "classification": {"name": "cyclone-classification", "version": "v1", "architecture": "efficientnet_b0"}
  },
  "inference": {"processing_time_ms": 46.22, "preprocessing_ms": 2.96, "model_ms": 41.98}
}
```

### Errors

Every failure returns `{"success": false, "error": {"code": "...", "message": "..."}}` — never a stack trace
(details go to the server log).

| HTTP | code | when |
|---|---|---|
| 400 | `NO_FILE` | no `file` field |
| 400 | `EMPTY_FILE` | zero-byte upload |
| 413 | `FILE_TOO_LARGE` | more than 10 MB |
| 415 | `INVALID_FILE_TYPE` | not an image, or not PNG/JPEG/TIFF/BMP/WebP |
| 400 | `CORRUPTED_IMAGE` | image cannot be fully decoded (e.g. truncated) |
| 400 | `UNSUPPORTED_DIMENSIONS` | a side under 64 px or over 8192 px, or too many pixels |
| 500 | `PREPROCESSING_FAILED` / `INFERENCE_FAILED` | unexpected failure inside the model step |
| 500 | `INVALID_MODEL_OUTPUT` | the network returned NaN/inf or probabilities that are not a distribution (nothing is shown) |
| 503 | `MODEL_NOT_LOADED` | the model's artifacts are missing, failed to load, or failed the load-time self-check |

Prediction adds `INVALID_CYCLONE_ID`, `CYCLONE_NOT_FOUND`, `OBSERVATION_NOT_FOUND`, `INSUFFICIENT_HISTORY`,
`MISSING_FEATURES`, `MISSING_CURRENT_INTENSITY`, `PREDICTION_OUT_OF_RANGE`, `DATA_UNAVAILABLE` and
`DATABASE_UNAVAILABLE` (see [Track prediction](#track-prediction-stage-3)).

A model that fails to load does not stop the API: its endpoints answer 503, `/api/health` and `/api/ml/status`
report `"degraded"`, and the other routers keep working.

### Inference safeguards (Phase 7)

- **Load once, verify at load.** `services/ml_registry.py` loads the three engines at startup. Each checks its
  required files, rebuilds the recorded architecture with `strict` weights, checks the class mapping / feature list /
  `model_spec` against its config, then runs a self-check (zero input of the training shape → expected output shape,
  finite). Any failure leaves the model not ready (`MODEL_SELF_CHECK_FAILED`, `INVALID_MODEL_CONFIG`, …).
- **Outputs are validated, not repaired.** Image models: probabilities must be finite, in [0, 1] and sum to 1
  (`INVALID_MODEL_OUTPUT`). Prediction: post-processing rejects out-of-range positions, winds and pressures; the
  only adjustments (wind floored at 0, implausible motion) are flagged in the response and logged.
- **Required inputs are never imputed.** Distance to land and storm nature were never missing in training, so a window
  without them is `MISSING_FEATURES` (422). Wind/pressure gaps inside the window are handled as in training (a
  missing-flag feature); at T0 both must be observed.
- **MongoDB (read-only).** Storms outside the held-out table are looked up in `cyclone_database`
  (`repositories/cyclone_repository.py` `MongoCycloneRepository`). Its positions lack distance to land and nature and
  no storm there has a 5-fix 6-hourly window, so such storms get `INSUFFICIENT_HISTORY` / `MISSING_FEATURES` — and
  their observed track via `/api/cyclones/{id}/track`. A database that cannot be reached is `DATABASE_UNAVAILABLE`.
- **Startup log.** `✅ … model loaded` / `❌ … model unavailable (CODE)` per model, `✅ MongoDB connected`, then one
  `Startup complete` / `Startup degraded` summary line.
- **Entry points.** `uvicorn server:app` and `uvicorn app.main:app` serve the same app.

## Running

```bash
cd backend
py -3.11 -m venv .venv && .venv\Scripts\activate          # Linux/macOS: python3.11 -m venv .venv && . .venv/bin/activate
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu   # CPU build is enough
pip install -r requirements.txt                           # emergentintegrations==0.2.0 comes from Emergent's package index
```

| variable | purpose |
|---|---|
Template: `backend/.env.example` (copy to `backend/.env`).

| variable | purpose |
|---|---|
| `MONGODB_URI`, `MONGODB_APP_DATABASE`, `MONGODB_CYCLONE_DATABASE` | required at import by `lib/db.py` and `app/core/config.py` (the ML routes themselves do not use MongoDB). The app DB holds users, sessions and audit; the cyclone DB holds the extracted cyclones, positions and satellite observations (`app/db/mongo.py`, `GET /api/database/health`). `lib/db.py` still accepts the older `MONGO_URL` / `DB_NAME` |
| `CORS_ORIGINS`, `FRONTEND_URL` | browser origins allowed cross-origin (comma-separated). Unset → `http://localhost:3000`, `http://127.0.0.1:3000`, `http://localhost:5173`, `http://127.0.0.1:5173`. `*` switches credentials off. Not needed for the default same-origin `/api` proxy |
| `ML_MODELS_DIR` | folder holding `identification/`, `classification/` and `prediction/` (default `backend/models`) |
| `ML_DEVICE` | `cpu` or `cuda` (default: `cuda` when available) |
| `CYCLONE_DATA_PATH` | observation table for the prediction service (default `backend/app/data/cyclones/observations.csv.gz`) |
| `APP_VERSION` | reported by `/api/health` and Swagger (default `1.0`) |

```bash
uvicorn server:app --host 0.0.0.0 --port 8001
# Windows, local: .venv\Scripts\python.exe -m uvicorn server:app --host 127.0.0.1 --port 8001
```

Swagger UI: `http://127.0.0.1:8001/docs` (OpenAPI JSON at `/openapi.json`).

Models load once at startup; restart the server after replacing the files in `models/`.

## Tests

Like the other suites here, the ML tests call a running server:

```bash
BACKEND_URL=http://127.0.0.1:8001 pytest tests/test_classification_api.py
```

They cover health/status, training-pipeline parity for both models (probabilities within 1e-4 of the
training code run in fp32 on held-out test images in `tests/fixtures/ml/`), response consistency, determinism,
the identification → classification gate, `prediction: null`, and every upload error code.

## Retraining the classifier

```bash
cd identification_model
python scripts/classification/prepare_candidates.py                        # label audit + candidates + class_mapping.json
python scripts/fetch_gridsat_crops.py --config configs/classification.yaml # resumable; fetches only missing crops
python scripts/classification/build_dataset.py                             # cleaning, duplicates, balanced selection
python scripts/create_splits.py --config configs/classification.yaml
python scripts/check_leakage.py --config configs/classification.yaml       # training refuses to start without PASS
python scripts/classification/write_dataset_report.py
python src/train.py --config configs/classification.yaml                   # writes backend/models/classification/
python src/evaluate_classification.py                                      # reports/classification/, results/classification/
python scripts/classification/make_backend_fixtures.py                     # refresh parity fixtures
```

## Track prediction (stage 3)

Model, data and results: `../prediction_model/README.md`. On 301 held-out test storms the T+24h track
error is 171.5 km, against 207.3 km for motion extrapolation and 420.6 km for persistence. The T+24h
wind MAE is 10.0 kt, against 14.3 kt for persistence.

| method | path | returns |
|---|---|---|
| POST | `/api/ml/predict` | forecast for `{cyclone_id, timestamp?, latitude?, longitude?, horizons_hours?}` — the frontend's endpoint |
| GET | `/api/ml/status` | `prediction.status`: `ready` · `loading` · `unavailable` (files not deployed) · `error` (load failed) |
| GET | `/api/cyclones/prediction-cases?region=&subregion=&basin=` | held-out storms with `forecastOrigins` (times a forecast can start from) |
| GET | `/api/cyclones/{id}/track?start=&end=` | observed fixes (`CycloneTrackResponse`; wind/pressure `null` when not observed) |
| GET | `/api/cyclones/{id}/prediction?at=` | forecast from the latest fix ≤ `at` (default: the newest fix) |

- **Cyclone ids** are IBTrACS SIDs, e.g. `2020136N10088` (AMPHAN).
- **Forecast fields.** Each step has `hours`, `forecastTime`, `latitude`, `longitude`, `windSpeed`
  (km/h), `windSpeedKt`, `pressure` (hPa), `category` (IMD, derived from the predicted wind),
  `uncertaintyRadiusKm`, `windSpeedRange` and `flags`.
- **Always null.** `confidence` is `null` everywhere, because the model has no calibrated confidence.
- **Uncertainty.** The radius is empirical (`uncertainty.method = "empirical"`): the 67th percentile of
  validation errors.
- **Traceability.** Every response names `model.version`, `modelVersion`, `issuedAt` (the forecast time,
  T0), `generatedAt` and `input` (the window used).
- **Caching.** Forecasts are cached per storm, T0 and model version (LRU, 256 entries). `cached: true`
  marks a repeat.

| HTTP | code | when |
|---|---|---|
| 400 | `INVALID_CYCLONE_ID` / `INVALID_TIME` | malformed id or timestamp |
| 400 | `UNSUPPORTED_HORIZON` / `POSITION_MISMATCH` | POST only: a lead time the model does not produce, or a `latitude`/`longitude` more than 50 km from the observed fix at T0 |
| 422 | `VALIDATION_ERROR` | malformed body (missing `cyclone_id`, out-of-range latitude, unknown key, invalid JSON …) |
| 404 | `CYCLONE_NOT_FOUND` / `OBSERVATION_NOT_FOUND` | unknown storm, or no fix within 3 h before `at` |
| 422 | `INSUFFICIENT_HISTORY` | fewer than 5 regular fixes in the previous 24 h — "Insufficient historical observations for the selected cyclone." |
| 422 | `MISSING_CURRENT_INTENSITY` | wind or pressure not observed at T0 |
| 500 | `PREDICTION_OUT_OF_RANGE` / `INFERENCE_FAILED` | output failed the post-processing checks, or inference failed |
| 503 | `MODEL_NOT_LOADED` / `DATA_UNAVAILABLE` | model or observation table not loaded |

Every error body is `{"success": false, "status": "error", "error": {"code": …, "message": …}}`; no stack traces.

```bash
curl -X POST http://127.0.0.1:8001/api/ml/predict -H "Content-Type: application/json" \
  -d '{"cyclone_id": "2020136N10088", "timestamp": "2020-05-18T18:00:00Z", "latitude": 14.9, "longitude": 86.6}'
curl "http://127.0.0.1:8001/api/cyclones/2020136N10088/prediction?at=2020-05-18T18:00:00Z"   # same result
```

`POST /api/ml/predict` and the GET endpoint share `prediction_service.predict()` (one cache, one response model).
The model's only input is the storm's observed history ending at `timestamp`; `latitude`/`longitude` are an
optional check that the client means the same fix, and unknown keys are rejected with 422 rather than ignored.

Tests: `pytest tests/test_prediction_core.py tests/test_ml_predict_inprocess.py` (no server needed) and
`BACKEND_URL=http://127.0.0.1:8001 pytest tests/test_prediction_api.py`.

- The core tests cover sequences, ordering, missing data, the split, baselines, haversine, the model,
  post-processing, real-model output ranges and the service's error paths.
- The in-process tests cover `POST /api/ml/predict` and `/api/ml/status` in the states a running server cannot be
  forced into (model not loaded, loading, load error), request validation (structured 422) and CORS.
- The API tests cover schema, POST ↔ GET equality, parity with in-process inference, caching, no-data and error codes.
