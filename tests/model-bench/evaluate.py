"""Re-evaluate the three DEPLOYED models on their full held-out test sets, through the live FastAPI backend.

Every prediction is a real HTTP request to the running API, the same path the React app uses:

  identification  POST /api/ml/identify  — every image of identification_model/data/splits/test.csv
  classification  POST /api/ml/classify  — every image of identification_model/data/metadata/classification/classification_test.csv
  prediction      POST /api/ml/predict   — every held-out storm × forecast time the API offers
                                          (GET /api/cyclones/prediction-cases), scored against the storm's
                                          later observed fixes (GET /api/cyclones/{id}/track)

Metrics are computed here from those responses — nothing is copied from the training reports. The reports'
values are stored alongside, only for comparison. Output: evaluation.json (read by evaluation.html).

    ..\\..\\backend\\.venv\\Scripts\\python.exe evaluate.py [--api http://127.0.0.1:8001/api] [--workers 8]
"""

from __future__ import annotations

import argparse
import json
import math
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
IDENT = REPO / "identification_model"
PRED = REPO / "prediction_model"
EARTH_RADIUS_KM = 6371.0088
KT_PER_KMH = 1 / 1.852
_local = threading.local()


# ---------------------------------------------------------------- helpers

def client() -> httpx.Client:
    if not hasattr(_local, "client"):
        _local.client = httpx.Client(timeout=120.0)
    return _local.client


def run_parallel(fn, items, workers: int, label: str) -> list:
    out, started = [], time.perf_counter()
    with ThreadPoolExecutor(workers) as pool:
        for i, result in enumerate(pool.map(fn, items), 1):
            out.append(result)
            if i % 250 == 0 or i == len(items):
                print(f"  {label}: {i}/{len(items)} ({time.perf_counter() - started:.0f} s)", flush=True)
    return out


def clean(value):
    """JSON-safe: NaN/inf → None, numpy → Python."""
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return None if not math.isfinite(float(value)) else round(float(value), 6)
    return value


def ratio(a: float, b: float) -> float:
    return float(a) / float(b) if b else float("nan")


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def wrap_lon(lon: float) -> float:
    return (lon + 180.0) % 360.0 - 180.0


def read_report(path: Path) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None  # json accepts the reports' NaN


# ---------------------------------------------------------------- metrics

def binary_metrics(y_true, y_pred, score) -> dict:
    y, p, s = np.asarray(y_true, bool), np.asarray(y_pred, bool), np.asarray(score, float)
    tp, fp = int((y & p).sum()), int((~y & p).sum())
    tn, fn = int((~y & ~p).sum()), int((y & ~p).sum())
    precision, recall = ratio(tp, tp + fp), ratio(tp, tp + fn)
    npos, nneg = int(y.sum()), int((~y).sum())
    ranks = pd.Series(s).rank(method="average").to_numpy()
    auc = (ranks[y].sum() - npos * (npos + 1) / 2) / (npos * nneg)
    order = np.argsort(-s, kind="mergesort")
    hits = y[order]
    ap = float((np.cumsum(hits) / np.arange(1, len(s) + 1))[hits].sum() / npos)
    thresholds = np.unique(s)[::-1]
    curve = [(0.0, 0.0)] + [(float(((s >= t) & ~y).sum() / nneg), float(((s >= t) & y).sum() / npos)) for t in thresholds] + [(1.0, 1.0)]
    if len(curve) > 160:  # keep the shape, drop redundant points
        keep = np.unique(np.linspace(0, len(curve) - 1, 160).round().astype(int))
        curve = [curve[i] for i in keep]
    edges = np.linspace(0, 1, 21)
    return {
        "n": int(len(y)), "positives": npos, "negatives": nneg,
        "confusion": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
        "accuracy": ratio(tp + tn, len(y)), "precision": precision, "recall": recall,
        "f1": ratio(2 * precision * recall, precision + recall), "specificity": ratio(tn, tn + fp),
        "roc_auc": float(auc), "pr_auc": ap,
        "roc_curve": [{"fpr": f, "tpr": t} for f, t in curve],
        "score_histogram": {"edges": edges.tolist(),
                            "cyclone": np.histogram(s[y], edges)[0].tolist(), "no_cyclone": np.histogram(s[~y], edges)[0].tolist()},
    }


def multiclass_metrics(y_true, y_pred, probs: np.ndarray, classes: list[dict]) -> dict:
    k, t, p = len(classes), np.asarray(y_true, int), np.asarray(y_pred, int)
    cm = np.zeros((k, k), int)
    for a, b in zip(t, p):
        cm[a, b] += 1
    per_class = []
    for i, c in enumerate(classes):
        tp, pred_n, true_n = cm[i, i], cm[:, i].sum(), cm[i, :].sum()
        precision, recall = ratio(tp, pred_n), ratio(tp, true_n)
        per_class.append({"class_id": i, "code": c["code"], "name": c["name"], "support": int(true_n), "predicted": int(pred_n),
                          "precision": precision, "recall": recall, "f1": ratio(2 * precision * recall, precision + recall)})
    f1s = np.array([c["f1"] for c in per_class], float)
    support = np.array([c["support"] for c in per_class], float)
    top2 = np.argsort(-probs, axis=1)[:, :2]
    return {
        "n": int(len(t)), "classes": [c["code"] for c in classes], "confusion_matrix": cm.tolist(), "per_class": per_class,
        "accuracy": ratio(np.trace(cm), len(t)),
        "balanced_accuracy": float(np.mean([c["recall"] for c in per_class])),
        "macro_precision": float(np.mean([c["precision"] for c in per_class])),
        "macro_recall": float(np.mean([c["recall"] for c in per_class])),
        "macro_f1": float(np.nanmean(f1s)), "weighted_f1": float(np.nansum(f1s * support) / support.sum()),
        "adjacent_accuracy": float(np.mean(np.abs(t - p) <= 1)), "top2_accuracy": float(np.mean([a in row for a, row in zip(t, top2)])),
    }


# ---------------------------------------------------------------- stage 1 + 2: images

def evaluate_identification(api: str, workers: int) -> dict:
    rows = pd.read_csv(IDENT / "data" / "splits" / "test.csv").to_dict("records")

    def one(row):
        path = IDENT / row["image_path"]
        r = client().post(f"{api}/ml/identify", files={"file": (path.name, path.read_bytes(), "image/png")})
        return row, r.status_code, r.json()

    results = run_parallel(one, rows, workers, "identification")
    ok = [(row, body["identification"], body["inference"]["processing_time_ms"]) for row, code, body in results if code == 200]
    failed = Counter(body.get("error", {}).get("code", str(code)) for _, code, body in results if code != 200)
    y = [int(row["label"]) == 1 for row, _, _ in ok]
    live = binary_metrics(y, [ident["detected"] for _, ident, _ in ok], [ident["cyclone_probability"] for _, ident, _ in ok])
    offline = pd.read_csv(IDENT / "results" / "test_predictions.csv").set_index("image_id")["predicted_label"].to_dict()
    agree = sum(int(ident["detected"]) == int(offline.get(row["image_id"], -1)) for row, ident, _ in ok)
    by_region = []
    frame = pd.DataFrame({"region": [row["region"] for row, _, _ in ok], "y": y, "p": [ident["detected"] for _, ident, _ in ok]})
    for region, g in frame.groupby("region"):
        m = binary_metrics(g["y"], g["p"], g["p"].astype(float)) if g["y"].nunique() == 2 else None
        by_region.append({"region": region, "n": int(len(g)), "accuracy": float((g["y"] == g["p"]).mean()),
                          "recall": m["recall"] if m else None, "precision": m["precision"] if m else None})
    report = read_report(IDENT / "reports" / "test_metrics.json")
    return {"live": {**live, "failed_requests": dict(failed), "median_server_ms": float(np.median([ms for *_, ms in ok])),
                     "agreement_with_training_evaluation": {"agree": agree, "of": len(ok)}, "by_region": by_region},
            "reported": report and {"overall": report["overall"], "test_split": report["test_split"], "model": report["model"]}}


def evaluate_classification(api: str, workers: int) -> dict:
    rows = pd.read_csv(IDENT / "data" / "metadata" / "classification" / "classification_test.csv").to_dict("records")
    mapping = json.loads((REPO / "backend" / "models" / "classification" / "class_mapping.json").read_text(encoding="utf-8"))
    classes = [{"id": int(k), **v} for k, v in sorted(mapping.items(), key=lambda kv: int(kv[0]))]

    def one(row):
        path = IDENT / row["image_path"]
        r = client().post(f"{api}/ml/classify", files={"file": (path.name, path.read_bytes(), "image/png")})
        return row, r.status_code, r.json()

    results = run_parallel(one, rows, workers, "classification")
    ok = [(row, body) for row, code, body in results if code == 200]
    failed = Counter(body.get("error", {}).get("code", str(code)) for _, code, body in results if code != 200)
    probs = np.array([[body["probabilities"][c["name"]] for c in classes] for _, body in ok])
    live = multiclass_metrics([int(row["label"]) for row, _ in ok], [body["prediction"]["class_id"] for _, body in ok], probs, classes)
    offline = pd.read_csv(IDENT / "results" / "classification" / "test_predictions.csv").set_index("image_id")["predicted_class"].to_dict()
    agree = sum(body["prediction"]["class_code"] == offline.get(row["image_id"]) for row, body in ok)
    report = read_report(IDENT / "reports" / "classification" / "classification_metrics.json")
    return {"live": {**live, "failed_requests": dict(failed), "median_server_ms": float(np.median([b["inference"]["processing_time_ms"] for _, b in ok])),
                     "agreement_with_training_evaluation": {"agree": agree, "of": len(ok)}},
            "reported": report and {"overall": report["overall"], "per_class": report["per_class"], "test_split": report["test_split"]}}


# ---------------------------------------------------------------- stage 3: track / wind / pressure

def evaluate_prediction(api: str, workers: int) -> dict:
    cases = client().get(f"{api}/cyclones/prediction-cases").json()["cases"]
    tracks = {c["cycloneId"]: {p["timestamp"]: p for p in client().get(f"{api}/cyclones/{c['cycloneId']}/track").json()["points"]} for c in cases}
    area = {c["cycloneId"]: c["area"] for c in cases}
    jobs = [(c["cycloneId"], t0) for c in cases for t0 in c["forecastOrigins"]]

    def one(job):
        cyclone_id, t0 = job
        r = client().post(f"{api}/ml/predict", json={"cyclone_id": cyclone_id, "timestamp": t0})
        return job, r.status_code, r.json()

    results = run_parallel(one, jobs, workers, "prediction")
    failed = Counter(body.get("error", {}).get("code", str(code)) for _, code, body in results if code != 200)
    rows, no_verifying_fix = [], 0
    for (cyclone_id, t0), code, body in results:
        if code != 200:
            continue
        track, cur = tracks[cyclone_id], body["current"]
        t12 = (pd.Timestamp(t0) - pd.Timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M:%SZ")
        prev = track.get(t12)
        for step in body["forecast"]:
            obs = track.get(step["forecastTime"])
            if obs is None:  # the storm was not observed at that time: nothing to score against
                no_verifying_fix += 1
                continue
            h = step["hours"]
            row = {"lead": h, "area": area[cyclone_id],
                   "model_km": haversine_km(step["latitude"], step["longitude"], obs["latitude"], obs["longitude"]),
                   "persistence_km": haversine_km(cur["latitude"], cur["longitude"], obs["latitude"], obs["longitude"]),
                   "radius_km": step.get("uncertaintyRadiusKm"), "cat_forecast": step.get("category"), "cat_observed": obs.get("category")}
            if prev is not None:  # 12 h mean-motion extrapolation, from the observed fixes only
                lat_e = cur["latitude"] + (cur["latitude"] - prev["latitude"]) * h / 12
                lon_e = wrap_lon(cur["longitude"] + wrap_lon(cur["longitude"] - prev["longitude"]) * h / 12)
                row["extrapolation_km"] = haversine_km(lat_e, lon_e, obs["latitude"], obs["longitude"])
            if obs.get("windKmh") is not None:
                obs_kt = obs["windKmh"] * KT_PER_KMH
                row["wind_err"], row["wind_err_persistence"] = abs(step["windSpeedKt"] - obs_kt), abs(cur["windKt"] - obs_kt)
            if obs.get("pressureHpa") is not None:
                row["pres_err"], row["pres_err_persistence"] = abs(step["pressure"] - obs["pressureHpa"]), abs(cur["pressureHpa"] - obs["pressureHpa"])
            rows.append(row)
    df = pd.DataFrame(rows)

    # IMD category order, from the observed data itself (median observed wind per category)
    winds = [(p["category"], p["windKmh"] * KT_PER_KMH) for t in tracks.values() for p in t.values() if p.get("category") and p.get("windKmh") is not None]
    order = list(pd.DataFrame(winds, columns=["cat", "kt"]).groupby("cat")["kt"].median().sort_values().index)
    rank = {c: i for i, c in enumerate(order)}

    leads = []
    for h, g in df.groupby("lead"):
        cats = g.dropna(subset=["cat_forecast", "cat_observed"])
        cats = cats[cats["cat_forecast"].isin(rank) & cats["cat_observed"].isin(rank)]
        f1s = []
        for c in order:
            tp = int(((cats["cat_forecast"] == c) & (cats["cat_observed"] == c)).sum())
            pn, tn_ = int((cats["cat_forecast"] == c).sum()), int((cats["cat_observed"] == c).sum())
            if tn_:
                pr, rc = ratio(tp, pn), ratio(tp, tn_)
                f1s.append(ratio(2 * pr * rc, pr + rc) if pn else 0.0)
        ext = g["extrapolation_km"].dropna()
        leads.append({
            "lead": int(h), "n": int(len(g)),
            "track_km": {"model": {"mean": g["model_km"].mean(), "median": g["model_km"].median(), "p90": g["model_km"].quantile(0.9)},
                         "persistence": {"mean": g["persistence_km"].mean()}, "extrapolation": {"mean": ext.mean(), "n": int(len(ext))}},
            "skill_vs_extrapolation_pct": 100 * (1 - g.loc[ext.index, "model_km"].mean() / ext.mean()),
            "skill_vs_persistence_pct": 100 * (1 - g["model_km"].mean() / g["persistence_km"].mean()),
            "wind_mae_kt": {"model": g["wind_err"].mean(), "persistence": g["wind_err_persistence"].mean(), "n": int(g["wind_err"].notna().sum())},
            "pressure_mae_hpa": {"model": g["pres_err"].mean(), "persistence": g["pres_err_persistence"].mean(), "n": int(g["pres_err"].notna().sum())},
            "within_radius": float((g["model_km"] <= g["radius_km"]).mean()) if g["radius_km"].notna().all() else None,
            "radius_km": float(g["radius_km"].iloc[0]) if g["radius_km"].notna().any() else None,
            "category": {"n": int(len(cats)), "accuracy": float((cats["cat_forecast"] == cats["cat_observed"]).mean()),
                         "within_one": float((cats["cat_forecast"].map(rank) - cats["cat_observed"].map(rank)).abs().le(1).mean()),
                         "macro_f1": float(np.mean(f1s)) if f1s else None},
        })
    last = df[df["lead"] == df["lead"].max()].dropna(subset=["cat_forecast", "cat_observed"])
    cm = pd.crosstab(pd.Categorical(last["cat_observed"], order), pd.Categorical(last["cat_forecast"], order), dropna=False)
    by_area = [{"area": a, "n": int(len(g)), "storms": None, "track_km": g["model_km"].mean(), "extrapolation_km": g["extrapolation_km"].mean()}
               for a, g in df[df["lead"] == df["lead"].max()].groupby("area")]
    report = read_report(PRED / "reports" / "test_metrics.json")
    return {"live": {"storms": len(cases), "forecasts_requested": len(jobs), "forecasts_ok": sum(1 for _, c, _ in results if c == 200),
                     "failed_requests": dict(failed), "steps_without_verifying_fix": no_verifying_fix, "leads": leads,
                     "category_order": order, "category_confusion_last_lead": {"lead": int(df["lead"].max()), "labels": order, "matrix": cm.to_numpy().tolist()},
                     "by_area_last_lead": by_area},
            "reported": report and {"overall": report["overall"], "uncertainty_coverage": report.get("uncertainty_coverage"), "test_split": report["test_split"]}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api", default="http://127.0.0.1:8001/api")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    api = args.api.rstrip("/")
    started = time.perf_counter()
    status = client().get(f"{api}/ml/status").json()
    print(f"Backend {api}: status {status['status']} — evaluating the deployed models on their held-out test sets", flush=True)
    out = {"generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "api": api,
           "models": {k: status.get(k) for k in ("identification", "classification", "prediction")}}
    for key, fn in (("identification", evaluate_identification), ("classification", evaluate_classification), ("prediction", evaluate_prediction)):
        t = time.perf_counter()
        out[key] = fn(api, args.workers)
        out[key]["seconds"] = round(time.perf_counter() - t, 1)
    out["seconds"] = round(time.perf_counter() - started, 1)
    (HERE / "evaluation.json").write_text(json.dumps(clean(out), indent=1, allow_nan=False), encoding="utf-8")
    i, c, p = out["identification"]["live"], out["classification"]["live"], out["prediction"]["live"]
    last = p["leads"][-1]
    print(f"\nIdentification  n={i['n']}  accuracy {i['accuracy']:.4f}  precision {i['precision']:.4f}  recall {i['recall']:.4f}  F1 {i['f1']:.4f}  ROC-AUC {i['roc_auc']:.4f}")
    print(f"Classification  n={c['n']}  accuracy {c['accuracy']:.4f}  macro P {c['macro_precision']:.4f}  macro R {c['macro_recall']:.4f}  macro F1 {c['macro_f1']:.4f}")
    print(f"Prediction      {p['forecasts_ok']} forecasts / {p['storms']} storms  T+{last['lead']}h track {last['track_km']['model']['mean']:.1f} km "
          f"(extrapolation {last['track_km']['extrapolation']['mean']:.1f}, persistence {last['track_km']['persistence']['mean']:.1f})  "
          f"wind MAE {last['wind_mae_kt']['model']:.2f} kt  category accuracy {last['category']['accuracy']:.3f}")
    print(f"Done in {out['seconds']:.0f} s -> {HERE / 'evaluation.json'}")


if __name__ == "__main__":
    main()
