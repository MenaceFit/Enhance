"""Sharpening and classical (non-generative) upscaling."""

from __future__ import annotations

import cv2
import numpy as np

from app.imaging.color import lab_to_rgb, rgb_to_lab


def sharpen(img: np.ndarray, amount: float, *, radius: float | None = None) -> np.ndarray:
    """Unsharp mask on L* with a noise threshold and halo (overshoot) control."""
    if amount <= 0:
        return img
    h, w = img.shape[:2]
    sigma = radius or max(0.7, 1.0 * (max(h, w) / 1600) ** 0.5)
    lab = rgb_to_lab(img)
    L = lab[..., 0]
    blur = cv2.GaussianBlur(L, (0, 0), sigma)
    detail = L - blur
    # soft threshold: ignore tiny variations (noise), keep real edges
    thr = 0.8
    detail = np.sign(detail) * np.maximum(np.abs(detail) - thr, 0.0)
    sharp = L + amount * 1.2 * detail
    # limit overshoot to the local min/max (+ small tolerance) → no halos
    k = np.ones((3, 3), np.uint8)
    lo = cv2.erode(L, k) - 2.0
    hi = cv2.dilate(L, k) + 2.0
    lab[..., 0] = np.clip(sharp, lo, hi)
    return lab_to_rgb(lab)


def classical_upscale(img: np.ndarray, width: int, height: int) -> np.ndarray:
    """Lanczos upscaling + edge-aware detail recovery. Invents no structure."""
    up = cv2.resize(img, (width, height), interpolation=cv2.INTER_LANCZOS4)
    return np.clip(sharpen(np.clip(up, 0, 1), 0.35, radius=1.2), 0, 1)
