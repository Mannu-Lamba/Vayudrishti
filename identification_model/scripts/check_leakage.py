#!/usr/bin/env python3
"""Data leakage check (must PASS before training) — any task.

    python scripts/check_leakage.py                                      # identification
    python scripts/check_leakage.py --config configs/classification.yaml

Re-derives everything from the split files and the image files themselves:
  1. no image path appears in two splits;
  2. no decoded-pixel hash appears in two splits (identical images);
  3. no near-duplicate pair (dHash + thumbnail correlation) spans two splits;
  4. no storm_id appears in two splits (train/val, train/test, val/test);
  5. no event group spans two splits;
  6. no two samples in different splits have overlapping crops within the grouping window;
  7. every manifest row is in exactly one split.

Writes the task's leakage report (with SHA-256 of the split files; src/train.py refuses to run
unless it says PASS for the current files) and prints DATA LEAKAGE CHECK: PASS / FAILED.
"""

from __future__ import annotations

import argparse
import sys
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.create_splits import overlapping_pairs  # noqa: E402
from src.utils import (  # noqa: E402
    cfg_file, dhash, load_config, near_duplicate_pairs, pixel_sha256, project_path, sha256_file, split_path, thumbnail,
    write_json,
)

SPLITS = ("train", "val", "test")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=None, help="task config (default: identification)")
    args = parser.parse_args()
    cfg = load_config(args.config)
    frames = []
    for s in SPLITS:
        df = pd.read_csv(split_path(cfg, s), keep_default_na=False, na_values=[""])
        frames.append(df.assign(split=s))
    allrows = pd.concat(frames, ignore_index=True)
    manifest = pd.read_csv(project_path(cfg, "metadata", cfg_file(cfg, "manifest", "identification_dataset.csv")),
                           keep_default_na=False, na_values=[""])

    pix, hashes, thumbs = [], [], []
    for p in allrows.image_path:
        arr = np.asarray(Image.open(ROOT / p).convert("L"), dtype=np.uint8)
        pix.append(pixel_sha256(arr))
        hashes.append(dhash(arr))
        thumbs.append(thumbnail(arr))
    allrows["pixel_sha256"] = pix

    def cross(col: str) -> list[str]:
        df = allrows[allrows[col].fillna("").astype(str) != ""]
        spans = df.groupby(col).split.nunique()
        return [str(v) for v in spans[spans > 1].index]

    results = {}
    results["identical_image_path_across_splits"] = cross("image_path")
    results["identical_pixels_across_splits"] = cross("pixel_sha256")
    im = cfg["imagery"]
    near = near_duplicate_pairs(hashes, np.stack(thumbs), im["near_duplicate_hamming"], im["near_duplicate_corr"])
    results["near_duplicates_across_splits"] = [
        f"{allrows.image_id[i]}({allrows.split[i]})~{allrows.image_id[j]}({allrows.split[j]})"
        for i, j, _, _ in near if allrows.split[i] != allrows.split[j]]
    has_storm = allrows.storm_id.fillna("").astype(str) != ""
    storm_sets = {s: set(allrows[has_storm & (allrows.split == s)].storm_id) for s in SPLITS}
    for a, b in combinations(SPLITS, 2):
        results[f"storm_ids_shared_{a}_{b}"] = sorted(storm_sets[a] & storm_sets[b])
    results["groups_across_splits"] = cross("group_id")
    rows = allrows.merge(manifest[["image_id", "latitude", "longitude"]], on="image_id", how="left")
    box = 2 * float(cfg["gridsat"]["half_width_deg"])
    results["overlapping_crops_across_splits"] = [
        f"{rows.image_id[a]}({rows.split[a]})~{rows.image_id[b]}({rows.split[b]})"
        for a, b in overlapping_pairs(rows, float(cfg["splits"]["group_overlap_hours"]), box) if rows.split[a] != rows.split[b]]
    in_splits = allrows.image_id.value_counts()
    results["manifest_rows_missing_from_splits"] = sorted(set(manifest.image_id) - set(in_splits.index))
    results["rows_in_more_than_one_split"] = [str(k) for k in in_splits[in_splits > 1].index]

    failed = {k: v for k, v in results.items() if v}
    status = "PASS" if not failed else "FAILED"
    report = {
        "status": status,
        "checks": {k: {"violations": len(v), "examples": v[:10]} for k, v in results.items()},
        "split_rows": {s: int((allrows.split == s).sum()) for s in SPLITS},
        "split_file_sha256": {s: sha256_file(split_path(cfg, s)) for s in SPLITS},
    }
    write_json(project_path(cfg, "reports", cfg_file(cfg, "leakage_report", "leakage_check.json")), report)
    for k, v in results.items():
        print(f"  {'ok  ' if not v else 'FAIL'} {k}: {len(v)}")
    print(f"DATA LEAKAGE CHECK: {status}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
