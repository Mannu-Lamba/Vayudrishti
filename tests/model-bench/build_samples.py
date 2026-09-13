"""Picks the held-out samples the model test bench runs live -> samples.json.

A seeded random draw from the identification and classification TEST splits (images never used for
training or model selection). Wrong answers are kept: nothing is filtered on the model's output.
Run with the backend venv (it has pandas):  ..\\..\\backend\\.venv\\Scripts\\python.exe build_samples.py
"""

import json
import math
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
IDENTIFICATION = HERE.parents[1] / "identification_model"
SEED = 2026
PER_IDENT_CLASS = 8   # 8 cyclone + 8 no-cyclone images
PER_INTENSITY_CLASS = 3  # 3 images per IMD intensity group


def clean(value):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return value.item() if hasattr(value, "item") else value


def image_url_path(image_path: str) -> str:
    return image_path.replace("\\", "/").removeprefix("data/processed/")


def main() -> None:
    ident = pd.read_csv(IDENTIFICATION / "results" / "test_predictions.csv")
    picks = pd.concat([ident[ident["actual_label"] == label].sample(PER_IDENT_CLASS, random_state=SEED) for label in (1, 0)])
    identification = [{
        "id": row["image_id"],
        "image": image_url_path(row["image_path"]),
        "truth": "CYCLONE" if row["actual_label"] == 1 else "NO_CYCLONE",
        "stormId": clean(row["storm_id"]),
        "basin": clean(row["basin"]),
        "timestamp": clean(row["timestamp"]),
        "windKt": clean(row["wind_speed_kt"]),
        "difficulty": clean(row["difficulty"]),
        "offline": {"label": "CYCLONE" if row["predicted_label"] == 1 else "NO_CYCLONE",
                    "cycloneProbability": clean(row["cyclone_probability"])},
    } for _, row in picks.iterrows()]

    cls = pd.read_csv(IDENTIFICATION / "results" / "classification" / "test_predictions.csv")
    classes = cls.groupby("label")[["class_code", "class_name"]].first().sort_index()
    picks = pd.concat([cls[cls["true_class"] == code].sample(PER_INTENSITY_CLASS, random_state=SEED) for code in classes["class_code"]])
    classification = [{
        "id": row["image_id"],
        "image": image_url_path(row["image_path"]),
        "truth": row["true_class"],
        "truthName": row["class_name"],
        "name": clean(row["name"]),
        "stormId": clean(row["storm_id"]),
        "basin": clean(row["basin"]),
        "timestamp": clean(row["timestamp"]),
        "windKt": clean(row["usa_wind_kt"]),
        "offline": {"class": row["predicted_class"], "confidence": clean(row["confidence"])},
    } for _, row in picks.iterrows()]

    manifest = {
        "seed": SEED,
        "classes": [{"code": code, "name": name} for code, name in classes.itertuples(index=False)],
        "testSetSizes": {"identification": len(ident), "classification": len(cls)},
        "identification": identification,
        "classification": classification,
    }
    (HERE / "samples.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"samples.json: {len(identification)} identification + {len(classification)} classification images (seed {SEED})")


if __name__ == "__main__":
    main()
