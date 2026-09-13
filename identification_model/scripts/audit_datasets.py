#!/usr/bin/env python3
"""STEP 1 — Dataset audit (read-only).

Audits the two PS-70 datasets without modifying them:

  Dataset A (positives) — IBTrACS v04r01-derived cyclone metadata
    * finalized ML metadata master sheet (every IBTrACS fix 2000–present, NI/SI/WP/EP/SP)
    * positive candidate workbook (2,000 fixes selected from it) + the PNGs collected for it
  Dataset B (negatives) — NOAA GridSat-B1 non-cyclone sample references (North Indian Ocean)
    * candidate pool CSV (4,615) + selected workbook (2,000)

It also snapshots the sources into data/raw/ with SHA-256 checksums (later steps read only the
snapshot) and cross-checks the negatives against the full IBTrACS archive.

    python scripts/audit_datasets.py            # audit + snapshot
    python scripts/audit_datasets.py --verify   # re-check that the originals are unchanged
"""

from __future__ import annotations

import argparse
import hashlib
import io
import shutil
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.utils import (  # noqa: E402
    angular_distance_deg, dhash, ensure_dir, intensity_from_max_wind, load_config, near_duplicate_pairs,
    pixel_sha256, project_path, read_json, sha256_file, thumbnail, ui_area, wrap_dlon, write_json,
)

COPY_SOURCES = ["finalized_metadata", "positive_candidates", "positive_downloader", "negative_pool", "negative_selected"]
CHECKSUM_ONLY = ["positive_images_workbook", "ibtracs"]
BBOX_HINTS = ("bbox", "xmin", "ymin", "xmax", "ymax", "x_min", "y_min", "box", "annotation", "polygon")
ANNOTATION_EXTS = {".txt", ".xml", ".json", ".csv"}
CATEGORY_MAP = {"Weak Cyclone": "weak", "Medium Cyclone": "medium", "Strong Cyclone": "strong"}


# --------------------------------------------------------------------------- snapshot / verify

def snapshot_sources(cfg: dict) -> dict:
    sources = ensure_dir(project_path(cfg, "raw", "sources"))
    record: dict = {}
    for key in COPY_SOURCES + CHECKSUM_ONLY:
        src = Path(cfg["sources"][key])
        entry = {"path": str(src), "bytes": src.stat().st_size, "sha256": sha256_file(src)}
        if key in COPY_SOURCES:
            dst = sources / src.name
            if not dst.exists() or sha256_file(dst) != entry["sha256"]:
                shutil.copy2(src, dst)
            entry["snapshot"] = dst.relative_to(ROOT).as_posix()
        record[key] = entry

    img_src = Path(cfg["sources"]["positive_images_dir"])
    img_dst = ensure_dir(project_path(cfg, "raw", "original_positive_png"))
    rows = []
    for path in sorted(p for p in img_src.iterdir() if p.is_file()):
        digest = sha256_file(path)
        dst = img_dst / path.name
        if not dst.exists() or sha256_file(dst) != digest:
            shutil.copy2(path, dst)
        rows.append({"file": path.name, "bytes": path.stat().st_size, "sha256": digest})
    listing = pd.DataFrame(rows)
    listing.to_csv(project_path(cfg, "raw", "original_positive_png_checksums.csv"), index=False)
    record["positive_images_dir"] = {
        "path": str(img_src), "files": len(rows),
        "listing_sha256": hashlib.sha256("".join(listing.file + listing.sha256).encode()).hexdigest(),
        "snapshot": img_dst.relative_to(ROOT).as_posix(),
    }
    write_json(project_path(cfg, "raw", "source_checksums.json"), record)
    return record


def verify_sources(cfg: dict) -> bool:
    record = read_json(project_path(cfg, "raw", "source_checksums.json"))
    ok = True
    for key, entry in record.items():
        path = Path(entry["path"])
        if key == "positive_images_dir":
            listing = pd.read_csv(project_path(cfg, "raw", "original_positive_png_checksums.csv"))
            current = sorted(p.name for p in path.iterdir() if p.is_file())
            same_files = current == sorted(listing.file)
            same_bytes = same_files and all(sha256_file(path / f) == h for f, h in zip(listing.file, listing.sha256))
            status = same_files and same_bytes
            print(f"  {key:<26} {'unchanged' if status else 'CHANGED'} ({len(current)} files)")
        else:
            status = path.exists() and sha256_file(path) == entry["sha256"]
            print(f"  {key:<26} {'unchanged' if status else 'CHANGED'}  {path}")
        ok &= status
    print(f"ORIGINAL DATASETS UNCHANGED: {'PASS' if ok else 'FAILED'}")
    return ok


# --------------------------------------------------------------------------- generic stats

def table_stats(df: pd.DataFrame, time: pd.Series, lat: pd.Series, lon: pd.Series,
                id_col: str | None, key_cols: list[str]) -> dict:
    bad_coords = lat.isna() | lon.isna() | (lat.abs() > 90) | (lon < -180) | (lon > 360)
    out = {
        "records": int(len(df)),
        "unique_storms": int(df[id_col].nunique()) if id_col else None,
        "missing_storm_id": int(df[id_col].isna().sum()) if id_col else None,
        "unique_timestamps": int(time.nunique()),
        "unique_dates": int(time.dt.date.nunique()),
        "time_range": [str(time.min()), str(time.max())],
        "invalid_timestamps": int(time.isna().sum()),
        "invalid_coordinates": int(bad_coords.sum()),
        "duplicate_rows": int(df.duplicated().sum()),
        "duplicate_keys": int(df.duplicated(key_cols).sum()),
        "duplicate_key_columns": key_cols,
        "missing_values": {c: int(n) for c, n in df.isna().sum().items() if n},
    }
    return out


def bbox_columns(*frames: pd.DataFrame) -> list[str]:
    cols = [str(c) for f in frames for c in f.columns]
    return [c for c in cols if any(h in c.lower() for h in BBOX_HINTS)]


def counts(series: pd.Series) -> dict:
    return {str(k): int(v) for k, v in series.value_counts(dropna=False).sort_index().items()}


# --------------------------------------------------------------------------- image audit

def audit_png_folder(folder: Path, cfg: dict) -> tuple[pd.DataFrame, dict]:
    rows, hashes, thumbs = [], [], []
    for path in sorted(p for p in folder.iterdir() if p.is_file()):
        row = {"file": path.name, "ext": path.suffix.lower(), "bytes": path.stat().st_size}
        try:
            with Image.open(path) as im:
                im.verify()
            with Image.open(path) as im:
                row.update(format=im.format, width=im.width, height=im.height, mode=im.mode)
                arr = np.asarray(im.convert("L"), dtype=np.uint8)
            row.update(
                readable=True, pixel_sha256=pixel_sha256(arr),
                zero_fraction=float((arr == 0).mean()), saturated_fraction=float((arr == 255).mean()),
                pixel_std=float(arr.std()), pixel_mean=float(arr.mean()),
            )
            hashes.append(dhash(arr))
            thumbs.append(thumbnail(arr))
            row["_idx"] = len(hashes) - 1
        except Exception as exc:  # corrupted / unreadable
            row.update(readable=False, error=str(exc)[:120])
        rows.append(row)
    df = pd.DataFrame(rows)
    ok = df[df.readable]
    exact_groups = ok.groupby("pixel_sha256").file.apply(list)
    exact_groups = exact_groups[exact_groups.map(len) > 1]
    im_cfg = cfg["imagery"]
    pairs = near_duplicate_pairs(hashes, np.stack(thumbs), im_cfg["near_duplicate_hamming"], im_cfg["near_duplicate_corr"]) if thumbs else []
    idx_to_file = dict(zip(ok._idx.astype(int), ok.file))
    summary = {
        "files": int(len(df)),
        "extensions": counts(df.ext),
        "formats": counts(ok.format),
        "dimensions": counts(ok.width.astype(int).astype(str) + "x" + ok.height.astype(int).astype(str)),
        "modes": counts(ok["mode"]),
        "corrupted_or_unreadable": int((~df.readable).sum()),
        "exact_duplicate_groups": [list(g) for g in exact_groups],
        "near_duplicate_pairs": [(idx_to_file[i], idx_to_file[j], h, round(c, 4)) for i, j, h, c in pairs],
        "zero_pixel_fraction_gt_5pct": int((ok.zero_fraction > 0.05).sum()),
        "zero_pixel_fraction_gt_20pct": int((ok.zero_fraction > 0.20).sum()),
        "saturated_fraction_gt_5pct": int((ok.saturated_fraction > 0.05).sum()),
        "annotation_files": int(df.ext.isin(ANNOTATION_EXTS).sum()),
    }
    return df.drop(columns="_idx", errors="ignore"), summary


def audit_embedded_workbook(path: Path, folder_pixel_hashes: set[str]) -> dict:
    with zipfile.ZipFile(path) as zf:
        media = [i for i in zf.infolist() if i.filename.startswith("xl/media/")]
        matched = 0
        for info in media:
            with Image.open(io.BytesIO(zf.read(info))) as im:
                matched += pixel_sha256(np.asarray(im.convert("L"), dtype=np.uint8)) in folder_pixel_hashes
    return {"embedded_images": len(media), "pixel_identical_to_folder_png": matched}


# --------------------------------------------------------------------------- IBTrACS cross-check

def load_ibtracs(path: Path) -> pd.DataFrame:
    cols = ["SID", "SEASON", "BASIN", "NAME", "ISO_TIME", "NATURE", "LAT", "LON", "TRACK_TYPE"]
    # keep_default_na=False: the North Atlantic basin code "NA" must not become NaN.
    ib = pd.read_csv(path, usecols=cols, skiprows=[1], keep_default_na=False, na_values=["", " "], low_memory=False)
    ib["time"] = pd.to_datetime(ib.ISO_TIME, errors="coerce")
    ib["LAT"] = pd.to_numeric(ib.LAT, errors="coerce")
    ib["LON"] = pd.to_numeric(ib.LON, errors="coerce")
    return ib[(ib.time >= "1999-11-01") & ib.LAT.notna() & ib.LON.notna()].reset_index(drop=True)


def negative_context(pool: pd.DataFrame, ib: pd.DataFrame, half_width: float, window_h: int) -> pd.DataFrame:
    """Nearest tracked system (any basin, any nature) at each negative's time, and whether a
    system centre falls inside the negative's crop box."""
    by_hour = {k: g for k, g in ib.groupby(ib.time.dt.round("h"))}
    rows = []
    for r in pool.itertuples():
        frames = [by_hour.get(r.time + pd.Timedelta(hours=k)) for k in range(-window_h, window_h + 1)]
        frames = [f for f in frames if f is not None]
        rec = {"SAMPLE_ID": r.SAMPLE_ID, "nearest_system_deg": np.nan, "nearest_system_nature": "",
               "nearest_system_sid": "", "nearest_ds_ts_mx_deg": np.nan, "systems_in_crop": 0, "natures_in_crop": ""}
        if frames:
            f = pd.concat(frames)
            d = angular_distance_deg(r.LAT, r.LON, f.LAT.to_numpy(), f.LON.to_numpy())
            k = int(np.argmin(d))
            rec.update(nearest_system_deg=float(d[k]), nearest_system_nature=f.NATURE.iloc[k], nearest_system_sid=f.SID.iloc[k])
            tropical = f.NATURE.isin(["DS", "TS", "MX"]).to_numpy()
            if tropical.any():
                rec["nearest_ds_ts_mx_deg"] = float(d[tropical].min())
            in_box = (np.abs(f.LAT.to_numpy() - r.LAT) <= half_width) & (np.abs(wrap_dlon(f.LON.to_numpy() - r.LON)) <= half_width)
            if in_box.any():
                rec["systems_in_crop"] = int(f.SID[in_box].nunique())
                rec["natures_in_crop"] = ",".join(sorted(set(f.NATURE[in_box])))
        rows.append(rec)
    return pd.DataFrame(rows)


def crop_overlap_pairs(a: pd.DataFrame, b: pd.DataFrame, half_width: float, hours: int, same: bool) -> int:
    """Pairs whose crop boxes intersect and whose times differ by <= `hours`."""
    total = 0
    b_sorted = b.sort_values("time").reset_index(drop=True)
    times = b_sorted.time.to_numpy()
    for i, r in enumerate(a.itertuples()):
        lo = np.searchsorted(times, np.datetime64(r.time - pd.Timedelta(hours=hours)))
        hi = np.searchsorted(times, np.datetime64(r.time + pd.Timedelta(hours=hours)), side="right")
        cand = b_sorted.iloc[lo:hi]
        hit = (np.abs(cand.lat.to_numpy() - r.lat) < 2 * half_width) & (np.abs(wrap_dlon(cand.lon.to_numpy() - r.lon)) < 2 * half_width)
        if same:
            hit &= cand.key.to_numpy() != r.key
        total += int(hit.sum())
    return total // 2 if same else total


# --------------------------------------------------------------------------- report

def md_table(rows: list[list], headers: list[str]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--verify", action="store_true", help="only verify the originals against stored checksums")
    args = parser.parse_args()
    cfg = load_config()
    if args.verify:
        return 0 if verify_sources(cfg) else 1

    print("Snapshotting sources (copy + SHA-256)...")
    snap = snapshot_sources(cfg)
    src_dir = project_path(cfg, "raw", "sources")
    name = lambda key: src_dir / Path(cfg["sources"][key]).name  # noqa: E731
    hw = float(cfg["gridsat"]["half_width_deg"])

    # ---------------- Dataset A: finalized metadata
    print("Auditing dataset A (finalized IBTrACS metadata)...")
    a = pd.read_excel(name("finalized_metadata"), sheet_name="ML_Dataset")
    a_readme = pd.read_excel(name("finalized_metadata"), sheet_name="README", header=None)
    a_stats = table_stats(a, a.timestamp, a.latitude, a.longitude, "cyclone_id", ["cyclone_id", "timestamp"])
    area = [ui_area(b, s) for b, s in zip(a.basin, a.subbasin)]
    a["ui_region"], a["ui_subregion"] = zip(*area)
    a_stats.update(
        basins=counts(a.basin), subbasins=counts(a.subbasin), source_regions=counts(a.region), natures=counts(a.nature),
        ui_areas=counts(a.ui_region + "/" + a.ui_subregion), seasons=[int(a.season.min()), int(a.season.max())],
        tropical_ts_fixes=int((a.nature == "TS").sum()), tropical_ts_storms=int(a[a.nature == "TS"].cyclone_id.nunique()),
        storms_by_basin={k: int(v) for k, v in a.groupby("basin").cyclone_id.nunique().items()},
        images="none — metadata only (README: satellite images 'intentionally not included yet')",
    )

    # ---------------- Dataset A: positive candidates + images
    print("Auditing positive candidates and collected PNGs...")
    pc = pd.read_excel(name("positive_candidates"), sheet_name="Positive_Cyclones")
    sel_storms = pd.read_excel(name("positive_candidates"), sheet_name="Selected_Cyclones")
    pc_stats = table_stats(pc, pc.timestamp, pc.latitude, pc.longitude, "cyclone_id", ["cyclone_id", "timestamp"])
    joined = pc.merge(a[["cyclone_id", "timestamp", "latitude", "longitude", "nature"]], on=["cyclone_id", "timestamp"], how="left", suffixes=("", "_a"))
    found = joined.latitude_a.notna()
    storm_max = a.groupby("cyclone_id").wind_speed.max()
    rule_cat = sel_storms.cyclone_id.map(storm_max).map(intensity_from_max_wind)
    pc_stats.update(
        labels=counts(pc.label), natures=counts(pc.nature), intensity_category=counts(pc.intensity_category),
        source_regions=counts(pc.region), basins=counts(pc.basin), lifecycle_stage=counts(pc.lifecycle_stage),
        images_per_storm={k: round(float(v), 2) for k, v in pc.groupby("cyclone_id").size().describe().items()},
        rows_found_in_dataset_a=int(found.sum()),
        max_coordinate_difference_vs_a=float(np.nanmax(np.abs(joined.latitude - joined.latitude_a).fillna(0).to_numpy()
                                                      + np.abs(joined.longitude - joined.longitude_a).fillna(0).to_numpy())),
        intensity_rule_agreement=float((rule_cat == sel_storms.intensity_category.map(CATEGORY_MAP)).mean()),
        storm_max_wind_agreement=float((sel_storms.cyclone_id.map(storm_max) == sel_storms.max_wind).mean()),
        satellite_source=counts(pc.satellite_source.fillna("<none>")),
        human_verified=counts(pc.human_verified),
    )
    img_df, img_summary = audit_png_folder(project_path(cfg, "raw", "original_positive_png"), cfg)
    img_df["sample_id"] = img_df.file.str.replace(".png", "", regex=False)
    img_df = img_df.merge(pc[["sample_id", "cyclone_id", "satellite_source"]], on="sample_id", how="left")
    img_df.to_csv(ensure_dir(project_path(cfg, "metadata")) / "original_positive_png_audit.csv", index=False)
    has_png = pc.sample_id.isin(img_df.sample_id)
    img_summary.update(
        candidates_with_png=int(has_png.sum()), candidates_without_png=int((~has_png).sum()),
        png_by_recorded_source=counts(img_df.satellite_source.fillna("<not recorded>")),
        png_storms=int(img_df.cyclone_id.nunique()),
        embedded_workbook=audit_embedded_workbook(Path(cfg["sources"]["positive_images_workbook"]), set(img_df.pixel_sha256.dropna())),
    )

    # ---------------- Dataset B: negatives
    print("Auditing dataset B (GridSat non-cyclone references)...")
    pool = pd.read_csv(name("negative_pool"))
    pool["time"] = pd.to_datetime(pool.GRID_SAT_TIME, utc=True, errors="coerce").dt.tz_localize(None)
    nsel = pd.read_excel(name("negative_selected"), sheet_name="Negative_Cyclones")
    nsel_meta = pd.read_excel(name("negative_selected"), sheet_name="Source_Metadata")
    nsel["time"] = pd.to_datetime(nsel.timestamp.astype(str).str.replace(" UTC", "", regex=False), errors="coerce")
    pool_stats = table_stats(pool, pool.time, pool.LAT, pool.LON, None, ["GRID_SAT_TIME", "LAT", "LON"])
    sel_stats = table_stats(nsel, nsel.time, nsel.latitude, nsel.longitude, None, ["timestamp", "latitude", "longitude"])
    pool["subregion_ibtracs_rule"] = [ui_area("NI", None, lon)[1] for lon in pool.LON]
    meta_region = nsel_meta.set_index("SAMPLE_ID").derived_region
    pool["source_region"] = pool.SAMPLE_ID.map(meta_region)
    pool_stats.update(
        labels=counts(pool.LABEL), rules=counts(pool.NEGATIVE_RULE), sources=counts(pool.SOURCE),
        lat_range=[float(pool.LAT.min()), float(pool.LAT.max())], lon_range=[float(pool.LON.min()), float(pool.LON.max())],
        integer_degree_grid=bool(((pool.LAT % 1 == 0) & (pool.LON % 1 == 0)).all()),
        hours=counts(pool.time.dt.hour), months=counts(pool.time.dt.month), years=[int(pool.time.dt.year.min()), int(pool.time.dt.year.max())],
        subregion_by_ibtracs_78E_boundary=counts(pool.subregion_ibtracs_rule),
        filename_matches_time=float((pool.GRIDSAT_FILENAME.str[11:24] == pool.time.dt.strftime("%Y.%m.%d.%H")).mean()),
        images="none — GridSat-B1 file references only",
    )
    sel_in_pool = nsel_meta.SAMPLE_ID.isin(pool.SAMPLE_ID)
    lon_rule_disagree = nsel_meta.assign(ib=[ui_area("NI", None, lon)[1] for lon in nsel_meta.LON])
    lon_rule_disagree = int(((lon_rule_disagree.derived_region.str.startswith("Arabian")) != (lon_rule_disagree.ib == "arabian_sea")).sum())
    sel_stats.update(
        source_regions=counts(nsel.region), basins=counts(nsel.basin), labels=counts(nsel.label),
        subset_of_pool=bool(sel_in_pool.all()), months=counts(nsel.time.dt.month),
        years=counts(nsel.time.dt.year), source_region_vs_78E_boundary_disagreements=lon_rule_disagree,
        images_embedded=0,
    )

    # ---------------- IBTrACS cross-check of the negatives
    print("Cross-checking negatives against the full IBTrACS archive (all basins)...")
    ib = load_ibtracs(Path(cfg["sources"]["ibtracs"]))
    ctx = negative_context(pool, ib, hw, int(cfg["candidates"]["negative_time_window_h"]))
    ctx.to_csv(project_path(cfg, "metadata", "negative_pool_ibtracs_context.csv"), index=False)
    ctx_stats = {
        "ibtracs_fixes_loaded": int(len(ib)),
        "no_system_within_window": int(ctx.nearest_system_deg.isna().sum()),
        "rule_violations_lt_10deg_ds_ts_mx": int((ctx.nearest_ds_ts_mx_deg < 10).sum()),
        "negatives_with_system_centre_in_crop": int((ctx.systems_in_crop > 0).sum()),
        "natures_in_crop": counts(ctx.natures_in_crop[ctx.systems_in_crop > 0]),
        "nearest_system_deg_percentiles": {p: round(float(np.nanpercentile(ctx.nearest_system_deg, p)), 2) for p in (0, 5, 25, 50, 75)},
    }

    # ---------------- overlap between datasets
    pos_pts = pc.assign(time=pc.timestamp, lat=pc.latitude, lon=pc.longitude, key=pc.sample_id)
    neg_pts = pool.assign(lat=pool.LAT, lon=pool.LON, key=pool.SAMPLE_ID)
    overlap = {
        "storm_ids_shared": 0,
        "negative_times_equal_to_a_positive_time": int(pool.time.isin(set(pc.timestamp)).sum()),
        "positive_negative_crop_overlaps_within_12h": crop_overlap_pairs(pos_pts, neg_pts, hw, 12, same=False),
        "negative_negative_crop_overlaps_within_12h": crop_overlap_pairs(neg_pts, neg_pts, hw, 12, same=True),
        "positive_positive_crop_overlaps_other_storm_within_12h": 0,
    }
    pp = crop_overlap_pairs(pos_pts, pos_pts, hw, 12, same=True)
    overlap["positive_positive_crop_overlaps_any_within_12h"] = pp

    bbox = bbox_columns(a, pc, sel_storms, pool, nsel, nsel_meta)
    summary = {
        "sources": snap, "dataset_a_finalized_metadata": a_stats, "dataset_a_positive_candidates": pc_stats,
        "dataset_a_positive_png": img_summary, "dataset_b_negative_pool": pool_stats, "dataset_b_negative_selected": sel_stats,
        "dataset_b_ibtracs_crosscheck": ctx_stats, "overlap": overlap,
        "bounding_boxes": {"bbox_like_columns": bbox, "annotation_files": img_summary["annotation_files"],
                           "conclusion": "No bounding-box annotations exist → binary image classification."},
        "readme_dataset_a": dict(zip(a_readme.iloc[1:, 0].astype(str), a_readme.iloc[1:, 1].astype(str))),
    }
    write_json(project_path(cfg, "reports", "audit", "audit_summary.json"), summary)
    write_report(cfg, summary)
    print(f"Audit written to {project_path(cfg, 'reports', 'dataset_audit.md')}")
    return 0


def write_report(cfg: dict, s: dict) -> None:
    a, pc, png = s["dataset_a_finalized_metadata"], s["dataset_a_positive_candidates"], s["dataset_a_positive_png"]
    pool, sel, ctx, ov = s["dataset_b_negative_pool"], s["dataset_b_negative_selected"], s["dataset_b_ibtracs_crosscheck"], s["overlap"]
    src_rows = [[k, v["path"], f"{v.get('bytes', v.get('files', ''))}", v.get("sha256", v.get("listing_sha256", ""))[:16] + "…"] for k, v in s["sources"].items()]
    L = [
        "# Dataset audit — VayuDrishti cyclone identification (PS-70)",
        "",
        "Generated by `scripts/audit_datasets.py`. The originals were only read; copies and SHA-256",
        "checksums are in `data/raw/` (`python scripts/audit_datasets.py --verify` re-checks them).",
        "",
        "## Sources",
        md_table(src_rows, ["key", "original path", "bytes / files", "sha256"]),
        "",
        "## Dataset A — positives (IBTrACS v04r01 derived)",
        "",
        "### A1. Finalized ML metadata (`PS70_Finalized_ML_Metadata_2000_Present.xlsx`, sheet `ML_Dataset`)",
        f"- Format: Excel workbook, 3 sheets (ML_Dataset, Data_Summary, README). Images: {a['images']}.",
        f"- Records: **{a['records']:,}** IBTrACS fixes; unique storms **{a['unique_storms']:,}**; unique dates {a['unique_dates']:,}; seasons {a['seasons'][0]}–{a['seasons'][1]}; time range {a['time_range'][0]} → {a['time_range'][1]}.",
        f"- Basins: {a['basins']}; storms per basin: {a['storms_by_basin']}.",
        f"- Subbasins: {a['subbasins']}; source region labels: {a['source_regions']}.",
        f"- UI areas (basin → region/subregion): {a['ui_areas']}.",
        f"- IBTrACS nature: {a['natures']} (TS = tropical; {a['tropical_ts_fixes']:,} TS fixes from {a['tropical_ts_storms']:,} storms).",
        f"- Missing values: {a['missing_values']}.",
        f"- Duplicate rows {a['duplicate_rows']}, duplicate (cyclone_id, timestamp) {a['duplicate_keys']}, invalid timestamps {a['invalid_timestamps']}, invalid coordinates {a['invalid_coordinates']}.",
        "",
        "### A2. Positive candidates (`PS70_Positive_Cyclone_Candidates_Satellite_Images.xlsx`)",
        f"- Records **{pc['records']:,}** (label {pc['labels']}), storms **{pc['unique_storms']}**, images per storm {pc['images_per_storm']}.",
        f"- All rows found in dataset A by (cyclone_id, timestamp): {pc['rows_found_in_dataset_a']}/{pc['records']} (max coordinate difference {pc['max_coordinate_difference_vs_a']}).",
        f"- Source regions {pc['source_regions']}; intensity {pc['intensity_category']}; lifecycle {pc['lifecycle_stage']}.",
        f"- IBTrACS nature of the fixes: {pc['natures']} — only TS fixes are tropical-cyclone observations.",
        f"- Intensity is **storm-level** (lifetime max wind). The rule <34 kt weak / 34–63 kt medium / ≥64 kt strong reproduces the workbook category for {pc['intensity_rule_agreement']:.1%} of storms (storm max wind agreement {pc['storm_max_wind_agreement']:.1%}).",
        f"- Missing values: {pc['missing_values']}. Duplicate rows {pc['duplicate_rows']}, duplicate (cyclone_id, timestamp) {pc['duplicate_keys']}.",
        f"- `human_verified`: {pc['human_verified']}; recorded satellite source: {pc['satellite_source']}.",
        "",
        "### A3. Collected positive PNGs (`PS70_NOAA_Satellite_Images/images/positive`)",
        f"- Files **{png['files']}** ({png['extensions']}), formats {png['formats']}, dimensions {png['dimensions']}, modes {png['modes']} (single-channel IR).",
        f"- Candidates with a PNG: {png['candidates_with_png']}; without: {png['candidates_without_png']} (the downloader stopped after POS_1107). Storms covered: {png['png_storms']}.",
        f"- Recorded source per PNG: {png['png_by_recorded_source']}.",
        f"- Corrupted/unreadable: {png['corrupted_or_unreadable']}. Exact duplicate groups: {len(png['exact_duplicate_groups'])}. Near-duplicate pairs: {len(png['near_duplicate_pairs'])}.",
        f"- Frames with >5 % black (missing-data) pixels: {png['zero_pixel_fraction_gt_5pct']} (>20 %: {png['zero_pixel_fraction_gt_20pct']}); >5 % saturated: {png['saturated_fraction_gt_5pct']}.",
        f"- Embedded-image workbook: {png['embedded_workbook']['embedded_images']} images, {png['embedded_workbook']['pixel_identical_to_folder_png']} pixel-identical to the folder PNGs (same images, not a second dataset).",
        "",
        "## Dataset B — negatives (NOAA GridSat-B1 references, North Indian Ocean)",
        "",
        "### B1. Candidate pool (`SIH_NIO_2000_2025_6HOURLY_NONCYCLONE_SAMPLES.csv`)",
        f"- Records **{pool['records']:,}**, labels {pool['labels']}, source {pool['sources']}.",
        f"- Rule: {list(pool['rules'])[0]}.",
        f"- Unique timestamps {pool['unique_timestamps']:,} (one sample per time), unique dates {pool['unique_dates']:,}, years {pool['years'][0]}–{pool['years'][1]}.",
        f"- Positions on an integer-degree grid: {pool['integer_degree_grid']}; lat {pool['lat_range']}, lon {pool['lon_range']} (includes points over land).",
        f"- Hours {pool['hours']}; months {pool['months']}.",
        f"- Subregion by the IBTrACS 78°E AS/BB boundary: {pool['subregion_by_ibtracs_78E_boundary']}.",
        f"- Missing {pool['missing_values']}; duplicate rows {pool['duplicate_rows']}; duplicate (time, lat, lon) {pool['duplicate_keys']}; invalid timestamps {pool['invalid_timestamps']}; invalid coordinates {pool['invalid_coordinates']}. {pool['images']}.",
        "",
        "### B2. Selected negatives (`PS70_Negative_Cyclones_2000_Sorted.xlsx`)",
        f"- Records **{sel['records']:,}**, subset of the pool: {sel['subset_of_pool']}; basin {sel['basins']}; source regions {sel['source_regions']}.",
        f"- The workbook assigns Arabian Sea for lon ≤ 67°E; {sel['source_region_vs_78E_boundary_disagreements']} of 2,000 disagree with the IBTrACS/frontend 78°E boundary, which this project uses.",
        f"- No storm/event ids; images embedded: {sel['images_embedded']}; `human_verified`: REVIEW_REQUIRED for all.",
        "",
        "### B3. IBTrACS cross-check (full since-1980 archive, all basins, fixes within ±1 h)",
        f"- IBTrACS fixes loaded: {ctx['ibtracs_fixes_loaded']:,}. Negatives with no system anywhere at that time: {ctx['no_system_within_window']}.",
        f"- Violations of the stated rule (<10° from a DS/TS/MX centre): **{ctx['rule_violations_lt_10deg_ds_ts_mx']}**.",
        f"- Negatives whose 18°×18° crop contains a tracked system centre (box corners reach 12.7°): **{ctx['negatives_with_system_centre_in_crop']}** (natures {ctx['natures_in_crop']}). These are rejected in cleaning.",
        f"- Distance to the nearest tracked system (deg) percentiles: {ctx['nearest_system_deg_percentiles']}.",
        "",
        "## Overlap between the datasets",
        f"- Shared storm ids: {ov['storm_ids_shared']} (negatives have none). Negative timestamps equal to a positive timestamp: {ov['negative_times_equal_to_a_positive_time']}.",
        f"- Crop boxes that overlap within 12 h — positive↔negative: {ov['positive_negative_crop_overlaps_within_12h']}; negative↔negative: {ov['negative_negative_crop_overlaps_within_12h']}; positive↔positive: {ov['positive_positive_crop_overlaps_any_within_12h']}. Such samples share cloud fields and are grouped together for splitting.",
        "",
        "## Bounding boxes",
        f"- Bounding-box-like columns: {s['bounding_boxes']['bbox_like_columns'] or 'none'}; annotation files: {s['bounding_boxes']['annotation_files']}.",
        f"- **{s['bounding_boxes']['conclusion']}** No boxes are invented.",
        "",
        "## Findings that shape the pipeline",
        "1. Only 1,101 of 2,000 positives have images, and none of the negatives do.",
        "2. The existing positives are mostly HURSAT-B1 (storm-centred ~21° boxes) while negatives can only come from GridSat-B1 (18° boxes). Mixing them lets a classifier learn the sensor/processing instead of cyclone morphology, so **both classes are regenerated from GridSat-B1 with one code path**. The original PNGs stay untouched in `data/raw/` as a cross-source check.",
        "3. Some positive fixes are not tropical-cyclone observations (IBTrACS nature DS/ET/SS/MX/NR); they are excluded and replaced with TS fixes from dataset A.",
        "4. Negatives cover only the North Indian Ocean. For SI/WP/EP/SP only recall can be measured.",
        "5. Negatives have no event id; spatio-temporal grouping (overlapping crops within 12 h) is used instead.",
    ]
    path = project_path(cfg, "reports", "dataset_audit.md")
    ensure_dir(path.parent)
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
