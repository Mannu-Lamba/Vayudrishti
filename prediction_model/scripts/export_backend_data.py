#!/usr/bin/env python3
"""Export the observation histories the API serves predictions from.

By default only held-out TEST storms are exported, so every forecast the API shows is out-of-sample
and can be checked against the storm's real later track. Writes backend/app/data/cyclones/
observations.csv.gz and manifest.json.

    python scripts/export_backend_data.py [--splits test]
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.common import ensure_dir, load_config, project_path, sha256_file, write_json  # noqa: E402
from src.data import load_observations, load_splits  # noqa: E402

COLUMNS = ["storm_id", "name", "season", "basin", "subbasin", "region", "subregion", "area", "time", "lat", "lon",
           "wind_kt", "pressure_hpa", "nature", "dist2land_km", "storm_speed_kt", "storm_dir_deg", "atcf_id", "split"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--splits", nargs="+", default=["test"], choices=["train", "val", "test"])
    args = parser.parse_args()
    cfg = load_config()
    obs, splits = load_observations(cfg), load_splits(cfg)
    obs = obs.assign(split=obs.storm_id.map(splits.set_index("storm_id")["split"]))
    out = obs[obs.split.isin(args.splits)][COLUMNS]
    out = out.assign(time=out["time"].dt.strftime("%Y-%m-%dT%H:%M:%SZ"))
    folder = ensure_dir(project_path(cfg, "backend_data"))
    path = folder / "observations.csv.gz"
    out.to_csv(path, index=False, compression="gzip")
    write_json(folder / "manifest.json", {
        "source": cfg["sources"]["ibtracs"], "built_by": "prediction_model/scripts/export_backend_data.py",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "splits": args.splits,
        "storms": int(out.storm_id.nunique()), "fixes": int(len(out)), "sha256": sha256_file(path),
        "note": "Held-out storms only: forecasts served from these are out-of-sample.",
    })
    print(f"Exported {out.storm_id.nunique()} storms / {len(out):,} fixes ({', '.join(args.splits)}) -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
