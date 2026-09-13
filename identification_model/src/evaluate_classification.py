"""Classification STEP 8 — evaluation on the held-out TEST split only (storms never seen in training).

    python src/evaluate_classification.py [--checkpoint ../backend/models/classification/best_model.pth]

Outputs (reports/classification/ unless noted)
  classification_metrics.json   overall, per-class, ROC-AUC/PR-AUC (one-vs-rest), adjacent accuracy,
                                region/basin-wise, calibration, boundary analysis, group-bootstrap CIs
  classification_report.csv     per-class precision / recall / F1 / support
  confusion_matrix.png, roc_curves.png, pr_curves.png, calibration.png
  region_metrics.csv, error_analysis.csv, errors/<true>_as_<pred>/*.png
  results/classification/test_predictions.csv (every prediction with its probability distribution)
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import torch  # noqa: E402
from sklearn.metrics import (  # noqa: E402
    accuracy_score, average_precision_score, balanced_accuracy_score, classification_report, confusion_matrix,
    f1_score, precision_recall_curve, roc_auc_score, roc_curve,
)

from src.dataset import read_split  # noqa: E402
from src.model import load_checkpoint  # noqa: E402
from src.preprocessing import build_transforms, load_grayscale, to_model_rgb  # noqa: E402
from src.utils import (  # noqa: E402
    AREA_LABELS, EVALUATION_AREAS, ROOT, cfg_file, ensure_dir, get_device, load_config, project_path, task_classes, write_json,
)

CONFIG = ROOT / "configs" / "classification.yaml"
BOOTSTRAP_REPS = 1000
COLORS = ["#3b82f6", "#10b981", "#f97316", "#dc2626"]


@torch.inference_mode()
def predict(model, transform, paths, device, batch: int = 64) -> np.ndarray:
    out = []
    for i in range(0, len(paths), batch):
        x = torch.stack([transform(to_model_rgb(load_grayscale(ROOT / p))) for p in paths[i:i + batch]]).to(device)
        out.append(torch.softmax(model(x).float(), dim=1).cpu().numpy())
    return np.concatenate(out)


def summary_metrics(y: np.ndarray, probs: np.ndarray, n_classes: int) -> dict:
    pred = probs.argmax(1)
    labels = list(range(n_classes))
    out = {
        "n": int(len(y)),
        "accuracy": float(accuracy_score(y, pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y, pred)) if len(set(y)) > 1 else float("nan"),
        "macro_f1": float(f1_score(y, pred, labels=labels, average="macro", zero_division=0)),
        "weighted_f1": float(f1_score(y, pred, labels=labels, average="weighted", zero_division=0)),
        "adjacent_accuracy": float(np.mean(np.abs(pred - y) <= 1)),
        "mean_absolute_class_error": float(np.mean(np.abs(pred - y))),
        "top2_accuracy": float(np.mean([t in np.argsort(p)[-2:] for t, p in zip(y, probs)])),
    }
    present = sorted(set(y))
    if len(present) == n_classes:
        out["roc_auc_ovr_macro"] = float(roc_auc_score(y, probs, multi_class="ovr", average="macro", labels=labels))
        onehot = np.eye(n_classes)[y]
        out["pr_auc_macro"] = float(np.mean([average_precision_score(onehot[:, k], probs[:, k]) for k in labels]))
    return out


def group_bootstrap(y, probs, groups, n_classes, seed) -> dict:
    rng = np.random.default_rng(seed)
    uniq = np.unique(groups)
    index = {g: np.flatnonzero(groups == g) for g in uniq}
    draws = {"accuracy": [], "macro_f1": [], "adjacent_accuracy": []}
    for _ in range(BOOTSTRAP_REPS):
        idx = np.concatenate([index[g] for g in rng.choice(uniq, size=len(uniq), replace=True)])
        pred = probs[idx].argmax(1)
        draws["accuracy"].append(accuracy_score(y[idx], pred))
        draws["macro_f1"].append(f1_score(y[idx], pred, labels=list(range(n_classes)), average="macro", zero_division=0))
        draws["adjacent_accuracy"].append(np.mean(np.abs(pred - y[idx]) <= 1))
    return {k: [round(float(np.percentile(v, 2.5)), 4), round(float(np.percentile(v, 97.5)), 4)] for k, v in draws.items()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=str(CONFIG))
    parser.add_argument("--checkpoint", default=None)
    args = parser.parse_args()
    cfg = load_config(args.config)
    classes = task_classes(cfg)
    codes = [c["code"] for c in classes]
    n_classes = len(classes)
    rep = ensure_dir(project_path(cfg, "reports"))
    device = get_device()
    ckpt_path = Path(args.checkpoint) if args.checkpoint else project_path(cfg, "models", "best_model.pth")
    model, ckpt = load_checkpoint(ckpt_path, device)
    transform = build_transforms(ckpt["config"], train=False)

    test = read_split(cfg, "test")
    manifest = pd.read_csv(project_path(cfg, "metadata", cfg_file(cfg, "manifest", "classification_dataset.csv")), keep_default_na=False, na_values=[""])
    extra = ["image_id", "name", "latitude", "longitude", "usa_wind_kt", "imd_category_of_usa_wind", "wmo_wind_kt", "wmo_agency", "sample_id"]
    test = test.merge(manifest[extra], on="image_id", how="left")
    probs = predict(model, transform, list(test.image_path), device)
    y = test.label.to_numpy().astype(int)
    pred = probs.argmax(1)
    conf = probs.max(1)

    # distance (kt) from the labelled wind to the nearest class boundary
    edges = np.array([c["max_kt"] + 0.5 for c in classes if c["max_kt"] is not None])
    kt_from_edge = np.min(np.abs(test.usa_wind_kt.to_numpy()[:, None] - edges[None, :]), axis=1)

    out = test.assign(true_class=[codes[i] for i in y], predicted_label=pred, predicted_class=[codes[i] for i in pred],
                      confidence=conf.round(6), correct=pred == y, kt_from_nearest_boundary=kt_from_edge)
    for k, code in enumerate(codes):
        out[f"p_{code}"] = probs[:, k].round(6)
    ensure_dir(project_path(cfg, "results"))
    out.to_csv(project_path(cfg, "results", "test_predictions.csv"), index=False)

    overall = summary_metrics(y, probs, n_classes)
    ci = group_bootstrap(y, probs, test.group_id.to_numpy(), n_classes, int(cfg["project"]["seed"]))
    rep_dict = classification_report(y, pred, labels=list(range(n_classes)), target_names=codes, output_dict=True, zero_division=0)
    onehot = np.eye(n_classes)[y]
    per_class = []
    for k, c in enumerate(classes):
        r = rep_dict[c["code"]]
        per_class.append({"class_id": k, "class_code": c["code"], "class_name": c["name"], "precision": r["precision"], "recall": r["recall"],
                          "f1": r["f1-score"], "support": int(r["support"]),
                          "roc_auc_ovr": float(roc_auc_score(onehot[:, k], probs[:, k])) if 0 < onehot[:, k].sum() < len(y) else None,
                          "pr_auc": float(average_precision_score(onehot[:, k], probs[:, k])) if onehot[:, k].sum() else None})
    pc = pd.DataFrame(per_class)
    pc.to_csv(rep / "classification_report.csv", index=False)
    cm = confusion_matrix(y, pred, labels=list(range(n_classes)))

    # ---------------- figures
    fig, ax = plt.subplots(figsize=(6.2, 5.2))
    norm = cm / np.maximum(cm.sum(1, keepdims=True), 1)
    ax.imshow(norm, cmap="Blues", vmin=0, vmax=1)
    for i in range(n_classes):
        for j in range(n_classes):
            ax.text(j, i, f"{cm[i, j]}\n{norm[i, j]:.0%}", ha="center", va="center", fontsize=9, color="white" if norm[i, j] > 0.5 else "black")
    ax.set_xticks(range(n_classes), codes)
    ax.set_yticks(range(n_classes), codes)
    ax.set_xlabel("PREDICTED")
    ax.set_ylabel("ACTUAL")
    ax.set_title(f"Test confusion matrix (n={len(y)}; row % = recall)", fontsize=10)
    fig.tight_layout()
    fig.savefig(rep / "confusion_matrix.png", dpi=140)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    for k, code in enumerate(codes):
        fpr, tpr, _ = roc_curve(onehot[:, k], probs[:, k])
        axes[0].plot(fpr, tpr, color=COLORS[k % 4], label=f"{code} (AUC {pc.roc_auc_ovr[k]:.3f})")
        prec, rec, _ = precision_recall_curve(onehot[:, k], probs[:, k])
        axes[1].plot(rec, prec, color=COLORS[k % 4], label=f"{code} (AP {pc.pr_auc[k]:.3f})")
    axes[0].plot([0, 1], [0, 1], color="#94a3b8", linestyle="--")
    axes[0].set_title("ROC (one-vs-rest)")
    axes[0].set_xlabel("False positive rate")
    axes[0].set_ylabel("True positive rate")
    axes[1].set_title("Precision–recall (one-vs-rest)")
    axes[1].set_xlabel("Recall")
    axes[1].set_ylabel("Precision")
    for ax in axes:
        ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(rep / "roc_pr_curves.png", dpi=140)
    plt.close(fig)

    bins = np.linspace(0.25, 1.0, int(cfg["evaluation"]["calibration_bins"]) + 1)
    cal_rows, ece = [], 0.0
    for lo, hi in zip(bins[:-1], bins[1:]):
        mask = (conf >= lo) & ((conf < hi) if hi < 1 else (conf <= hi))
        if mask.any():
            acc_bin = float((pred[mask] == y[mask]).mean())
            ece += mask.mean() * abs(conf[mask].mean() - acc_bin)
            cal_rows.append({"bin": f"{lo:.3f}-{hi:.3f}", "n": int(mask.sum()), "mean_confidence": round(float(conf[mask].mean()), 4), "accuracy": round(acc_bin, 4)})
    cal = {"expected_calibration_error": round(float(ece), 4), "mean_confidence": round(float(conf.mean()), 4),
           "accuracy": round(float((pred == y).mean()), 4), "share_confidence_ge_0_9": round(float((conf >= 0.9).mean()), 4),
           "errors_with_confidence_ge_0_9": int(((pred != y) & (conf >= 0.9)).sum()), "bins": cal_rows}
    fig, ax = plt.subplots(figsize=(4.6, 4.2))
    cb = pd.DataFrame(cal_rows)
    ax.plot([0.25, 1], [0.25, 1], color="#94a3b8", linestyle="--")
    ax.plot(cb.mean_confidence, cb.accuracy, marker="o", color="#c2410c")
    ax.set_xlabel("confidence (max softmax)")
    ax.set_ylabel("accuracy")
    ax.set_title(f"Reliability (ECE {cal['expected_calibration_error']:.3f})")
    fig.tight_layout()
    fig.savefig(rep / "calibration.png", dpi=140)
    plt.close(fig)

    # ---------------- region / basin
    min_n = int(cfg["evaluation"]["min_samples_per_area"])
    region_rows = []
    for area, col in EVALUATION_AREAS:
        sub = out[out[col] == area]
        row = {"area": AREA_LABELS[area], "level": col, "n": int(len(sub)), **{f"n_{c}": int((sub.true_class == c).sum()) for c in codes}}
        if len(sub) >= min_n:
            row.update(accuracy=float(sub.correct.mean()), adjacent_accuracy=float((abs(sub.predicted_label - sub.label) <= 1).mean()),
                       macro_f1=float(f1_score(sub.label, sub.predicted_label, labels=list(range(n_classes)), average="macro", zero_division=0)),
                       note="all metrics" if sub.label.nunique() == n_classes else "macro F1 over classes present in this area is not comparable")
        else:
            row["note"] = f"fewer than {min_n} samples — not reported"
        region_rows.append(row)
    for basin, sub in out.groupby("basin"):
        region_rows.append({"area": f"basin {basin}", "level": "basin", "n": int(len(sub)), **{f"n_{c}": int((sub.true_class == c).sum()) for c in codes},
                            "accuracy": float(sub.correct.mean()) if len(sub) >= min_n else None,
                            "adjacent_accuracy": float((abs(sub.predicted_label - sub.label) <= 1).mean()) if len(sub) >= min_n else None,
                            "note": "" if len(sub) >= min_n else f"fewer than {min_n} samples — not reported"})
    region = pd.DataFrame(region_rows)
    region.to_csv(rep / "region_metrics.csv", index=False)

    # ---------------- error analysis
    err = out[~out.correct].copy()
    err["error_type"] = np.where(abs(err.predicted_label - err.label) == 1, "adjacent_class", "non_adjacent")
    err_cols = ["image_path", "image_id", "true_class", "predicted_class", "confidence"] + [f"p_{c}" for c in codes] + [
        "error_type", "usa_wind_kt", "kt_from_nearest_boundary", "imd_category_of_usa_wind", "storm_id", "name", "basin", "region",
        "subregion", "timestamp", "wmo_wind_kt", "wmo_agency", "group_id"]
    err.sort_values("confidence", ascending=False)[err_cols].rename(columns={"image_path": "image"}).to_csv(rep / "error_analysis.csv", index=False)
    err_dir = rep / "errors"
    if err_dir.exists():
        shutil.rmtree(err_dir)
    limit = int(cfg["evaluation"]["max_error_examples"])
    for r in err.sort_values("confidence", ascending=False).head(limit).itertuples():
        folder = ensure_dir(err_dir / f"{r.true_class}_as_{r.predicted_class}")
        shutil.copy2(ROOT / r.image_path, folder / f"{r.image_id}_conf{r.confidence:.3f}_{r.usa_wind_kt:.0f}kt.png")
    near_edge = out.kt_from_nearest_boundary <= 5
    boundary = {
        "error_rate_within_5kt_of_a_boundary": round(float((~out.correct[near_edge]).mean()), 4) if near_edge.any() else None,
        "error_rate_further_than_5kt": round(float((~out.correct[~near_edge]).mean()), 4) if (~near_edge).any() else None,
        "share_of_samples_within_5kt": round(float(near_edge.mean()), 4),
        "median_kt_from_boundary_errors": float(err.kt_from_nearest_boundary.median()) if len(err) else None,
        "median_kt_from_boundary_correct": float(out[out.correct].kt_from_nearest_boundary.median()),
        "errors_adjacent_class": int((err.error_type == "adjacent_class").sum()),
        "errors_non_adjacent": int((err.error_type == "non_adjacent").sum()),
    }

    result = {
        "model": {"architecture": ckpt["model_name"], "head": ckpt.get("head"), "checkpoint": str(ckpt_path), "epoch": ckpt["epoch"],
                  "version": cfg["project"]["model_version"]},
        "test_split": {"n": int(len(y)), "storms": int(test.storm_id.nunique()), "groups": int(test.group_id.nunique()),
                       "class_counts": {c: int((y == k).sum()) for k, c in enumerate(codes)}},
        "overall": overall, "bootstrap_95ci_by_group": ci, "per_class": per_class,
        "confusion_matrix": {"labels": codes, "rows_actual_cols_predicted": cm.tolist()},
        "region": region_rows, "calibration": cal, "boundary_analysis": boundary,
    }
    write_json(rep / "classification_metrics.json", result)

    print(f"\nHeld-out TEST: {len(y)} images, {result['test_split']['storms']} storms, classes {result['test_split']['class_counts']}")
    for k in ["accuracy", "balanced_accuracy", "macro_f1", "weighted_f1", "adjacent_accuracy", "top2_accuracy", "roc_auc_ovr_macro", "pr_auc_macro"]:
        print(f"  {k:<22} {overall.get(k, float('nan')):.4f}" + (f"   95% CI {ci[k]}" if k in ci else ""))
    print(pc[["class_code", "precision", "recall", "f1", "support", "roc_auc_ovr", "pr_auc"]].to_string(index=False))
    print("confusion (rows actual, cols predicted):", codes)
    print(cm)
    print(region[["area", "n", "accuracy", "adjacent_accuracy", "macro_f1", "note"]].to_string(index=False))
    print("boundary analysis:", boundary)
    print(f"calibration: ECE {cal['expected_calibration_error']}, conf>=0.9 share {cal['share_confidence_ge_0_9']}, errors>=0.9 {cal['errors_with_confidence_ge_0_9']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
