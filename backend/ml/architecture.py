"""Network definitions shared by the identification and classification models.

Mirrors identification_model/src/model.py (the training code) so a checkpoint's recorded
`model_name` + `head` rebuild exactly the trained network. Weights come only from the checkpoint
(`weights=None`), so nothing is downloaded at runtime.
"""

from __future__ import annotations

from pathlib import Path

import torch
from torch import nn

SUPPORTED_ARCHITECTURES = ("efficientnet_b0", "resnet50", "mobilenet_v3_large")


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


def build_network(name: str, num_classes: int, head: dict | None = None) -> nn.Module:
    """Backbone (ending in global average pooling) + task head."""
    from torchvision import models

    if name == "efficientnet_b0":
        model = models.efficientnet_b0(weights=None)
        model.classifier[1] = make_head(model.classifier[1].in_features, num_classes, head)
    elif name == "resnet50":
        model = models.resnet50(weights=None)
        model.fc = make_head(model.fc.in_features, num_classes, head)
    elif name == "mobilenet_v3_large":
        model = models.mobilenet_v3_large(weights=None)
        model.classifier[3] = make_head(model.classifier[3].in_features, num_classes, head)
    else:
        raise ValueError(f"Unsupported architecture '{name}'. Supported: {', '.join(SUPPORTED_ARCHITECTURES)}")
    return model


def load_network(checkpoint_path: Path, device: torch.device) -> tuple[nn.Module, dict]:
    """Rebuild the architecture recorded in a training checkpoint and load its weights in eval mode.

    `weights_only=True`: the checkpoint holds tensors plus plain Python metadata, so no arbitrary
    objects are unpickled.
    """
    ckpt = torch.load(checkpoint_path, map_location=device, weights_only=True)
    model = build_network(ckpt["model_name"], int(ckpt["num_classes"]), ckpt.get("head"))
    model.load_state_dict(ckpt["state_dict"], strict=True)
    model.to(device).eval()
    return model, ckpt


class ModelOutputError(RuntimeError):
    """The network returned something that cannot be a valid answer (NaN/inf, not a probability distribution).
    Services turn it into 500 INVALID_MODEL_OUTPUT; nothing is repaired or shown."""

    code = "INVALID_MODEL_OUTPUT"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def check_probabilities(probs: torch.Tensor, n_classes: int) -> None:
    """Softmax output for one image: `n_classes` finite values in [0, 1] that sum to 1."""
    if tuple(probs.shape) != (n_classes,):
        raise ModelOutputError(f"expected {n_classes} class probabilities, got shape {tuple(probs.shape)}")
    if not bool(torch.isfinite(probs).all()):
        raise ModelOutputError("the class probabilities contain NaN or infinity")
    if bool(((probs < 0) | (probs > 1)).any()) or abs(float(probs.sum()) - 1.0) > 1e-3:
        raise ModelOutputError("the class probabilities do not form a distribution")


@torch.inference_mode()
def self_check(model: nn.Module, input_shape: tuple[int, ...], expected_shape: tuple[int, ...], device: torch.device) -> None:
    """Load-time check: the rebuilt network accepts the training input shape and returns the expected, finite output
    shape. Raises ValueError, which the loaders report as MODEL_SELF_CHECK_FAILED (the model is never 'ready')."""
    out = model(torch.zeros(input_shape, device=device))
    if tuple(out.shape) != tuple(expected_shape):
        raise ValueError(f"output shape {tuple(out.shape)} for input {tuple(input_shape)}; expected {tuple(expected_shape)}")
    if not bool(torch.isfinite(out).all()):
        raise ValueError("non-finite output for a zero input")
