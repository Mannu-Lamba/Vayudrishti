#!/usr/bin/env python3
"""Storm-level data-leakage check. Training refuses to start unless this passes.

Checks that no storm, observation or sample window crosses splits, and records SHA-256 hashes of the
split file and observation table the verdict applies to (train.py re-checks them).

    python scripts/check_leakage.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.common import load_config, project_path, sequence_config, sha256_file, write_json  # noqa: E402
from src.data import OBSERVATIONS_FILE, SPLITS_FILE, load_observations, load_splits  # noqa: E402
from ml.prediction.sequences import build_samples  # noqa: E402

PAIRS = (("train", "val"), ("train", "test"), ("val", "test"))


def main() -> int:
    cfg = load_config()
    obs, splits = load_observations(cfg), load_splits(cfg)
    by_split = {name: set(g.storm_id) for name, g in splits.groupby("split")}
    split_of = splits.set_index("storm_id")["split"]
    checks: dict[str, int] = {}
    checks["storms_listed_twice"] = int(splits.storm_id.duplicated().sum())
    for a, b in PAIRS:
        checks[f"storm_ids_shared_{a}_{b}"] = len(by_split.get(a, set()) & by_split.get(b, set()))
    checks["observed_storms_without_split"] = int((~obs.storm_id.isin(split_of.index)).sum())
    obs_split = obs.assign(split=obs.storm_id.map(split_of))
    checks["observations_in_more_than_one_split"] = int(obs_split.groupby(["storm_id", "time"]).split.nunique().gt(1).sum())

    # Every sample is built from one storm only, and that storm sits in exactly one split.
    samples = build_samples(obs, sequence_config(cfg))
    meta = samples.meta.assign(split=samples.meta.storm_id.map(split_of))
    checks["samples_without_split"] = int(meta.split.isna().sum())
    sample_sets = {name: set(zip(g.storm_id, g.t0)) for name, g in meta.groupby("split")}
    for a, b in PAIRS:
        checks[f"sample_origins_shared_{a}_{b}"] = len(sample_sets.get(a, set()) & sample_sets.get(b, set()))

    passed = all(v == 0 for v in checks.values())
    for name, value in checks.items():
        print(f"  {'ok  ' if value == 0 else 'FAIL'} {name}: {value}")
    verdict = "PASS" if passed else "FAIL"
    print(f"STORM-LEVEL DATA LEAKAGE CHECK: {verdict}")
    write_json(project_path(cfg, "reports", "leakage_check.json"), {
        "passed": passed, "verdict": verdict, "checks": checks,
        "storms_per_split": {k: len(v) for k, v in by_split.items()},
        "samples_per_split": {k: int(v) for k, v in meta.split.value_counts().items()},
        "split_file_sha256": sha256_file(project_path(cfg, "splits", SPLITS_FILE)),
        "observations_sha256": sha256_file(project_path(cfg, "processed", OBSERVATIONS_FILE)),
    })
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
