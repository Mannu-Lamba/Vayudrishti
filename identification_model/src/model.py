"""Model factory shared by both tasks. EfficientNet-B0 is the baseline; other torchvision backbones
plug in by name.

Identification: 0 = NO_CYCLONE, 1 = CYCLONE (linear head).
Classification: IMD intensity groups from configs/classification.yaml (FC → ReLU → Dropout → head).
The backbone ends in global average pooling in every supported architecture.
"""

from __future__ import annotations

import os
from pathlib import Path

import torch
from torch import nn

ROOT = Path(__file__).resolve().parents[1]
# Keep downloaded ImageNet weights inside the project instead of the (small) system drive.
os.environ.setdefault("TORCH_HOME", str(ROOT / ".cache" / "torch"))

SUPPORTED_MODELS = ("efficientnet_b0", "resnet50", "mobilenet_v3_large")


def make_head(in_features: int, num_classes: int, head: dict | None = None) -> nn.Module:
    """A linear classifier, or FC → ReLU → Dropout → classifier when `head.hidden` is set."""
    if not head or not head.get("hidden"):
        return nn.Linear(in_features, num_classes)
    hidden = int(head["hidden"])
    return nn.Sequential(
        nn.Linear(in_features, hidden),
        nn.ReLU(inplace=True),
        nn.Dropout(float(head.get("dropout", 0.0))),
        nn.Linear(hidden, num_classes),
    )


def build_model(name: str = "efficientnet_b0", num_classes: int = 2, pretrained: bool = True, head: dict | None = None) -> nn.Module:
    from torchvision import models

    if name == "efficientnet_b0":
        model = models.efficientnet_b0(weights=models.EfficientNet_B0_Weights.IMAGENET1K_V1 if pretrained else None)
        model.classifier[1] = make_head(model.classifier[1].in_features, num_classes, head)
    elif name == "resnet50":
        model = models.resnet50(weights=models.ResNet50_Weights.IMAGENET1K_V2 if pretrained else None)
        model.fc = make_head(model.fc.in_features, num_classes, head)
    elif name == "mobilenet_v3_large":
        model = models.mobilenet_v3_large(weights=models.MobileNet_V3_Large_Weights.IMAGENET1K_V2 if pretrained else None)
        model.classifier[3] = make_head(model.classifier[3].in_features, num_classes, head)
    else:
        raise ValueError(f"Unknown model '{name}'. Supported: {', '.join(SUPPORTED_MODELS)}")
    return model


def pretrained_weights_name(name: str) -> str:
    return {"efficientnet_b0": "IMAGENET1K_V1", "resnet50": "IMAGENET1K_V2", "mobilenet_v3_large": "IMAGENET1K_V2"}[name]


def load_checkpoint(path: str | Path, device: torch.device | str = "cpu") -> tuple[nn.Module, dict]:
    """Rebuild the architecture recorded in the checkpoint and load its weights (no download)."""
    ckpt = torch.load(path, map_location=device, weights_only=False)
    model = build_model(ckpt["model_name"], ckpt["num_classes"], pretrained=False, head=ckpt.get("head"))
    model.load_state_dict(ckpt["state_dict"])
    model.to(device).eval()
    return model, ckpt
