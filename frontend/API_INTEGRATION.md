# VayuDrishti frontend — API integration guide

The frontend runs in two modes and switches between them without component changes:

```
DEMO MODE  (VITE_USE_MOCK_DATA=true, default)      LIVE MODE  (VITE_USE_MOCK_DATA=false)
React → hooks → services → src/data/mock           React → hooks → services → FastAPI → ML → dataset
```

Components never import mock data or build URLs. They call hooks (`src/hooks/`), hooks call
services (`src/services/`), and every service function is a single `serve({ demo, live })`
switch (`src/services/dataMode.ts`). Every result carries a `source` (`demo` | `live` |
`historical`) that the UI shows as a **DEMO DATA / LIVE API / DEMO / MOCK MODEL OUTPUT** badge.

The real dataset is **not** bundled into the website. It stays behind the backend; the browser
only receives what a view needs (filtered by region, paged, date-bounded).

## Environment variables

Copy `frontend/.env.example` to `frontend/.env.local`. Only public values — every `VITE_*`
variable is compiled into the browser bundle. Never put API secrets, database credentials or
model keys here.

| Variable | Default | Meaning |
|---|---|---|
| `VITE_API_BASE_URL` | `/api` | FastAPI base URL, including `/api`. Relative keeps the httpOnly session cookie same-origin (Vite proxies `/api` → `http://localhost:8001` in dev). A cross-origin value such as `http://127.0.0.1:8001/api` requires the backend to allow the frontend origin (`CORS_ORIGINS` / `FRONTEND_URL`; localhost and 127.0.0.1 on ports 3000 and 5173 are allowed by default). Credentials are sent, so `*` is not enough. |
| `VITE_USE_MOCK_DATA` | `true` | `true` = demo data for cyclones, satellite, predictions, regions and model status. `false` = call the FastAPI endpoints below. |
| `VITE_API_TIMEOUT_MS` | `15000` | Per-request timeout. Streams (Claude analyst) only time out until headers arrive. |
| `VITE_PREDICTION_STRATEGY` | `resource` | Registry-driven prediction section: `resource` → `GET /api/cyclones/{id}/prediction`; `inference` → `POST /api/ml/predict` (same service, same body). The Track forecast panel always uses `POST /api/ml/predict`. |

Sign-in, sessions, audit, admin and the Claude analyst always use the real backend in both modes —
demo mode only replaces the dataset/ML-backed data.

## Modes and indicators

- **Top-bar pill** (`ApiStatusIndicator`): `Demo mode` · `Checking API` · `Live API` · `Syncing` · `API offline`.
  In live mode it probes `GET /api/health` every 30 s; any 2xx–4xx reply counts as reachable,
  network errors / timeouts / 5xx do not. `Live API` is never shown while the backend is unreachable.
- **Fallback:** when the API is unreachable, error panels and the top bar offer **Use demo data**.
  The fallback lasts for the browser session and shows `Demo fallback · live API configured` (pill
  tooltip) with a **Retry live** button.
- **Prediction page banner:** `USING DEMO PREDICTION` in demo mode, `LIVE MODEL OUTPUT` in live mode.

## Service → endpoint map

| Service (`src/services/`) | Function | Live endpoint |
|---|---|---|
| `regionApi` | `getRegions()` | `GET /api/regions` |
| | `getRegion(id)` | `GET /api/regions/{regionId}` |
| | `getCoastalDistricts()` | `GET /api/regions/coastal-districts` |
| `cycloneApi` | `getCyclones(query)` | `GET /api/cyclones?region=…&subregion=…&basin=…&startDate=…&endDate=…&active=…` |
| | `getCycloneById(id)` | `GET /api/cyclones/{id}` |
| | `getCycloneTrack(id, {start, end})` | `GET /api/cyclones/{id}/track?start=…&end=…` |
| | `getCycloneHistory(id, {page, pageSize, start, end})` | `GET /api/cyclones/{id}/history?…` |
| | `getRegionalObservation(selection, at)` | `GET /api/cyclones/regional-observation?region=…&subregion=…&at=…` |
| | `getCycloneArchive({region, year, page, pageSize})` | `GET /api/cyclones/archive?…` |
| | `getArchiveSummary()` | `GET /api/cyclones/archive/summary` |
| | `getRecentEvents(limit)` | `GET /api/events?limit=…` |
| `satelliteApi` | `getSatelliteSources(selection)` | `GET /api/satellite/sources?region=…&subregion=…` |
| | `getSatelliteObservations(query)` | `GET /api/satellite?region=…&source=…&channel=…&start=…&end=…&page=…` |
| | `getSatelliteObservationById(id)` | `GET /api/satellite/{id}` |
| | `getSatelliteCatalog(selection)` | composes the two calls above |
| | `getLatestSatelliteFrame(region)` | `GET /api/satellite/latest?region=…` |
| `predictionApi` ² | `getPrediction(id)` | `GET /api/cyclones/{id}/prediction` or `POST /api/ml/predict` (400/404/422 → `null`, "no prediction") |
| | `getTrackPrediction(id)` / `getIntensityPrediction(id)` | derived from `getPrediction` |
| | `getMlAssessment()` | no request: registry cyclones carry no image, so detection/classification stay `null` |
| | `getModelRegistry()` | `GET /api/ml/status` (per-model `identification` / `classification` / `prediction` status) |
| | `analyzeImage(file, metadata)` / `identifyImage` / `classifyImage` ¹ | `POST /api/ml/analyze` / `identify` / `classify` (multipart) |
| | `getPredictionCases()` ¹ | `GET /api/cyclones/prediction-cases` |
| | `getObservedTrack(id)` ¹ | `GET /api/cyclones/{id}/track` |
| | `predictCyclone(payload)` ¹ | `POST /api/ml/predict` |
| | `getPredictionServiceStatus()` ¹ | `GET /api/health` (backend reachable?) + `GET /api/ml/status` (`prediction.status`) |
| `apiClient` | `checkApiHealth()` | `GET /api/health` |

¹ These power the **Track forecast** panel (`components/prediction/ModelForecastPanel.tsx`, `/prediction#track-forecast`)
and the **Identify cyclone** panel (`ImageAnalysisPanel.tsx`, `/prediction#identify-cyclone`).

² Every ML function calls the live backend, in demo mode too: forecasts, classifications and model status can only
come from the trained models, so there is no mock ML output anywhere (`data/mock/predictions.ts` and `models.ts` were
removed in Phase 7). Demo mode still serves the non-ML registry pages (cyclone list, regions, satellite) until those
endpoints exist.

Region query values are UI region ids (`north_indian_ocean`, `south_indian_ocean`,
`pacific_ocean`) and subregion ids (`arabian_sea`, `bay_of_bengal`, `western_pacific`,
`eastern_pacific`, `southern_pacific`). They are **not** IBTrACS basin codes: the backend maps
them onto basins (NI, SI, WP, EP, SP). Arabian Sea and Bay of Bengal are both `NI`; `basin=`
filters on the dataset code itself.

### `GET /api/cyclones` filters

| Param | Example | Meaning |
|---|---|---|
| `region` | `north_indian_ocean` | UI region id (basin + position mapping happens in the backend) |
| `subregion` | `arabian_sea` | UI subregion id |
| `basin` | `NI` | IBTrACS basin code |
| `startDate`, `endDate` | `2026-09-01T00:00:00Z` | ISO 8601 bounds on the latest observation time |
| `active` | `true` | `true` = currently tracked systems (the operational registry), `false` = no longer tracked |

The browser only ever asks for the systems in view (region/subregion) plus the small active
registry used for region counts. Tracks are requested one cyclone at a time, when it is selected.

## Map data flow

```
Page (/cyclones, /, /satellite, /prediction)
  → useCyclones(selection)          GET /api/cyclones?region=…&subregion=…   → markers (toMapMarkers)
  → useCycloneMapData(selectedId)   GET /api/cyclones/{id}/track            → normalizeTrack → scene
                                    GET /api/cyclones/{id}/prediction       → forecast points (if any)
                                    GET /api/regions/coastal-districts       → risk-zone impacts
  → <CycloneMap cyclones selectedCycloneId scene districts status viewport />
```

`CycloneMap` (`src/components/map/`) is presentational: it receives markers, a scene, districts
and a loading/error status as props and never fetches. It cannot tell demo data from live data.

- **Markers:** every system in view is drawn; the selected one gets the full marker, others a
  point you can hover (details) and click (select). Colour comes from the category the API returns
  (`src/config/cycloneCategories.ts`); the frontend never derives a category from wind speed.
  Unknown category labels are drawn neutral.
- **Forecast:** drawn only from the prediction service. A cyclone without a prediction (404) shows
  its observed track and no forecast.
- **Viewports:** region/subregion cameras live in `src/config/mapViewports.ts`, keyed by UI region
  id. Regions added later through `GET /api/regions` fall back to their `mapBounds`.
- **URL state:** `/cyclones?region=…&subregion=…&cyclone=…` (`cyclone` accepts an id or a code such
  as `VD-001`; without `region` the page opens on that cyclone's own region/subregion).

## Response contracts

TypeScript interfaces in `src/types/` are the contract; keep them in sync with the Pydantic models.

| Endpoint | Type |
|---|---|
| `/regions` | `Region[]` (`types/region.ts`) |
| `/cyclones`, `/cyclones/{id}` | `CycloneData` (`types/cyclone.ts`) — includes `basin: "NI" \| "SI" \| "WP" \| "EP" \| "SP" \| …`, `category`, `status`, `location`, `observedAt`; tracks are not embedded |
| `/cyclones/{id}/track` | `CycloneTrackResponse` = `{ cycloneId, observedAt?, points: TrackPoint[], uncertaintyKm?, riskZones? }` (`types/track.ts`) |
| `/cyclones/{id}/history`, `/cyclones/archive` | `Paginated<T>` = `{ items, page, pageSize, total }` (`types/api.ts`) |
| `/cyclones/regional-observation` | `RegionalCycloneObservation` |
| `/satellite/sources` | `SatelliteSourceCatalog` = `{ availability, sources }` |
| `/satellite`, `/satellite/{id}` | `SatelliteObservation` (with `imageUrl` + `bounds` on `/{id}`) |
| `POST /ml/identify` | `ImageIdentifyResponse` (multipart `file`; snake_case) |
| `POST /ml/classify` | `ImageClassifyResponse` — `prediction` + `probabilities` keyed by the model's class names |
| `POST /ml/analyze` | `ImageAnalysisResponse` — `identification`, `classification` (null when no cyclone), `prediction: AnalysisPrediction` = `{ available, reason, message, forecast: PredictionResourceResponse \| null }` |
| `POST /ml/predict` | body `PredictionRequest` = `{ cycloneId, timestamp?, latitude?, longitude?, horizonsHours? }` (snake_case keys also accepted); response `PredictionResourceResponse` |
| `/cyclones/{id}/prediction` | `PredictionResourceResponse` — the same response model as `POST /ml/predict` |
| `/ml/status` | `ModelRegistry` = `{ status: "ok" \| "degraded", components, models, identification, classification, prediction: PredictionModelStatus }` |

Track payload (`GET /api/cyclones/{id}/track`):

```json
{
  "cycloneId": "vd-001",
  "observedAt": "2026-09-08T14:30:00Z",
  "points": [
    { "timestamp": "2026-09-07T14:30:00Z", "latitude": 13.4, "longitude": 89.2, "windKmh": 92,  "pressureHpa": 992, "category": "Cyclonic Storm" },
    { "timestamp": "2026-09-08T14:30:00Z", "latitude": 15.2, "longitude": 87.4, "windKmh": 118, "pressureHpa": 978, "category": "Severe Cyclonic Storm", "confidence": 0.947 }
  ],
  "riskZones": [
    { "id": "vd-001-severe", "level": "severe", "radiusKm": 130, "center": { "latitude": 15.2, "longitude": 87.4 }, "label": "Core wind field" }
  ]
}
```

- Send measured values only. `services/cycloneApi.ts::normalizeTrack` sorts the fixes, measures lead
  time from `observedAt` (or the last observed fix) and builds the `NOW` / `T-6h` labels.
- `category`, `confidence` (0–1 or percent), `forecast` and `uncertaintyRadiusKm` are optional.
- Use `start` / `end` to bound long tracks. A `404` means no track: the map keeps the marker at the
  registry position.

Prediction payload (both prediction endpoints):

```json
{
  "cycloneId": "vd-001",
  "issuedAt": "2026-09-08T14:35:00Z",
  "modelVersion": "vd-track v0.1",
  "forecast": [
    { "hours": 6,  "latitude": 15.8, "longitude": 86.8, "windSpeed": 124, "pressure": 973, "confidence": 0.91, "uncertaintyRadiusKm": 65 },
    { "hours": 12, "latitude": 16.4, "longitude": 86.2, "windSpeed": 131, "pressure": 969, "confidence": 0.88, "uncertaintyRadiusKm": 72 }
  ],
  "confidence": { "track": 0.91, "intensity": 0.87, "classification": 0.95, "detection": 0.947 },
  "uncertainty": { "method": "model", "polygon": [[86.1, 15.2], [85.9, 16.1], "…"], "confidenceLevel": 0.67 }
}
```

- `windSpeed` is km/h and `pressure` hPa. Confidence may be 0–1 or a percentage; the adapter normalises it.
- `forecastTime` per step is optional (derived from the observation time).
- `uncertainty.polygon` (a `[lon, lat]` ring) replaces the per-point corridor when present; without
  any radius the map draws a nominal corridor that is never presented as model output.
- Horizons are data-driven: returning 36 / 48 / 72 h steps needs no component change.
- A `404` from the resource endpoint means **no prediction available** (empty state, not an error).

**Implemented today** (backend `routers/ml.py` + `routers/cyclones.py`, trained GRU; see `prediction_model/README.md`):

- **Endpoints.** `POST /api/ml/predict` (the frontend's endpoint) and `GET /api/cyclones/{id}/prediction?at=…`
  run the same service (`services/prediction_service.py`) and return the same body. Ids are IBTrACS SIDs;
  only held-out test storms are served. `latitude`/`longitude` in the POST body are a consistency check of
  the position at T0 (400 `POSITION_MISMATCH` beyond 50 km), not model inputs; unknown keys are rejected.
- **Track forecast panel flow.** Select area · cyclone · T0 → **Run prediction** → `useRunPrediction` →
  `predictCyclone` → `POST /api/ml/predict` → `normalizePrediction` → `sceneFromPrediction` → `CycloneMap`
  (forecast dashed, observed history up to T0 solid). Nothing is requested before the button is pressed.
- **Panel states.** Badge (from `getPredictionServiceStatus`, polled every 30 s): `BACKEND UNAVAILABLE` ·
  `CHECKING MODEL` · `MODEL LOADING` · `MODEL READY` · `MODEL UNAVAILABLE` · `MODEL ERROR` · `PREDICTION RUNNING`.
  Body: idle · `PREDICTION RUNNING` · forecast · `PREDICTION NOT AVAILABLE` (422 `INSUFFICIENT_HISTORY` /
  `MISSING_CURRENT_INTENSITY`, 404 `OBSERVATION_NOT_FOUND`) · `MODEL UNAVAILABLE` (503 `MODEL_NOT_LOADED`) ·
  error (the backend's message, never a stack trace).
- **Error body.** Every `/api/ml/*` and `/api/cyclones/*` error is `{ success: false, status: "error",
  error: { code, message } }`, including malformed requests (422 `VALIDATION_ERROR`).
- **`confidence` is `null`** at both the top level and per step. The adapter keeps it `undefined`, and
  the UI shows "Not produced by the model", never 0 %.
- **Uncertainty.** `uncertainty.method` is `"empirical"`: `uncertaintyRadiusKm` is the 67th percentile of
  validation track errors. `UncertaintyPanel` says so; it is not a per-forecast probability.
- **Anchoring.** `current` carries the observed state at T0. `normalizePrediction` anchors on it when
  there is no registry entry.
- **No-prediction responses.** `422 INSUFFICIENT_HISTORY` and `MISSING_CURRENT_INTENSITY` mean "no
  prediction for this time". The panel shows **PREDICTION NOT AVAILABLE** instead of an error.
- **Not built yet.** The live cyclone registry (`/api/cyclones`, `/api/cyclones/{id}`) and `/api/regions`
  don't exist, so the page's main live-mode flow still has no registry to select from.

`services/predictionApi.ts::normalizePrediction` turns any of these into the `CyclonePrediction`
the UI renders; demo data goes through the same adapter.

## Errors

`services/apiClient.ts` raises `ApiError` with `kind` (`http`, `network`, `timeout`, `parse`,
`aborted`) and `status`. `describeApiError` maps them to operator wording (400, 401, 403, 404, 422,
429, 5xx, network, timeout) — raw bodies and stack traces are never shown. Cyclone registry and
track failures read **CYCLONE DATA UNAVAILABLE — Unable to retrieve cyclone information.** with
Retry and Use demo data; the map stays visible underneath. Hooks retry transient failures
(network, timeout, 429, 5xx) twice in live mode only.

## Going live checklist

1. Implement the endpoints above (or a subset — unimplemented ones surface as friendly error states).
2. Set `VITE_USE_MOCK_DATA=false` (and `VITE_API_BASE_URL` if the API is not same-origin).
3. Optionally add `GET /api/health` returning `{ "status": "ok", "version": "…" }`.
4. Rebuild. Badges switch to **LIVE API / LIVE MODEL OUTPUT** automatically.
