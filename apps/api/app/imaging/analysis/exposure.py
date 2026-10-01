"""Exposure statistics and the suggested linear exposure gain."""

from __future__ import annotations

import cv2
import numpy as np

from app.imaging.color import LUMA_LINEAR, rgb_to_lab, srgb_to_linear, to_float
from app.imaging.types import ExposureStats

TARGET_HIGHLIGHT_Y = 0.80  # linear luminance for the 99th percentile (~L* 92)
MAX_GAIN = 2.2
MIN_GAIN = 0.75


def analyze_exposure(img: np.ndarray, garment_mask: np.ndarray, illuminant_gains=None) -> ExposureStats:
    f = to_float(img)
    if max(f.shape[:2]) > 512:
        s = 512 / max(f.shape[:2])
        f = cv2.resize(f, (round(f.shape[1] * s), round(f.shape[0] * s)), interpolation=cv2.INTER_AREA)
    m = cv2.resize(garment_mask, (f.shape[1], f.shape[0]), interpolation=cv2.INTER_AREA) > 127
    lin = srgb_to_linear(f)
    if illuminant_gains is not None:
        lin = np.clip(lin * np.asarray(illuminant_gains, np.float32), 0, 1)
    Y = lin @ LUMA_LINEAR
    L = rgb_to_lab(f)[..., 0]
    p01, p50, p99 = (float(np.percentile(L, q)) for q in (1, 50, 99))
    g50 = float(np.percentile(L[m], 50)) if m.any() else p50
    clipped_high = float((f.max(axis=2) > 0.995).mean())
    clipped_low = float((f.max(axis=2) < 0.01).mean())

    y99 = float(np.percentile(Y, 99.0))
    gain = TARGET_HIGHLIGHT_Y / max(y99, 1e-3)
    # Do not push a scene whose highlights are already bright; never darken much.
    gain = float(np.clip(gain, MIN_GAIN, MAX_GAIN))
    if clipped_high > 0.02:
        gain = min(gain, 1.0)
    return ExposureStats(
        p01=round(p01, 2), p50=round(p50, 2), p99=round(p99, 2), garment_p50=round(g50, 2),
        clipped_high=round(clipped_high, 4), clipped_low=round(clipped_low, 4), gain=round(gain, 3),
    )
