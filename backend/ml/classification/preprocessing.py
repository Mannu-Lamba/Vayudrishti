"""Classification preprocessing — identical to the training evaluation transform (see ml/imaging.py)."""

from __future__ import annotations

import torch
from PIL import Image

from ml.imaging import decode_image, to_model_tensor


class PreprocessingError(RuntimeError):
    pass


def preprocess_image(image: Image.Image | bytes, model_config: dict) -> torch.Tensor:
    """Validated image (or raw upload bytes) → [1, 3, H, W] tensor for the classification network."""
    img = image if isinstance(image, Image.Image) else decode_image(image)
    try:
        return to_model_tensor(img, model_config)
    except Exception as exc:  # a decoded image that still cannot be transformed is a server-side failure
        raise PreprocessingError(str(exc)) from exc
