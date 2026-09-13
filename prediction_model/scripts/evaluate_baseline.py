#!/usr/bin/env python3
"""STEPS 3–4 — persistence and motion-extrapolation baselines on the validation and test storms.

The learned model is only useful if it beats these. Same samples, same metrics as src/evaluate.py.
Writes reports/baseline_metrics.{json,md}.

    python scripts/evaluate_baseline.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.common import load_config, project_path, sequence_config, write_json  # noqa: E402
from src.data import load_observations, load_splits, split_samples  # noqa: E402
from src.metrics import forecast_errors, region_breakdown, storm_bootstrap, summarize  # noqa: E402
from ml.prediction.baseline import BASELINES  # noqa: E402


def evaluate_baselines(cfg: dict, samples, split: str) -> dict:
    seq, ev = sequence_config(cfg), cfg["evaluation"]
    result = {}
    for name, fn in BASELINES.items():
        errors = forecast_errors(samples.meta, fn(samples.X, seq), samples.y)
        entry = {"overall": summarize(errors, seq)}
        last = len(seq.horizons_hours) - 1
        entry["track_km_ci95_last_horizon"] = storm_bootstrap(errors["track_km"][:, last], samples.meta.storm_id.to_numpy(),
                                                              ev["bootstrap"], cfg["project"]["seed"])
        if split == "test":
            entry["region"] = region_breakdown(errors, samples.meta, seq, ev["min_samples_per_area"], ev["min_storms_per_area"])
        result[name] = entry
    return result


def main() -> int:
    cfg = load_config()
    seq = sequence_config(cfg)
    obs, splits = load_observations(cfg), load_splits(cfg)
    report = {"sequence": seq.to_dict()}
    lines = ["# Baseline forecasts", "",
             "- **persistence** — position, wind and pressure stay at their T0 values.",
             f"- **extrapolation** — the mean motion of the last {seq.motion_window_hours} h continues; intensity and pressure persist.", ""]
    for split in ("val", "test"):
        samples = split_samples(cfg, split, obs, splits)
        report[split] = {"samples": len(samples), "storms": int(samples.meta.storm_id.nunique()), **evaluate_baselines(cfg, samples, split)}
        lines += [f"## {split} — {len(samples):,} samples from {report[split]['storms']} storms", "",
                  "| baseline | " + " | ".join(f"T+{h}h track km" for h in seq.horizons_hours) + " | T+24h wind MAE kt | T+24h pressure MAE hPa |",
                  "|---|" + "---|" * (len(seq.horizons_hours) + 2)]
        for name in BASELINES:
            o = report[split][name]["overall"]
            last = str(seq.horizons_hours[-1])
            lines.append(f"| {name} | " + " | ".join(f"{o[str(h)]['track_km_mean']}" for h in seq.horizons_hours)
                         + f" | {o[last]['wind_mae_kt']} | {o[last]['pressure_mae_hpa']} |")
        lines.append("")
        print(f"{split}: {len(samples):,} samples")
        for name in BASELINES:
            o = report[split][name]["overall"]
            print(f"  {name:<14} track km " + "  ".join(f"T+{h}:{o[str(h)]['track_km_mean']}" for h in seq.horizons_hours)
                  + f" | wind MAE T+24 {o[str(seq.horizons_hours[-1])]['wind_mae_kt']} kt")
    write_json(project_path(cfg, "reports", "baseline_metrics.json"), report)
    (project_path(cfg, "reports", "baseline_metrics.md")).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
