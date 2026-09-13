"""STEPS 15–18, 25, 30–32 — Train an image model from a task config.

    python src/train.py                                         # identification (configs/config.yaml)
    python src/train.py --config configs/classification.yaml    # IMD intensity classification
    python src/train.py --model-name resnet50 --run-name resnet50_try   # later experiments

Refuses to start unless the task's leakage report says PASS for the current split files.
Model selection: binary → highest validation F1 of the CYCLONE class; multiclass → highest
validation macro F1. Ties → lower validation loss.
Outputs (paths from the config): best_model.pth, last_model.pth, model_config.json,
class_mapping.json, training_history.csv / .png.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import torch  # noqa: E402
import torchvision  # noqa: E402
from sklearn.metrics import accuracy_score, precision_recall_fscore_support  # noqa: E402
from torch import nn  # noqa: E402

from src.dataset import make_loaders  # noqa: E402
from src.model import build_model, pretrained_weights_name  # noqa: E402
from src.preprocessing import IMAGENET_MEAN, IMAGENET_STD  # noqa: E402
from src.utils import (  # noqa: E402
    cfg_file, class_mapping_json, ensure_dir, get_device, is_multiclass, load_config, project_path, read_json, set_seed,
    sha256_file, split_path, task_classes, write_json,
)


def binary_metrics(y: np.ndarray, p: np.ndarray, threshold: float) -> dict:
    pred = (p >= threshold).astype(int)
    tp = int(((pred == 1) & (y == 1)).sum())
    fp = int(((pred == 1) & (y == 0)).sum())
    fn = int(((pred == 0) & (y == 1)).sum())
    tn = int(((pred == 0) & (y == 0)).sum())
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {
        "accuracy": (tp + tn) / max(len(y), 1),
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
    }


def task_metrics(y: np.ndarray, probs: np.ndarray, cfg: dict) -> dict:
    """Binary: CYCLONE-class precision/recall/F1 at the threshold. Multiclass: macro averages (argmax)."""
    if not is_multiclass(cfg):
        return binary_metrics(y, probs[:, 1], float(cfg["train"]["decision_threshold"]))
    pred = probs.argmax(axis=1)
    p, r, f, _ = precision_recall_fscore_support(y, pred, labels=list(range(probs.shape[1])), average="macro", zero_division=0)
    return {"accuracy": float(accuracy_score(y, pred)), "precision": float(p), "recall": float(r), "f1": float(f)}


def run_epoch(model, loader, criterion, device, optimizer=None, scaler=None, amp=False):
    training = optimizer is not None
    model.train(training)
    total_loss, n, labels, probs = 0.0, 0, [], []
    with torch.set_grad_enabled(training):
        for x, y, _ in loader:
            x, y = x.to(device, non_blocking=True), y.to(device, non_blocking=True)
            with torch.autocast(device_type=device.type, dtype=torch.float16, enabled=amp):
                logits = model(x)
                loss = criterion(logits, y)
            if training:
                optimizer.zero_grad(set_to_none=True)
                scaler.scale(loss).backward()
                scaler.step(optimizer)
                scaler.update()
            total_loss += float(loss.detach()) * len(y)
            n += len(y)
            labels.append(y.cpu().numpy())
            probs.append(torch.softmax(logits.detach().float(), dim=1).cpu().numpy())
    return total_loss / max(n, 1), np.concatenate(labels), np.concatenate(probs)


def require_leakage_pass(cfg: dict) -> dict:
    path = project_path(cfg, "reports", cfg_file(cfg, "leakage_report", "leakage_check.json"))
    if not path.exists():
        raise SystemExit("No leakage check found — run `python scripts/check_leakage.py` for this task first.")
    report = read_json(path)
    current = {s: sha256_file(split_path(cfg, s)) for s in ("train", "val", "test")}
    if report.get("status") != "PASS":
        raise SystemExit("DATA LEAKAGE CHECK did not pass — training refused.")
    if report.get("split_file_sha256") != current:
        raise SystemExit("Split files changed since the leakage check — re-run `python scripts/check_leakage.py`.")
    return report


def plot_history(history: pd.DataFrame, path: Path, best_epoch: int, multiclass: bool) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 4, figsize=(16, 3.6))
    f1_name = "macro F1" if multiclass else "F1 (cyclone)"
    for ax, metric in zip(axes, ["loss", "accuracy", "f1", "recall"]):
        ax.plot(history.epoch, history[f"train_{metric}"], label="train", color="#64748b")
        ax.plot(history.epoch, history[f"val_{metric}"], label="validation", color="#c2410c")
        if metric == "recall":
            ax.plot(history.epoch, history["val_precision"], label="val precision", color="#2563eb", linestyle="--")
        ax.axvline(best_epoch, color="#16a34a", linestyle=":", label=f"best (epoch {best_epoch})")
        ax.set_title({"f1": f1_name, "recall": "recall / precision" + (" (macro)" if multiclass else "")}.get(metric, metric))
        ax.set_xlabel("epoch")
        ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=None)
    parser.add_argument("--model-name", default=None, help="override train.model_name")
    parser.add_argument("--epochs", type=int, default=None)
    parser.add_argument("--run-name", default=None, help="write to <models>/runs/<name>/ instead of the main paths")
    args = parser.parse_args()

    cfg = load_config(args.config)
    if args.model_name:
        cfg["train"]["model_name"] = args.model_name
    if args.epochs:
        cfg["train"]["epochs"] = args.epochs
    tr = cfg["train"]
    multiclass = is_multiclass(cfg)
    classes = task_classes(cfg)
    n_classes = int(tr["num_classes"])
    assert n_classes == len(classes), f"train.num_classes={n_classes} but {len(classes)} classes are defined"
    seed = int(cfg["project"]["seed"])
    set_seed(seed, deterministic=True)
    device = get_device()
    leakage = require_leakage_pass(cfg)

    model_dir = ensure_dir(project_path(cfg, "models") / ("runs/" + args.run_name if args.run_name else ""))
    report_dir = ensure_dir(project_path(cfg, "reports") / ("runs/" + args.run_name if args.run_name else ""))

    datasets, loaders, balance = make_loaders(cfg)
    for split, ds in datasets.items():
        counts = np.bincount(ds.labels, minlength=n_classes)
        print(f"{split:<5}: {len(ds)} images  " + "  ".join(f"{c['code']}={counts[c['id']]}" for c in classes))
    print(f"Class balance strategy: {balance['strategy']}")

    head = tr.get("head")
    model = build_model(tr["model_name"], n_classes, bool(tr["pretrained"]), head).to(device)
    weights = balance["class_weights"].to(device) if balance["class_weights"] is not None else None
    criterion = nn.CrossEntropyLoss(weight=weights)
    optimizer = torch.optim.AdamW(model.parameters(), lr=float(tr["learning_rate"]), weight_decay=float(tr["weight_decay"]))
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=int(tr["epochs"])) if tr["scheduler"] == "cosine" else None
    amp = bool(tr["amp"]) and device.type == "cuda"
    scaler = torch.amp.GradScaler("cuda", enabled=amp)
    threshold = float(tr["decision_threshold"])

    def checkpoint(epoch: int, val: dict) -> dict:
        return {
            "state_dict": copy.deepcopy(model.state_dict()),
            "model_name": tr["model_name"], "num_classes": n_classes, "head": head, "task": cfg.get("task", "binary"),
            "class_names": [c["name"] for c in classes], "classes": classes,
            "input_size": int(tr["input_size"]), "decision_threshold": threshold, "epoch": epoch, "val_metrics": val,
            "config": cfg, "dataset_version": cfg["project"]["dataset_version"], "seed": seed,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

    history, best, stale = [], None, 0
    best_f1, best_loss = -1.0, float("inf")
    started = time.time()
    for epoch in range(1, int(tr["epochs"]) + 1):
        t0 = time.time()
        tl, ty, tp = run_epoch(model, loaders["train"], criterion, device, optimizer, scaler, amp)
        vl, vy, vp = run_epoch(model, loaders["val"], criterion, device, amp=amp)
        if scheduler:
            scheduler.step()
        trm, vam = task_metrics(ty, tp, cfg), task_metrics(vy, vp, cfg)
        row = {"epoch": epoch, "train_loss": tl, "val_loss": vl,
               **{f"train_{k}": v for k, v in trm.items()}, **{f"val_{k}": v for k, v in vam.items()},
               "lr": optimizer.param_groups[0]["lr"], "seconds": round(time.time() - t0, 1)}
        history.append(row)
        # Selection: higher validation F1 (CYCLONE class / macro); ties broken by lower validation loss.
        improved = vam["f1"] > best_f1 or (vam["f1"] == best_f1 and vl < best_loss)
        if improved:
            best_f1, best_loss, stale = vam["f1"], vl, 0
            best = checkpoint(epoch, {"loss": vl, **vam})
            torch.save(best, model_dir / "best_model.pth")
        else:
            stale += 1
        print(f"epoch {epoch:>2}  train loss {tl:.4f} acc {trm['accuracy']:.3f} f1 {trm['f1']:.3f} | "
              f"val loss {vl:.4f} acc {vam['accuracy']:.3f} P {vam['precision']:.3f} R {vam['recall']:.3f} F1 {vam['f1']:.3f}"
              f"{'  *best' if stale == 0 else ''}  ({row['seconds']}s)", flush=True)
        if stale >= int(tr["early_stopping_patience"]):
            print(f"Early stopping: no validation F1 improvement for {stale} epochs.")
            break

    last = checkpoint(history[-1]["epoch"], {"loss": history[-1]["val_loss"], **{k[4:]: v for k, v in history[-1].items() if k.startswith("val_") and k != "val_loss"}})
    torch.save(last, model_dir / "last_model.pth")
    hist = pd.DataFrame(history)
    hist.to_csv(report_dir / "training_history.csv", index=False)
    plot_history(hist, report_dir / "training_history.png", best["epoch"], multiclass)

    class_mapping = class_mapping_json(classes)
    model_config = {
        "task": cfg.get("task", "binary"),
        "architecture": tr["model_name"],
        "head": head or {"type": "linear"},
        "pretrained_weights": f"torchvision {pretrained_weights_name(tr['model_name'])} (ImageNet)" if tr["pretrained"] else None,
        "classes": {str(c["id"]): c["code"] for c in classes},
        "number_of_classes": n_classes,
        "class_mapping": class_mapping,
        "input_size": [int(tr["input_size"]), int(tr["input_size"])],
        "channels": 3,
        "input": {
            "imagery": "GridSat-B1 IRWIN CDR (~11 µm) brightness temperature, 18°×18° crop centred on the position of interest, north up",
            "rendering": f"BT clipped to {cfg['imagery']['bt_min_k']}–{cfg['imagery']['bt_max_k']} K, linear to 8-bit, cold = bright, 256×256 grayscale",
            "model_transform": "grayscale → 3 identical channels → resize 224×224 (bilinear, antialias) → [0,1] → ImageNet mean/std",
        },
        "preprocessing": {
            "color_mode": "L", "replicate_to_channels": 3, "resize": [int(tr["input_size"]), int(tr["input_size"])],
            "interpolation": "bilinear", "antialias": True, "scale": "divide by 255",
            "bt_range_k": [cfg["imagery"]["bt_min_k"], cfg["imagery"]["bt_max_k"]], "source_png_size": cfg["imagery"]["png_size"],
        },
        "normalization": {"mean": list(IMAGENET_MEAN), "std": list(IMAGENET_STD)},
        "decision_threshold": threshold if not multiclass else None,
        "training_seed": seed,
        "dataset_version": cfg["project"]["dataset_version"],
        "model_version": cfg["project"]["model_version"],
        "training_configuration": {
            "optimizer": tr["optimizer"], "learning_rate": tr["learning_rate"], "weight_decay": tr["weight_decay"],
            "scheduler": tr["scheduler"], "batch_size": tr["batch_size"], "max_epochs": tr["epochs"],
            "epochs_run": int(hist.epoch.max()), "early_stopping_patience": tr["early_stopping_patience"],
            "selection_metric": tr["selection_metric"], "loss": "cross-entropy", "amp": amp,
            "class_balance": balance["strategy"],
            "class_weights": balance["class_weights"].tolist() if balance["class_weights"] is not None else None,
            "augmentation": cfg["augmentation"], "deterministic": True,
        },
        "best_epoch": best["epoch"],
        "best_validation_metrics": best["val_metrics"],
        "split_sizes": {s: len(ds) for s, ds in datasets.items()},
        "split_file_sha256": leakage["split_file_sha256"],
        "device": torch.cuda.get_device_name(0) if device.type == "cuda" else device.type,
        "framework": {"torch": torch.__version__, "torchvision": torchvision.__version__},
        "torch_version": torch.__version__,
        "training_minutes": round((time.time() - started) / 60, 2),
        "created_at": best["created_at"],
    }
    write_json(model_dir / "model_config.json", model_config)
    if multiclass:
        write_json(model_dir / "class_mapping.json", class_mapping)
    print(f"Best epoch {best['epoch']}: {json.dumps({k: round(v, 4) for k, v in best['val_metrics'].items()})}")
    print(f"Saved {model_dir / 'best_model.pth'} and {model_dir / 'last_model.pth'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
