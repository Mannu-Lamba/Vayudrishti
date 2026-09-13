#!/usr/bin/env python3
"""STEP 23 — Error analysis of the held-out test predictions (run after src/evaluate.py).

  reports/errors/false_positives/   actual NO CYCLONE, predicted CYCLONE (most confident first)
  reports/errors/false_negatives/   actual CYCLONE, predicted NO CYCLONE
  reports/errors/errors.csv         image, actual, predicted, confidence, storm_id, region, basin, timestamp, …
  reports/errors/*_grid.png         contact sheets
  reports/errors/error_summary.json breakdowns by area, difficulty, intensity, nature, lifecycle
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from PIL import Image  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.audit_datasets import load_ibtracs  # noqa: E402
from src.utils import ensure_dir, load_config, project_path, wrap_dlon, write_json  # noqa: E402

CLASS = {0: "NO_CYCLONE", 1: "CYCLONE"}
PREGENESIS_WINDOW_H = 72


def system_entering_crop(neg: pd.DataFrame, ib: pd.DataFrame, half_width: float, hours: int) -> pd.DataFrame:
    """For each negative: the first IBTrACS system (any basin/nature) whose centre lies inside the crop
    box during the NEXT `hours` hours. The PS-70 negative rule only checked the matched time, so a
    hit means the scene may show a pre-genesis disturbance that was tracked shortly afterwards."""
    ib = ib.sort_values("time").reset_index(drop=True)
    times = ib.time.to_numpy()
    rows = []
    for r in neg.itertuples():
        t = pd.Timestamp(r.timestamp).tz_localize(None) if pd.Timestamp(r.timestamp).tzinfo else pd.Timestamp(r.timestamp)
        lo = np.searchsorted(times, np.datetime64(t), side="right")
        hi = np.searchsorted(times, np.datetime64(t + pd.Timedelta(hours=hours)), side="right")
        win = ib.iloc[lo:hi]
        inside = win[(np.abs(win.LAT.to_numpy() - r.latitude) <= half_width) & (np.abs(wrap_dlon(win.LON.to_numpy() - r.longitude)) <= half_width)]
        if inside.empty:
            rows.append({"image_id": r.image_id, "system_enters_crop_72h": False, "system": "", "hours_ahead": np.nan})
        else:
            first = inside.iloc[0]
            rows.append({"image_id": r.image_id, "system_enters_crop_72h": True,
                         "system": f"{first.SID} {first.NAME} ({first.NATURE})",
                         "hours_ahead": round((first.time - t).total_seconds() / 3600, 1)})
    return pd.DataFrame(rows)


def contact_sheet(df: pd.DataFrame, title: str, path: Path, cols: int = 6) -> None:
    if df.empty:
        return
    rows = int(np.ceil(len(df) / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(cols * 2.0, rows * 2.35))
    for ax in np.atleast_1d(axes).flat:
        ax.axis("off")
    for ax, r in zip(np.atleast_1d(axes).flat, df.itertuples()):
        ax.imshow(Image.open(ROOT / r.image_path), cmap="gray", vmin=0, vmax=255)
        extra = r.intensity if r.actual_label == 1 else r.difficulty
        ax.set_title(f"{r.image_id} p(cyc)={r.cyclone_probability:.2f}\n{r.subregion or r.region} · {extra} · {str(r.timestamp)[:10]}", fontsize=6)
    fig.suptitle(title, fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def main() -> int:
    cfg = load_config()
    pred = pd.read_csv(project_path(cfg, "results", "test_predictions.csv"), keep_default_na=False, na_values=[""])
    err_dir = project_path(cfg, "reports", "errors")
    limit = int(cfg["evaluation"]["max_error_examples"])
    fp = pred[(pred.actual_label == 0) & (pred.predicted_label == 1)].sort_values("confidence", ascending=False)
    fn = pred[(pred.actual_label == 1) & (pred.predicted_label == 0)].sort_values("confidence", ascending=False)

    for name, df in (("false_positives", fp), ("false_negatives", fn)):
        folder = err_dir / name
        if folder.exists():
            shutil.rmtree(folder)
        ensure_dir(folder)
        for rank, r in enumerate(df.head(limit).itertuples(), 1):
            shutil.copy2(ROOT / r.image_path, folder / f"{rank:02d}_{r.image_id}_pcyc{r.cyclone_probability:.3f}.png")
        contact_sheet(df.head(36), f"{name.replace('_', ' ').title()} — {len(df)} total (most confident first)", err_dir / f"{name}_grid.png")

    # Pre-genesis check: do tracked systems enter false-positive crops more often than true-negative crops?
    ib = load_ibtracs(Path(cfg["sources"]["ibtracs"]))
    negatives = pred[pred.actual_label == 0]
    ctx = system_entering_crop(negatives, ib, float(cfg["gridsat"]["half_width_deg"]), PREGENESIS_WINDOW_H)
    negatives = negatives.merge(ctx, on="image_id")
    fp = fp.merge(ctx, on="image_id", how="left")
    fn = fn.assign(system_enters_crop_72h=np.nan, system="", hours_ahead=np.nan)
    tn_mask = negatives.predicted_label == 0
    pregenesis = {
        "window_hours": PREGENESIS_WINDOW_H,
        "false_positives_with_system_entering_crop": int(fp.system_enters_crop_72h.sum()),
        "false_positives": int(len(fp)),
        "false_positive_rate_of_hits": round(float(fp.system_enters_crop_72h.mean()), 4) if len(fp) else None,
        "true_negatives_with_system_entering_crop": int(negatives[tn_mask].system_enters_crop_72h.sum()),
        "true_negatives": int(tn_mask.sum()),
        "true_negative_rate_of_hits": round(float(negatives[tn_mask].system_enters_crop_72h.mean()), 4),
        "false_positive_details": fp[fp.system_enters_crop_72h.astype(bool)][["image_id", "timestamp", "cyclone_probability", "system", "hours_ahead"]].to_dict("records"),
    }

    errors = pd.concat([fp.assign(error_type="false_positive"), fn.assign(error_type="false_negative")])
    table = pd.DataFrame({
        "image": errors.image_path, "actual": errors.actual_label.map(CLASS), "predicted": errors.predicted_label.map(CLASS),
        "confidence": errors.confidence, "storm_id": errors.storm_id, "region": errors.region, "basin": errors.basin,
        "timestamp": errors.timestamp, "error_type": errors.error_type, "image_id": errors.image_id,
        "subregion": errors.subregion, "cyclone_probability": errors.cyclone_probability, "intensity": errors.intensity,
        "difficulty": errors.difficulty, "nature": errors.nature, "wind_speed_kt": errors.wind_speed_kt,
        "lifecycle_stage": errors.lifecycle_stage, "cold_cloud_fraction": errors.cold_cloud_fraction,
        "central_cold_cloud_fraction": errors.central_cold_cloud_fraction,
        "ibtracs_system_entering_crop_next_72h": errors.system.fillna(""),
        "hours_until_system_in_crop": errors.hours_ahead,
    })
    ensure_dir(err_dir)
    table.to_csv(err_dir / "errors.csv", index=False)

    neg, pos = pred[pred.actual_label == 0], pred[pred.actual_label == 1]
    rate = lambda df, key, bad: {str(k): {"n": int(len(g)), "errors": int(bad(g).sum()), "rate": round(float(bad(g).mean()), 4)}  # noqa: E731
                                 for k, g in df.groupby(key)}
    is_fp = lambda g: g.predicted_label == 1  # noqa: E731
    is_fn = lambda g: g.predicted_label == 0  # noqa: E731
    summary = {
        "false_positives": int(len(fp)), "false_negatives": int(len(fn)),
        "fp_rate_by_difficulty": rate(neg, "difficulty", is_fp),
        "fp_rate_by_subregion": rate(neg, "subregion", is_fp),
        "fn_rate_by_intensity": rate(pos, "intensity", is_fn),
        "fn_rate_by_area": rate(pos.assign(area=pos.subregion.fillna("").where(pos.subregion.fillna("") != "", pos.region)), "area", is_fn),
        "fn_rate_by_lifecycle_stage": rate(pos.assign(lifecycle_stage=pos.lifecycle_stage.fillna("reserve (not staged)")), "lifecycle_stage", is_fn),
        "fn_wind_kt_median": float(fn.wind_speed_kt.median()) if len(fn) else None,
        "tp_wind_kt_median": float(pos[pos.predicted_label == 1].wind_speed_kt.median()) if len(pos) else None,
        "fn_central_cold_cloud_median": float(fn.central_cold_cloud_fraction.median()) if len(fn) else None,
        "tp_central_cold_cloud_median": float(pos[pos.predicted_label == 1].central_cold_cloud_fraction.median()) if len(pos) else None,
        "fp_central_cold_cloud_median": float(fp.central_cold_cloud_fraction.median()) if len(fp) else None,
        "tn_central_cold_cloud_median": float(neg[neg.predicted_label == 0].central_cold_cloud_fraction.median()) if len(neg) else None,
        "fp_months": {str(k): int(v) for k, v in pd.to_datetime(fp.timestamp).dt.month.value_counts().sort_index().items()},
        "fn_months": {str(k): int(v) for k, v in pd.to_datetime(fn.timestamp).dt.month.value_counts().sort_index().items()},
        "fn_wind_le_25kt": int((fn.wind_speed_kt <= 25).sum()),
        "fn_wind_missing": int(fn.wind_speed_kt.isna().sum()),
        "fn_weak_storms": int((fn.intensity == "weak").sum()),
        "fn_bay_of_bengal": int((fn.subregion == "bay_of_bengal").sum()),
        "fp_hard": int((fp.difficulty == "hard").sum()),
        "pregenesis": pregenesis,
    }
    write_json(err_dir / "error_summary.json", summary)
    print(f"False positives: {len(fp)}; false negatives: {len(fn)} → {err_dir}")
    for k in ("fp_rate_by_difficulty", "fn_rate_by_intensity", "fn_rate_by_area"):
        print(f"  {k}: {summary[k]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
