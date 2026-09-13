#!/usr/bin/env python3
"""Classification STEPS 3–4 — image cleaning, duplicate detection, balanced selection and manifest.

For every candidate with a GridSat crop: reject failed downloads, wrongly shaped crops, crops with
more than `imagery.max_missing_fraction` missing pixels and constant frames; render the processed
PNG with the SAME rendering as identification (180–310 K, cold = bright, 256×256, north up);
detect exact duplicates (decoded-pixel SHA-256) and near-duplicates (dHash + thumbnail correlation).
A near-duplicate pair with different labels is a label conflict → the sample of the more common
class is dropped. Then exactly `selection.per_class` samples per class are selected, equal UI areas
where possible (shortfalls go to the least-filled areas), round-robin across storms.

Writes <metadata>/classification_dataset.csv (manifest), cleaned_samples.csv, near_duplicates.csv,
image_rejections.csv and <reports>/audit/build_summary.json.

    python scripts/classification/build_dataset.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.build_manifest import allocate, round_robin  # noqa: E402
from scripts.clean_dataset import VALID_BT, latest_fetch_status  # noqa: E402
from scripts.fetch_gridsat_crops import crop_path  # noqa: E402
from src.preprocessing import cold_cloud_fraction, counts_to_bt, missing_fraction, render_image  # noqa: E402
from src.utils import (  # noqa: E402
    cfg_file, dhash, ensure_dir, load_config, near_duplicate_pairs, pixel_sha256, project_path, set_seed, task_classes,
    thumbnail, write_json,
)

CONFIG = ROOT / "configs" / "classification.yaml"
AREAS = ["arabian_sea", "bay_of_bengal", "south_indian_ocean", "western_pacific", "eastern_pacific", "southern_pacific"]


def main() -> int:
    cfg = load_config(CONFIG)
    seed = int(cfg["project"]["seed"])
    set_seed(seed)
    rng = np.random.default_rng(seed)
    g, im = cfg["gridsat"], cfg["imagery"]
    classes = task_classes(cfg)
    meta_dir = project_path(cfg, "metadata")
    cand = pd.read_csv(meta_dir / cfg_file(cfg, "candidates", "candidates.csv"), keep_default_na=False, na_values=[""])
    status = latest_fetch_status(project_path(cfg, "raw", "gridsat", "fetch_log.csv"))
    expected = 2 * int(round(g["half_width_deg"] / 0.07)) + 1

    accepted, rejected, hashes, thumbs = [], [], [], []
    for n, row in enumerate(cand.itertuples(), 1):
        npz = crop_path(cfg, row.sample_id, row.label)
        st = status.loc[row.sample_id] if row.sample_id in status.index else None
        reject = lambda reason, detail="": rejected.append(  # noqa: E731
            {"sample_id": row.sample_id, "label": int(row.label), "reason": reason, "detail": detail})
        if not npz.exists():
            reject("not_fetched" if st is None else str(st.status), "" if st is None else str(st.error)[:160])
            continue
        try:
            with np.load(npz) as z:
                counts = z["counts"]
        except Exception as exc:
            reject("corrupted_crop", str(exc)[:160])
            continue
        if counts.ndim != 2 or counts.shape != (expected, expected):
            reject("unexpected_dimensions", f"{counts.shape}")
            continue
        bt = counts_to_bt(counts, g["scale_factor"], g["add_offset"], g["fill_value"])
        bt[(bt < VALID_BT[0]) | (bt > VALID_BT[1])] = np.nan
        miss = missing_fraction(bt)
        if miss > im["max_missing_fraction"]:
            reject("missing_data_exceeds_limit", f"{miss:.3f}")
            continue
        if np.nanstd(bt) < 0.5:
            reject("constant_image", f"std={np.nanstd(bt):.3f}K")
            continue
        img = render_image(bt, im["png_size"], im["bt_min_k"], im["bt_max_k"])
        arr = np.asarray(img, dtype=np.uint8)
        path = ensure_dir(project_path(cfg, "processed", row.class_code)) / f"{row.sample_id}.png"
        img.save(path, format="PNG", optimize=True)
        hashes.append(dhash(arr))
        thumbs.append(thumbnail(arr))
        accepted.append({
            "sample_id": row.sample_id, "image_path": path.relative_to(ROOT).as_posix(),
            "gridsat_slot": "" if st is None else st.slot_time, "time_offset_h": np.nan if st is None else float(st.time_offset_h),
            "missing_fraction": round(miss, 5), "bt_mean_k": round(float(np.nanmean(bt)), 2), "bt_min_k": round(float(np.nanmin(bt)), 2),
            "cold_cloud_fraction": round(cold_cloud_fraction(bt, im["cold_cloud_bt_k"]), 5),
            "central_cold_cloud_fraction": round(cold_cloud_fraction(bt, im["cold_cloud_bt_k"], im["central_box_fraction"]), 5),
            "pixel_sha256": pixel_sha256(arr), "dhash": f"{hashes[-1]:016x}",
        })
        if n % 1000 == 0:
            print(f"  {n}/{len(cand)} processed, {len(accepted)} accepted", flush=True)

    acc = pd.DataFrame(accepted).merge(cand, on="sample_id", how="left")
    acc["_row"] = np.arange(len(acc))
    drop = set()
    dup = acc.duplicated("pixel_sha256", keep="first")
    keeper = acc.drop_duplicates("pixel_sha256").set_index("pixel_sha256").sample_id
    for r in acc[dup].itertuples():
        drop.add(r._row)
        rejected.append({"sample_id": r.sample_id, "label": int(r.label), "reason": "exact_duplicate", "detail": f"duplicate of {keeper[r.pixel_sha256]}"})

    class_size = acc.label.value_counts().to_dict()
    pairs = near_duplicate_pairs(hashes, np.stack(thumbs), im["near_duplicate_hamming"], im["near_duplicate_corr"])
    nd_rows = []
    for i, j, ham, corr in pairs:
        a, b = acc.iloc[i], acc.iloc[j]
        nd_rows.append({"sample_a": a.sample_id, "sample_b": b.sample_id, "label_a": int(a.label), "label_b": int(b.label),
                        "hamming": ham, "thumbnail_corr": round(corr, 4)})
        if a.label != b.label:  # same scene, different intensity label → drop the more common class's sample
            loser = a if class_size[a.label] >= class_size[b.label] else b
            other = b if loser is a else a
            if loser._row not in drop:
                drop.add(loser._row)
                rejected.append({"sample_id": loser.sample_id, "label": int(loser.label), "reason": "near_duplicate_conflicting_label",
                                 "detail": f"{other.sample_id} (hamming {ham}, r={corr:.3f})"})
    near = pd.DataFrame(nd_rows, columns=["sample_a", "sample_b", "label_a", "label_b", "hamming", "thumbnail_corr"])
    for r in acc[acc._row.isin(drop)].itertuples():
        (ROOT / r.image_path).unlink(missing_ok=True)
    clean = acc[~acc._row.isin(drop)].drop(columns="_row").copy()
    clean["area"] = clean.subregion.fillna("").where(clean.subregion.fillna("") != "", clean.region)

    # ---------------- balanced selection: per class, equal areas where possible, round-robin over storms
    per_class = int(cfg["selection"]["per_class"])
    chosen, quotas = [], {}
    for c in classes:
        pool = clean[clean.label == c["id"]]
        avail = pool.groupby("area").size().to_dict()
        targets = {a: per_class / len(AREAS) for a in AREAS}
        quota = allocate(targets, avail, per_class)
        quotas[c["code"]] = quota
        for area, q in quota.items():
            if q:
                chosen.append(round_robin(pool[pool.area == area], q, "storm_id", rng))
    sel = pd.concat(chosen).sort_values(["label", "timestamp", "sample_id"]).reset_index(drop=True)
    assert sel.image_path.is_unique and sel.pixel_sha256.is_unique, "selection contains a duplicated image"
    sel.insert(0, "image_id", [f"CLS-IMG{i:05d}" for i in range(1, len(sel) + 1)])
    columns = ["image_id", "image_path", "label", "class_code", "class_name", "storm_id", "name", "basin", "region", "subregion",
               "timestamp", "latitude", "longitude", "usa_wind_kt", "imd_category_of_usa_wind", "wmo_wind_kt", "wmo_agency",
               "usa_sshs", "dataset_a_wind_kt", "in_dataset_a", "sample_id", "gridsat_slot", "time_offset_h", "missing_fraction",
               "bt_mean_k", "bt_min_k", "cold_cloud_fraction", "central_cold_cloud_fraction", "pixel_sha256", "dhash"]
    sel[columns].to_csv(meta_dir / cfg_file(cfg, "manifest", "classification_dataset.csv"), index=False)
    clean.drop(columns="area").to_csv(meta_dir / "cleaned_samples.csv", index=False)
    near.to_csv(meta_dir / cfg_file(cfg, "near_duplicates", "near_duplicates.csv"), index=False)
    rej = pd.DataFrame(rejected, columns=["sample_id", "label", "reason", "detail"])
    rej.to_csv(meta_dir / "image_rejections.csv", index=False)

    by_id = {c["id"]: c["code"] for c in classes}
    summary = {
        "candidates": int(len(cand)),
        "accepted_clean_pool": int(len(clean)),
        "rejected": int(len(rej)),
        "rejected_by_reason": {k: int(v) for k, v in rej.reason.value_counts().items()},
        "exact_duplicates": int(rej.reason.eq("exact_duplicate").sum()),
        "near_duplicate_pairs": int(len(near)),
        "near_duplicate_label_conflicts": int(rej.reason.eq("near_duplicate_conflicting_label").sum()),
        "clean_pool_by_class": {by_id[int(k)]: int(v) for k, v in clean.label.value_counts().sort_index().items()},
        "selected": int(len(sel)),
        "selected_by_class": {by_id[int(k)]: int(v) for k, v in sel.label.value_counts().sort_index().items()},
        "selected_by_class_area": {f"{by_id[int(k[0])]}/{k[1]}": int(v) for k, v in
                                   sel.assign(area=sel.subregion.fillna("").where(sel.subregion.fillna("") != "", sel.region)).groupby(["label", "area"]).size().items()},
        "area_quotas": quotas,
        "selected_storms": int(sel.storm_id.nunique()),
        "images_per_storm": {k: round(float(v), 2) for k, v in sel.groupby("storm_id").size().describe().items()},
    }
    write_json(ensure_dir(project_path(cfg, "reports", "audit")) / "build_summary.json", summary)
    print(f"Clean pool {len(clean)} of {len(cand)} (rejected {len(rej)}: {summary['rejected_by_reason']}); near-duplicate pairs {len(near)}")
    print(f"Selected {len(sel)} images from {summary['selected_storms']} storms: {summary['selected_by_class']}")
    print("By class/area:", summary["selected_by_class_area"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
