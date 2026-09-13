#!/usr/bin/env python3
"""STEP 1 — data retrieval: IBTrACS v04r01 → clean 6-hourly observation table.

Raw IBTrACS → basin/season/main-track filter → synoptic 6-hourly fixes → UTC timestamps → UI area
(identification_model ui_area: basin + subbasin, or longitude for NI) → validation (the same
validate_observations the API uses) → data/processed/observations.csv.gz + reports/data_audit.{json,md}.

The original IBTrACS file is only read, never modified.

    python scripts/build_dataset.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.common import ensure_dir, identification_utils, load_config, project_path, sequence_config, write_json  # noqa: E402
from src.data import OBSERVATIONS_FILE  # noqa: E402
from ml.prediction.features import validate_observations  # noqa: E402
from ml.prediction.sequences import build_samples  # noqa: E402

IBTRACS_COLUMNS = ["SID", "SEASON", "BASIN", "SUBBASIN", "NAME", "ISO_TIME", "NATURE", "LAT", "LON", "TRACK_TYPE",
                   "DIST2LAND", "USA_ATCF_ID", "USA_WIND", "USA_PRES", "STORM_SPEED", "STORM_DIR"]

ENVIRONMENTAL_FIELDS = {
    "sea_surface_temperature": "NOT AVAILABLE — IBTrACS has no SST and no SST product is in the project",
    "vertical_wind_shear": "NOT AVAILABLE — needs reanalysis winds (e.g. ERA5 200/850 hPa), not in the project",
    "relative_humidity": "NOT AVAILABLE — needs reanalysis, not in the project",
    "environmental_pressure": "NOT AVAILABLE — only the storm's central pressure (USA_PRES) exists",
    "distance_to_land": "AVAILABLE — IBTrACS DIST2LAND (km), used as a feature",
}
SATELLITE_NOTE = ("NOT USED — GridSat crops exist only for the fixes sampled for the identification and classification "
                  "datasets (the NOAA server outage stopped further downloads). A temporal window needs an image for "
                  "every 6-hourly step, so there are no per-fix satellite features yet; the feature list has no "
                  "satellite group until per-fix embeddings exist.")


def main() -> int:
    cfg = load_config()
    d = cfg["data"]
    raw = pd.read_csv(cfg["sources"]["ibtracs"], usecols=IBTRACS_COLUMNS, skiprows=[1], keep_default_na=False,
                      na_values=[" ", ""], low_memory=False)
    funnel = {"ibtracs_rows": int(len(raw))}
    raw["SEASON"] = pd.to_numeric(raw["SEASON"], errors="coerce")
    df = raw[(raw["SEASON"] >= d["min_season"]) & raw["BASIN"].isin(d["basins"])]
    funnel["basins_and_seasons"] = int(len(df))
    df = df[df["TRACK_TYPE"] == d["track_type"]]
    funnel["main_track"] = int(len(df))
    times = pd.to_datetime(df["ISO_TIME"], utc=True)
    synoptic = times.dt.hour.isin(d["synoptic_hours"]) & (times.dt.minute == 0) & (times.dt.second == 0)
    df = df[synoptic].reset_index(drop=True)
    times = times[synoptic].reset_index(drop=True)
    funnel["synoptic_6_hourly"] = int(len(df))

    ui_area = identification_utils().ui_area
    lon = pd.to_numeric(df["LON"], errors="coerce")
    areas = [ui_area(b, s, l) for b, s, l in zip(df["BASIN"], df["SUBBASIN"], lon)]
    obs = pd.DataFrame({
        "storm_id": df["SID"], "name": df["NAME"], "season": df["SEASON"].astype(int), "basin": df["BASIN"],
        "subbasin": df["SUBBASIN"], "region": [a[0] for a in areas], "subregion": [a[1] for a in areas],
        "time": times, "lat": pd.to_numeric(df["LAT"], errors="coerce"), "lon": lon,
        "wind_kt": pd.to_numeric(df[d["wind_column"]], errors="coerce"),
        "pressure_hpa": pd.to_numeric(df[d["pressure_column"]], errors="coerce"),
        "nature": df["NATURE"], "dist2land_km": pd.to_numeric(df["DIST2LAND"], errors="coerce"),
        "storm_speed_kt": pd.to_numeric(df["STORM_SPEED"], errors="coerce"),
        "storm_dir_deg": pd.to_numeric(df["STORM_DIR"], errors="coerce"), "atcf_id": df["USA_ATCF_ID"],
    })
    obs["area"] = np.where(obs["subregion"].astype(str) != "", obs["subregion"], obs["region"])
    clean, validation = validate_observations(obs)
    funnel["after_validation"] = int(len(clean))

    samples = build_samples(clean, sequence_config(cfg))
    out = ensure_dir(project_path(cfg, "processed")) / OBSERVATIONS_FILE
    clean.assign(time=clean["time"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")).to_csv(out, index=False, compression="gzip")

    missing = {c: round(float(clean[c].isna().mean()), 4) for c in ("wind_kt", "pressure_hpa", "dist2land_km", "storm_speed_kt")}
    by_basin = {b: {"storms": int(g.storm_id.nunique()), "fixes": int(len(g)),
                    "wind_missing": round(float(g.wind_kt.isna().mean()), 4), "pressure_missing": round(float(g.pressure_hpa.isna().mean()), 4)}
                for b, g in clean.groupby("basin")}
    by_area = {a or "(none)": {"storms": int(g.storm_id.nunique()), "fixes": int(len(g))} for a, g in clean.groupby("area")}
    audit = {
        "source": cfg["sources"]["ibtracs"],
        "funnel": funnel,
        "validation": validation,
        "storms": int(clean.storm_id.nunique()),
        "fixes": int(len(clean)),
        "period": [clean.time.min().isoformat(), clean.time.max().isoformat()],
        "fixes_per_storm": {k: round(float(v), 1) for k, v in clean.groupby("storm_id").size().describe().items()},
        "missing_fraction": missing,
        "by_basin": by_basin,
        "by_area": by_area,
        "nature": {k: int(v) for k, v in clean.nature.value_counts().items()},
        "fields_used": {"position": "LAT/LON (IBTrACS combined best track)", "wind": f"{d['wind_column']} (kt, 1-min)",
                        "pressure": f"{d['pressure_column']} (hPa)", "time": "ISO_TIME (UTC)", "nature": "NATURE",
                        "distance_to_land": "DIST2LAND (km)", "area": "BASIN + SUBBASIN (NI: longitude when SUBBASIN absent)"},
        "environmental_fields": ENVIRONMENTAL_FIELDS,
        "satellite_features": SATELLITE_NOTE,
        "sequence": sequence_config(cfg).to_dict(),
        "samples_all_storms": int(len(samples)),
        "samples_skipped": samples.skipped,
    }
    rep = ensure_dir(project_path(cfg, "reports"))
    write_json(rep / "data_audit.json", audit)

    lines = [
        "# Prediction data audit", "",
        f"Source: `{audit['source']}` (read only). {audit['storms']:,} storms, {audit['fixes']:,} six-hourly fixes, "
        f"{audit['period'][0][:10]} → {audit['period'][1][:10]}.", "",
        "## Funnel", "", "| step | rows |", "|---|---|", *[f"| {k} | {v:,} |" for k, v in funnel.items()], "",
        f"Validation: {validation}", "",
        "## Missing values", "", "| field | missing |", "|---|---|", *[f"| {k} | {v:.1%} |" for k, v in missing.items()], "",
        "| basin | storms | fixes | wind missing | pressure missing |", "|---|---|---|---|---|",
        *[f"| {b} | {v['storms']} | {v['fixes']:,} | {v['wind_missing']:.1%} | {v['pressure_missing']:.1%} |" for b, v in by_basin.items()], "",
        "## Environmental / meteorological fields", "", *[f"- **{k}**: {v}" for k, v in ENVIRONMENTAL_FIELDS.items()], "",
        f"**Satellite features:** {SATELLITE_NOTE}", "",
        "## Samples", "",
        f"Window {audit['sequence']['history_window_hours']} h every {audit['sequence']['observation_interval_hours']} h, "
        f"horizons {audit['sequence']['horizons_hours']} h → {len(samples):,} samples over all storms (before the split). "
        f"Skipped: {samples.skipped}.",
    ]
    (rep / "data_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Observations: {audit['fixes']:,} fixes from {audit['storms']:,} storms -> {out}")
    print(f"Funnel: {funnel}")
    print(f"Validation: {validation}")
    print(f"Missing: {missing}")
    print(f"Samples (all storms): {len(samples):,}; skipped {samples.skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
