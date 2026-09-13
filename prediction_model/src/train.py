#!/usr/bin/env python3
"""STEPS 5–6 — train the multi-task temporal forecaster (track + intensity + pressure).

* storm-level splits only; refuses to start unless reports/leakage_check.json PASSES for the current
  split file and observation table;
* inputs standardised with TRAINING statistics only; targets = changes from T0, standardised per
  horizon; missing targets (e.g. pressure) are masked out of the loss, never imputed;
* loss = Σ weight_head × masked Huber (weights and rationale in configs/prediction.yaml);
* model selection on validation mean track error (km, mean over horizons); ReduceLROnPlateau;
  early stopping; seeded and deterministic; CUDA when available, CPU otherwise;
* after training: empirical uncertainty radii = quantile of VALIDATION errors per horizon.

Writes to backend/models/prediction/: best_model.pth, last_model.pth, model_config.json;
reports/training_history.{csv,png}.

    python src/train.py [--epochs N] [--architecture gru|lstm|transformer]
"""

from __future__ import annotations

import argparse
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.common import (  # noqa: E402
    ensure_dir, get_device, load_config, project_path, read_json, sequence_config, set_seed, sha256_file, write_json,
)
from src.data import OBSERVATIONS_FILE, SPLITS_FILE, load_observations, load_splits, split_samples  # noqa: E402
from src.metrics import forecast_errors, summarize  # noqa: E402
from ml.prediction.features import FEATURE_NAMES, FEATURES, TARGETS, Normalizer  # noqa: E402
from ml.prediction.model import build_model  # noqa: E402

HEADS = {"track": slice(0, 2), "intensity": slice(2, 3), "pressure": slice(3, 4)}


def require_leakage_pass(cfg: dict) -> dict:
    path = project_path(cfg, "reports", "leakage_check.json")
    if not path.exists():
        sys.exit("Leakage check missing: run scripts/check_leakage.py first.")
    report = read_json(path)
    if not report.get("passed"):
        sys.exit("Leakage check FAILED: training is blocked. Fix the splits and re-run scripts/check_leakage.py.")
    if report["split_file_sha256"] != sha256_file(project_path(cfg, "splits", SPLITS_FILE)) or \
            report["observations_sha256"] != sha256_file(project_path(cfg, "processed", OBSERVATIONS_FILE)):
        sys.exit("Splits or observations changed since the leakage check: re-run scripts/check_leakage.py.")
    return report


def masked_huber(pred: torch.Tensor, target: torch.Tensor, delta: float) -> torch.Tensor:
    mask = torch.isfinite(target)
    if not mask.any():
        return pred.sum() * 0.0
    loss = F.huber_loss(pred, torch.where(mask, target, torch.zeros_like(target)), reduction="none", delta=delta)
    return (loss * mask).sum() / mask.sum()


def multitask_loss(pred, target, weights: dict, delta: float):
    parts = {head: masked_huber(pred[..., sl], target[..., sl], delta) for head, sl in HEADS.items()}
    return sum(weights[head] * value for head, value in parts.items()), {k: float(v) for k, v in parts.items()}


@torch.no_grad()
def predict_physical(model, normalizer: Normalizer, X_norm: torch.Tensor, batch: int = 4096) -> np.ndarray:
    model.eval()
    out = [model(X_norm[i:i + batch]).float().cpu().numpy() for i in range(0, len(X_norm), batch)]
    return normalizer.denormalize_targets(np.concatenate(out))


def plot_history(hist: pd.DataFrame, path: Path, best_epoch: int) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 3, figsize=(14, 3.8))
    axes[0].plot(hist.epoch, hist.train_loss, label="train")
    axes[0].plot(hist.epoch, hist.val_loss, label="val")
    axes[0].set_title("Loss (weighted masked Huber)")
    axes[1].plot(hist.epoch, hist.val_track_km, color="tab:blue")
    axes[1].set_title("Val track error, mean over horizons (km)")
    axes[2].plot(hist.epoch, hist.val_wind_mae_kt, label="wind MAE (kt)")
    axes[2].plot(hist.epoch, hist.val_pressure_mae_hpa, label="pressure MAE (hPa)")
    axes[2].set_title("Val intensity / pressure")
    for ax in axes:
        ax.axvline(best_epoch, color="grey", ls=":", lw=1)
        ax.set_xlabel("epoch")
        ax.grid(alpha=0.3)
    axes[0].legend()
    axes[2].legend()
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=None)
    parser.add_argument("--epochs", type=int, default=None)
    parser.add_argument("--architecture", choices=["gru", "lstm", "transformer"], default=None)
    args = parser.parse_args()
    cfg = load_config(args.config)
    if args.architecture:
        cfg["model"]["architecture"] = args.architecture
    tr, seq = cfg["train"], sequence_config(cfg)
    seed = int(cfg["project"]["seed"])
    set_seed(seed)
    device = get_device()
    leakage = require_leakage_pass(cfg)

    obs, splits = load_observations(cfg), load_splits(cfg)
    train, val = split_samples(cfg, "train", obs, splits), split_samples(cfg, "val", obs, splits)
    print(f"train: {len(train):,} samples / {train.meta.storm_id.nunique()} storms   "
          f"val: {len(val):,} samples / {val.meta.storm_id.nunique()} storms   window {seq.steps} x {len(FEATURES)} features")
    normalizer = Normalizer.fit(train.X, train.y)
    Xtr = torch.from_numpy(normalizer.transform(train.X)).to(device)
    ytr = torch.from_numpy(normalizer.normalize_targets(train.y)).to(device)
    Xva = torch.from_numpy(normalizer.transform(val.X)).to(device)
    yva = torch.from_numpy(normalizer.normalize_targets(val.y)).to(device)

    spec = {"n_features": len(FEATURES), "n_steps": seq.steps, "n_horizons": len(seq.horizons_hours), **cfg["model"]}
    model = build_model(spec).to(device)
    n_params = sum(p.numel() for p in model.parameters())
    print(f"Model: {spec['architecture']} hidden {spec['hidden']} x {spec['layers']} layers, {n_params:,} parameters")
    optimizer = torch.optim.AdamW(model.parameters(), lr=tr["learning_rate"], weight_decay=tr["weight_decay"])
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode="min", factor=tr["plateau_factor"], patience=tr["plateau_patience"])
    weights, delta = tr["loss_weights"], float(tr["huber_delta"])
    generator = torch.Generator(device="cpu").manual_seed(seed)

    model_dir = ensure_dir(project_path(cfg, "models"))
    epochs = args.epochs or tr["epochs"]
    best, stale, history = None, 0, []
    for epoch in range(1, epochs + 1):
        started = time.time()
        model.train()
        order = torch.randperm(len(Xtr), generator=generator).to(device)
        total, seen = 0.0, 0
        for i in range(0, len(order), tr["batch_size"]):
            idx = order[i:i + tr["batch_size"]]
            loss, _ = multitask_loss(model(Xtr[idx]), ytr[idx], weights, delta)
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), tr["grad_clip"])
            optimizer.step()
            total += float(loss) * len(idx)
            seen += len(idx)
        model.eval()
        with torch.no_grad():
            val_loss, parts = multitask_loss(torch.cat([model(Xva[i:i + 4096]) for i in range(0, len(Xva), 4096)]), yva, weights, delta)
        pred = predict_physical(model, normalizer, Xva)
        metrics = summarize(forecast_errors(val.meta, pred, val.y), seq)["mean_over_horizons"]
        score = metrics["track_km_mean"]
        scheduler.step(score)
        improved = best is None or score < best["score"]
        row = {"epoch": epoch, "train_loss": total / seen, "val_loss": float(val_loss), **{f"val_{k}_loss": v for k, v in parts.items()},
               "val_track_km": score, "val_wind_mae_kt": metrics["wind_mae_kt"], "val_pressure_mae_hpa": metrics["pressure_mae_hpa"],
               "lr": optimizer.param_groups[0]["lr"], "seconds": round(time.time() - started, 1)}
        history.append(row)
        print(f"epoch {epoch:>2}  train {row['train_loss']:.4f} | val {row['val_loss']:.4f}  track {score:7.2f} km  "
              f"wind {metrics['wind_mae_kt']:5.2f} kt  pres {metrics['pressure_mae_hpa']:5.2f} hPa  lr {row['lr']:.1e}"
              f"{'  *best' if improved else ''}  ({row['seconds']}s)", flush=True)
        if improved:
            best = {"score": score, "epoch": epoch, "metrics": metrics, "state": {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}}
            torch.save({"state_dict": best["state"], "model_spec": spec, "epoch": epoch, "val_metrics": metrics}, model_dir / "best_model.pth")
            stale = 0
        else:
            stale += 1
            if stale >= tr["early_stopping_patience"]:
                print(f"Early stopping: no validation track improvement for {stale} epochs.")
                break
    torch.save({"state_dict": {k: v.cpu() for k, v in model.state_dict().items()}, "model_spec": spec, "epoch": epoch}, model_dir / "last_model.pth")

    # Empirical uncertainty from the best model's VALIDATION errors (never from test).
    model.load_state_dict(best["state"])
    val_errors = forecast_errors(val.meta, predict_physical(model, normalizer, Xva), val.y)
    q = float(cfg["uncertainty"]["quantile"])
    uncertainty = {
        "method": cfg["uncertainty"]["method"],
        "quantile": q,
        "source": f"validation storms ({val.meta.storm_id.nunique()}), best epoch",
        "note": (f"Radius containing {q:.0%} of validation track errors at each lead time (NHC-cone style). It describes this "
                 "model's typical error, not a per-forecast calibrated probability."),
        "track_radius_km": {str(h): round(float(np.nanquantile(val_errors["track_km"][:, k], q)), 1) for k, h in enumerate(seq.horizons_hours)},
        "wind_abs_error_kt": {str(h): round(float(np.nanquantile(np.abs(val_errors["wind_err_kt"][:, k]), q)), 1) for k, h in enumerate(seq.horizons_hours)},
    }

    report_dir = ensure_dir(project_path(cfg, "reports"))
    hist = pd.DataFrame(history)
    hist.to_csv(report_dir / "training_history.csv", index=False)
    plot_history(hist, report_dir / "training_history.png", best["epoch"])
    model_config = {
        "name": "cyclone-track-prediction",
        "display_name": cfg["project"]["name"],
        "model_version": cfg["project"]["model_version"],
        "dataset_version": cfg["project"]["dataset_version"],
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "task": "track + intensity + pressure forecast",
        "architecture": spec["architecture"],
        "model_spec": spec,
        "parameters": n_params,
        "sequence": seq.to_dict(),
        "features": FEATURE_NAMES,
        "feature_kinds": {name: kind for name, kind in FEATURES},
        "targets": list(TARGETS),
        "target_units": {"dlat": "deg", "dlon": "deg", "dwind": "kt (IBTrACS USA_WIND, 1-min)", "dpres": "hPa (USA_PRES)"},
        "normalization": normalizer.to_dict(),
        "uncertainty": uncertainty,
        "loss": {"type": "masked Huber", "delta": delta, "weights": weights},
        "train": {k: tr[k] for k in ("batch_size", "learning_rate", "weight_decay", "scheduler", "early_stopping_patience", "grad_clip")} | {"epochs_run": epoch},
        "data": {"source": cfg["sources"]["ibtracs"], **{k: cfg["data"][k] for k in ("min_season", "basins", "wind_column", "pressure_column")}},
        "splits": leakage["storms_per_split"],
        "samples": {"train": len(train), "val": len(val)},
        "best_epoch": best["epoch"],
        "val_metrics": best["metrics"],
        "framework": {"python": platform.python_version(), "torch": torch.__version__, "device": device.type},
    }
    write_json(model_dir / "model_config.json", model_config)
    print(f"Best epoch {best['epoch']}: val {best['metrics']}")
    print(f"Uncertainty radii (km): {uncertainty['track_radius_km']}")
    print(f"Saved best_model.pth, last_model.pth, model_config.json to {model_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
