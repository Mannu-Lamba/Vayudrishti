"""Upload validation and model-input preprocessing shared by both models.

The transform is the evaluation transform used in training (identification_model/src/preprocessing.py):
decode → single-channel IR ('L') → 3 identical channels → resize to the model input (bilinear,
antialiased) → [0, 1] → ImageNet mean/std. No augmentation is ever applied at inference.
"""

from __future__ import annotations

import io

import numpy as np
import torch
from PIL import Image, UnidentifiedImageError

ALLOWED_FORMATS = {"PNG", "JPEG", "TIFF", "BMP", "WEBP"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MIN_SIDE_PX = 64
MAX_SIDE_PX = 8192


class ImageValidationError(ValueError):
    """A client-side problem with the uploaded file (maps to a 4xx response)."""

    def __init__(self, code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def decode_image(data: bytes | None) -> Image.Image:
    """Validate and fully decode an uploaded image (truncated files fail here, not in the model)."""
    if data is None:
        raise ImageValidationError("NO_FILE", "No image was uploaded. Send the satellite image as multipart field 'file'.")
    if not data:
        raise ImageValidationError("EMPTY_FILE", "The uploaded file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ImageValidationError("FILE_TOO_LARGE", f"The image is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.", 413)
    try:
        img = Image.open(io.BytesIO(data))
        fmt = img.format
        img.load()
    except UnidentifiedImageError:
        raise ImageValidationError("INVALID_FILE_TYPE", "The file is not a supported image (PNG, JPEG, TIFF, BMP or WebP).", 415) from None
    except Image.DecompressionBombError:
        raise ImageValidationError("UNSUPPORTED_DIMENSIONS", "The image has too many pixels.") from None
    except (OSError, SyntaxError, ValueError):
        raise ImageValidationError("CORRUPTED_IMAGE", "The image file is corrupted and could not be decoded.") from None
    if fmt not in ALLOWED_FORMATS:
        raise ImageValidationError("INVALID_FILE_TYPE", f"Unsupported image format '{fmt}'. Use PNG, JPEG, TIFF, BMP or WebP.", 415)
    width, height = img.size
    if min(width, height) < MIN_SIDE_PX or max(width, height) > MAX_SIDE_PX:
        raise ImageValidationError(
            "UNSUPPORTED_DIMENSIONS", f"Image sides must be between {MIN_SIDE_PX} and {MAX_SIDE_PX} px (got {width}×{height}).")
    return img


COLOUR_PIXEL_SATURATION = 0.15   # a pixel counts as "coloured" above this HSV saturation
COLOUR_FRACTION_LIMIT = 0.05     # more than 5 % coloured pixels → not a single-channel IR scene
MAX_ASPECT_RATIO = 1.25
MIN_DETAIL_PX = 128
MIN_CONTRAST = 0.05


def describe_image(img: Image.Image) -> dict:
    """What the models are about to see, and how it differs from their training domain: GridSat-B1 infrared (~11 µm),
    single channel with cold cloud tops bright, a square ~18°×18° scene centred on the system, 256 px. Descriptive
    only — it never changes the prediction; the warnings tell the reader how far to trust it."""
    width, height = img.size
    small = img.convert("RGB")
    small.thumbnail((256, 256))
    rgb = np.asarray(small, dtype=np.float32) / 255.0
    high, low = rgb.max(axis=2), rgb.min(axis=2)
    saturation = np.where(high > 0, (high - low) / np.maximum(high, 1e-6), 0.0)
    colour_fraction = float((saturation > COLOUR_PIXEL_SATURATION).mean())
    grey = np.asarray(small.convert("L"), dtype=np.float32) / 255.0
    contrast = float(grey.std())
    aspect = max(width, height) / min(width, height)
    warnings = []
    if colour_fraction > COLOUR_FRACTION_LIMIT:
        warnings.append({"code": "COLOUR_IMAGE", "message": (
            f"{colour_fraction:.0%} of the pixels are coloured. The models were trained on single-channel infrared (GridSat-B1, "
            "~11 µm), where brightness means cold cloud tops. Colour-enhanced, visible, water-vapour or true-colour images are "
            "converted to grey, which is not the same signal, so treat the result with caution.")})
    if aspect > MAX_ASPECT_RATIO:
        warnings.append({"code": "NOT_SQUARE", "message": (
            f"The image is {width}×{height}. The models expect a square scene centred on the system (about 18°×18°); "
            "it is stretched to 224×224, which distorts the cloud pattern.")})
    if min(width, height) < MIN_DETAIL_PX:
        warnings.append({"code": "LOW_RESOLUTION", "message": f"The shorter side is only {min(width, height)} px; training scenes were 256 px."})
    if contrast < MIN_CONTRAST:
        warnings.append({"code": "LOW_CONTRAST", "message": "The image has almost no contrast (blank, overexposed or heavily compressed)."})
    return {
        "format": img.format, "width": width, "height": height, "mode": img.mode,
        "colour_fraction": round(colour_fraction, 4), "contrast": round(contrast, 4),
        "in_training_domain": not warnings, "warnings": warnings,
    }


def input_size(model_config: dict) -> tuple[int, int]:
    size = model_config.get("preprocessing", {}).get("resize") or model_config["input_size"]
    return int(size[0]), int(size[1])


def to_model_tensor(img: Image.Image, model_config: dict) -> torch.Tensor:
    """PIL image → normalised [1, 3, H, W] float tensor, exactly as in training evaluation."""
    from torchvision.transforms import v2

    norm = model_config["normalization"]
    transform = v2.Compose([
        v2.ToImage(),
        v2.Resize(input_size(model_config), antialias=True),
        v2.ToDtype(torch.float32, scale=True),
        v2.Normalize(norm["mean"], norm["std"]),
    ])
    rgb = img.convert("L").convert("RGB")  # IR is single-channel; the ImageNet backbone expects 3 channels
    return transform(rgb).unsqueeze(0)
