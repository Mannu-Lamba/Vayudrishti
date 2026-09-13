"""STEPS 19–22, 24 — Evaluation on the held-out TEST split (unseen storms / events).

    python src/evaluate.py [--checkpoint models/best_model.pth]

Outputs
  results/test_predictions.csv          every test prediction with probabilities and metadata
  reports/test_metrics.json             overall, region-wise, intensity, difficulty, hard negatives,
                                        calibration, cross-source check, group-bootstrap 95 % CIs
  reports/region_metrics.csv
  reports/confusion_matrix.png, roc_curve.png, pr_curve.png, calibration.png
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from PIL import Image  # noqa: E402
from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score, roc_curve  # noqa: E402

from src.inference import DEFAULT_CHECKPOINT, CycloneIdentifier  # noqa: E402
from src.utils import AREA_LABELS, EVALUATION_AREAS, ROOT, ensure_dir, load_config, project_path, write_json  # noqa: E402

BOOTSTRAP_REPS = 1000


def metrics(y: np.ndarray, p: np.ndarray, thr: float) -> dict:
    pred = (p >= thr).astype(int)
    tp = int(((pred == 1) & (y == 1)).sum()); fp = int(((pred == 1) & (y == 0)).sum())
    tn = int(((pred == 0) & (y == 0)).sum()); fn = int(((pred == 0) & (y == 1)).sum())
    n_pos, n_neg = tp + fn, tn + fp
    nan = float("nan")
    precision = tp / (tp + fp) if tp + fp else nan
    recall = tp / n_pos if n_pos else nan
    out = {
        "n": int(len(y)), "n_cyclone": n_pos, "n_no_cyclone": n_neg, "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "accuracy": (tp + tn) / len(y) if len(y) else nan,
        "precision": precision, "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if tp else (0.0 if n_pos else nan),
        "specificity": tn / n_neg if n_neg else nan, "false_positive_rate": fp / n_neg if n_neg else nan,
        "roc_auc": nan, "pr_auc": nan,
    }
    if n_pos and n_neg:
        out["roc_auc"] = float(roc_auc_score(y, p))
        out["pr_auc"] = float(average_precision_score(y, p))
    return out


def group_bootstrap(df: pd.DataFrame, thr: float, seed: int) -> dict:
    """95 % intervals resampling whole event groups (samples in a group are correlated)."""
    rng = np.random.default_rng(seed)
    groups = df.group_id.to_numpy()
    uniq = np.unique(groups)
    index = {g: np.flatnonzero(groups == g) for g in uniq}
    y, p = df.actual_label.to_numpy(), df.cyclone_probability.to_numpy()
    keys = ["accuracy", "precision", "recall", "f1", "roc_auc", "pr_auc", "false_positive_rate"]
    draws = {k: [] for k in keys}
    for _ in range(BOOTSTRAP_REPS):
        idx = np.concatenate([index[g] for g in rng.choice(uniq, size=len(uniq), replace=True)])
        m = metrics(y[idx], p[idx], thr)
        for k in keys:
            draws[k].append(m[k])
    return {k: [round(float(np.nanpercentile(v, 2.5)), 4), round(float(np.nanpercentile(v, 97.5)), 4)] for k, v in draws.items()}


def calibration(y: np.ndarray, p: np.ndarray, bins: int) -> dict:
    pred = (p >= 0.5).astype(int)
    conf = np.where(pred == 1, p, 1 - p)
    correct = (pred == y).astype(float)
    edges = np.linspace(0.5, 1.0, bins + 1)
    table, ece = [], 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (conf >= lo) & (conf < hi if hi < 1.0 else conf <= hi)
        if mask.any():
            gap = abs(conf[mask].mean() - correct[mask].mean())
            ece += mask.mean() * gap
            table.append({"bin": f"{lo:.2f}-{hi:.2f}", "n": int(mask.sum()), "mean_confidence": round(float(conf[mask].mean()), 4),
                          "accuracy": round(float(correct[mask].mean()), 4)})
    # Reliability of the cyclone probability itself (fraction of positives per probability bin)
    pbins = np.linspace(0, 1, bins + 1)
    prob_table = []
    for lo, hi in zip(pbins[:-1], pbins[1:]):
        mask = (p >= lo) & (p < hi if hi < 1 else p <= hi)
        if mask.any():
            prob_table.append({"bin": f"{lo:.1f}-{hi:.1f}", "n": int(mask.sum()), "mean_p_cyclone": round(float(p[mask].mean()), 4),
                               "fraction_cyclone": round(float(y[mask].mean()), 4)})
    wrong = correct == 0
    return {
        "expected_calibration_error": round(float(ece), 4),
        "mean_confidence": round(float(conf.mean()), 4), "accuracy": round(float(correct.mean()), 4),
        "share_confidence_ge_0_99": round(float((conf >= 0.99).mean()), 4),
        "errors": int(wrong.sum()),
        "errors_with_confidence_ge_0_9": int((wrong & (conf >= 0.9)).sum()),
        "median_confidence_correct": round(float(np.median(conf[~wrong])), 4) if (~wrong).any() else None,
        "median_confidence_errors": round(float(np.median(conf[wrong])), 4) if wrong.any() else None,
        "confidence_bins": table, "probability_bins": prob_table,
    }


def plot_confusion(m: dict, path: Path) -> None:
    cm = np.array([[m["tn"], m["fp"]], [m["fn"], m["tp"]]])
    fig, ax = plt.subplots(figsize=(4.8, 4.2))
    ax.imshow(cm, cmap="Blues")
    labels = ["NO CYCLONE", "CYCLONE"]
    for i in range(2):
        for j in range(2):
            share = cm[i, j] / max(cm[i].sum(), 1)
            ax.text(j, i, f"{cm[i, j]}\n({share:.1%} of row)", ha="center", va="center",
                    color="white" if cm[i, j] > cm.max() / 2 else "black", fontsize=10)
    ax.set_xticks([0, 1], labels)
    ax.set_yticks([0, 1], [f"ACTUAL {l}" for l in labels])
    ax.set_xlabel("PREDICTED")
    ax.xaxis.set_label_position("top")
    ax.xaxis.tick_top()
    ax.set_title(f"Test confusion matrix (n={m['n']})", pad=28, fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def plot_curves(y, p, overall, rep: Path) -> None:
    fpr, tpr, _ = roc_curve(y, p)
    fig, ax = plt.subplots(figsize=(4.6, 4.2))
    ax.plot(fpr, tpr, color="#c2410c", label=f"ROC-AUC = {overall['roc_auc']:.3f}")
    ax.plot([0, 1], [0, 1], color="#94a3b8", linestyle="--", label="chance")
    ax.set_xlabel("False positive rate"); ax.set_ylabel("True positive rate (recall)")
    ax.set_title("ROC curve — held-out test"); ax.legend(loc="lower right")
    fig.tight_layout(); fig.savefig(rep / "roc_curve.png", dpi=140); plt.close(fig)

    prec, rec, _ = precision_recall_curve(y, p)
    fig, ax = plt.subplots(figsize=(4.6, 4.2))
    ax.plot(rec, prec, color="#2563eb", label=f"PR-AUC (AP) = {overall['pr_auc']:.3f}")
    ax.axhline(y.mean(), color="#94a3b8", linestyle="--", label=f"prevalence {y.mean():.2f}")
    ax.set_xlabel("Recall"); ax.set_ylabel("Precision"); ax.set_ylim(0, 1.02)
    ax.set_title("Precision–recall curve — held-out test"); ax.legend(loc="lower left")
    fig.tight_layout(); fig.savefig(rep / "pr_curve.png", dpi=140); plt.close(fig)


def plot_calibration(cal: dict, y, p, path: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.8))
    tb = pd.DataFrame(cal["probability_bins"])
    axes[0].plot([0, 1], [0, 1], color="#94a3b8", linestyle="--")
    axes[0].plot(tb.mean_p_cyclone, tb.fraction_cyclone, marker="o", color="#c2410c")
    axes[0].set_xlabel("predicted cyclone probability"); axes[0].set_ylabel("observed cyclone fraction")
    axes[0].set_title(f"Reliability (ECE {cal['expected_calibration_error']:.3f})")
    axes[1].hist([p[y == 0], p[y == 1]], bins=20, label=["actual no_cyclone", "actual cyclone"], color=["#2563eb", "#c2410c"])
    axes[1].set_yscale("log"); axes[1].set_xlabel("predicted cyclone probability"); axes[1].legend(fontsize=8)
    axes[1].set_title("Score distribution (log count)")
    fig.tight_layout(); fig.savefig(path, dpi=140); plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    args = parser.parse_args()
    cfg = load_config()
    ev = cfg["evaluation"]
    ident = CycloneIdentifier(args.checkpoint, verbose=True)
    thr = ident.threshold
    rep = ensure_dir(project_path(cfg, "reports"))

    test = pd.read_csv(project_path(cfg, "splits", "test.csv"), keep_default_na=False, na_values=[""])
    manifest = pd.read_csv(project_path(cfg, "metadata", "identification_dataset.csv"), keep_default_na=False, na_values=[""])
    extra = ["image_id", "sample_id", "latitude", "longitude", "nature", "wind_speed_kt", "cold_cloud_fraction",
             "central_cold_cloud_fraction", "candidate_source", "lifecycle_stage"]
    test = test.merge(manifest[extra], on="image_id", how="left")
    probs = ident.predict_proba([ROOT / p for p in test.image_path])
    pred = (probs[:, 1] >= thr).astype(int)
    out = test.assign(
        actual_label=test.label, predicted_label=pred,
        cyclone_probability=probs[:, 1].round(6), no_cyclone_probability=probs[:, 0].round(6),
        confidence=np.where(pred == 1, probs[:, 1], probs[:, 0]).round(6),
    )
    cols = ["image_id", "actual_label", "predicted_label", "cyclone_probability", "no_cyclone_probability", "confidence",
            "image_path", "storm_id", "group_id", "basin", "region", "subregion", "timestamp", "intensity", "difficulty",
            "latitude", "longitude", "nature", "wind_speed_kt", "cold_cloud_fraction", "central_cold_cloud_fraction",
            "candidate_source", "lifecycle_stage"]
    out = out[cols]
    ensure_dir(project_path(cfg, "results"))
    out.to_csv(project_path(cfg, "results", "test_predictions.csv"), index=False)

    y, p = out.actual_label.to_numpy(), out.cyclone_probability.to_numpy()
    overall = metrics(y, p, thr)
    ci = group_bootstrap(out, thr, int(cfg["project"]["seed"]))
    plot_confusion(overall, rep / "confusion_matrix.png")
    plot_curves(y, p, overall, rep)
    cal = calibration(y, p, int(ev["calibration_bins"]))
    plot_calibration(cal, y, p, rep / "calibration.png")

    # ---------------- region-wise (only where statistically meaningful)
    rows = []
    for area, col in EVALUATION_AREAS:
        sub = out[out[col] == area]
        m = metrics(sub.actual_label.to_numpy(), sub.cyclone_probability.to_numpy(), thr) if len(sub) else metrics(np.array([]), np.array([]), thr)
        both = m["n_cyclone"] >= ev["min_samples_per_class"] and m["n_no_cyclone"] >= ev["min_samples_per_class"]
        recall_ok = m["n_cyclone"] >= ev["min_samples_recall"]
        rows.append({
            "area": AREA_LABELS[area], "level": col, "n": m["n"], "n_cyclone": m["n_cyclone"], "n_no_cyclone": m["n_no_cyclone"],
            "recall": m["recall"] if recall_ok else None,
            "precision": m["precision"] if both else None, "f1": m["f1"] if both else None,
            "accuracy": m["accuracy"] if both else None, "false_positive_rate": m["false_positive_rate"] if both else None,
            "roc_auc": m["roc_auc"] if both else None,
            "note": "all metrics" if both else ("recall only — no/too few negatives in this area" if recall_ok else "too few samples"),
        })
    region = pd.DataFrame(rows)
    region.to_csv(rep / "region_metrics.csv", index=False)

    # ---------------- intensity / difficulty / hard negatives
    by_intensity = {lvl: metrics(g.actual_label.to_numpy(), g.cyclone_probability.to_numpy(), thr)
                    for lvl, g in out[out.actual_label == 1].groupby("intensity")}
    by_difficulty = {lvl: metrics(g.actual_label.to_numpy(), g.cyclone_probability.to_numpy(), thr)
                     for lvl, g in out[out.actual_label == 0].groupby("difficulty")}
    hard = out[(out.actual_label == 0) & (out.difficulty == "hard")]
    pos_all = out[out.actual_label == 1]
    ni_pos = pos_all[pos_all.region == "north_indian_ocean"]
    hard_m = metrics(pd.concat([pos_all, hard]).actual_label.to_numpy(), pd.concat([pos_all, hard]).cyclone_probability.to_numpy(), thr)
    hard_ni = metrics(pd.concat([ni_pos, hard]).actual_label.to_numpy(), pd.concat([ni_pos, hard]).cyclone_probability.to_numpy(), thr)
    hard_negative = {
        "n_hard_negatives": int(len(hard)),
        "hard_negative_accuracy": float((hard.cyclone_probability < thr).mean()) if len(hard) else None,
        "hard_negative_false_positive_rate": float((hard.cyclone_probability >= thr).mean()) if len(hard) else None,
        "precision_all_positives_vs_hard_negatives": hard_m["precision"],
        "roc_auc_all_positives_vs_hard_negatives": hard_m["roc_auc"],
        "precision_ni_positives_vs_hard_negatives": hard_ni["precision"],
        "roc_auc_ni_positives_vs_hard_negatives": hard_ni["roc_auc"],
        "n_ni_positives": int(len(ni_pos)),
    }
    ni = out[out.region == "north_indian_ocean"]
    ni_metrics = metrics(ni.actual_label.to_numpy(), ni.cyclone_probability.to_numpy(), thr)

    # ---------------- cross-source check on the original PS-70 PNGs of TEST storms only
    cand = pd.read_csv(project_path(cfg, "metadata", "candidates.csv"), keep_default_na=False, na_values=[""])
    test_storms = set(pos_all.storm_id)
    orig = cand[(cand.label == 1) & cand.storm_id.isin(test_storms) & (cand.original_png.fillna("") != "")].reset_index(drop=True)
    orig["original_png_source"] = orig.original_png_source.fillna("<not recorded>")
    cross = {}
    if len(orig):
        # The PS-70 PNGs are stored south-up (see cleaning report); flip to the north-up training orientation.
        imgs = [Image.fromarray(np.flipud(np.asarray(Image.open(ROOT / pth).convert("L")))) for pth in orig.original_png]
        pc = ident.predict_proba(imgs)[:, 1]
        for source, sel in orig.groupby("original_png_source").indices.items():
            cross[source] = {"n": int(len(sel)), "recall": round(float((pc[sel] >= thr).mean()), 4),
                                                 "median_p_cyclone": round(float(np.median(pc[sel])), 4)}

    result = {
        "checkpoint": str(Path(args.checkpoint).resolve().relative_to(ROOT)) if Path(args.checkpoint).resolve().is_relative_to(ROOT) else str(args.checkpoint),
        "model": ident.model_info, "decision_threshold": thr,
        "test_split": {"n": int(len(out)), "cyclone": int((y == 1).sum()), "no_cyclone": int((y == 0).sum()),
                       "storms": int(pos_all.storm_id.nunique()), "groups": int(out.group_id.nunique())},
        "overall": overall, "bootstrap_95ci_by_group": ci,
        "north_indian_ocean_only": ni_metrics,
        "region": rows, "by_intensity": by_intensity, "by_negative_difficulty": by_difficulty,
        "hard_negative": hard_negative, "calibration": cal, "cross_source_original_png": cross,
    }
    write_json(rep / "test_metrics.json", result)

    print(f"\nHeld-out TEST ({overall['n']} images: {overall['n_cyclone']} cyclone / {overall['n_no_cyclone']} no_cyclone, "
          f"{result['test_split']['storms']} storms)")
    for k in ["accuracy", "precision", "recall", "f1", "roc_auc", "pr_auc", "false_positive_rate"]:
        print(f"  {k:<20} {overall[k]:.4f}   95% CI {ci[k]}")
    print(f"  confusion: TN {overall['tn']}  FP {overall['fp']}  FN {overall['fn']}  TP {overall['tp']}")
    print("\nRegion-wise:")
    print(region[["area", "n_cyclone", "n_no_cyclone", "recall", "precision", "f1", "false_positive_rate", "note"]].to_string(index=False))
    print(f"\nHard negatives: {hard_negative}")
    print(f"Calibration: ECE {cal['expected_calibration_error']}  share conf≥0.99 {cal['share_confidence_ge_0_99']}  "
          f"errors≥0.9 conf {cal['errors_with_confidence_ge_0_9']}/{cal['errors']}")
    print(f"Cross-source (original PS-70 PNGs of test storms): {cross}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
