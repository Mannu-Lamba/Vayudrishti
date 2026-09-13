#!/usr/bin/env python3
"""Storm/event-grouped, stratified train / validation / test split (any task).

    python scripts/create_splits.py                                      # identification
    python scripts/create_splits.py --config configs/classification.yaml

Grouping (a group never spans two splits):
  1. same IBTrACS storm_id (all fixes of a storm stay together);
  2. crops whose 18°×18° boxes intersect within `splits.group_overlap_hours` (shared cloud field —
     the event grouping for negatives, which have no storm id; it also ties nearby storms together);
  3. near-duplicate or pixel-identical images.

Stratification: StratifiedGroupKFold (seed from config) with 20 folds on the stratum
label × area (× intensity | difficulty for identification); 3 folds → test (15 %),
3 → validation (15 %), 14 → train (70 %).

Writes the split CSVs, adds split/group_id to the manifest and saves <reports>/audit/split_summary.json.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedGroupKFold

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.utils import (  # noqa: E402
    cfg_file, ensure_dir, is_multiclass, load_config, project_path, set_seed, split_path, wrap_dlon, write_json,
)

SPLIT_COLUMNS = ["image_path", "label", "storm_id", "basin", "region", "subregion", "timestamp",
                 "image_id", "class_name", "class_code", "intensity", "difficulty", "group_id"]
N_FOLDS = 20


class UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def overlapping_pairs(m: pd.DataFrame, hours: float, box_deg: float):
    """Yield index pairs whose crop boxes intersect and whose times differ by <= hours."""
    t = pd.to_datetime(m.timestamp, utc=True).dt.tz_localize(None).to_numpy()
    order = np.argsort(t)
    ts, lat, lon = t[order], m.latitude.to_numpy()[order], m.longitude.to_numpy()[order]
    window = np.timedelta64(int(hours * 3600), "s")
    for a in range(len(order)):
        b_end = np.searchsorted(ts, ts[a] + window, side="right")
        if b_end <= a + 1:
            continue
        sl = slice(a + 1, b_end)
        hit = (np.abs(lat[sl] - lat[a]) < box_deg) & (np.abs(wrap_dlon(lon[sl] - lon[a])) < box_deg)
        for b in np.flatnonzero(hit) + a + 1:
            yield int(order[a]), int(order[b])


def build_groups(m: pd.DataFrame, near: pd.DataFrame, cfg: dict) -> tuple[np.ndarray, dict]:
    uf = UnionFind(len(m))
    reasons = {"storm": 0, "crop_overlap": 0, "near_duplicate": 0, "pixel_identical": 0}
    storms = m.storm_id.fillna("").astype(str)
    for _, idx in m[storms != ""].groupby(storms[storms != ""]).indices.items():
        for j in idx[1:]:
            uf.union(int(idx[0]), int(j))
            reasons["storm"] += 1
    box = 2 * float(cfg["gridsat"]["half_width_deg"])
    for a, b in overlapping_pairs(m, float(cfg["splits"]["group_overlap_hours"]), box):
        uf.union(a, b)
        reasons["crop_overlap"] += 1
    pos_of = {s: i for i, s in enumerate(m.sample_id)}
    for r in near.itertuples():
        if r.sample_a in pos_of and r.sample_b in pos_of:
            uf.union(pos_of[r.sample_a], pos_of[r.sample_b])
            reasons["near_duplicate"] += 1
    for _, idx in m.groupby("pixel_sha256").indices.items():
        for j in idx[1:]:
            uf.union(int(idx[0]), int(j))
            reasons["pixel_identical"] += 1
    roots = np.array([uf.find(i) for i in range(len(m))])
    _, gid = np.unique(roots, return_inverse=True)
    return gid, reasons


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=None, help="task config (default: identification)")
    args = parser.parse_args()
    cfg = load_config(args.config)
    seed = int(cfg["project"]["seed"])
    set_seed(seed)
    man_path = project_path(cfg, "metadata", cfg_file(cfg, "manifest", "identification_dataset.csv"))
    m = pd.read_csv(man_path, keep_default_na=False, na_values=[""])
    m = m.drop(columns=[c for c in ("split", "group_id") if c in m.columns])
    near_path = project_path(cfg, "metadata", cfg_file(cfg, "near_duplicates", "near_duplicates.csv"))
    near = pd.read_csv(near_path) if near_path.exists() else pd.DataFrame(columns=["sample_a", "sample_b"])

    gid, link_counts = build_groups(m, near, cfg)
    m["group_id"] = [f"G{g:04d}" for g in gid]
    area = m.subregion.fillna("").where(m.subregion.fillna("") != "", m.region)
    if is_multiclass(cfg):
        stratum = m.label.astype(str) + "|" + area
    else:
        detail = m.intensity.fillna("").where(m.label == 1, m.difficulty.fillna(""))
        stratum = m.label.astype(str) + "|" + area + "|" + detail

    sgkf = StratifiedGroupKFold(n_splits=N_FOLDS, shuffle=True, random_state=seed)
    fold = np.empty(len(m), dtype=int)
    for k, (_, test_idx) in enumerate(sgkf.split(np.zeros(len(m)), stratum, groups=m.group_id)):
        fold[test_idx] = k
    n_test = round(N_FOLDS * cfg["splits"]["test"])
    n_val = round(N_FOLDS * cfg["splits"]["val"])
    m["split"] = np.where(fold < n_test, "test", np.where(fold < n_test + n_val, "val", "train"))

    columns = [c for c in SPLIT_COLUMNS if c in m.columns]
    for split in ("train", "val", "test"):
        path = split_path(cfg, split)
        ensure_dir(path.parent)
        m[m.split == split][columns].to_csv(path, index=False)
    m.to_csv(man_path, index=False)

    sizes = m.group_id.value_counts()
    tab = lambda col: {s: {str(k): int(v) for k, v in g[col].value_counts().sort_index().items()} for s, g in m.groupby("split")}  # noqa: E731
    storm_rows = m.storm_id.fillna("").astype(str) != ""
    summary = {
        "seed": seed,
        "method": f"StratifiedGroupKFold(n_splits={N_FOLDS}, shuffle=True) on {'label|area' if is_multiclass(cfg) else 'label|area|intensity-or-difficulty'}; "
                  f"{n_test} folds test, {n_val} folds val, rest train",
        "group_links": link_counts,
        "groups": int(sizes.size),
        "group_size": {"max": int(sizes.max()), "median": float(sizes.median()), "mean": round(float(sizes.mean()), 2),
                       "singletons": int((sizes == 1).sum()), "largest_share": round(float(sizes.max() / len(m)), 4)},
        "largest_groups": [{"group_id": g, "size": int(n), "labels": {str(k): int(v) for k, v in m[m.group_id == g].label.value_counts().items()},
                            "areas": area[m.group_id == g].value_counts().to_dict()} for g, n in sizes.head(5).items()],
        "rows": {s: int(n) for s, n in m.split.value_counts().items()},
        "share": {s: round(float(n / len(m)), 4) for s, n in m.split.value_counts().items()},
        "label": tab("label"),
        "area": {s: {str(k): int(v) for k, v in area[g.index].value_counts().sort_index().items()} for s, g in m.groupby("split")},
        "storms": {s: int(g[storm_rows[g.index]].storm_id.nunique()) for s, g in m.groupby("split")},
        "groups_per_split": {s: int(g.group_id.nunique()) for s, g in m.groupby("split")},
    }
    if not is_multiclass(cfg):
        summary["cyclone_share"] = {s: round(float(g.label.mean()), 4) for s, g in m.groupby("split")}
        summary["intensity"] = {s: {str(k): int(v) for k, v in g[g.label == 1].intensity.value_counts().sort_index().items()} for s, g in m.groupby("split")}
        summary["difficulty"] = {s: {str(k): int(v) for k, v in g[g.label == 0].difficulty.value_counts().sort_index().items()} for s, g in m.groupby("split")}
    write_json(project_path(cfg, "reports", "audit", "split_summary.json"), summary)
    print(f"Groups: {summary['groups']} (largest {summary['group_size']['max']} = {summary['group_size']['largest_share']:.1%}); links {link_counts}")
    for s in ("train", "val", "test"):
        print(f"  {s:<5} rows {summary['rows'][s]:>4} ({summary['share'][s]:.1%})  labels {summary['label'][s]}  storms {summary['storms'][s]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
