#!/usr/bin/env python3
"""Classification STEPS 2–3 — label audit and candidate fixes for the intensity classifier.

There is no pre-labelled intensity image set in the project, so the classification dataset is
built from the same PS-70 sources as identification:
  * Dataset A — PS-70 finalized IBTrACS metadata (storm ids, fixes, positions, basins);
  * IBTrACS v04r01 — USA_WIND (JTWC/NHC 1-minute sustained wind), the only wind reported on one
    averaging basis in every basin (dataset A's `wind_speed` mixes 1-, 3- and 10-minute agency winds).

Labels = the IMD category of USA_WIND, grouped into the 4 classes of configs/classification.yaml.
No class is invented: every class is a set of IMD categories and its knot range is IMD's.

Candidates (over-provisioned, rarest class first): NATURE == TS, main track, 3-hourly synoptic
fixes (exact GridSat slots), USA_WIND present and >= 17 kt, inside GridSat latitude coverage.
Within a class, fixes are picked round-robin across the 6 UI areas and across storms, at most
`max_fixes_per_storm` per storm and at least `min_hours_apart` between fixes of the same storm.

    python scripts/classification/prepare_candidates.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.utils import (  # noqa: E402
    cfg_file, class_mapping_json, ensure_dir, load_config, project_path, set_seed, task_classes, ui_area, write_json,
)

CONFIG = ROOT / "configs" / "classification.yaml"
AREAS = ["arabian_sea", "bay_of_bengal", "south_indian_ocean", "western_pacific", "eastern_pacific", "southern_pacific"]
IMD_FINE = [(17, 27, "D"), (28, 33, "DD"), (34, 47, "CS"), (48, 63, "SCS"), (64, 89, "VSCS"), (90, 119, "ESCS"), (120, 999, "SuCS")]


def class_of(wind: pd.Series, classes: list[dict]) -> pd.Series:
    """Class id for each wind (kt); -1 when below the IMD depression threshold or missing."""
    out = pd.Series(-1, index=wind.index, dtype=int)
    for c in classes:
        hi = np.inf if c["max_kt"] is None else c["max_kt"]
        out[(wind >= c["min_kt"]) & (wind <= hi)] = c["id"]
    return out


def imd_fine(wind: pd.Series) -> pd.Series:
    out = pd.Series("", index=wind.index)
    for lo, hi, code in IMD_FINE:
        out[(wind >= lo) & (wind <= hi)] = code
    return out


def select_class(pool: pd.DataFrame, n: int, chosen: dict, per_storm: dict, cap: int, gap_h: float, rng) -> list[int]:
    """Round-robin over areas (one pick per area per round), and over storms within an area."""
    queues: dict[str, list] = {}
    for area, g in pool.groupby("area"):
        storms = list(g.SID.unique())
        rng.shuffle(storms)
        by_storm = {sid: list(rng.permutation(idx)) for sid, idx in g.groupby("SID").groups.items()}
        queues[area] = [[sid, by_storm[sid]] for sid in storms]
    ptr = {a: 0 for a in queues}
    active = [a for a in AREAS if a in queues] + [a for a in queues if a not in AREAS]
    gap = pd.Timedelta(hours=gap_h)
    picked: list[int] = []
    while len(picked) < n and active:
        for area in list(active):
            if len(picked) >= n:
                break
            storms, tries, got = queues[area], 0, False
            while storms and tries < len(storms) and not got:
                k = ptr[area] % len(storms)
                sid, q = storms[k]
                if per_storm.get(sid, 0) >= cap or not q:
                    storms.pop(k)
                    continue
                idx = q.pop()
                t = pool.at[idx, "time"]
                if all(abs(t - s) >= gap for s in chosen.get(sid, [])):
                    picked.append(idx)
                    chosen.setdefault(sid, []).append(t)
                    per_storm[sid] = per_storm.get(sid, 0) + 1
                    got = True
                ptr[area] = k + 1
                tries += 1
            if not storms:
                active.remove(area)
    return picked


def main() -> int:
    cfg = load_config(CONFIG)
    seed = int(cfg["project"]["seed"])
    set_seed(seed)
    rng = np.random.default_rng(seed)
    cc, classes = cfg["candidates"], task_classes(cfg)
    hw = float(cfg["gridsat"]["half_width_deg"])

    cols = ["SID", "SEASON", "BASIN", "SUBBASIN", "NAME", "ISO_TIME", "NATURE", "LAT", "LON", "WMO_WIND", "WMO_AGENCY",
            "USA_WIND", "USA_SSHS", "TRACK_TYPE"]
    ib = pd.read_csv(cfg["sources"]["ibtracs"], usecols=cols, skiprows=[1], keep_default_na=False, na_values=["", " "], low_memory=False)
    for c in ["SEASON", "LAT", "LON", "WMO_WIND", "USA_WIND", "USA_SSHS"]:
        ib[c] = pd.to_numeric(ib[c], errors="coerce")
    ib["time"] = pd.to_datetime(ib.ISO_TIME, errors="coerce")

    funnel = {}
    df = ib[(ib.SEASON >= cc["min_season"]) & ib.BASIN.isin(cc["basins"])]
    funnel["fixes_in_basins_since_min_season"] = len(df)
    df = df[df.TRACK_TYPE == "main"]
    funnel["main_track"] = len(df)
    df = df[df.NATURE.isin(cc["natures"])]
    funnel["tropical_nature_TS"] = len(df)
    df = df[(df.time.dt.minute == 0) & (df.time.dt.hour % 3 == 0)]
    funnel["synoptic_3_hourly"] = len(df)
    df = df[df.LAT.abs() <= 70 - hw]
    funnel["inside_gridsat_coverage"] = len(df)
    funnel["usa_wind_missing"] = int(df[cc["wind_column"]].isna().sum())
    df = df[df[cc["wind_column"]].notna()]
    df = df.assign(label=class_of(df[cc["wind_column"]], classes))
    funnel["below_17kt"] = int((df.label < 0).sum())
    df = df[df.label >= 0].copy()
    funnel["labelled_fixes"] = len(df)
    funnel["labelled_storms"] = int(df.SID.nunique())
    df["region"], df["subregion"] = zip(*[ui_area(b, s if isinstance(s, str) else None, lon) for b, s, lon in zip(df.BASIN, df.SUBBASIN, df.LON)])
    df["area"] = df.subregion.where(df.subregion != "", df.region)

    # ---------------- link to dataset A and compare winds
    a = pd.read_excel(cfg["sources"]["finalized_metadata"], sheet_name="ML_Dataset", usecols=["cyclone_id", "timestamp", "wind_speed"])
    df = df.merge(a.rename(columns={"cyclone_id": "SID", "timestamp": "time", "wind_speed": "dataset_a_wind_kt"}), on=["SID", "time"], how="left", indicator=True)
    df["in_dataset_a"] = df.pop("_merge") == "both"
    both = df.dataset_a_wind_kt.notna()
    ni = df[(df.BASIN == "NI") & (df.WMO_AGENCY == "newdelhi") & df.WMO_WIND.notna()]
    imd_cls = class_of(ni.WMO_WIND, classes)
    agree = (imd_cls == ni.label)

    # ---------------- availability + selection (rarest class first)
    avail = df.groupby(["label", "area"]).agg(fixes=("SID", "size"), storms=("SID", "nunique")).reset_index()
    order = df.label.value_counts().sort_values().index.tolist()
    chosen_times: dict = {}
    per_storm: dict = {}
    picks = []
    for label in order:
        pool = df[df.label == label]
        idx = select_class(pool, int(cc["per_class"]), chosen_times, per_storm, int(cc["max_fixes_per_storm"]), float(cc["min_hours_apart"]), rng)
        picks.append(df.loc[idx])
    cand = pd.concat(picks).sort_values(["label", "time"]).reset_index(drop=True)
    by_id = {c["id"]: c for c in classes}
    out = pd.DataFrame({
        "sample_id": [f"CLS_{i:05d}" for i in range(1, len(cand) + 1)],
        "label": cand.label,
        "class_code": cand.label.map(lambda i: by_id[i]["code"]),
        "class_name": cand.label.map(lambda i: by_id[i]["name"]),
        "storm_id": cand.SID,
        "name": cand.NAME,
        "basin": cand.BASIN,
        "subbasin": cand.SUBBASIN,
        "region": cand.region,
        "subregion": cand.subregion,
        "timestamp": cand.time.dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "latitude": cand.LAT,
        "longitude": cand.LON,
        "nature": cand.NATURE,
        "usa_wind_kt": cand.USA_WIND,
        "imd_category_of_usa_wind": imd_fine(cand.USA_WIND),
        "wmo_wind_kt": cand.WMO_WIND,
        "wmo_agency": cand.WMO_AGENCY,
        "usa_sshs": cand.USA_SSHS,
        "dataset_a_wind_kt": cand.dataset_a_wind_kt,
        "in_dataset_a": cand.in_dataset_a,
    })
    meta_dir = ensure_dir(project_path(cfg, "metadata"))
    out.to_csv(meta_dir / cfg_file(cfg, "candidates", "candidates.csv"), index=False)

    mapping = class_mapping_json(classes)
    write_json(ensure_dir(project_path(cfg, "models")) / "class_mapping.json", mapping)

    summary = {
        "sources": {"dataset_a": cfg["sources"]["finalized_metadata"], "ibtracs": cfg["sources"]["ibtracs"]},
        "label_rule": "IMD category thresholds (kt) applied to IBTrACS USA_WIND; classes in configs/classification.yaml",
        "class_mapping": mapping,
        "funnel": funnel,
        "fixes_in_dataset_a": int(df.in_dataset_a.sum()),
        "dataset_a_wind_vs_usa_wind_same_class": round(float((class_of(df.dataset_a_wind_kt[both], classes) == df.label[both]).mean()), 4),
        "ni_imd_wind_vs_usa_wind": {
            "fixes_with_both": int(len(ni)),
            "same_class": round(float(agree.mean()), 4) if len(ni) else None,
            "usa_class_higher": round(float((ni.label > imd_cls).mean()), 4) if len(ni) else None,
            "usa_class_lower": round(float((ni.label < imd_cls).mean()), 4) if len(ni) else None,
            "confusion_imd_rows_usa_cols": pd.crosstab(imd_cls, ni.label).to_dict() if len(ni) else {},
        },
        "available": {f"{by_id[int(r.label)]['code']}/{r.area}": {"fixes": int(r.fixes), "storms": int(r.storms)} for r in avail.itertuples()},
        "available_by_class": {by_id[int(k)]["code"]: {"fixes": int(v), "storms": int(df[df.label == k].SID.nunique())} for k, v in df.label.value_counts().sort_index().items()},
        "candidates_by_class_area": {f"{by_id[int(k[0])]['code']}/{k[1]}": int(v) for k, v in cand.groupby(["label", "area"]).size().items()},
        "candidates_by_class": {by_id[int(k)]["code"]: int(v) for k, v in cand.label.value_counts().sort_index().items()},
        "candidate_storms": int(cand.SID.nunique()),
        "missing_values_in_candidates": {c: int(n) for c, n in out.isna().sum().items() if n},
    }
    write_json(ensure_dir(project_path(cfg, "reports", "audit")) / "candidates_summary.json", summary)
    print("Funnel:", funnel)
    print("Available by class:", summary["available_by_class"])
    print(f"NI IMD-wind vs USA-wind same class: {summary['ni_imd_wind_vs_usa_wind']['same_class']} "
          f"(USA higher {summary['ni_imd_wind_vs_usa_wind']['usa_class_higher']}) over {len(ni)} fixes")
    print("Candidates by class:", summary["candidates_by_class"], " storms:", summary["candidate_storms"])
    print("Candidates by class/area:", summary["candidates_by_class_area"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
