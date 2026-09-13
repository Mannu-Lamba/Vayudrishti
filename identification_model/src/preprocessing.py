"""Image preprocessing shared by dataset building, training and inference.

Rendering (dataset build) — GridSat-B1 IRWIN brightness temperature (K) → 8-bit grayscale with
cold cloud tops bright, using the same linear 180–310 K mapping as the original PS-70 downloader,
so the new PNGs remain comparable with the images collected earlier.

Model input (train / inference) — grayscale image → 3 identical channels → 224×224 → ImageNet
mean/std, because the backbone is initialised with ImageNet weights.
"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
from PIL import Image

IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)


# --------------------------------------------------------------------------- satellite rendering

def counts_to_bt(counts: np.ndarray, scale: float, offset: float, fill: int) -> np.ndarray:
    """GridSat packed Int16 counts → brightness temperature in Kelvin (NaN where missing)."""
    counts = np.asarray(counts)
    bt = counts.astype(np.float32) * scale + offset
    bt[counts == fill] = np.nan
    return bt


def missing_fraction(bt: np.ndarray) -> float:
    return float(np.mean(~np.isfinite(bt)))


def bt_to_uint8(bt: np.ndarray, bt_min: float, bt_max: float) -> np.ndarray:
    """Linear BT → 0..255, colder = brighter. Missing pixels become 0, as in the PS-70 downloader."""
    clipped = np.clip(bt, bt_min, bt_max)
    norm = (bt_max - clipped) / (bt_max - bt_min)
    norm = np.nan_to_num(norm, nan=0.0, posinf=0.0, neginf=0.0)
    return np.clip(np.round(norm * 255.0), 0, 255).astype(np.uint8)


def uint8_to_bt(img: np.ndarray, bt_min: float, bt_max: float) -> np.ndarray:
    """Inverse of bt_to_uint8 (approximate, 0.5 K steps)."""
    return bt_max - img.astype(np.float32) / 255.0 * (bt_max - bt_min)


def render_image(bt: np.ndarray, size: int, bt_min: float, bt_max: float) -> Image.Image:
    return Image.fromarray(bt_to_uint8(bt, bt_min, bt_max), mode="L").resize((size, size), Image.Resampling.BILINEAR)


def central_box(arr: np.ndarray, fraction: float) -> np.ndarray:
    h, w = arr.shape[:2]
    bh, bw = max(1, int(round(h * fraction))), max(1, int(round(w * fraction)))
    top, left = (h - bh) // 2, (w - bw) // 2
    return arr[top:top + bh, left:left + bw]


def cold_cloud_fraction(bt: np.ndarray, threshold_k: float, central_fraction: float | None = None) -> float:
    """Fraction of valid pixels colder than `threshold_k` (optionally inside the central box)."""
    region = central_box(bt, central_fraction) if central_fraction else bt
    valid = np.isfinite(region)
    if not valid.any():
        return float("nan")
    return float(np.mean(region[valid] < threshold_k))


# --------------------------------------------------------------------------- model input

def load_grayscale(source: str | Path | bytes | Image.Image | np.ndarray) -> Image.Image:
    """Accept a path, raw bytes, PIL image or array and return a single-channel ('L') image."""
    if isinstance(source, Image.Image):
        img = source
    elif isinstance(source, np.ndarray):
        img = Image.fromarray(source)
    elif isinstance(source, (bytes, bytearray)):
        img = Image.open(io.BytesIO(source))
    else:
        img = Image.open(source)
    img.load()
    if img.mode != "L":
        img = img.convert("L")
    return img


def to_model_rgb(img: Image.Image) -> Image.Image:
    """Replicate the IR channel into 3 channels for an ImageNet-pretrained backbone."""
    return img.convert("RGB")


def build_transforms(cfg: dict, train: bool):
    import torch
    from torchvision.transforms import InterpolationMode, v2

    size = int(cfg["train"]["input_size"])
    tail = [v2.ToDtype(torch.float32, scale=True), v2.Normalize(IMAGENET_MEAN, IMAGENET_STD)]
    if not train:
        return v2.Compose([v2.ToImage(), v2.Resize((size, size), antialias=True), *tail])
    aug = cfg["augmentation"]
    noise = float(aug.get("noise_std") or 0.0)
    return v2.Compose([
        v2.ToImage(),
        v2.RandomRotation(degrees=aug["rotation_deg"], interpolation=InterpolationMode.BILINEAR),
        v2.RandomResizedCrop(size, scale=tuple(aug["scale"]), ratio=(1.0, 1.0), antialias=True),
        v2.RandomHorizontalFlip(aug["hflip"]),
        v2.RandomVerticalFlip(aug["vflip"]),
        v2.ColorJitter(brightness=aug["brightness"], contrast=aug["contrast"]),
        v2.ToDtype(torch.float32, scale=True),
        *([v2.GaussianNoise(sigma=noise, clip=True)] if noise > 0 else []),  # controlled sensor-like noise
        v2.Normalize(IMAGENET_MEAN, IMAGENET_STD),
    ])
