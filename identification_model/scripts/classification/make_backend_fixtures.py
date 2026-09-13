#!/usr/bin/env python3
"""Backend parity fixtures: a few held-out TEST images + what the training code predicts for them.

Copies images into backend/tests/fixtures/ml/ and writes expected.json. Images are chosen from the
evaluation outputs (results/test_predictions.csv, results/classification/test_predictions.csv); the
expected probabilities are then recomputed with the TRAINING code path (src/evaluate_classification.predict:
evaluation transform + the deployed checkpoint) on the CPU in fp32. backend/tests/test_classification_api.py
checks that the deployed backend reproduces them, i.e. that serving-time preprocessing and weights match
training.

Why recompute instead of copying the evaluation CSV: evaluation ran on the GPU, where PyTorch uses TF32
convolutions by default. That moves non-saturated probabilities by up to ~2e-3 (and the amount depends on the
batch), which would force a loose tolerance and hide a real preprocessing difference. In fp32 the backend
and the training code agree to ~1e-6.

Non-saturated examples are picked on purpose (a probability of 1.0 would hide preprocessing drift):
per class, the correctly classified test image whose confidence is closest to 0.75.

    python scripts/classification/make_backend_fixtures.py
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.evaluate_classification import predict  # noqa: E402
from src.model import load_checkpoint  # noqa: E402
from src.preprocessing import build_transforms  # noqa: E402
from src.utils import ensure_dir, load_config, project_path, task_classes  # noqa: E402

CONFIG = ROOT / "configs" / "classification.yaml"
OUT = ROOT.parent / "backend" / "tests" / "fixtures" / "ml"
TOLERANCE = 1e-4  # training code (fp32, CPU) vs backend (fp32): observed max difference ~1e-6
TARGET_CONFIDENCE = 0.75


def copy(image_path: str, name: str) -> str:
    shutil.copyfile(ROOT / image_path, OUT / name)
    return name


def training_pipeline_probs(checkpoint: Path, files: list[str]) -> np.ndarray:
    """Softmax outputs of the training code path (evaluation transform + checkpoint), CPU fp32."""
    device = torch.device("cpu")
    model, ckpt = load_checkpoint(checkpoint, device)
    return predict(model, build_transforms(ckpt["config"], train=False), [str(OUT / f) for f in files], device)


def main() -> int:
    cfg, id_cfg = load_config(CONFIG), load_config()
    classes = task_classes(cfg)
    ensure_dir(OUT)
    for old in OUT.glob("*.png"):
        old.unlink()

    # ---- classification: one correctly classified, non-saturated test image per class
    cls = pd.read_csv(project_path(cfg, "results", "test_predictions.csv"))
    picked = []
    for c in classes:
        pool = cls[(cls.true_class == c["code"]) & cls.correct]
        picked.append((c, pool.iloc[(pool.confidence - TARGET_CONFIDENCE).abs().argsort().iloc[0]]))
    cls_files = [copy(row.image_path, f"cls_{c['code']}_{row.image_id}.png") for c, row in picked]
    cls_probs = training_pipeline_probs(project_path(cfg, "models", "best_model.pth"), cls_files)
    classification = [{
        "file": name, "image_id": row.image_id, "true_class": c["code"], "usa_wind_kt": float(row.usa_wind_kt),
        "class_code": classes[int(p.argmax())]["code"],
        "probabilities": {k["name"]: float(p[k["id"]]) for k in classes},
    } for (c, row), name, p in zip(picked, cls_files, cls_probs)]

    # ---- identification: a clear cyclone, a clear non-cyclone and one non-saturated cyclone
    ident = pd.read_csv(ROOT / "results" / "test_predictions.csv")
    correct = ident[ident.actual_label == ident.predicted_label]
    cyclones = correct[correct.actual_label == 1]
    picks = {
        "cyclone": cyclones.sort_values("cyclone_probability", ascending=False).iloc[0],
        "no_cyclone": correct[correct.actual_label == 0].sort_values("cyclone_probability").iloc[0],
        "uncertain": cyclones.iloc[(cyclones.cyclone_probability - TARGET_CONFIDENCE).abs().argsort().iloc[0]],
    }
    files = {kind: copy(row.image_path, f"ident_{kind}_{row.image_id}.png") for kind, row in picks.items()}
    p_cyclone = training_pipeline_probs(project_path(id_cfg, "models", "best_model.pth"), list(files.values()))[:, 1]
    threshold = float(id_cfg["train"].get("decision_threshold", 0.5))
    identification = [{"file": files[kind], "image_id": row.image_id,
                       "class_name": "CYCLONE" if p >= threshold else "NO_CYCLONE", "cyclone_probability": float(p)}
                      for (kind, row), p in zip(picks.items(), p_cyclone)]

    expected = {
        "source": "held-out test images; probabilities from the training code path (evaluation transform + deployed "
                  "checkpoint) on CPU in fp32 — see make_backend_fixtures.py",
        "tolerance": TOLERANCE,
        "classification": classification,
        "identification": identification,
        "analyze": {"cyclone": files["cyclone"], "no_cyclone": files["no_cyclone"]},
    }
    (OUT / "expected.json").write_text(json.dumps(expected, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(classification) + len(identification)} fixtures + expected.json to {OUT}")
    for case in classification:
        print(f"  {case['file']}: {case['class_code']} p={max(case['probabilities'].values()):.4f}")
    for case in identification:
        print(f"  {case['file']}: {case['class_name']} p_cyclone={case['cyclone_probability']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
