# VayuDrishti — cyclone identification model (PS-70, stage 1)

Binary image classification of IR satellite scenes: **CYCLONE** (1) / **NO_CYCLONE** (0).
It is the first stage of the pipeline: satellite image → identification → classification → track prediction.

The datasets contain no bounding boxes, so this is image classification, not object detection.

## Layout

```
identification_model/
├── configs/config.yaml        every path and hyperparameter
├── data/
│   ├── raw/                   snapshots of the original sources + SHA-256, GridSat crops (gitignored)
│   ├── processed/             rendered 256×256 PNGs (gitignored)
│   ├── metadata/              candidates, rejections, near-duplicates, identification_dataset.csv
│   └── splits/                train.csv / val.csv / test.csv
├── scripts/                   dataset pipeline (audit → candidates → fetch → clean → select → split → leakage → figures)
├── src/                       dataset, model, train, evaluate, inference, preprocessing, utils
├── models/                    best_model.pth, last_model.pth (gitignored), model_config.json
├── reports/                   audit, cleaning, dataset v1, model report, figures, errors
└── results/                   prediction CSVs (gitignored)
```

## Setup

```powershell
cd identification_model
py -3.11 -m venv .venv
.\.venv\Scripts\python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
.\.venv\Scripts\python -m pip install -r requirements.txt
```

A GPU is used automatically when available (CUDA → MPS → CPU).

## Rebuild everything

Run from `identification_model/` with the venv Python:

```powershell
python scripts/audit_datasets.py        # 1  audit both datasets, snapshot + checksum the originals
python scripts/prepare_candidates.py    # 2  metadata cleaning, TS-only positives, reserve fixes, negative rule checks
python scripts/fetch_gridsat_crops.py   # 3  GridSat-B1 IR crops for both classes (OPeNDAP, resumable, ~20 min)
python scripts/clean_dataset.py         # 4  image cleaning, rendering, exact/near duplicate detection
python scripts/build_manifest.py        # 5  2,000 + 2,000 stratified selection → identification_dataset.csv
python scripts/create_splits.py         # 6  storm/event-grouped 70/15/15 split (seed 42)
python scripts/check_leakage.py         # 7  must print DATA LEAKAGE CHECK: PASS
python scripts/visualize_dataset.py     # 8  figures + reports/dataset_v1_report.md
python src/train.py                     # 9  EfficientNet-B0 baseline (refuses to run without a PASS)
python src/evaluate.py                  # 10 held-out test metrics, curves, region-wise, hard negatives
python scripts/error_analysis.py        # 11 false positives / negatives
python scripts/write_model_report.py    # 12 reports/model_report.md
python scripts/audit_datasets.py --verify   # originals still byte-identical
```

## Inference

```powershell
python src/inference.py --image path/to/image.png
python src/inference.py --image path/to/image.png --json
python src/inference.py --input_dir path/to/images --output results/predictions.csv
```

The input should match the training domain:
- GridSat-style IR (~11 µm) brightness temperature;
- 180–310 K mapped linearly to 8 bits, with cold cloud tops bright;
- an 18°×18° scene, north up, roughly centred on the point of interest.

Anything else is out of distribution, for example visible-channel images, colour-enhanced IR or very different scales. For raw satellite data, use `CycloneIdentifier.predict_brightness_temperature(bt_kelvin)`: it renders the data exactly as training did.

## FastAPI integration (for the backend — not wired in yet)

```python
import sys
sys.path.insert(0, "/path/to/identification_model")   # or install as a package

from fastapi import APIRouter, File, UploadFile
from src.inference import get_identifier, predict_image

router = APIRouter()
get_identifier()          # load the model once at import/startup

@router.post("/api/identification")
def identify(file: UploadFile = File(...)):            # sync def → runs in FastAPI's threadpool
    return predict_image(file.file.read())
```

`predict_image` returns a JSON-ready dict:

```json
{"success": true,
 "prediction": {"class": "cyclone", "confidence": 0.972},
 "probabilities": {"no_cyclone": 0.028, "cyclone": 0.972},
 "model": {"name": "VayuDrishti Cyclone Identification Model", "version": "v1"}}
```

Unreadable uploads return `{"success": false, "error": {"code": "invalid_image", ...}}`. The probabilities are softmax outputs, not calibrated probabilities; see the calibration section of `reports/model_report.md`.

Latency measured on the development laptop (RTX 4060 Laptop GPU; model already loaded):

| Device | Single image | Batch of 64 |
|---|---|---|
| GPU (CUDA) | ~16 ms | ~4.5 ms per image |
| CPU | ~23 ms | ~18 ms per image |

A CPU-only server is fine for per-request use.
