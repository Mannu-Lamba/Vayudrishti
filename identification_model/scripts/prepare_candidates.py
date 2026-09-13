#!/usr/bin/env python3
"""STEP 4a — Metadata cleaning and candidate list.

Builds the list of samples to image (data/metadata/candidates.csv) and records every rejected
metadata row with its reason (data/metadata/candidate_rejections.csv).

Positives
  * PS-70 positive candidates, keeping only IBTrACS NATURE == TS fixes with valid id/time/coords.
  * Reserve TS fixes from dataset A (finalized metadata) so 2,000 positives survive image cleaning.
    Reserves are stratified by UI subregion × storm intensity, prefer storms not already used,
    take at most 4 fixes per storm and keep them >= 24 h apart.
Negatives
  * Every row of the 4,615 GridSat candidate pool, minus rows that break the dataset's own rule
    (< 10° from a DS/TS/MX centre) or whose crop contains a tracked system centre (audit step).

Run after scripts/audit_datasets.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.utils import ensure_dir, intensity_from_max_wind, load_config, project_path, set_seed, ui_area, write_json  # noqa: E402

CATEGORY_MAP = {"Weak Cyclone": "weak", "Medium Cyclone": "medium", "Strong Cyclone": "strong"}
INTENSITY_SHARE = {"weak": 0.35, "medium": 0.35, "strong": 0.30}  # the PS-70 design: 700 / 700 / 600
POSITIVE_STRATA = ["arabian_sea", "bay_of_bengal", "south_indian_ocean", "western_pacific", "eastern_pacific", "southern_pacific"]
MAX_RESERVE_PER_STORM = 4
MIN_HOURS_APART = 24


def main() -> int:
    cfg = load_config()
    seed = int(cfg["project"]["seed"])
    set_seed(seed)
    rng = np.random.default_rng(seed)
    src = project_path(cfg, "raw", "sources")
    name = lambda key: src / Path(cfg["sources"][key]).name  # noqa: E731
    hw = float(cfg["gridsat"]["half_width_deg"])
    natures = set(cfg["candidates"]["positive_natures"])
    rejections: list[dict] = []

    a = pd.read_excel(name("finalized_metadata"), sheet_name="ML_Dataset")
    storm_max = a.groupby("cyclone_id").wind_speed.max()
    storm_first = a.groupby("cyclone_id").timestamp.min()
    storm_last = a.groupby("cyclone_id").timestamp.max()

    # ---------------------------------------------------------------- positives from the PS-70 list
    pc = pd.read_excel(name("positive_candidates"), sheet_name="Positive_Cyclones")
    pc["timestamp"] = pd.to_datetime(pc.timestamp, errors="coerce")
    original_png = project_path(cfg, "raw", "original_positive_png")
    reason = np.select(
        [
            pc.cyclone_id.isna() | (pc.cyclone_id.astype(str).str.strip() == ""),
            pc.timestamp.isna(),
            pc.latitude.isna() | pc.longitude.isna() | (pc.latitude.abs() > 90),
            pc.duplicated(["cyclone_id", "timestamp"], keep="first"),
            ~pc.nature.isin(natures),
            pc.latitude.abs() > 70 - hw,
        ],
        ["missing_storm_id", "invalid_timestamp", "invalid_coordinates", "duplicate_metadata_row",
         "nature_not_tropical", "outside_gridsat_latitude_coverage"],
        default="",
    )
    for r, why in zip(pc.itertuples(), reason):
        if why:
            rejections.append({"sample_id": r.sample_id, "label": 1, "stage": "metadata", "reason": why,
                               "detail": f"nature={r.nature}" if why == "nature_not_tropical" else ""})
    keep = pc[reason == ""].copy()
    pos = pd.DataFrame({
        "sample_id": keep.sample_id,
        "label": 1,
        "candidate_source": "ps70_positive_candidates",
        "ps70_selected": True,
        "storm_id": keep.cyclone_id,
        "basin": keep.basin,
        "subbasin": keep.subbasin,
        "source_region": keep.region,
        "name": keep.name,
        "timestamp": keep.timestamp,
        "latitude": keep.latitude,
        "longitude": keep.longitude,
        "nature": keep.nature,
        "wind_speed_kt": keep.wind_speed,
        "pressure_hpa": keep.pressure,
        "intensity": keep.intensity_category.map(CATEGORY_MAP),
        "storm_max_wind_kt": keep.cyclone_id.map(storm_max),
        "lifecycle_stage": keep.lifecycle_stage,
        "lifecycle_position": keep.lifecycle_position,
        "original_png": [f"data/raw/original_positive_png/{s}.png" if (original_png / f"{s}.png").exists() else "" for s in keep.sample_id],
        "original_png_source": keep.satellite_source.fillna(""),
    })

    # ---------------------------------------------------------------- reserve positives from dataset A
    a_ok = a[a.nature.isin(natures) & a.latitude.notna() & a.longitude.notna() & (a.latitude.abs() <= 70 - hw)].copy()
    a_ok = a_ok.merge(pc[["cyclone_id", "timestamp"]].assign(_used=1), on=["cyclone_id", "timestamp"], how="left")
    a_ok = a_ok[a_ok._used.isna()].drop(columns="_used")
    a_ok["intensity"] = a_ok.cyclone_id.map(storm_max).map(intensity_from_max_wind)
    a_ok = a_ok[a_ok.intensity != ""]
    a_ok["stratum_area"] = [ui_area(b, s)[1] or ui_area(b, s)[0] for b, s in zip(a_ok.basin, a_ok.subbasin)]
    pos["stratum_area"] = [ui_area(b, s)[1] or ui_area(b, s)[0] for b, s in zip(pos.basin, pos.subbasin)]

    per_area = cfg["selection"]["positives"] / len(POSITIVE_STRATA)
    target = {(ar, it): per_area * share for ar in POSITIVE_STRATA for it, share in INTENSITY_SHARE.items()}
    have = pos.groupby(["stratum_area", "intensity"]).size().to_dict()
    deficit = {k: max(0.0, t - have.get(k, 0)) for k, t in target.items()}
    budget = int(cfg["candidates"]["positive_reserve"])
    buffer = max(0.0, budget - sum(deficit.values()))
    quota = {k: int(np.ceil(deficit[k] + buffer * target[k] / sum(target.values()))) for k in target}

    used_storms = set(pos.storm_id)
    chosen_times: dict[str, list[pd.Timestamp]] = {s: list(g) for s, g in pos.groupby("storm_id").timestamp}
    per_storm: dict[str, int] = {}
    order = a_ok.sample(frac=1.0, random_state=seed)
    order["_new_storm"] = ~order.cyclone_id.isin(used_storms)
    order = order.sort_values("_new_storm", ascending=False, kind="stable")  # prefer unseen storms
    taken = {k: 0 for k in quota}
    reserve_rows = []
    for r in order.itertuples():
        key = (r.stratum_area, r.intensity)
        if key not in quota or taken[key] >= quota[key] or per_storm.get(r.cyclone_id, 0) >= MAX_RESERVE_PER_STORM:
            continue
        times = chosen_times.setdefault(r.cyclone_id, [])
        if any(abs((r.timestamp - t).total_seconds()) < MIN_HOURS_APART * 3600 for t in times):
            continue
        times.append(r.timestamp)
        per_storm[r.cyclone_id] = per_storm.get(r.cyclone_id, 0) + 1
        taken[key] += 1
        span = (storm_last[r.cyclone_id] - storm_first[r.cyclone_id]).total_seconds()
        reserve_rows.append({
            "sample_id": f"PRS_{len(reserve_rows) + 1:04d}", "label": 1, "candidate_source": "finalized_metadata_reserve",
            "ps70_selected": False, "storm_id": r.cyclone_id, "basin": r.basin, "subbasin": r.subbasin,
            "source_region": r.region, "name": r.name, "timestamp": r.timestamp, "latitude": r.latitude,
            "longitude": r.longitude, "nature": r.nature, "wind_speed_kt": r.wind_speed, "pressure_hpa": r.pressure,
            "intensity": r.intensity, "storm_max_wind_kt": storm_max[r.cyclone_id], "lifecycle_stage": "",
            "lifecycle_position": (r.timestamp - storm_first[r.cyclone_id]).total_seconds() / span if span > 0 else 0.0,
            "original_png": "", "original_png_source": "", "stratum_area": r.stratum_area,
        })
    reserves = pd.DataFrame(reserve_rows)

    # ---------------------------------------------------------------- negatives
    pool = pd.read_csv(name("negative_pool"))
    pool["time"] = pd.to_datetime(pool.GRID_SAT_TIME, utc=True, errors="coerce").dt.tz_localize(None)
    meta = pd.read_excel(name("negative_selected"), sheet_name="Source_Metadata")
    ctx = pd.read_csv(project_path(cfg, "metadata", "negative_pool_ibtracs_context.csv"))
    pool = pool.merge(ctx, on="SAMPLE_ID", how="left")
    reason = np.select(
        [
            pool.time.isna(),
            pool.LAT.isna() | pool.LON.isna() | (pool.LAT.abs() > 90),
            pool.duplicated(["GRID_SAT_TIME", "LAT", "LON"], keep="first"),
            pool.LABEL != 0,
            pool.nearest_ds_ts_mx_deg < 10,
            pool.systems_in_crop > 0,
        ],
        ["invalid_timestamp", "invalid_coordinates", "duplicate_metadata_row", "label_not_zero",
         "violates_dataset_negative_rule", "tracked_system_centre_in_crop"],
        default="",
    )
    for r, why in zip(pool.itertuples(), reason):
        if why:
            detail = f"natures_in_crop={r.natures_in_crop}; nearest={r.nearest_system_deg:.1f}deg" if why.startswith(("tracked", "violates")) else ""
            rejections.append({"sample_id": r.SAMPLE_ID, "label": 0, "stage": "metadata", "reason": why, "detail": detail})
    keepn = pool[reason == ""]
    neg_id = dict(zip(meta.SAMPLE_ID, meta.sample_id))
    neg_region = dict(zip(meta.SAMPLE_ID, meta.derived_region))
    areas = [ui_area("NI", None, lon) for lon in keepn.LON]
    neg = pd.DataFrame({
        "sample_id": keepn.SAMPLE_ID,
        "label": 0,
        "candidate_source": "ps70_negative_pool",
        "ps70_selected": keepn.SAMPLE_ID.isin(neg_id),
        "ps70_negative_id": keepn.SAMPLE_ID.map(neg_id).fillna(""),
        "storm_id": "",
        "basin": "NI",
        "subbasin": "",
        "source_region": keepn.SAMPLE_ID.map(neg_region).fillna(""),
        "name": "",
        "timestamp": keepn.time,
        "latitude": keepn.LAT,
        "longitude": keepn.LON,
        "nearest_system_deg": keepn.nearest_system_deg,
        "nearest_system_nature": keepn.nearest_system_nature,
        "gridsat_file_reference": keepn.GRIDSAT_FILENAME,
        "stratum_area": [sub for _, sub in areas],
    })

    cand = pd.concat([pos, reserves, neg], ignore_index=True, sort=False)
    region_sub = [ui_area(b, s if isinstance(s, str) and s else None, lon) for b, s, lon in zip(cand.basin, cand.subbasin, cand.longitude)]
    cand["region"], cand["subregion"] = zip(*region_sub)
    cand["class_name"] = np.where(cand.label == 1, "cyclone", "no_cyclone")
    cand["timestamp"] = pd.to_datetime(cand.timestamp).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    cand = cand.drop(columns="stratum_area")
    out_dir = ensure_dir(project_path(cfg, "metadata"))
    cand.to_csv(out_dir / "candidates.csv", index=False)
    rej = pd.DataFrame(rejections)
    rej.to_csv(out_dir / "candidate_rejections.csv", index=False)

    summary = {
        "positive_candidates_in": int(len(pc)),
        "positive_candidates_kept": int(len(pos)),
        "positive_reserve_added": int(len(reserves)),
        "positive_reserve_quota": {f"{k[0]}/{k[1]}": v for k, v in quota.items()},
        "positive_reserve_taken": {f"{k[0]}/{k[1]}": v for k, v in taken.items()},
        "negative_pool_in": int(len(pool)),
        "negative_kept": int(len(neg)),
        "rejections": rej.groupby(["label", "reason"]).size().rename("n").reset_index().to_dict("records") if len(rej) else [],
        "candidates_total": int(len(cand)),
        "positives_by_area_intensity": {f"{k[0]}/{k[1]}": int(v) for k, v in cand[cand.label == 1].groupby(["subregion", "intensity"]).size().items()},
    }
    write_json(project_path(cfg, "reports", "audit", "candidates_summary.json"), summary)
    print(f"Positives kept from PS-70 list: {len(pos)} / {len(pc)}; reserve positives added: {len(reserves)}")
    print(f"Negatives kept from pool: {len(neg)} / {len(pool)}")
    print(rej.groupby(["label", "reason"]).size().to_string() if len(rej) else "no rejections")
    print(f"Candidates to image: {len(cand)} → {out_dir / 'candidates.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
