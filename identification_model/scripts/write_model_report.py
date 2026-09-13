#!/usr/bin/env python3
"""STEP 40 — Assemble reports/model_report.md from the saved pipeline outputs.

Every number is read from files written by the pipeline (audit, cleaning, selection, splits,
leakage check, training, test evaluation, error analysis); nothing is typed in by hand.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.utils import AREA_LABELS, load_config, project_path, read_json  # noqa: E402


def f(x, digits: int = 3) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/a"
    if isinstance(x, (int,)) and not isinstance(x, bool):
        return f"{x:,}"
    return f"{x:.{digits}f}"


def ci(c: dict, key: str) -> str:
    lo, hi = c.get(key, [None, None])
    return f"[{f(lo)}, {f(hi)}]"


def table(rows: list[list], headers: list[str]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    return "\n".join(out + ["| " + " | ".join(str(c) for c in r) + " |" for r in rows])


def main() -> int:
    cfg = load_config()
    rep, aud = project_path(cfg, "reports"), project_path(cfg, "reports", "audit")
    audit = read_json(aud / "audit_summary.json")
    cand = read_json(aud / "candidates_summary.json")
    sel = read_json(aud / "selection_summary.json")
    split = read_json(aud / "split_summary.json")
    repro = read_json(aud / "reproduction_check.json")
    leak = read_json(rep / "leakage_check.json")
    mc = read_json(project_path(cfg, "models", "model_config.json"))
    tm = read_json(rep / "test_metrics.json")
    err = read_json(rep / "errors" / "error_summary.json")
    hist = pd.read_csv(rep / "training_history.csv")
    man = pd.read_csv(project_path(cfg, "metadata", "identification_dataset.csv"), keep_default_na=False, na_values=[""])
    meta_rej = pd.read_csv(project_path(cfg, "metadata", "candidate_rejections.csv"))
    img_rej = pd.read_csv(project_path(cfg, "metadata", "image_rejections.csv"))
    man["area"] = man.subregion.fillna("").where(man.subregion.fillna("") != "", man.region)
    o, c, tc = tm["overall"], tm["bootstrap_95ci_by_group"], mc["training_configuration"]
    hn, cal, ni = tm["hard_negative"], tm["calibration"], tm["north_indian_ocean_only"]
    a, pos_png = audit["dataset_a_finalized_metadata"], audit["dataset_a_positive_png"]
    pool, ctx = audit["dataset_b_negative_pool"], audit["dataset_b_ibtracs_crosscheck"]
    best = hist.loc[hist.epoch == mc["best_epoch"]].iloc[0]

    area_rows = []
    for area in ["arabian_sea", "bay_of_bengal", "south_indian_ocean", "western_pacific", "eastern_pacific", "southern_pacific"]:
        g = man[man.area == area]
        area_rows.append([AREA_LABELS[area], int((g.label == 1).sum()), int((g.label == 0).sum())])

    region_rows = [[r["area"], r["n_cyclone"], r["n_no_cyclone"], f(r["recall"]), f(r["precision"]), f(r["f1"]),
                    f(r["false_positive_rate"]), f(r["roc_auc"]), r["note"]] for r in tm["region"]]
    intensity_rows = [[k, v["n_cyclone"], f(v["recall"]), v["fn"]] for k, v in sorted(tm["by_intensity"].items())]
    diff_rows = [[k, v["n_no_cyclone"], f(v["specificity"]), f(v["false_positive_rate"]), v["fp"]]
                 for k, v in sorted(tm["by_negative_difficulty"].items(), key=lambda kv: ["easy", "moderate", "hard"].index(kv[0]))]
    cross_rows = [[k, v["n"], f(v["recall"]), f(v["median_p_cyclone"])] for k, v in tm["cross_source_original_png"].items()]
    recall_only = [r["area"] for r in tm["region"] if r["note"].startswith("recall only")]

    L = [
        "# Model report — VayuDrishti cyclone identification (PS-70, stage 1)",
        "",
        f"Model **{mc['architecture']}** · model version {mc['model_version']} · dataset {mc['dataset_version']} · trained {mc['created_at']} on {mc['device']}.",
        "All numbers below are read from the pipeline outputs; test metrics come only from the held-out test split.",
        "",
        "## 1. Dataset sources",
        f"- **Dataset A (positives):** PS-70 finalized IBTrACS v04r01 metadata — {a['records']:,} fixes, {a['unique_storms']:,} storms, seasons {a['seasons'][0]}–{a['seasons'][1]}, basins NI/SI/WP/EP/SP. The PS-70 positive candidate workbook (2,000 fixes, 721 storms) is a selection from it; {pos_png['files']} PNGs had been collected (mostly HURSAT-B1).",
        f"- **Dataset B (negatives):** PS-70 GridSat-B1 non-cyclone pool — {pool['records']:,} North Indian Ocean samples ({pool['years'][0]}–{pool['years'][1]}) with the rule “≥ 10° from every IBTrACS DS/TS/MX centre”, plus its 2,000-sample selection. No images.",
        "- **Imagery used for training (both classes):** NOAA GridSat-B1 v02r01 IRWIN CDR (~11 µm), 18°×18° crops at the nearest 3-hourly slot, one code path for both classes. See `reports/dataset_audit.md`.",
        f"- No bounding-box annotations exist → binary image classification.",
        "",
        "## 2. Dataset size",
        f"- **{len(man):,} images: {int((man.label == 1).sum()):,} cyclone + {int((man.label == 0).sum()):,} no_cyclone**, no duplicated images.",
        f"- Cleaning: {len(meta_rej)} rows rejected on metadata, {len(img_rej)} on imagery (`reports/cleaning_report.md`).",
        "",
        "## 3. Positive / negative distribution",
        f"- Positive intensity (storm lifetime max wind; <34 / 34–63 / ≥64 kt): {man[man.label == 1].intensity.value_counts().to_dict()}; {sel['positive_storms']} storms; sources {sel['positive_sources']}.",
        f"- Negative difficulty: {man[man.label == 0].difficulty.value_counts().to_dict()}. Hard = central 9°×9° cold-cloud (<235 K) fraction ≥ {sel['hard_negative_central_cold_fraction_threshold']:.3f} (P{cfg['selection']['hard_reference_percentile']} of positives); easy = whole-crop cold cloud < {cfg['selection']['easy_max_cold_fraction']:.0%}.",
        "",
        "## 4. Regional distribution",
        table(area_rows, ["area", "cyclone", "no_cyclone"]),
        "",
        "Negatives exist only in the North Indian Ocean (Dataset B covers only that basin).",
        "",
        "## 5. Split methodology",
        f"- {split['method']}; seed {split['seed']}.",
        f"- Rows {split['rows']} (shares {split['share']}); cyclone share per split {split['cyclone_share']}.",
        f"- Positive storms per split {split['storms']}; negative difficulty per split {split['difficulty']}.",
        "",
        "## 6. Leakage prevention",
        f"- Groups ({split['groups']:,}): same storm id, crops whose boxes overlap within {cfg['splits']['group_overlap_hours']} h (event grouping for negatives), near-duplicates; largest group {split['group_size']['max']} samples.",
        f"- **DATA LEAKAGE CHECK: {leak['status']}**: " + "; ".join(f"{k} = {v['violations']}" for k, v in leak["checks"].items()) + ".",
        "- `src/train.py` refuses to run unless the check passed for the exact split files (SHA-256 recorded).",
        "",
        "## 7. Preprocessing",
        f"- {mc['input']['rendering']}; north up. Crops with > {cfg['imagery']['max_missing_fraction']:.0%} missing pixels rejected.",
        f"- Model input: {mc['input']['model_transform']} (mean {mc['normalization']['mean']}, std {mc['normalization']['std']}).",
        f"- Reproduction check vs the original PS-70 PNGs: {repro}. The GridSat originals are reproduced exactly once flipped vertically — the PS-70 PNGs are stored south-up.",
        "",
        "## 8. Augmentation (train only)",
        f"- {tc['augmentation']}.",
        "- Flips are justified because the data spans both hemispheres (cyclonic rotation is mirrored between them); rotations and crops are small so storm structure is kept. Validation/test are resized only.",
        "",
        "## 9. Model architecture",
        f"- {mc['architecture']} with {mc['pretrained_weights']} weights; classifier head replaced by a 2-class linear layer. Classes {mc['classes']}. Input {mc['input_size']}.",
        "- Backbone is configurable (`--model-name resnet50 | mobilenet_v3_large`); only the baseline was trained.",
        "",
        "## 10. Training configuration",
        table([[k, v] for k, v in tc.items() if k != "augmentation"] + [["seed", mc["training_seed"]], ["decision threshold", mc["decision_threshold"]],
              ["best epoch", mc["best_epoch"]], ["training time (min)", mc["training_minutes"]]], ["setting", "value"]),
        "",
        "## 11. Validation results (best epoch, threshold 0.5)",
        f"- Epoch {mc['best_epoch']}: loss {f(best.val_loss, 4)}, accuracy {f(best.val_accuracy)}, precision {f(best.val_precision)}, recall {f(best.val_recall)}, F1 {f(best.val_f1)}.",
        "- Curves: `reports/training_history.png`; per-epoch values: `reports/training_history.csv`.",
        "",
        "## 12. Test results (held-out storms / events)",
        f"Test split: {tm['test_split']['n']} images ({tm['test_split']['cyclone']} cyclone / {tm['test_split']['no_cyclone']} no_cyclone), {tm['test_split']['storms']} storms never seen in training. 95 % intervals: bootstrap over event groups.",
        "",
        table([[k.replace("_", " "), f(o[k]), ci(c, k)] for k in ["accuracy", "precision", "recall", "f1", "roc_auc", "pr_auc", "false_positive_rate"]],
              ["metric", "value", "95 % CI"]),
        "",
        f"North Indian Ocean only (the one area with both classes): n={ni['n']} ({ni['n_cyclone']} / {ni['n_no_cyclone']}), accuracy {f(ni['accuracy'])}, precision {f(ni['precision'])}, recall {f(ni['recall'])}, F1 {f(ni['f1'])}, ROC-AUC {f(ni['roc_auc'])}.",
        "",
        "## 13. Confusion matrix",
        table([["ACTUAL NO CYCLONE", o["tn"], o["fp"]], ["ACTUAL CYCLONE", o["fn"], o["tp"]]], ["", "PREDICTED NO", "PREDICTED CYCLONE"]),
        "",
        "![confusion](confusion_matrix.png)",
        "",
        "## 14. ROC-AUC",
        f"ROC-AUC {f(o['roc_auc'])} {ci(c, 'roc_auc')}. ![roc](roc_curve.png)",
        "",
        "## 15. PR-AUC",
        f"PR-AUC (average precision) {f(o['pr_auc'])} {ci(c, 'pr_auc')}. ![pr](pr_curve.png)",
        "",
        "## 16. Region-wise performance",
        f"Precision/FPR are reported only where both classes have ≥ {cfg['evaluation']['min_samples_per_class']} test samples; recall needs ≥ {cfg['evaluation']['min_samples_recall']} positives.",
        "",
        table(region_rows, ["area", "cyclone", "no_cyclone", "recall", "precision", "F1", "FPR", "ROC-AUC", "note"]),
        "",
        f"Recall by storm intensity:",
        "",
        table(intensity_rows, ["intensity", "n", "recall", "missed"]),
        "",
        "## 17. Hard-negative performance",
        table([[k, n, spec, fpr, fp] for k, n, spec, fpr, fp in diff_rows], ["difficulty", "n", "accuracy (specificity)", "false positive rate", "false positives"]),
        "",
        f"- Hard negatives: n={hn['n_hard_negatives']}, accuracy {f(hn['hard_negative_accuracy'])}, false positive rate {f(hn['hard_negative_false_positive_rate'])}.",
        f"- Precision with all test positives vs hard negatives only: {f(hn['precision_all_positives_vs_hard_negatives'])} (ROC-AUC {f(hn['roc_auc_all_positives_vs_hard_negatives'])}); North Indian Ocean positives vs hard negatives: precision {f(hn['precision_ni_positives_vs_hard_negatives'])}, ROC-AUC {f(hn['roc_auc_ni_positives_vs_hard_negatives'])} (n_pos={hn['n_ni_positives']}).",
        "",
        "## 18. Error analysis",
        f"- False positives: {err['false_positives']}; false negatives: {err['false_negatives']} (`reports/errors/`, `reports/errors/errors.csv`).",
        f"- FP rate by difficulty: {err['fp_rate_by_difficulty']}.",
        f"- FN rate by intensity: {err['fn_rate_by_intensity']}.",
        f"- FN rate by area: {err['fn_rate_by_area']}.",
        f"- FN rate by lifecycle stage: {err['fn_rate_by_lifecycle_stage']}.",
        f"- Median wind at missed fixes {f(err['fn_wind_kt_median'], 1)} kt vs detected {f(err['tp_wind_kt_median'], 1)} kt; central cold-cloud fraction FN {f(err['fn_central_cold_cloud_median'])} vs TP {f(err['tp_central_cold_cloud_median'])}; FP {f(err['fp_central_cold_cloud_median'])} vs TN {f(err['tn_central_cold_cloud_median'])}.",
        f"- **Missed cyclones:** {err['fn_weak_storms']} of {err['false_negatives']} belong to weak (depression-strength) storms, {err['fn_wind_le_25kt']} were ≤ 25 kt at the imaged fix ({err['fn_wind_missing']} without a wind value), and {err['fn_bay_of_bengal']} are in the Bay of Bengal — disorganised monsoon-season depressions and sheared remnants without a clear central dense overcast.",
        f"- **False alarms:** {err['fp_hard']} of {err['false_positives']} are hard negatives — large, central deep-convective clusters. "
        f"A tracked IBTrACS system entered the crop within the next {err['pregenesis']['window_hours']} h for "
        f"{err['pregenesis']['false_positives_with_system_entering_crop']} of {err['pregenesis']['false_positives']} false positives "
        f"({f(err['pregenesis']['false_positive_rate_of_hits'])}) vs {err['pregenesis']['true_negatives_with_system_entering_crop']} of {err['pregenesis']['true_negatives']} true negatives "
        f"({f(err['pregenesis']['true_negative_rate_of_hits'])}). The PS-70 negative rule only checks the matched time, so some of these scenes may show pre-genesis disturbances; "
        f"details: {err['pregenesis']['false_positive_details']}.",
        "",
        "Confidence analysis (softmax scores are not calibrated probabilities):",
        f"- ECE {f(cal['expected_calibration_error'])}; mean confidence {f(cal['mean_confidence'])} vs accuracy {f(cal['accuracy'])}; {cal['share_confidence_ge_0_99']:.1%} of predictions have confidence ≥ 0.99; "
        f"{cal['errors_with_confidence_ge_0_9']} of {cal['errors']} errors were made with confidence ≥ 0.9 (median error confidence {f(cal['median_confidence_errors'])}). ![calibration](calibration.png)",
        "",
        "Cross-source check — original PS-70 PNGs (other sensor processing) of **test storms only**, flipped to north-up (recall only; all positives):",
        "",
        table(cross_rows, ["original source", "n", "recall", "median p(cyclone)"]) if cross_rows else "- none available",
        "",
        "## 19. Limitations",
        f"- **Negatives cover only the North Indian Ocean.** For {', '.join(recall_only) or 'the other basins'} only recall can be measured; the false-positive behaviour outside the NIO is unknown and could be worse (no negatives from those climates/backgrounds were ever seen).",
        "- **Geographic confounding:** every negative is an NIO scene (and some are centred over land), while 2/3 of positives come from other basins. Part of the separation can come from background (coastlines, land temperature, latitude/climate) rather than cyclone morphology; the NIO-only and hard-negative numbers are the fairest view.",
        "- **Storm-centred positives:** positives are centred on the IBTrACS position; the model answers “is there a cyclone at the centre of this 18° scene”, not “anywhere in a large image”. Full-disk use needs a sliding window.",
        "- **Label source:** positives follow IBTrACS TS nature and negatives the PS-70 ≥ 10° rule; no human verification (all REVIEW_REQUIRED). Weak (depression-strength) systems are genuinely ambiguous in IR.",
        "- **Intensity** is the storm's lifetime category, not the intensity at the imaged time.",
        "- **Hard negatives** are defined by an image heuristic (cold-cloud amount), not by meteorological labels such as monsoon depressions or disturbances.",
        "- **Calibration:** the softmax confidence is not a calibrated probability.",
        f"- **Sample size:** the test set has {tm['test_split']['n']} images from {tm['test_split']['groups']} event groups; per-area numbers carry wide uncertainty.",
        "- **Single sensor/channel:** trained on GridSat-B1 IR only; INSAT-3D/3DR imagery or other renderings need domain validation before use.",
        "",
        "## 20. Recommended next improvements",
        "1. Add negatives for SI/WP/EP/SP generated with the same IBTrACS distance rule (append them to `candidates.csv`, then re-run fetch → clean → select → split) so precision can be measured in every basin and the geographic shortcut is removed.",
        "2. Add explicit hard negatives from IBTrACS disturbances (DS), monsoon depressions and pre-genesis clusters, and have analysts verify a sample of both classes.",
        "3. Evaluate on INSAT-3D/3DR IR imagery of recent NIO cyclones before operational use; fine-tune if the domain gap is large.",
        "4. Calibrate the scores on validation data (temperature scaling) before showing them as probabilities, and choose the operating threshold from the recall/precision trade-off the forecasters need.",
        "5. Add a land-mask channel or drop land-centred negatives to test how much the background contributes.",
        "6. Compare ResNet50 / MobileNetV3 with the same splits (`python src/train.py --model-name ... --run-name ...`).",
    ]
    (rep / "model_report.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"Wrote {rep / 'model_report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
