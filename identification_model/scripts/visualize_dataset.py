#!/usr/bin/env python3
"""STEPS 12 + 35 — Dataset figures, sample grids and the dataset v1.0 report.

Figures (reports/figures/): class, region, basin, positive intensity, negative difficulty,
images per storm, split distribution, cloud-metric distributions (shortcut check) and sample
grids of positives and easy / moderate / hard negatives. Also writes reports/dataset_v1_report.md.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from PIL import Image  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.utils import AREA_LABELS, ensure_dir, load_config, project_path, read_json  # noqa: E402

COLORS = {0: "#2563eb", 1: "#c2410c"}
NAMES = {0: "no_cyclone", 1: "cyclone"}
AREA_ORDER = ["arabian_sea", "bay_of_bengal", "south_indian_ocean", "western_pacific", "eastern_pacific", "southern_pacific"]


def savefig(fig, path: Path) -> None:
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def grouped_bars(ax, table: pd.DataFrame, title: str) -> None:
    x = np.arange(len(table.index))
    width = 0.8 / max(len(table.columns), 1)
    for k, col in enumerate(table.columns):
        bars = ax.bar(x + (k - (len(table.columns) - 1) / 2) * width, table[col], width, label=NAMES.get(col, str(col)),
                      color=COLORS.get(col) if col in COLORS else None)
        ax.bar_label(bars, fontsize=7)
    ax.set_xticks(x, [str(i) for i in table.index], rotation=20, ha="right", fontsize=8)
    ax.set_title(title, fontsize=10)
    ax.legend(fontsize=8)


def sample_grid(df: pd.DataFrame, caption, title: str, path: Path, n: int, seed: int, cols: int = 6) -> None:
    pick = df.sample(min(n, len(df)), random_state=seed) if len(df) else df
    rows = max(1, int(np.ceil(len(pick) / cols)))
    fig, axes = plt.subplots(rows, cols, figsize=(cols * 2.0, rows * 2.3))
    for ax in np.atleast_1d(axes).flat:
        ax.axis("off")
    for ax, r in zip(np.atleast_1d(axes).flat, pick.itertuples()):
        ax.imshow(Image.open(ROOT / r.image_path), cmap="gray", vmin=0, vmax=255)
        ax.set_title(caption(r), fontsize=6.5)
    fig.suptitle(title, fontsize=10)
    savefig(fig, path)


def main() -> int:
    cfg = load_config()
    seed = int(cfg["project"]["seed"])
    m = pd.read_csv(project_path(cfg, "metadata", "identification_dataset.csv"), keep_default_na=False, na_values=[""])
    m["area"] = m.subregion.fillna("").where(m.subregion.fillna("") != "", m.region)
    fig_dir = ensure_dir(project_path(cfg, "reports", "figures"))
    pos, neg = m[m.label == 1], m[m.label == 0]

    fig, ax = plt.subplots(figsize=(4, 3.2))
    counts = m.label.value_counts().sort_index()
    bars = ax.bar([NAMES[i] for i in counts.index], counts.values, color=[COLORS[i] for i in counts.index])
    ax.bar_label(bars)
    ax.set_title("1. Class distribution")
    savefig(fig, fig_dir / "01_class_distribution.png")

    fig, ax = plt.subplots(figsize=(8, 3.6))
    grouped_bars(ax, pd.crosstab(m.area, m.label).reindex(AREA_ORDER).fillna(0).astype(int), "2. Region / subregion distribution")
    savefig(fig, fig_dir / "02_region_distribution.png")

    fig, ax = plt.subplots(figsize=(6, 3.4))
    grouped_bars(ax, pd.crosstab(m.basin, m.label), "3. IBTrACS basin distribution")
    savefig(fig, fig_dir / "03_basin_distribution.png")

    fig, ax = plt.subplots(figsize=(8, 3.6))
    grouped_bars(ax, pd.crosstab(pos.area, pos.intensity).reindex(AREA_ORDER).fillna(0).astype(int)[["weak", "medium", "strong"]],
                 "4. Positive intensity (storm lifetime max wind) by area")
    savefig(fig, fig_dir / "04_positive_intensity.png")

    fig, ax = plt.subplots(figsize=(6, 3.4))
    grouped_bars(ax, pd.crosstab(neg.difficulty, neg.area).reindex(["easy", "moderate", "hard"]), "5. Negative difficulty by subregion")
    savefig(fig, fig_dir / "05_negative_difficulty.png")

    fig, ax = plt.subplots(figsize=(6, 3.4))
    per_storm = pos.groupby("storm_id").size()
    ax.hist(per_storm, bins=np.arange(1, per_storm.max() + 2) - 0.5, color=COLORS[1])
    ax.set_xlabel("images per storm")
    ax.set_ylabel("storms")
    ax.set_title(f"6. Images per storm ({per_storm.size} storms, median {per_storm.median():.0f}, max {per_storm.max()})", fontsize=10)
    savefig(fig, fig_dir / "06_images_per_storm.png")

    if "split" in m.columns:
        fig, axes = plt.subplots(1, 2, figsize=(11, 3.6))
        grouped_bars(axes[0], pd.crosstab(m.split, m.label).reindex(["train", "val", "test"]), "7a. Split × class")
        grouped_bars(axes[1], pd.crosstab(m.area, m.split).reindex(AREA_ORDER)[["train", "val", "test"]], "7b. Area × split")
        savefig(fig, fig_dir / "07_split_distribution.png")

    fig, axes = plt.subplots(1, 3, figsize=(12, 3.4))
    for ax, col, title in zip(axes, ["cold_cloud_fraction", "central_cold_cloud_fraction", "bt_mean_k"],
                              ["whole-crop cold cloud (<235 K)", "central-box cold cloud (<235 K)", "mean BT (K)"]):
        groups = [pos[col]] + [neg[neg.difficulty == d][col] for d in ("easy", "moderate", "hard")]
        ax.boxplot(groups, tick_labels=["cyclone", "neg easy", "neg moderate", "neg hard"], showfliers=False)
        ax.set_title(title, fontsize=9)
        ax.tick_params(axis="x", labelsize=7)
    fig.suptitle("8. Cloud metrics: hard negatives are as cloudy as cyclone scenes (shortcut check)", fontsize=10)
    savefig(fig, fig_dir / "08_cloud_metrics.png")

    pos_caption = lambda r: f"{r.image_id} {AREA_LABELS.get(r.area, r.area)}\n{r.intensity} · {r.timestamp[:10]}"  # noqa: E731
    neg_caption = lambda r: f"{r.image_id} {AREA_LABELS.get(r.area, r.area)}\n{r.timestamp[:10]} · cold {r.cold_cloud_fraction:.0%}"  # noqa: E731
    for level in ("weak", "medium", "strong"):
        sample_grid(pos[pos.intensity == level], pos_caption, f"Positive examples — {level} storms", fig_dir / f"samples_positive_{level}.png", 18, seed)
    for level in ("easy", "moderate", "hard"):
        sample_grid(neg[neg.difficulty == level], neg_caption, f"Negative examples — {level}", fig_dir / f"samples_negative_{level}.png", 18, seed)

    write_dataset_report(cfg, m)
    print(f"Figures written to {fig_dir}")
    return 0


def write_dataset_report(cfg: dict, m: pd.DataFrame) -> None:
    aud = project_path(cfg, "reports", "audit")
    sel = read_json(aud / "selection_summary.json")
    cand = read_json(aud / "candidates_summary.json")
    split = read_json(aud / "split_summary.json") if (aud / "split_summary.json").exists() else None
    leak_path = project_path(cfg, "reports", "leakage_check.json")
    leak = read_json(leak_path) if leak_path.exists() else {"status": "not run"}
    im, g = cfg["imagery"], cfg["gridsat"]
    pos, neg = m[m.label == 1], m[m.label == 0]
    area_tab = pd.crosstab(m.area, m.label).reindex(AREA_ORDER).fillna(0).astype(int)
    L = [
        f"# Dataset {cfg['project']['dataset_version']} — VayuDrishti cyclone identification",
        "",
        f"- **Date created:** {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC",
        f"- **Samples:** {len(m)} = **{len(pos)} cyclone** (label 1) + **{len(neg)} no_cyclone** (label 0). No image is duplicated.",
        f"- **Random seed:** {cfg['project']['seed']} (selection and splits)",
        "- **Manifest:** `data/metadata/identification_dataset.csv`; splits in `data/splits/`.",
        "",
        "## Source datasets",
        "- **Dataset A (positives):** PS-70 finalized IBTrACS v04r01 metadata (139,829 fixes, 2,299 storms, 2000–2026) and the",
        "  PS-70 positive candidate workbook (2,000 fixes from 721 storms) derived from it.",
        "- **Dataset B (negatives):** PS-70 GridSat-B1 non-cyclone pool (4,615 North Indian Ocean samples, 2000–2025, rule:",
        "  ≥ 10° from every IBTrACS DS/TS/MX centre) and its 2,000-sample selection.",
        f"- **Imagery (both classes):** NOAA GridSat-B1 v02r01 IRWIN CDR (~11 µm), nearest 3-hourly slot, {2 * g['half_width_deg']:.0f}°×{2 * g['half_width_deg']:.0f}° crop",
        "  centred on the sample position, fetched by OPeNDAP subset. One source and one code path for both classes.",
        "",
        "## Preprocessing",
        f"- Brightness temperature clipped to {im['bt_min_k']:.0f}–{im['bt_max_k']:.0f} K and mapped linearly to 8-bit (cold = bright), as in the",
        f"  original PS-70 downloader; 259×259 crop resized to {im['png_size']}×{im['png_size']} PNG, north up.",
        f"- Crops with > {im['max_missing_fraction']:.0%} missing pixels, constant frames, failed downloads and duplicates are rejected",
        "  (`reports/cleaning_report.md`).",
        "",
        "## Sampling strategy",
        f"- Positives: only IBTrACS nature TS fixes (non-tropical DS/ET/SS/MX/NR removed: "
        f"{sum(r['n'] for r in cand['rejections'] if r['label'] == 1)}); {cand['positive_reserve_added']} reserve TS fixes drawn from dataset A.",
        "  Stratified by UI subregion × storm intensity (target equal areas, 35/35/30 % weak/medium/strong); shortfalls are",
        "  redistributed to the least-filled strata. PS-70 candidates are preferred, picked round-robin across storms.",
        f"- Positive sources: {sel['positive_sources']}; storms: {sel['positive_storms']}.",
        f"- Negatives: difficulty by a documented image rule — easy: whole-crop cold cloud (< {im['cold_cloud_bt_k']:.0f} K) below "
        f"{cfg['selection']['easy_max_cold_fraction']:.0%}; hard: central 9°×9° cold-cloud fraction ≥ {sel['hard_negative_central_cold_fraction_threshold']:.3f} "
        f"(P{cfg['selection']['hard_reference_percentile']} of the positives); moderate: the rest.",
        f"  Clean pool difficulty: {sel['negative_pool_difficulty']}. Targets {cfg['selection']['negative_difficulty_targets']}, 50/50 Arabian Sea / Bay of Bengal,",
        f"  round-robin over years. {sel['negative_from_ps70_selected_2000']} of the chosen negatives were also in the PS-70 2,000 selection.",
        "",
        "## Distribution",
        "",
        "| area | cyclone | no_cyclone |",
        "|---|---|---|",
    ]
    L += [f"| {AREA_LABELS.get(a, a)} | {row.get(1, 0)} | {row.get(0, 0)} |" for a, row in area_tab.iterrows()]
    L += [
        "",
        f"- Positive intensity: {pos.intensity.value_counts().to_dict()}",
        f"- Negative difficulty: {neg.difficulty.value_counts().to_dict()}",
        f"- Basins: {m.groupby(['basin', 'label']).size().unstack(fill_value=0).to_dict('index')}",
        "",
        "## Split strategy",
    ]
    if split:
        L += [
            f"- {split['method']}.",
            f"- Groups: {split['groups']} (storm id, overlapping crops within {cfg['splits']['group_overlap_hours']} h, near-duplicates); "
            f"largest group {split['group_size']['max']} samples ({split['group_size']['largest_share']:.1%}).",
            f"- Rows: {split['rows']} (share {split['share']}); cyclone share {split['cyclone_share']}.",
            f"- Positive storms per split: {split['storms']}; difficulty per split: {split['difficulty']}.",
        ]
    L += [
        f"- **Leakage check:** {leak['status']} (`reports/leakage_check.json`).",
        "",
        "## Known limitations",
        "- Negatives exist only for the North Indian Ocean. In other basins only recall (detection rate) can be measured.",
        "- Negative crops are centred on an integer-degree grid that includes land; positives are over ocean. Coastlines and",
        "  land surface temperature can act as a geographic cue.",
        "- Intensity is the storm's lifetime category, not the intensity at the imaged fix.",
        "- Labels come from IBTrACS positions and the PS-70 negative rule; `human_verified` is REVIEW_REQUIRED for all rows.",
        "",
        "## Figures",
        "![class](figures/01_class_distribution.png) ![region](figures/02_region_distribution.png)",
        "![basin](figures/03_basin_distribution.png) ![intensity](figures/04_positive_intensity.png)",
        "![difficulty](figures/05_negative_difficulty.png) ![per storm](figures/06_images_per_storm.png)",
        "![split](figures/07_split_distribution.png) ![cloud](figures/08_cloud_metrics.png)",
        "",
        "Sample grids: `figures/samples_positive_{weak,medium,strong}.png`, `figures/samples_negative_{easy,moderate,hard}.png`.",
    ]
    (project_path(cfg, "reports", "dataset_v1_report.md")).write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
