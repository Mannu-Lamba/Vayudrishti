# VayuDrishti — track, intensity and pressure prediction (pipeline stage 3)

Forecasts a tropical cyclone's position, 1-minute sustained wind and central pressure at **T+6, 12, 18
and 24 h** from its own last 24 h of best-track observations. It is AI-assisted decision support, not a
replacement for IMD / RSMC forecasts, and it is not validated for operational use.

```
Current observation → IBTrACS history → validation + UTC sync + UI area → 24 h window (5 fixes)
  → features → GRU → shared representation → track / intensity / pressure heads
  → changes from T0 → post-processing → FastAPI JSON → React (map, timeline, charts)
```

**One code path.** Validation, feature engineering, sequence construction, baselines, the model and
post-processing live in `backend/ml/prediction/`. This workspace imports that package, so the API builds
a forecast exactly the way the model was trained and evaluated. `tests/test_prediction_api.py` also
checks that the served forecast equals an in-process run.

## Data

The source is **IBTrACS v04r01** (`H:/ibtracs.since1980.list.v04r01.csv`, read only). The table below
shows how the raw file is narrowed down.

| step | rows |
|---|---|
| IBTrACS since 1980 | 309,258 |
| seasons ≥ 2000, basins NI SI WP EP SP | 139,829 |
| main track | 132,085 |
| synoptic 6-hourly fixes (00/06/12/18 UTC) | **66,528** fixes, **2,156** storms, 2000 → 2025-10-31 |

**Fields used**

| role | IBTrACS field | notes |
|---|---|---|
| storm id | `SID` | also the API's cyclone id |
| time | `ISO_TIME` | UTC |
| position | `LAT`, `LON` | longitude wrapped to [-180, 180) |
| wind | `USA_WIND` | kt, 1-minute sustained; the same basis in every basin, as used for the classification labels; missing on 16.9 % of fixes |
| pressure | `USA_PRES` | hPa; missing on 20.7 % of fixes |
| stage | `NATURE` | |
| distance to land | `DIST2LAND` | km |
| UI area | `BASIN` + `SUBBASIN` | NI falls back to longitude when `SUBBASIN` is absent; mapped by `ui_area` from identification_model |

**Not available, so not used and never invented:**
- sea-surface temperature;
- vertical wind shear;
- humidity;
- environmental pressure.

None of these exist in the project; they would need a reanalysis such as ERA5.

**Satellite features are not used yet.** GridSat crops exist only for the fixes sampled for the image
models, while a window needs one for every 6-hourly step. The full audit is in `reports/data_audit.md`.

## Sequences

- **Window.** `history_window_hours: 24` every `observation_interval_hours: 6` gives 5 fixes (T-24 … T0).
  The horizons are `[6, 12, 18, 24]`. All of these values live in `configs/prediction.yaml` and
  `ml/prediction/config.py`; nothing else hardcodes them. Adding 36, 48 or 72 h is a config change plus
  retraining and evaluation.
- **Matching rule.** Fixes must lie on the regular 6-hourly grid (`time_tolerance_minutes: 0`), and any
  gap makes a window unusable. Targets are matched by timestamp, never by row position.
- **Forecast time.** A requested forecast time snaps to the latest fix at most 3 h earlier.
- **Features.** There are 29 per step:
  - position, relative to T0 and absolute;
  - motion over the previous 6 h (Δlat, Δlon, speed, direction), plus a missing flag;
  - wind and pressure with their 6 h tendencies, plus missing flags;
  - distance to land;
  - storm age;
  - day of year;
  - tropical / extratropical stage;
  - a one-hot UI area.
- **Missing data.** Continuous features are standardised with training statistics only; a missing value
  becomes 0 (the training mean) and keeps its flag. Missing targets are masked out of the loss, never
  imputed.
- **Samples.** There are **49,559**. Skipped: 8,345 fixes without four future positions (storm ends) and
  220 fixes in storms too short to fill a window.

## Storm-level split (leakage prevention)

Every storm goes to exactly one split. The split is stratified by the storm's area at its first fix,
with seed 42. `scripts/check_leakage.py` runs 10 checks: no storm, observation or sample origin is shared
between splits.

**STORM-LEVEL DATA LEAKAGE CHECK: PASS.** Training refuses to start unless this passes for the current
files, which it verifies with SHA-256 hashes.

| split | storms | samples |
|---|---|---|
| train | 1,509 | 34,911 |
| val | 323 | 7,248 |
| test | 324 (301 with samples) | 7,400 |

## Model and training

- **Architecture.**
  - Input: [5 steps × 29 features].
  - Encoder: a 2-layer GRU (hidden 128, dropout 0.2).
  - The last hidden state goes through a shared FC (128, ReLU, dropout) to three heads: track (Δlat,
    Δlon × 4 horizons), intensity (Δwind × 4) and pressure (Δpressure × 4).
  - 178,704 parameters.
  - `architecture: lstm | transformer` swaps the encoder without touching the rest.
- **Targets.** Changes from T0, standardised per horizon. Persistence is therefore the zero prediction.
- **Loss.** Masked Huber (δ = 1) per head, weighted track 1.0, intensity 0.5, pressure 0.5. Track is the
  primary output. The standardised targets make the three losses comparable in scale. Pressure targets
  are missing more often, so its loss is noisier.
- **Optimisation.**
  - AdamW, learning rate 1e-3, weight decay 1e-4, batch 512.
  - ReduceLROnPlateau (factor 0.5, patience 4) and gradient clipping at 1.0.
  - The model is selected on validation mean track error, with early stopping after 12 epochs without
    improvement.
  - Deterministic, seed 42; CUDA when available, otherwise CPU.
- **Run.** It stopped at epoch 36; the best epoch was 24, with a validation mean track error of 98.2 km,
  wind MAE 6.89 kt and pressure MAE 4.99 hPa. It took about 1 s per epoch on an RTX 4060.
- **Outputs.** `backend/models/prediction/` holds `best_model.pth`, `last_model.pth` and `model_config.json`,
  the last containing the window, feature list, normalisation, uncertainty radii and versions.

## Results — 7,400 forecasts from 301 held-out test storms

Figures in brackets are 95 % confidence intervals from a storm-level bootstrap.

**Track error, great-circle (haversine) km**

| forecast | T+6h | T+12h | T+18h | T+24h |
|---|---|---|---|---|
| **model** | **34.3** (32.8–35.8) | **73.5** (70.4–76.7) | **119.5** (114.4–124.9) | **171.5** (164.0–179.5) |
| persistence | 106.0 | 210.8 | 315.6 | 420.6 |
| motion extrapolation (last 12 h) | 39.7 | 87.1 | 143.2 | 207.3 (197.2–217.5) |

**Wind and pressure**

| forecast | T+6h | T+12h | T+18h | T+24h | T+24h pressure MAE |
|---|---|---|---|---|---|
| **model** wind MAE | **3.5 kt** | **5.9 kt** | **8.1 kt** | **10.0 kt** | **7.3 hPa** |
| persistence wind MAE | 4.1 kt | 7.8 kt | 11.2 kt | 14.3 kt | 10.3 hPa |

**Skill (percentage error reduction)**

| comparison | T+6h | T+12h | T+18h | T+24h |
|---|---|---|---|---|
| track vs extrapolation | 13.7 | 15.6 | 16.5 | 17.3 |
| wind vs persistence | 14.0 | 24.9 | 28.1 | 30.2 |

The full per-horizon latitude and longitude MAE, RMSE, bias, p90 and paired-difference confidence
intervals are in `reports/test_metrics.json`.

**By region (model, T+24h).** Areas below 100 samples or 5 storms would report counts only; none fell
below that here.

| area | samples | storms | track km | wind MAE kt |
|---|---|---|---|---|
| North Indian Ocean | 358 | 28 | 125.9 | 11.2 |
| Arabian Sea | 199 | 11 | 119.6 | 13.2 |
| Bay of Bengal | 159 | 19 | 133.8 | 8.5 |
| South Indian Ocean | 2,006 | 67 | 174.2 | 10.7 |
| Pacific Ocean | 5,036 | 212 | 173.7 | 9.6 |
| Western Pacific | 2,695 | 107 | 193.5 | 10.0 |
| Eastern Pacific | 1,484 | 72 | 122.9 | 8.7 |
| Southern Pacific | 857 | 38 | 199.1 | 10.6 |

The North Indian Ocean test set is small (28 storms), so treat its numbers as indicative.

## Uncertainty, confidence and post-processing

- **Uncertainty radius.** The radius is the 67th percentile of **validation** track errors at each lead
  time, as in the NHC cone: 36.9, 80.1, 129.8 and 184.9 km. On the unseen test storms these radii
  contained 66.5 %, 66.1 %, 65.7 % and 65.3 % of errors. The wind bands (±3.8 to ±11.0 kt) contained
  66–68 % of errors.
- **What the radius means.** It is the model's typical error. It is **not** a per-forecast calibrated
  probability, and the API says so.
- **Confidence.** Always `null`, because the model produces no calibrated confidence. The UI shows "Not
  produced by the model", never 0 %.
- **Post-processing rules.** They are in `ml/prediction/postprocess.py`, and every adjustment is flagged:
  - latitude outside [-90, 90] rejects the forecast;
  - longitude is wrapped to [-180, 180);
  - wind above 200 kt or pressure outside [870, 1030] hPa rejects the forecast;
  - negative wind is set to 0 and flagged;
  - motion faster than 120 km/h is flagged;
  - timestamps are T0 + h and strictly increasing.
- **Rules on the test set.** 6,172 forecasts were accepted, none rejected and none flagged. 1,228 had no
  observed wind or pressure at T0; the API refuses those with `MISSING_CURRENT_INTENSITY`.

## Serving

These are FastAPI endpoints; see `backend/README.md`.

- `GET /api/cyclones/{SID}/prediction?at=ISO` returns the forecast.
- `GET /api/cyclones/{SID}/track` returns the observed fixes.
- `GET /api/cyclones/prediction-cases` returns the held-out storms and their valid forecast times.

The data flow is repository (`backend/app/data/cyclones/observations.csv.gz`, **held-out test storms only**,
exported by `scripts/export_backend_data.py`), then `services/prediction_service.py` (validation,
caching, errors), then `ml/prediction/inference.py`. The inference class is loaded once at startup, and
`/api/health` reports `prediction_model: true` only when it is.

Example:

```
GET /api/cyclones/2020136N10088/prediction?at=2020-05-18T18:00:00Z  → 200
AMPHAN, observed 140 kt / 910 hPa at 14.9°N 86.6°E
T+6h  15.94°N 86.93°E 132 kt  (observed 15.60°N 86.80°E 125 kt)
T+24h 19.36°N 88.85°E 101 kt  (observed 18.30°N 87.20°E 105 kt)
```

Standalone inference, from `backend/`:

```python
import pandas as pd
from ml.prediction.inference import PredictionInference
from repositories.cyclone_repository import FileCycloneRepository

repo = FileCycloneRepository(); repo.load()
engine = PredictionInference("models/prediction", device="cpu")
result = engine.predict(repo.get_observations("2020136N10088"), pd.Timestamp("2020-05-18T18:00:00Z"))
for step in result.steps:
    print(step.hours, step.latitude, step.longitude, step.wind_kt, step.pressure_hpa, step.uncertainty_radius_km)
```

## Commands

Training uses the CUDA venv of identification_model:

```bash
cd prediction_model
PY=../identification_model/.venv/Scripts/python.exe
$PY scripts/build_dataset.py        # IBTrACS → data/processed/observations.csv.gz + reports/data_audit.md
$PY scripts/create_splits.py        # storm-level split → data/splits/storm_splits.csv
$PY scripts/check_leakage.py        # STORM-LEVEL DATA LEAKAGE CHECK: PASS / FAIL
$PY scripts/evaluate_baseline.py    # persistence + extrapolation → reports/baseline_metrics.md
$PY src/train.py                    # → backend/models/prediction/ (add --architecture lstm|transformer)
$PY src/evaluate.py                 # held-out test → reports/test_metrics.{json,md}, results/test_predictions.csv
$PY scripts/export_backend_data.py  # held-out storms → backend/app/data/cyclones/
```

Restart the backend after retraining; models load once at startup.

## Limitations

- **No environmental or satellite predictors.** The model extrapolates storm behaviour from its own
  track, and cannot know about steering flow, shear or ocean heat. Errors grow with lead time
  accordingly.
- **Best-track input.** It uses post-season best track, which is smoother and more accurate than the
  real-time fixes an operational system receives. Real-time skill would be lower.
- **Intensity basis.** Intensity is the JTWC/NHC 1-minute wind; IMD bulletins use a 3-minute wind.
- **Missing current values.** 17 % of fixes lack wind and 21 % lack pressure; no forecast is served from
  those times.
- **Horizons.** Only 6–24 h. Longer horizons need retraining and evaluation first.
- **Storage.** Forecasts are cached in memory, not persisted. MongoDB has no cyclone or prediction
  collections yet.

## Remaining work before production

- A real-time data feed (IMD/JTWC fixes) behind a Mongo-backed repository.
- Environmental predictors (e.g. ERA5 shear and SST).
- Per-fix satellite embeddings from the identification model.
- Probabilistic outputs, via quantile heads or an ensemble, with calibrated uncertainty.
- Persisted, versioned forecast storage.
- Longer horizons.
- Authentication on the ML endpoints.
- Evaluation against official forecast errors.
