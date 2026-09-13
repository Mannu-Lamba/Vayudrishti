#!/usr/bin/env python3
"""STEP 7 — evaluate the trained model on the held-out TEST storms against both baselines.

Loads the model exactly as the API does (backend ml.prediction.inference.PredictionInference, CPU)
and reports, per lead time: track error (great-circle km: mean / median / p90, storm-bootstrap 95 %
CI), MAE latitude / longitude, wind MAE / RMSE / bias, pressure MAE / RMSE; skill against persistence
and extrapolation with a paired storm-bootstrap CI; region-wise metrics with sample counts (areas with
too little data report counts only); coverage of the empirical uncertainty radii; and what the
post-processing rules did on every test forecast.

Writes reports/test_metrics.{json,md}, reports/figures/*.png, results/test_predictions.csv.

    python src/evaluate.py
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.common import ensure_dir, load_config, project_path, read_json, sequence_config, write_json  # noqa: E402
from src.data import load_observations, load_splits, split_samples  # noqa: E402
from src.metrics import forecast_errors, region_breakdown, storm_bootstrap, summarize  # noqa: E402
from ml.prediction.baseline import BASELINES  # noqa: E402
from ml.prediction.inference import PredictionInference  # noqa: E402
from ml.prediction.postprocess import PostprocessingError, postprocess  # noqa: E402


def skill(model: dict, base: dict, horizons, key: str) -> dict:
    out = {}
    for h in horizons:
        m, b = model[str(h)][key], base[str(h)][key]
        out[str(h)] = None if m is None or not b else round(100.0 * (1.0 - m / b), 1)
    return out


def plot_errors(overall: dict, horizons, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 3, figsize=(14, 3.8))
    for ax, key, title in zip(axes, ("track_km_mean", "wind_mae_kt", "pressure_mae_hpa"),
                              ("Track error (km)", "Wind MAE (kt)", "Pressure MAE (hPa)")):
        for name, values in overall.items():
            ax.plot(horizons, [values[str(h)][key] for h in horizons], marker="o", label=name)
        ax.set_title(f"Test — {title}")
        ax.set_xlabel("lead time (h)")
        ax.set_xticks(horizons)
        ax.grid(alpha=0.3)
    axes[0].legend()
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def main() -> int:
    cfg = load_config()
    seq, ev = sequence_config(cfg), cfg["evaluation"]
    seed, horizons = int(cfg["project"]["seed"]), list(seq.horizons_hours)
    engine = PredictionInference(project_path(cfg, "models"), device="cpu")  # the serving code path
    if engine.cfg != seq:
        sys.exit("model_config.json sequence settings differ from configs/prediction.yaml - retrain or restore the config.")
    test = split_samples(cfg, "test", load_observations(cfg), load_splits(cfg))
    storms = test.meta.storm_id.to_numpy()
    print(f"Held-out TEST: {len(test):,} samples from {len(set(storms))} storms")

    with torch.inference_mode():
        X = torch.from_numpy(engine.normalizer.transform(test.X))
        z = np.concatenate([engine.model(X[i:i + 4096]).numpy() for i in range(0, len(X), 4096)])
    predictions = {"model": engine.normalizer.denormalize_targets(z)}
    predictions.update({name: fn(test.X, seq) for name, fn in BASELINES.items()})
    errors = {name: forecast_errors(test.meta, pred, test.y) for name, pred in predictions.items()}
    overall = {name: summarize(err, seq) for name, err in errors.items()}

    ci = {name: {str(h): storm_bootstrap(err["track_km"][:, k], storms, ev["bootstrap"], seed) for k, h in enumerate(horizons)}
          for name, err in errors.items()}
    paired = {}
    for base in BASELINES:
        paired[base] = {}
        for k, h in enumerate(horizons):
            diff = errors["model"]["track_km"][:, k] - errors[base]["track_km"][:, k]
            wdiff = np.abs(errors["model"]["wind_err_kt"][:, k]) - np.abs(errors[base]["wind_err_kt"][:, k])
            paired[base][str(h)] = {"track_km_diff_mean": round(float(np.nanmean(diff)), 2),
                                    "track_km_diff_ci95": storm_bootstrap(diff, storms, ev["bootstrap"], seed),
                                    "wind_abs_err_diff_mean": round(float(np.nanmean(wdiff)), 3),
                                    "wind_abs_err_diff_ci95": storm_bootstrap(wdiff, storms, ev["bootstrap"], seed)}
    skills = {base: {"track": skill(overall["model"], overall[base], horizons, "track_km_mean"),
                     "wind": skill(overall["model"], overall[base], horizons, "wind_mae_kt"),
                     "pressure": skill(overall["model"], overall[base], horizons, "pressure_mae_hpa")} for base in BASELINES}
    regions = {name: region_breakdown(err, test.meta, seq, ev["min_samples_per_area"], ev["min_storms_per_area"]) for name, err in errors.items()}
    tropical = (test.meta.nature0.astype(str) == "TS").to_numpy()
    tropical_only = {name: summarize(err, seq, np.flatnonzero(tropical)) for name, err in errors.items()}

    # Uncertainty coverage on unseen storms (radii were fitted on validation storms).
    unc = engine.uncertainty or {}
    coverage = {}
    for k, h in enumerate(horizons):
        radius = (unc.get("track_radius_km") or {}).get(str(h))
        werr = (unc.get("wind_abs_error_kt") or {}).get(str(h))
        track, wind = errors["model"]["track_km"][:, k], errors["model"]["wind_err_kt"][:, k]
        coverage[str(h)] = {
            "radius_km": radius, "track_within_radius": None if radius is None else round(float(np.mean(track <= radius)), 4),
            "wind_band_kt": werr, "wind_within_band": None if werr is None else round(float(np.mean(np.abs(wind[np.isfinite(wind)]) <= werr)), 4),
        }

    # Post-processing rules applied to every test forecast that has a current wind and pressure.
    pp = Counter()
    for i in range(len(test)):
        m = test.meta.iloc[i]
        if not (np.isfinite(m.wind0) and np.isfinite(m.pres0)):
            pp["skipped_no_current_intensity"] += 1
            continue
        try:
            steps = postprocess({"t0": m.t0, "lat0": m.lat0, "lon0": m.lon0, "wind0": m.wind0, "pres0": m.pres0},
                                predictions["model"][i], seq, unc)
            pp["accepted"] += 1
            for step in steps:
                for flag in step.flags:
                    pp[f"flag_{flag}"] += 1
        except PostprocessingError as exc:
            pp[f"rejected_{exc.code}"] += 1

    report = {
        "model": engine.info, "test_split": {"samples": len(test), "storms": int(len(set(storms))),
                                             "samples_with_wind_target_last_horizon": overall["model"][str(horizons[-1])]["n_wind"]},
        "overall": overall, "track_km_ci95": ci, "skill_percent": skills, "paired_difference_vs_baseline": paired,
        "tropical_stage_only": tropical_only, "region": regions, "uncertainty_coverage": coverage, "postprocessing": dict(pp),
        "val_metrics_at_selection": read_json(project_path(cfg, "models", "model_config.json")).get("val_metrics"),
    }
    rep = ensure_dir(project_path(cfg, "reports"))
    write_json(rep / "test_metrics.json", report)
    plot_errors(overall, horizons, ensure_dir(rep / "figures") / "test_error_by_horizon.png")

    rows = []
    for k, h in enumerate(horizons):
        frame = test.meta[["storm_id", "t0", "area", "region", "subregion", "lat0", "lon0", "wind0", "pres0"]].copy()
        frame["hours"] = h
        frame["true_lat"] = test.meta.lat0 + test.y[:, k, 0]
        frame["true_lon"] = (test.meta.lon0 + test.y[:, k, 1] + 180) % 360 - 180
        frame["pred_lat"] = test.meta.lat0 + predictions["model"][:, k, 0]
        frame["pred_lon"] = (test.meta.lon0 + predictions["model"][:, k, 1] + 180) % 360 - 180
        frame["true_wind_kt"] = test.meta.wind0 + test.y[:, k, 2]
        frame["pred_wind_kt"] = test.meta.wind0 + predictions["model"][:, k, 2]
        frame["true_pressure_hpa"] = test.meta.pres0 + test.y[:, k, 3]
        frame["pred_pressure_hpa"] = test.meta.pres0 + predictions["model"][:, k, 3]
        for name in errors:
            frame[f"track_km_{name}"] = errors[name]["track_km"][:, k]
        rows.append(frame)
    ensure_dir(project_path(cfg, "results"))
    table = pd.concat(rows)
    numeric = table.select_dtypes("number").columns
    table[numeric] = table[numeric].round(4)
    table.to_csv(project_path(cfg, "results", "test_predictions.csv"), index=False)

    names = list(errors)
    lines = ["# Track prediction — held-out test evaluation", "",
             f"{len(test):,} forecasts from {len(set(storms))} test storms never seen in training or validation. "
             f"Model {engine.info['architecture']} {engine.info['version']}.", "",
             "## Track error (great-circle km, mean) — storm-bootstrap 95 % CI", "",
             "| forecast | " + " | ".join(f"T+{h}h" for h in horizons) + " |", "|---|" + "---|" * len(horizons)]
    for name in names:
        lines.append(f"| {name} | " + " | ".join(f"{overall[name][str(h)]['track_km_mean']} ({ci[name][str(h)][0]}–{ci[name][str(h)][1]})" for h in horizons) + " |")
    lines += ["", "## Intensity and pressure", "", "| forecast | " + " | ".join(f"T+{h}h wind MAE kt" for h in horizons) + " | T+24h pressure MAE hPa |",
              "|---|" + "---|" * (len(horizons) + 1)]
    for name in names:
        lines.append(f"| {name} | " + " | ".join(f"{overall[name][str(h)]['wind_mae_kt']}" for h in horizons)
                     + f" | {overall[name][str(horizons[-1])]['pressure_mae_hpa']} |")
    lines += ["", "## Skill of the model (% error reduction)", ""]
    for base in BASELINES:
        lines.append(f"- vs {base}: track {skills[base]['track']}, wind {skills[base]['wind']}, pressure {skills[base]['pressure']}")
    lines += ["", "## Region-wise (model; counts always shown)", "", "| area | samples | storms | T+24h track km | T+24h wind MAE kt |", "|---|---|---|---|---|"]
    for row in regions["model"]:
        m = row["metrics"]
        last = str(horizons[-1])
        lines.append(f"| {row['label']} | {row['samples']} | {row['storms']} | "
                     + (f"{m[last]['track_km_mean']} | {m[last]['wind_mae_kt']} |" if m else f"{row['note']} | |"))
    lines += ["", "## Uncertainty radii (fitted on validation) — coverage on test", "",
              "| lead | radius km | track errors inside | wind band ± kt | wind errors inside |", "|---|---|---|---|---|"]
    for h in horizons:
        c = coverage[str(h)]
        lines.append(f"| T+{h}h | {c['radius_km']} | {c['track_within_radius']} | {c['wind_band_kt']} | {c['wind_within_band']} |")
    lines += ["", f"Post-processing on test forecasts: {dict(pp)}", ""]
    (rep / "test_metrics.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    for name in names:
        print(f"  {name:<14} track km " + "  ".join(f"T+{h}:{overall[name][str(h)]['track_km_mean']}" for h in horizons)
              + f" | wind MAE " + " ".join(f"{overall[name][str(h)]['wind_mae_kt']}" for h in horizons))
    print(f"Skill vs extrapolation (track %): {skills['extrapolation']['track']}")
    print(f"Coverage: {coverage}")
    print(f"Post-processing: {dict(pp)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
