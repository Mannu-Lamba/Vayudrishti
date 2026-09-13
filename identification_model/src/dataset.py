"""PyTorch Dataset / DataLoaders over a task's split CSVs (binary identification or multiclass)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import torch
from PIL import Image
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler

from src.preprocessing import build_transforms, load_grayscale, to_model_rgb
from src.utils import ROOT, split_path

SPLITS = ("train", "val", "test")


class CycloneDataset(Dataset):
    """Grayscale IR PNGs → model tensors. Images are small (256×256×1), so they are cached in memory."""

    def __init__(self, frame: pd.DataFrame, transform, root: Path = ROOT):
        self.frame = frame.reset_index(drop=True)
        self.labels = self.frame.label.astype(int).to_numpy()
        self.images = [np.asarray(load_grayscale(root / p), dtype=np.uint8) for p in self.frame.image_path]
        self.transform = transform

    def __len__(self) -> int:
        return len(self.frame)

    def __getitem__(self, idx: int):
        img = to_model_rgb(Image.fromarray(self.images[idx], mode="L"))
        return self.transform(img), int(self.labels[idx]), idx


def read_split(cfg: dict, split: str) -> pd.DataFrame:
    return pd.read_csv(split_path(cfg, split), keep_default_na=False, na_values=[""])


def class_balance(labels: np.ndarray, cfg: dict) -> tuple[str, torch.Tensor | None, WeightedRandomSampler | None]:
    """Resolve `train.class_balance`. 'auto' → none when every class share is within the tolerance of
    1/num_classes, else class weights. Class weights and a weighted sampler are never combined."""
    mode = cfg["train"]["class_balance"]
    n_classes = int(cfg["train"]["num_classes"])
    counts = np.bincount(labels, minlength=n_classes).astype(float)
    if mode == "auto":
        shares = counts / counts.sum()
        balanced = np.all(np.abs(shares - 1.0 / n_classes) <= cfg["train"]["class_balance_tolerance"])
        mode = "none" if balanced else "class_weights"
    if mode == "class_weights":
        return mode, torch.tensor(counts.sum() / (n_classes * np.maximum(counts, 1)), dtype=torch.float32), None
    if mode == "weighted_sampler":
        weights = (1.0 / np.maximum(counts, 1))[labels]
        return mode, None, WeightedRandomSampler(torch.as_tensor(weights, dtype=torch.double), len(labels), replacement=True)
    return "none", None, None


def _seed_worker(worker_id: int) -> None:
    seed = torch.initial_seed() % 2**32
    np.random.seed(seed)
    import random

    random.seed(seed)


def make_loaders(cfg: dict, splits=SPLITS) -> tuple[dict, dict, dict]:
    tr = cfg["train"]
    datasets, loaders = {}, {}
    balance = {"strategy": "none", "class_weights": None}
    for split in splits:
        ds = CycloneDataset(read_split(cfg, split), build_transforms(cfg, train=split == "train"))
        datasets[split] = ds
        sampler = None
        if split == "train":
            strategy, weights, sampler = class_balance(ds.labels, cfg)
            balance = {"strategy": strategy, "class_weights": weights}
        gen = torch.Generator()
        gen.manual_seed(int(cfg["project"]["seed"]))
        workers = int(tr["num_workers"])
        loaders[split] = DataLoader(
            ds, batch_size=int(tr["batch_size"]), shuffle=(split == "train" and sampler is None), sampler=sampler,
            num_workers=workers, persistent_workers=workers > 0, pin_memory=torch.cuda.is_available(),
            worker_init_fn=_seed_worker, generator=gen, drop_last=False,
        )
    return datasets, loaders, balance
