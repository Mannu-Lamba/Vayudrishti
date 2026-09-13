#!/usr/bin/env python3
"""STEP 4c/5 — Image cleaning, rendering and duplicate detection.

For every candidate with a GridSat crop:
  * reject missing/failed downloads, unreadable or wrongly shaped crops, crops with more than
    `imagery.max_missing_fraction` missing pixels and constant (information-free) frames;
  * render the processed 256×256 PNG (data/processed/<class>/<sample_id>.png);
  * compute cloud metrics used later for negative difficulty;
  * detect exact duplicates (decoded-pixel SHA-256) and near-duplicates (64-bit dHash + thumbnail
    correlation). Exact duplicates are dropped; near-duplicate pairs are kept but recorded so the
    split step keeps them in the same split. A near-duplicate across classes drops the negative.

Writes data/metadata/cleaned_samples.csv, data/metadata/near_duplicates.csv,
data/metadata/image_rejections.csv and reports/cleaning_report.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.preprocessing import cold_cloud_fraction, counts_to_bt, missing_fraction, render_image  # noqa: E402
from src.utils import (  # noqa: E402
    CLASS_NAMES, dhash, ensure_dir, load_config, near_duplicate_pairs, pixel_sha256, project_path, thumbnail, write_json,
)

VALID_BT = (140.0, 375.0)  # GridSat-B1 irwin_cdr valid_range (DAS)
DEEP_CONVECTION_BT_K = 208.0


def latest_fetch_status(log_path: Path) -> pd.DataFrame:
    if not log_path.exists():
        return pd.DataFrame(columns=["sample_id", "status", "slot_time", "time_offset_h", "error"])
    log = pd.read_csv(log_path)
    return log.drop_duplicates("sample_id", keep="last").set_index("sample_id")


def main() -> int:
    cfg = load_config()
    g, im = cfg["gridsat"], cfg["imagery"]
    cand = pd.read_csv(project_path(cfg, "metadata", "candidates.csv"), keep_default_na=False, na_values=[""])
    raw = project_path(cfg, "raw", "gridsat")
    status = latest_fetch_status(raw / "fetch_log.csv")
    out_dirs = {label: ensure_dir(project_path(cfg, "processed", CLASS_NAMES[label])) for label in (0, 1)}
    expected = 2 * int(round(g["half_width_deg"] / 0.07)) + 1

    accepted, rejected, hashes, thumbs = [], [], [], []
    for n, row in enumerate(cand.itertuples(), 1):
        label = int(row.label)
        npz = raw / CLASS_NAMES[label] / f"{row.sample_id}.npz"
        st = status.loc[row.sample_id] if row.sample_id in status.index else None
        reject = lambda reason, detail="": rejected.append(  # noqa: E731
            {"sample_id": row.sample_id, "label": label, "stage": "image", "reason": reason, "detail": detail})
        if not npz.exists():
            reason = "not_fetched" if st is None else str(st.status)
            reject(reason if reason != "ok" else "crop_file_missing", "" if st is None else str(st.error)[:160])
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
        path = out_dirs[label] / f"{row.sample_id}.png"
        img.save(path, format="PNG", optimize=True)
        hashes.append(dhash(arr))
        thumbs.append(thumbnail(arr))
        accepted.append({
            "sample_id": row.sample_id,
            "image_path": path.relative_to(ROOT).as_posix(),
            "gridsat_slot": "" if st is None else st.slot_time,
            "time_offset_h": np.nan if st is None else float(st.time_offset_h),
            "missing_fraction": round(miss, 5),
            "bt_mean_k": round(float(np.nanmean(bt)), 2),
            "bt_min_k": round(float(np.nanmin(bt)), 2),
            "cold_cloud_fraction": round(cold_cloud_fraction(bt, im["cold_cloud_bt_k"]), 5),
            "central_cold_cloud_fraction": round(cold_cloud_fraction(bt, im["cold_cloud_bt_k"], im["central_box_fraction"]), 5),
            "deep_convection_fraction": round(cold_cloud_fraction(bt, DEEP_CONVECTION_BT_K), 5),
            "pixel_sha256": pixel_sha256(arr),
            "dhash": f"{hashes[-1]:016x}",
        })
        if n % 500 == 0:
            print(f"  {n}/{len(cand)} processed, {len(accepted)} accepted", flush=True)

    acc = pd.DataFrame(accepted).merge(cand, on="sample_id", how="left")
    thumbs_arr = np.stack(thumbs)

    # ---------------- exact duplicates: keep the highest-priority sample of each pixel hash
    priority = np.select([acc.candidate_source.eq("ps70_positive_candidates"), acc.candidate_source.eq("finalized_metadata_reserve"),
                          acc.ps70_selected.astype(str).eq("True")], [0, 1, 2], 3)
    acc["_prio"] = priority
    acc["_row"] = np.arange(len(acc))
    order = acc.sort_values(["_prio", "sample_id"])
    dup_mask = order.duplicated("pixel_sha256", keep="first")
    keeper = order.drop_duplicates("pixel_sha256").set_index("pixel_sha256").sample_id
    for r in order[dup_mask].itertuples():
        rejected.append({"sample_id": r.sample_id, "label": int(r.label), "stage": "image", "reason": "exact_duplicate",
                         "detail": f"duplicate of {keeper[r.pixel_sha256]}"})
    drop_rows = set(order[dup_mask]._row)

    # ---------------- near duplicates
    pairs = near_duplicate_pairs(hashes, thumbs_arr, im["near_duplicate_hamming"], im["near_duplicate_corr"])
    nd_rows = []
    for i, j, ham, corr in pairs:
        a, b = acc.iloc[i], acc.iloc[j]
        nd_rows.append({"sample_a": a.sample_id, "sample_b": b.sample_id, "label_a": int(a.label), "label_b": int(b.label),
                        "hamming": ham, "thumbnail_corr": round(corr, 4)})
        if a.label != b.label:  # same scene, opposite labels → keep the positive, drop the negative
            neg = a if a.label == 0 else b
            pos = b if a.label == 0 else a
            if neg._row not in drop_rows:
                drop_rows.add(neg._row)
                rejected.append({"sample_id": neg.sample_id, "label": 0, "stage": "image", "reason": "near_duplicate_of_positive",
                                 "detail": f"{pos.sample_id} (hamming {ham}, r={corr:.3f})"})
    near = pd.DataFrame(nd_rows, columns=["sample_a", "sample_b", "label_a", "label_b", "hamming", "thumbnail_corr"])

    cleaned = acc[~acc._row.isin(drop_rows)].drop(columns=["_prio", "_row"])
    for r in acc[acc._row.isin(drop_rows)].itertuples():  # remove rendered files of dropped samples
        (ROOT / r.image_path).unlink(missing_ok=True)

    meta_dir = project_path(cfg, "metadata")
    cleaned.to_csv(meta_dir / "cleaned_samples.csv", index=False)
    near.to_csv(meta_dir / "near_duplicates.csv", index=False)
    img_rej = pd.DataFrame(rejected, columns=["sample_id", "label", "stage", "reason", "detail"])
    img_rej.to_csv(meta_dir / "image_rejections.csv", index=False)

    repro = reproduction_check(cleaned, cfg)
    write_report(cfg, cand, cleaned, img_rej, near, repro)
    print(f"Accepted {len(cleaned)} ({(cleaned.label == 1).sum()} cyclone / {(cleaned.label == 0).sum()} no_cyclone); "
          f"rejected {len(img_rej)}; near-duplicate pairs {len(near)}")
    return 0


def reproduction_check(cleaned: pd.DataFrame, cfg: dict) -> dict:
    """Compare regenerated crops with the original PS-70 PNGs of the same fixes."""
    out = {}
    have = cleaned[cleaned.original_png.fillna("").astype(str).str.len() > 0]
    have = have.assign(original_png_source=have.original_png_source.fillna("<not recorded>"))
    for source, grp in have.groupby("original_png_source"):
        rs, rs_flip = [], []
        for r in grp.itertuples():
            new = np.asarray(Image.open(ROOT / r.image_path), dtype=np.float32).ravel()
            orig = np.asarray(Image.open(ROOT / r.original_png), dtype=np.float32)
            rs.append(np.corrcoef(new, orig.ravel())[0, 1])
            rs_flip.append(np.corrcoef(new, np.flipud(orig).ravel())[0, 1])
        out[source or "<not recorded>"] = {"n": len(rs), "median_r": round(float(np.nanmedian(rs)), 3),
                                           "median_r_if_original_flipped": round(float(np.nanmedian(rs_flip)), 3)}
    write_json(project_path(cfg, "reports", "audit", "reproduction_check.json"), out)
    return out


def write_report(cfg, cand, cleaned, img_rej, near, repro) -> None:
    meta_rej = pd.read_csv(project_path(cfg, "metadata", "candidate_rejections.csv"))
    pos_in = 2000
    neg_in = 4615
    lines = [
        "# Cleaning report — dataset v1.0",
        "",
        "Generated by `scripts/prepare_candidates.py` (metadata stage) and `scripts/clean_dataset.py` (image stage).",
        "Original files are never modified; rejected samples are listed with reasons in",
        "`data/metadata/candidate_rejections.csv` and `data/metadata/image_rejections.csv`.",
        "",
        "## Summary",
        "",
        "| | cyclone | no_cyclone |",
        "|---|---|---|",
        f"| Source rows (PS-70 positive list / negative pool) | {pos_in} | {neg_in} |",
        f"| Rejected at metadata stage | {(meta_rej.label == 1).sum()} | {(meta_rej.label == 0).sum()} |",
        f"| Reserve TS fixes added from dataset A | {(cand.candidate_source == 'finalized_metadata_reserve').sum()} | – |",
        f"| Candidates imaged | {(cand.label == 1).sum()} | {(cand.label == 0).sum()} |",
        f"| Rejected at image stage | {(img_rej.label == 1).sum()} | {(img_rej.label == 0).sum()} |",
        f"| **Accepted (clean pool for selection)** | **{(cleaned.label == 1).sum()}** | **{(cleaned.label == 0).sum()}** |",
        "",
        "## Rejections by reason",
        "",
        "| stage | reason | cyclone | no_cyclone |",
        "|---|---|---|---|",
    ]
    for (stage, reason), grp in pd.concat([meta_rej, img_rej]).groupby(["stage", "reason"]):
        lines.append(f"| {stage} | {reason} | {(grp.label == 1).sum()} | {(grp.label == 0).sum()} |")
    missing_meta = meta_rej[meta_rej.reason.isin(["missing_storm_id", "invalid_timestamp", "invalid_coordinates"])]
    lines += [
        "",
        "Category totals requested by the spec:",
        f"- accepted: {len(cleaned)}",
        f"- rejected: {len(meta_rej) + len(img_rej)}",
        f"- duplicated: {int(meta_rej.reason.eq('duplicate_metadata_row').sum() + img_rej.reason.isin(['exact_duplicate', 'near_duplicate_of_positive']).sum())} "
        f"(metadata rows {int(meta_rej.reason.eq('duplicate_metadata_row').sum())}, exact image {int(img_rej.reason.eq('exact_duplicate').sum())}, cross-class near-duplicate {int(img_rej.reason.eq('near_duplicate_of_positive').sum())})",
        f"- missing metadata: {len(missing_meta)}",
        f"- corrupted / unreadable: {int(img_rej.reason.isin(['corrupted_crop', 'unexpected_dimensions']).sum())}",
        f"- missing satellite data (>{cfg['imagery']['max_missing_fraction']:.0%} fill pixels, or GridSat file unavailable): "
        f"{int(img_rej.reason.isin(['missing_data_exceeds_limit', 'gridsat_file_missing', 'failed', 'not_fetched']).sum())}",
        "",
        "## Near-duplicates",
        f"- Pairs (dHash distance ≤ {cfg['imagery']['near_duplicate_hamming']} and 32×32 thumbnail r ≥ {cfg['imagery']['near_duplicate_corr']}): {len(near)} "
        f"(same class {int((near.label_a == near.label_b).sum())}, cross-class {int((near.label_a != near.label_b).sum())}). Same-class pairs are kept and forced into the same split.",
        "",
        "## Residual differences between the classes (shortcut check)",
        "",
        "| metric | cyclone median | no_cyclone median |",
        "|---|---|---|",
    ]
    for col in ["missing_fraction", "bt_mean_k", "cold_cloud_fraction", "central_cold_cloud_fraction", "time_offset_h"]:
        lines.append(f"| {col} | {cleaned[cleaned.label == 1][col].median():.4f} | {cleaned[cleaned.label == 0][col].median():.4f} |")
    lines += [
        "",
        "## Reproduction check against the original PS-70 PNGs",
        "Regenerated crops compared with the original PNG of the same fix (Pearson r of pixels):",
        "",
    ]
    for source, v in repro.items():
        lines.append(f"- {source}: n={v['n']}, median r={v['median_r']} (r if the original is flipped vertically: {v['median_r_if_original_flipped']})")
    path = project_path(cfg, "reports", "cleaning_report.md")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
