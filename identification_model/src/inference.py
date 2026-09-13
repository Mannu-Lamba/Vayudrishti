"""STEPS 26–29 — Inference: single image, batch folder, and a FastAPI-ready function.

    python src/inference.py --image path/to/image.png
    python src/inference.py --input_dir path/to/images [--output results/predictions.csv]

FastAPI (not implemented here):

    from src.inference import predict_image          # identification_model/ on sys.path
    result = predict_image(await upload.read())      # → JSON-ready dict

Every number comes from the trained checkpoint; nothing is hardcoded. The model expects the
training input domain: GridSat-style IR (~11 µm) brightness temperature rendered 180–310 K →
cold = bright, an 18°×18° scene roughly centred on the point of interest. Other imagery (visible
channel, colour-enhanced IR, different scales) is out of distribution and the output is unreliable.
"""

from __future__ import annotations

import argparse
import json
import sys
from functools import lru_cache
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import torch  # noqa: E402

from src.model import load_checkpoint  # noqa: E402
from src.preprocessing import build_transforms, load_grayscale, render_image, to_model_rgb  # noqa: E402
from src.utils import CLASS_NAMES, DISPLAY_NAMES, ROOT, ensure_dir, get_device  # noqa: E402

DEFAULT_CHECKPOINT = ROOT / "models" / "best_model.pth"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}


class CycloneIdentifier:
    """Loads the trained checkpoint once and classifies images as cyclone / no_cyclone."""

    def __init__(self, checkpoint: str | Path = DEFAULT_CHECKPOINT, device: str | None = None, verbose: bool = False):
        self.device = torch.device(device) if device else get_device(verbose=verbose)
        self.model, self.checkpoint = load_checkpoint(checkpoint, self.device)
        self.cfg = self.checkpoint["config"]
        self.transform = build_transforms(self.cfg, train=False)
        self.threshold = float(self.checkpoint.get("decision_threshold", 0.5))
        self.model_info = {
            "name": self.cfg["project"]["name"],
            "version": self.cfg["project"]["model_version"],
            "architecture": self.checkpoint["model_name"],
            "dataset_version": self.checkpoint.get("dataset_version"),
        }

    @torch.inference_mode()
    def predict_proba(self, images: list, batch_size: int = 64) -> np.ndarray:
        """(N, 2) array of [no_cyclone, cyclone] softmax outputs. Images: paths, bytes, PIL or arrays."""
        out = []
        for start in range(0, len(images), batch_size):
            batch = torch.stack([self.transform(to_model_rgb(load_grayscale(im))) for im in images[start:start + batch_size]])
            logits = self.model(batch.to(self.device))
            out.append(torch.softmax(logits.float(), dim=1).cpu().numpy())
        return np.concatenate(out) if out else np.zeros((0, 2), dtype=np.float32)

    def _result(self, probs: np.ndarray) -> dict:
        p_cyclone = float(probs[1])
        label = int(p_cyclone >= self.threshold)
        return {
            "label": label,
            "class": CLASS_NAMES[label],
            "display": DISPLAY_NAMES[label],
            "confidence": float(probs[label]),
            "probabilities": {"no_cyclone": float(probs[0]), "cyclone": p_cyclone},
        }

    def predict(self, image) -> dict:
        return self._result(self.predict_proba([image])[0])

    def predict_many(self, images: list, batch_size: int = 64) -> list[dict]:
        return [self._result(p) for p in self.predict_proba(images, batch_size)]

    def predict_brightness_temperature(self, bt_kelvin: np.ndarray) -> dict:
        """Classify a raw IR brightness-temperature crop (Kelvin, NaN = missing), rendered exactly
        as in training. Use this when the backend has satellite data rather than a PNG."""
        im = self.cfg["imagery"]
        return self.predict(render_image(np.asarray(bt_kelvin, dtype=np.float32), im["png_size"], im["bt_min_k"], im["bt_max_k"]))

    def api_response(self, image) -> dict:
        r = self.predict(image)
        return {
            "success": True,
            "prediction": {"class": r["class"], "confidence": round(r["confidence"], 4)},
            "probabilities": {k: round(v, 4) for k, v in r["probabilities"].items()},
            "model": {"name": self.model_info["name"], "version": self.model_info["version"]},
        }


@lru_cache(maxsize=2)
def get_identifier(checkpoint: str = str(DEFAULT_CHECKPOINT)) -> CycloneIdentifier:
    """Process-wide cached model (load once at FastAPI startup, reuse per request)."""
    return CycloneIdentifier(checkpoint)


def predict_image(image, checkpoint: str | Path | None = None) -> dict:
    """FastAPI entry point: image bytes / path / PIL image → JSON-serialisable dict."""
    try:
        return get_identifier(str(checkpoint or DEFAULT_CHECKPOINT)).api_response(image)
    except (OSError, ValueError) as exc:  # unreadable or unsupported image
        return {"success": False, "error": {"code": "invalid_image", "message": f"Could not read the image: {exc.__class__.__name__}"}}


def list_images(folder: Path) -> list[Path]:
    return sorted(p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTS)


def main() -> int:
    parser = argparse.ArgumentParser(description="VayuDrishti cyclone identification inference")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--image", type=Path, help="classify one image")
    group.add_argument("--input_dir", type=Path, help="classify every image under a folder")
    parser.add_argument("--output", type=Path, default=ROOT / "results" / "predictions.csv", help="CSV for --input_dir")
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--json", action="store_true", help="print the API JSON response for --image")
    args = parser.parse_args()

    ident = CycloneIdentifier(args.checkpoint, verbose=not args.json)
    if args.image:
        if args.json:
            print(json.dumps(ident.api_response(args.image), indent=2))
            return 0
        r = ident.predict(args.image)
        print(f"\nPrediction:\n{r['display']}\n\nConfidence:\n{r['confidence']:.3f}\n\nProbabilities:\n")
        print(f"NO_CYCLONE: {r['probabilities']['no_cyclone']:.3f}\nCYCLONE: {r['probabilities']['cyclone']:.3f}")
        return 0

    files = list_images(args.input_dir)
    readable, skipped = [], []
    for f in files:
        try:
            load_grayscale(f)
            readable.append(f)
        except (OSError, ValueError):
            skipped.append(f)
    results = ident.predict_many(readable)
    df = pd.DataFrame({
        "image": [str(f) for f in readable],
        "predicted_class": [r["display"] for r in results],
        "cyclone_probability": [round(r["probabilities"]["cyclone"], 6) for r in results],
        "no_cyclone_probability": [round(r["probabilities"]["no_cyclone"], 6) for r in results],
        "confidence": [round(r["confidence"], 6) for r in results],
    })
    ensure_dir(args.output.parent)
    df.to_csv(args.output, index=False)
    print(f"Classified {len(df)} images → {args.output}  ({df.predicted_class.value_counts().to_dict()})")
    for f in skipped:
        print(f"  skipped unreadable file: {f}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
