#!/usr/bin/env python3
"""STEPS 8–11 — Balanced selection, stratification and the dataset manifest.

Selects exactly `selection.positives` cyclone and `selection.negatives` no-cyclone samples from the
clean pool (data/metadata/cleaned_samples.csv) without duplicating any image:

Positives — stratified by UI subregion × storm intensity (PS-70 design: equal areas, 35/35/30 %
  weak/medium/strong). A stratum that runs short passes its quota to the least-filled strata.
  Within a stratum PS-70 candidates come first, then reserve fixes, picked round-robin across storms.

Negatives — difficulty from a documented image rule (see config `selection`):
  easy     : whole-crop cold-cloud fraction (BT < 235 K) below `easy_max_cold_fraction`
  hard     : central 9°×9° cold-cloud fraction >= the P{hard_reference_percentile} of the positives,
             i.e. as much deep cloud near the centre as a typical cyclone scene
  moderate : the rest
  Stratified by difficulty × subregion (Arabian Sea / Bay of Bengal, 50/50 where possible), picked
  round-robin across years so seasons and years stay represented.

Writes data/metadata/identification_dataset.csv and reports/audit/selection_summary.json.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.utils import load_config, project_path, set_seed, write_json  # noqa: E402

INTENSITY_SHARE = {"weak": 0.35, "medium": 0.35, "strong": 0.30}
POSITIVE_AREAS = ["arabian_sea", "bay_of_bengal", "south_indian_ocean", "western_pacific", "eastern_pacific", "southern_pacific"]
NEGATIVE_AREAS = ["arabian_sea", "bay_of_bengal"]
MANIFEST_COLUMNS = ["image_id", "image_path", "label", "class_name", "storm_id", "basin", "region", "subregion",
                    "timestamp", "latitude", "longitude", "intensity", "difficulty"]


def allocate(targets: dict, available: dict, total: int) -> dict:
    """Integer quotas summing to `total` (or everything available), filling the stratum with the
    lowest quota/target ratio first so proportions are kept and shortfalls spread evenly."""
    quota = {k: 0 for k in targets}
    for _ in range(min(total, sum(available.values()))):
        open_keys = [k for k in targets if quota[k] < available.get(k, 0)]
        k = min(open_keys, key=lambda key: (quota[key] + 1) / max(targets[key], 1e-9))
        quota[k] += 1
    return quota


def round_robin(df: pd.DataFrame, k: int, key: str, rng: np.random.Generator, priority: str | None = None) -> pd.DataFrame:
    """Pick k rows cycling over the values of `key` (random order), highest priority first within a key."""
    if k >= len(df):
        return df
    df = df.assign(_r=rng.random(len(df)))
    sort_cols = ([priority] if priority else []) + ["_r"]
    queues = {g: list(sub.sort_values(sort_cols).index) for g, sub in df.groupby(key)}
    order = list(queues)
    rng.shuffle(order)
    picked: list = []
    while len(picked) < k:
        for g in order:
            if queues[g] and len(picked) < k:
                picked.append(queues[g].pop(0))
    return df.loc[picked].drop(columns="_r")


def main() -> int:
    cfg = load_config()
    seed = int(cfg["project"]["seed"])
    set_seed(seed)
    rng = np.random.default_rng(seed)
    sel_cfg = cfg["selection"]
    clean = pd.read_csv(project_path(cfg, "metadata", "cleaned_samples.csv"), keep_default_na=False, na_values=[""])
    clean["area"] = clean.subregion.fillna("").where(clean.subregion.fillna("") != "", clean.region)
    pos, neg = clean[clean.label == 1].copy(), clean[clean.label == 0].copy()

    # ---------------- positives
    per_area = sel_cfg["positives"] / len(POSITIVE_AREAS)
    p_targets = {(a, i): per_area * s for a in POSITIVE_AREAS for i, s in INTENSITY_SHARE.items()}
    p_avail = pos.groupby(["area", "intensity"]).size().to_dict()
    p_quota = allocate(p_targets, p_avail, sel_cfg["positives"])
    pos["_prio"] = np.where(pos.candidate_source == "ps70_positive_candidates", 0, 1)
    chosen_pos = pd.concat([round_robin(pos[(pos.area == a) & (pos.intensity == i)], q, "storm_id", rng, "_prio")
                            for (a, i), q in p_quota.items() if q > 0]).drop(columns="_prio")

    # ---------------- negatives: difficulty
    hard_ref = float(np.percentile(pos.central_cold_cloud_fraction, sel_cfg["hard_reference_percentile"]))
    neg["difficulty"] = np.select(
        [neg.central_cold_cloud_fraction >= hard_ref, neg.cold_cloud_fraction < sel_cfg["easy_max_cold_fraction"]],
        ["hard", "easy"], "moderate")
    shares = sel_cfg["negative_difficulty_targets"]
    n_targets = {(d, a): sel_cfg["negatives"] * shares[d] / len(NEGATIVE_AREAS) for d in shares for a in NEGATIVE_AREAS}
    n_avail = neg.groupby(["difficulty", "area"]).size().to_dict()
    n_quota = allocate(n_targets, n_avail, sel_cfg["negatives"])
    neg["year"] = neg.timestamp.str[:4]
    chosen_neg = pd.concat([round_robin(neg[(neg.difficulty == d) & (neg.area == a)], q, "year", rng)
                            for (d, a), q in n_quota.items() if q > 0]).drop(columns="year")

    chosen_pos["difficulty"] = ""
    chosen_pos = chosen_pos.sort_values(["timestamp", "sample_id"])
    chosen_neg = chosen_neg.sort_values(["timestamp", "sample_id"])
    manifest = pd.concat([chosen_pos, chosen_neg], ignore_index=True)
    manifest.insert(0, "image_id", [f"IMG{i:04d}" for i in range(1, len(manifest) + 1)])
    manifest["intensity"] = manifest.intensity.fillna("")
    assert manifest.image_path.is_unique and manifest.pixel_sha256.is_unique, "selection contains a duplicated image"
    extras = [c for c in ["sample_id", "candidate_source", "ps70_selected", "ps70_negative_id", "source_region", "name", "nature",
                          "wind_speed_kt", "pressure_hpa", "storm_max_wind_kt", "lifecycle_stage", "lifecycle_position",
                          "gridsat_slot", "time_offset_h", "missing_fraction", "bt_mean_k", "cold_cloud_fraction",
                          "central_cold_cloud_fraction", "deep_convection_fraction", "nearest_system_deg", "pixel_sha256",
                          "dhash", "original_png", "original_png_source"] if c in manifest.columns]
    manifest = manifest[MANIFEST_COLUMNS + extras]
    manifest.to_csv(project_path(cfg, "metadata", "identification_dataset.csv"), index=False)

    all_neg_difficulty = neg.difficulty.value_counts().to_dict()
    summary = {
        "dataset_version": cfg["project"]["dataset_version"],
        "positives": int((manifest.label == 1).sum()),
        "negatives": int((manifest.label == 0).sum()),
        "hard_negative_central_cold_fraction_threshold": round(hard_ref, 4),
        "positive_quota": {f"{a}/{i}": q for (a, i), q in p_quota.items()},
        "positive_available": {f"{a}/{i}": int(v) for (a, i), v in p_avail.items()},
        "negative_quota": {f"{d}/{a}": q for (d, a), q in n_quota.items()},
        "negative_available": {f"{d}/{a}": int(v) for (d, a), v in n_avail.items()},
        "negative_pool_difficulty": {k: int(v) for k, v in all_neg_difficulty.items()},
        "positive_sources": manifest[manifest.label == 1].candidate_source.value_counts().to_dict(),
        "positive_storms": int(manifest[manifest.label == 1].storm_id.nunique()),
        "negative_from_ps70_selected_2000": int(manifest[manifest.label == 0].ps70_selected.astype(str).eq("True").sum()),
    }
    write_json(project_path(cfg, "reports", "audit", "selection_summary.json"), summary)
    print(f"Manifest: {summary['positives']} cyclone + {summary['negatives']} no_cyclone "
          f"({summary['positive_storms']} storms); hard-negative threshold = {hard_ref:.3f}")
    print("positive quota:", summary["positive_quota"])
    print("negative quota:", summary["negative_quota"], " pool difficulty:", summary["negative_pool_difficulty"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
