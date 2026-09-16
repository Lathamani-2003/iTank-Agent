from __future__ import annotations

from io import BytesIO
from typing import Union

import cv2
import numpy as np
from PIL import Image, ImageOps


ImageLike = Union[Image.Image, bytes, bytearray]


def load_image(data: ImageLike) -> Image.Image:
    if isinstance(data, Image.Image):
        return data.convert("RGB")
    return Image.open(BytesIO(bytes(data))).convert("RGB")


def rotate_image(image: Image.Image, orientation: str) -> Image.Image:
    value = (orientation or "").lower()
    if "90" in value and "counter" in value:
        return image.rotate(90, expand=True)
    if "90" in value and "clockwise" in value:
        return image.rotate(-90, expand=True)
    if "180" in value:
        return image.rotate(180, expand=True)
    return ImageOps.exif_transpose(image)


def resize_for_ai(image: Image.Image, max_side: int = 2200) -> Image.Image:
    image = image.convert("RGB")
    width, height = image.size
    scale = min(1.0, max_side / max(width, height))
    if scale >= 1.0:
        return image
    return image.resize(
        (max(1, int(width * scale)), max(1, int(height * scale))),
        Image.Resampling.LANCZOS,
    )


def enhance_sketch(image: Image.Image) -> Image.Image:
    """OpenCV enhancement that preserves topology while improving handwriting/lines."""
    rgb = np.array(image.convert("RGB"))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)

    # Correct uneven lighting without aggressively removing thin pipes.
    background = cv2.GaussianBlur(gray, (0, 0), 21)
    normalized = cv2.divide(gray, background, scale=255)

    # Local contrast + adaptive threshold keeps faint pen strokes visible.
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    contrast = clahe.apply(normalized)
    binary = cv2.adaptiveThreshold(
        contrast,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        41,
        11,
    )

    # Remove only isolated speckles; do not erode continuous connection lines.
    kernel = np.ones((2, 2), np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)

    return Image.fromarray(binary).convert("RGB")
