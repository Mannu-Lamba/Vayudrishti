#!/usr/bin/env python3
"""Classification STEP 2–4 report — reports/classification/classification_dataset_report.{json,md} + figures.

Run after build_dataset.py, create_splits.py and check_leakage.py (classification config).
"""

from __future__ import annotations

import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from PIL import Image  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.utils import AREA_LABELS, cfg_file, ensure_dir, load_config, project_path, read_json, task_classes, write_json  # noqa: E402

CONFIG = ROOT / "configs" / "classification.yaml"
AREAS = ["arabian_sea", "bay_of_bengal", "south_indian_ocean", "western_pacific", "eastern_pacific", "southern_pacific"]
COLORS = ["#3b82f6", "#10b981", "#f97316", "#dc2626"]


def table(rows, headers) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    return "\n".join(out + ["| " + " | ".join(str(c) for c in r) + " |" for r in rows])


def main() -> int:
    cfg = load_config(CONFIG)
    classes = task_classes(cfg)
    codes = [c["code"] for c in classes]
    aud = project_path(cfg, "reports", "audit")
    cand_s, build_s, split_s = read_json(aud / "candidates_summary.json"), read_json(aud / "build_summary.json"), read_json(aud / "split_summary.json")
    leak = read_json(project_path(cfg, "reports", cfg_file(cfg, "leakage_report", "leakage_check.json")))
    m = pd.read_csv(project_path(cfg, "metadata", cfg_file(cfg, "manifest", "classification_dataset.csv")), keep_default_na=False, na_values=[""])
    m["area"] = m.subregion.fillna("").where(m.subregion.fillna("") != "", m.region)
    fig_dir = ensure_dir(project_path(cfg, "reports", "figures"))

    fmt, dims, modes = Counter(), Counter(), Counter()
    for p in m.image_path:
        with Image.open(ROOT / p) as img:
            fmt[img.format] += 1
            dims[f"{img.width}x{img.height}"] += 1
            modes[img.mode] += 1

    class_area = pd.crosstab(m.class_code, m.area).reindex(index=codes, columns=AREAS).fillna(0).astype(int)
    class_basin = pd.crosstab(m.class_code, m.basin).reindex(index=codes).fillna(0).astype(int)
    split_class = pd.crosstab(m.split, m.class_code).reindex(index=["train", "val", "test"], columns=codes).fillna(0).astype(int)
    wind = m.groupby("class_code").usa_wind_kt.describe()[["min", "50%", "max"]].reindex(codes)

    # ---------------- figures
    fig, axes = plt.subplots(1, 2, figsize=(12, 3.8))
    x = np.arange(len(AREAS))
    for k, code in enumerate(codes):
        axes[0].bar(x + (k - 1.5) * 0.2, class_area.loc[code], 0.2, label=code, color=COLORS[k])
    axes[0].set_xticks(x, [AREA_LABELS[a] for a in AREAS], rotation=20, ha="right", fontsize=8)
    axes[0].set_title("Class × area")
    axes[0].legend(fontsize=8)
    xs = np.arange(3)
    for k, code in enumerate(codes):
        axes[1].bar(xs + (k - 1.5) * 0.2, split_class[code], 0.2, label=code, color=COLORS[k])
    axes[1].set_xticks(xs, ["train", "val", "test"])
    axes[1].set_title("Class × split")
    fig.tight_layout()
    fig.savefig(fig_dir / "class_distribution.png", dpi=130)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 3.4))
    for k, c in enumerate(classes):
        ax.hist(m[m.label == c["id"]].usa_wind_kt, bins=np.arange(15, 185, 5), color=COLORS[k], label=c["code"], alpha=0.85)
    for edge in (33.5, 63.5, 89.5):
        ax.axvline(edge, color="#334155", linestyle=":")
    ax.set_xlabel("IBTrACS USA_WIND (kt, 1-min)")
    ax.set_ylabel("images")
    ax.set_title("Label source: wind at the imaged fix, IMD thresholds (dotted)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(fig_dir / "wind_by_class.png", dpi=130)
    plt.close(fig)

    fig, axes = plt.subplots(len(classes), 6, figsize=(12, 2.3 * len(classes)))
    for r, c in enumerate(classes):
        pick = m[m.label == c["id"]].sample(6, random_state=int(cfg["project"]["seed"]))
        for ax, row in zip(axes[r], pick.itertuples()):
            ax.imshow(Image.open(ROOT / row.image_path), cmap="gray", vmin=0, vmax=255)
            ax.set_title(f"{c['code']} · {row.usa_wind_kt:.0f} kt\n{AREA_LABELS.get(row.area, row.area)} · {row.timestamp[:10]}", fontsize=6.5)
            ax.axis("off")
    fig.suptitle("Classification samples (north up, cold cloud bright)", fontsize=10)
    fig.tight_layout()
    fig.savefig(fig_dir / "samples_by_class.png", dpi=120)
    plt.close(fig)

    report = {
        "dataset_version": cfg["project"]["dataset_version"],
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources": cand_s["sources"],
        "label_rule": cand_s["label_rule"],
        "class_mapping": cand_s["class_mapping"],
        "candidate_funnel": cand_s["funnel"],
        "available_fixes_by_class": cand_s["available_by_class"],
        "label_source_check": {
            "ni_imd_3min_vs_usa_1min_same_class": cand_s["ni_imd_wind_vs_usa_wind"]["same_class"],
            "ni_usa_class_higher": cand_s["ni_imd_wind_vs_usa_wind"]["usa_class_higher"],
            "ni_usa_class_lower": cand_s["ni_imd_wind_vs_usa_wind"]["usa_class_lower"],
            "ni_fixes_compared": cand_s["ni_imd_wind_vs_usa_wind"]["fixes_with_both"],
            "dataset_a_wind_vs_usa_wind_same_class": cand_s["dataset_a_wind_vs_usa_wind_same_class"],
        },
        "cleaning": {k: build_s[k] for k in ("candidates", "accepted_clean_pool", "rejected", "rejected_by_reason", "exact_duplicates",
                                             "near_duplicate_pairs", "near_duplicate_label_conflicts")},
        "number_of_samples": int(len(m)),
        "image_formats": dict(fmt), "image_dimensions": dict(dims), "channels": {"modes": dict(modes), "note": "single-channel IR (L); replicated to 3 channels for the model"},
        "satellite_source": "NOAA GridSat-B1 v02r01 IRWIN CDR (~11 µm), 18°×18° crops, nearest 3-hourly slot (all fixes are exact slots)",
        "class_distribution": {c: int(v) for c, v in m.class_code.value_counts().reindex(codes).items()},
        "class_by_area": class_area.to_dict("index"),
        "class_by_basin": class_basin.to_dict("index"),
        "storms": int(m.storm_id.nunique()),
        "storms_by_class": {c: int(m[m.class_code == c].storm_id.nunique()) for c in codes},
        "images_per_storm": build_s["images_per_storm"],
        "usa_wind_kt_by_class": {c: {k: float(v) for k, v in wind.loc[c].items()} for c in codes},
        "missing_values": {c: int(n) for c, n in m.isna().sum().items() if n},
        "timestamps": [m.timestamp.min(), m.timestamp.max()],
        "splits": {"method": split_s["method"], "rows": split_s["rows"], "share": split_s["share"], "storms": split_s["storms"],
                   "groups": split_s["groups"], "largest_group": split_s["group_size"]["max"], "class_by_split": split_class.to_dict("index")},
        "leakage_check": {"status": leak["status"], **{k: v["violations"] for k, v in leak["checks"].items()}},
    }
    write_json(project_path(cfg, "reports", "classification_dataset_report.json"), report)

    lc = report["label_source_check"]
    md = [
        "# Classification dataset report — cls-v1.0",
        "",
        f"Created {report['created_at']}. Generated by `scripts/classification/write_dataset_report.py` from the pipeline outputs.",
        "",
        "## Sources and labels",
        "- No pre-labelled intensity image set exists in the project. Fixes come from **Dataset A** (PS-70 finalized IBTrACS metadata);",
        "  the label comes from IBTrACS `USA_WIND` (JTWC/NHC 1-minute sustained wind), the only wind reported on one basis in every basin.",
        f"- Rule: {report['label_rule']}.",
        "",
        table([[k, v["code"], v["name"], ", ".join(v["imd_categories"]), f"{v['wind_kt'][0]}–{v['wind_kt'][1] or '∞'} kt"] for k, v in report["class_mapping"].items()],
              ["id", "code", "name", "IMD categories", "USA_WIND"]),
        "",
        f"- **Label-source check (North Indian Ocean, {lc['ni_fixes_compared']:,} fixes with both winds):** IMD's own 3-minute wind gives the same class "
        f"{lc['ni_imd_3min_vs_usa_1min_same_class']:.1%} of the time; the 1-minute label is one class higher in {lc['ni_usa_class_higher']:.1%} "
        f"and lower in {lc['ni_usa_class_lower']:.1%}. Expect disagreement with official IMD bulletins near class boundaries.",
        "",
        "## Candidate funnel",
        table([[k, f"{v:,}"] for k, v in report["candidate_funnel"].items()], ["step", "fixes"]),
        "",
        "## Cleaning",
        f"- Candidates {report['cleaning']['candidates']:,}; accepted {report['cleaning']['accepted_clean_pool']:,}; rejected {report['cleaning']['rejected']} "
        f"({report['cleaning']['rejected_by_reason']}).",
        f"- Exact duplicates {report['cleaning']['exact_duplicates']}; near-duplicate pairs {report['cleaning']['near_duplicate_pairs']} "
        f"(label conflicts dropped: {report['cleaning']['near_duplicate_label_conflicts']}). Corrupted images: none (every file decoded).",
        "",
        "## Final dataset",
        f"- **{report['number_of_samples']:,} images**, {report['storms']:,} storms, {report['timestamps'][0]} → {report['timestamps'][1]}.",
        f"- Format {report['image_formats']}, dimensions {report['image_dimensions']}, channels {report['channels']['modes']} (IR, single channel).",
        f"- Satellite source: {report['satellite_source']}.",
        f"- Class distribution: {report['class_distribution']}; storms per class {report['storms_by_class']}.",
        f"- Missing values in the manifest: {report['missing_values'] or 'none'} (WMO wind is absent where the agency did not report one).",
        "",
        table([[AREA_LABELS[a]] + [int(class_area.loc[c, a]) for c in codes] for a in AREAS], ["area"] + codes),
        "",
        "## Split (storm/event grouped)",
        f"- {report['splits']['method']}. Rows {report['splits']['rows']}; storms {report['splits']['storms']}; groups {report['splits']['groups']:,} (largest {report['splits']['largest_group']}).",
        "",
        table([[s] + [int(split_class.loc[s, c]) for c in codes] for s in ["train", "val", "test"]], ["split"] + codes),
        "",
        f"- **Leakage check: {report['leakage_check']['status']}** — " + ", ".join(f"{k} {v}" for k, v in report["leakage_check"].items() if k != "status") + ".",
        "",
        "## Figures",
        "![classes](figures/class_distribution.png)",
        "![wind](figures/wind_by_class.png)",
        "![samples](figures/samples_by_class.png)",
    ]
    (project_path(cfg, "reports", "classification_dataset_report.md")).write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"Dataset report: {report['number_of_samples']} images, classes {report['class_distribution']}, leakage {leak['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
