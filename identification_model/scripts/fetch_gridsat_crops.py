#!/usr/bin/env python3
"""Acquire GridSat-B1 IR crops for every candidate of a task (one code path for all imagery).

For each row of the task's candidates CSV: nearest 3-hourly GridSat-B1 v02r01 slot, an 18°×18°
IRWIN-CDR crop centred on the sample position, fetched as an OPeNDAP subset (only the crop is
transferred). Raw packed counts are stored north-up as .npz so rendering can change without
re-downloading. Resumable; every attempt is logged.

    python scripts/fetch_gridsat_crops.py [--config configs/classification.yaml] [--limit N] [--label L] [--force]
"""

from __future__ import annotations

import argparse
import csv
import struct
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.utils import CLASS_NAMES, cfg_file, ensure_dir, is_multiclass, load_config, project_path, wrap_dlon  # noqa: E402

LOG_FIELDS = ["sample_id", "label", "status", "url", "slot_time", "time_offset_h", "grid_lat", "grid_lon",
              "rows", "cols", "error", "elapsed_s"]
_local = threading.local()
_log_lock = threading.Lock()


class MissingFile(Exception):
    pass


def session() -> requests.Session:
    if not hasattr(_local, "session"):
        _local.session = requests.Session()
        _local.session.headers["User-Agent"] = "VayuDrishti-PS70-identification/1.0 (research)"
    return _local.session


def get(url: str, timeout: float, retries: int) -> bytes:
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = session().get(url, timeout=(30, timeout))
            if resp.status_code == 404:
                raise MissingFile(f"HTTP 404 {url}")
            resp.raise_for_status()
            if b"\nData:\n" not in resp.content:
                raise ValueError("response has no DAP data section")
            return resp.content
        except MissingFile:
            raise
        except (requests.RequestException, ValueError) as exc:
            last = exc
            time.sleep(2 ** (attempt + 1))
    raise RuntimeError(f"failed after {retries + 1} attempts: {last}")


def dap_arrays(content: bytes, dtypes: list[str]) -> list[np.ndarray]:
    """Decode the DAP2 binary section. Int16 and Float32 both travel as 4-byte big-endian values."""
    buf = memoryview(content)[content.find(b"\nData:\n") + 7:]
    out, pos = [], 0
    for dtype in dtypes:
        n = struct.unpack(">I", buf[pos:pos + 4])[0]
        pos += 8
        out.append(np.frombuffer(buf[pos:pos + 4 * n], dtype=dtype).copy())
        pos += 4 * n
    return out


def gridsat_url(cfg: dict, slot: pd.Timestamp) -> str:
    fname = f"GRIDSAT-B1.{slot:%Y.%m.%d.%H}.v02r01.nc"
    return f"{cfg['gridsat']['opendap_base']}/{slot:%Y}/{fname}"


def grid_axes(cfg: dict, cache: Path) -> tuple[np.ndarray, np.ndarray]:
    if cache.exists():
        with np.load(cache) as z:
            return z["lat"], z["lon"]
    url = gridsat_url(cfg, pd.Timestamp("2015-07-11 09:00"))
    lat, lon = dap_arrays(get(f"{url}.dods?lat,lon", cfg["gridsat"]["timeout_s"], cfg["gridsat"]["retries"]), [">f4", ">f4"])
    ensure_dir(cache.parent)
    np.savez(cache, lat=lat, lon=lon)
    return lat, lon


def crop_path(cfg: dict, sample_id: str, label: int) -> Path:
    """Where a sample's raw crop lives: <raw>/gridsat/<class>/<id>.npz (binary) or <raw>/gridsat/crops/<id>.npz."""
    folder = "crops" if is_multiclass(cfg) else CLASS_NAMES[int(label)]
    return project_path(cfg, "raw", "gridsat", folder, f"{sample_id}.npz")


def runs(idx: np.ndarray) -> list[tuple[int, int]]:
    """Split sorted-by-position (possibly wrapped) indices into contiguous inclusive runs."""
    out, start = [], idx[0]
    for prev, cur in zip(idx[:-1], idx[1:]):
        if cur != prev + 1:
            out.append((int(start), int(prev)))
            start = cur
    out.append((int(start), int(idx[-1])))
    return out


def fetch_one(row, cfg: dict, lats: np.ndarray, lons: np.ndarray, out_path: Path) -> dict:
    g = cfg["gridsat"]
    t0 = time.time()
    ts = pd.Timestamp(row.timestamp)
    ts = ts.tz_localize(None) if ts.tzinfo else ts
    slot = ts.round(f"{g['slot_hours']}h")
    offset = abs((ts - slot).total_seconds()) / 3600
    url = gridsat_url(cfg, slot)
    rec = {"sample_id": row.sample_id, "label": int(row.label), "url": url, "slot_time": slot.strftime("%Y-%m-%dT%H:%M:%SZ"),
           "time_offset_h": round(offset, 3)}
    try:
        if offset > g["max_time_offset_h"]:
            raise ValueError(f"time offset {offset:.2f} h exceeds limit")
        lat_res = float(np.median(np.diff(lats)))
        lon_res = float(np.median(np.diff(lons)))
        r_lat, r_lon = int(round(g["half_width_deg"] / lat_res)), int(round(g["half_width_deg"] / lon_res))
        i0 = int(np.argmin(np.abs(lats - row.latitude)))
        j0 = int(np.argmin(np.abs(wrap_dlon(lons - row.longitude))))
        rows = np.arange(i0 - r_lat, i0 + r_lat + 1)
        cols = np.arange(j0 - r_lon, j0 + r_lon + 1) % len(lons)
        crop = np.full((len(rows), len(cols)), g["fill_value"], dtype=np.int16)
        valid = rows[(rows >= 0) & (rows < len(lats))]
        if valid.size:
            r0, r1 = int(valid[0]), int(valid[-1])
            parts = []
            for c0, c1 in runs(cols):
                q = f"{url}.dods?{g['variable']}.{g['variable']}[0][{r0}:1:{r1}][{c0}:1:{c1}]"
                (arr,) = dap_arrays(get(q, g["timeout_s"], g["retries"]), [">i4"])
                parts.append(arr.reshape(r1 - r0 + 1, c1 - c0 + 1))
            first = int(np.flatnonzero(rows == r0)[0])
            crop[first:first + (r1 - r0 + 1), :] = np.concatenate(parts, axis=1).astype(np.int16)
        crop = np.flipud(crop)  # GridSat latitude ascends; store north-up
        ensure_dir(out_path.parent)
        np.savez_compressed(out_path, counts=crop)
        rec.update(status="ok", grid_lat=float(lats[i0]), grid_lon=float(lons[j0]), rows=crop.shape[0], cols=crop.shape[1])
    except MissingFile as exc:
        rec.update(status="gridsat_file_missing", error=str(exc)[:200])
    except Exception as exc:
        rec.update(status="failed", error=str(exc)[:200])
    rec["elapsed_s"] = round(time.time() - t0, 2)
    return rec


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=None, help="task config (default: identification)")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--label", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    cfg = load_config(args.config)

    cand = pd.read_csv(project_path(cfg, "metadata", cfg_file(cfg, "candidates", "candidates.csv")))
    if args.label is not None:
        cand = cand[cand.label == args.label]
    base = ensure_dir(project_path(cfg, "raw", "gridsat"))
    todo = cand[[args.force or not crop_path(cfg, s, l).exists() for s, l in zip(cand.sample_id, cand.label)]]
    if args.limit:
        todo = todo.head(args.limit)
    lats, lons = grid_axes(cfg, base / "grid_axes.npz")
    print(f"GridSat grid: lat {lats[0]:.3f}..{lats[-1]:.3f} ({len(lats)}), lon {lons[0]:.3f}..{lons[-1]:.3f} ({len(lons)})")
    print(f"Candidates: {len(cand)}; to fetch: {len(todo)}; workers: {cfg['gridsat']['workers']}")

    log_path = base / "fetch_log.csv"
    new_log = not log_path.exists()
    stats: dict[str, int] = {}
    start = time.time()
    with open(log_path, "a", newline="", encoding="utf-8") as fh, ThreadPoolExecutor(cfg["gridsat"]["workers"]) as pool:
        writer = csv.DictWriter(fh, fieldnames=LOG_FIELDS)
        if new_log:
            writer.writeheader()
        futures = [pool.submit(fetch_one, row, cfg, lats, lons, crop_path(cfg, row.sample_id, row.label)) for row in todo.itertuples()]
        for n, fut in enumerate(as_completed(futures), 1):
            rec = fut.result()
            stats[rec["status"]] = stats.get(rec["status"], 0) + 1
            with _log_lock:
                writer.writerow({k: rec.get(k, "") for k in LOG_FIELDS})
                fh.flush()
            if n % 100 == 0 or n == len(futures):
                rate = n / max(time.time() - start, 1e-6)
                print(f"  {n}/{len(futures)}  {stats}  {rate:.1f}/s  ETA {(len(futures) - n) / rate / 60:.1f} min", flush=True)
    print(f"Done: {stats}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
