#!/usr/bin/env python3
"""Storm-level train / val / test split — no storm is ever divided between splits.

Every storm (IBTrACS SID) goes to exactly one split, stratified by the storm's area at its first fix
so each region is represented in val and test. Seeded (project.seed). Individual observations or
samples are never split randomly.

Writes data/splits/storm_splits.csv and reports/split_summary.json.

    python scripts/create_splits.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.common import ensure_dir, load_config, project_path, sequence_config, write_json  # noqa: E402
from src.data import SPLITS_FILE, load_observations  # noqa: E402
from ml.prediction.sequences import build_samples  # noqa: E402

MIN_STRATUM = 6  # smaller strata are pooled so every stratum can reach all three splits


def main() -> int:
    cfg = load_config()
    seed, s = int(cfg["project"]["seed"]), cfg["splits"]
    obs = load_observations(cfg)
    storms = obs.groupby("storm_id", sort=True).agg(
        name=("name", "first"), season=("season", "first"), basin=("basin", "first"), area=("area", "first"),
        n_fixes=("time", "size"), first_fix=("time", "min"),
    ).reset_index()
    strata = storms["area"].replace("", "unknown")
    counts = strata.value_counts()
    strata = strata.where(strata.map(counts) >= MIN_STRATUM, "pooled")

    holdout = s["val"] + s["test"]
    train, rest = train_test_split(storms, test_size=holdout, stratify=strata, random_state=seed)
    val, test = train_test_split(rest, test_size=s["test"] / holdout, stratify=strata.loc[rest.index], random_state=seed)
    out = pd.concat([train.assign(split="train"), val.assign(split="val"), test.assign(split="test")])
    out = out.sort_values(["split", "storm_id"])[["storm_id", "split", "name", "season", "basin", "area", "n_fixes"]]
    path = ensure_dir(project_path(cfg, "splits")) / SPLITS_FILE
    out.to_csv(path, index=False)

    samples = build_samples(obs, sequence_config(cfg))
    sample_split = samples.meta["storm_id"].map(out.set_index("storm_id")["split"])
    summary = {
        "method": f"storm-level stratified split by first-fix area (seed {seed}); strata < {MIN_STRATUM} storms pooled",
        "storms": {k: int(v) for k, v in out.split.value_counts().items()},
        "fixes": {k: int(v) for k, v in out.groupby("split").n_fixes.sum().items()},
        "samples": {k: int(v) for k, v in sample_split.value_counts().items()},
        "storms_by_area": {f"{sp}/{a or 'unknown'}": int(n) for (sp, a), n in out.groupby(["split", "area"]).size().items()},
        "samples_by_area": {f"{sp}/{a or 'unknown'}": int(n) for (sp, a), n in
                            samples.meta.assign(split=sample_split).groupby(["split", "area"]).size().items()},
        "seasons": {sp: [int(g.season.min()), int(g.season.max())] for sp, g in out.groupby("split")},
    }
    write_json(ensure_dir(project_path(cfg, "reports")) / "split_summary.json", summary)
    print(f"Storms {summary['storms']}  fixes {summary['fixes']}  samples {summary['samples']}")
    print(f"-> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
