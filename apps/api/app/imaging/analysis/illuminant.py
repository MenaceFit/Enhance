"""White-balance estimation that never looks at the garment.

Classic gray-world fails badly on clothing photos: a red T-shirt filling the
frame would be "corrected" towards cyan, falsifying the article. We estimate
the illuminant from the *background* only (sheets, walls and floors are close
to neutral far more often than garments are), and we down-weight casts that are
implausible for a real light source (real illuminants vary mostly along the
blue–yellow axis, with some green for fluorescent tubes).
"""

from __future__ import annotations

import cv2
import numpy as np

from app.imaging.color import LUMA_LINEAR, rgb_to_lab, srgb_to_linear, to_float
from app.imaging.types import IlluminantEstimate

MAX_GAIN_RATIO = 1.45  # cap between strongest and weakest channel gain


def _cast_label(a: float, b: float) -> str | None:
    if np.hypot(a, b) < 2.5:
        return None
    hue = np.degrees(np.arctan2(b, a)) % 360
    if 40 <= hue < 120:
        return "lumière jaune"
    if 120 <= hue < 200:
        return "lumière verte"
    if 200 <= hue < 300:
        return "lumière bleue"
    return "lumière rosée"


def _plausibility(a: float, b: float) -> float:
    c = float(np.hypot(a, b)) + 1e-6
    along_by = abs(b) / c
    p = 0.35 + 0.65 * along_by
    if a < 0:  # greenish: fluorescent/LED, plausible
        p = max(p, 0.75)
    return float(np.clip(p, 0.0, 1.0))


def _gains_from_rgb(mean_lin: np.ndarray) -> np.ndarray:
    mean_lin = np.maximum(mean_lin, 1e-4)
    gray = float(mean_lin @ LUMA_LINEAR)
    gains = gray / mean_lin
    # normalise so luminance is preserved
    gains = gains / float(gains @ LUMA_LINEAR)
    ratio = gains.max() / gains.min()
    if ratio > MAX_GAIN_RATIO:
        # compress towards 1 in log space
        lg = np.log(gains)
        lg *= np.log(MAX_GAIN_RATIO) / np.log(ratio)
        gains = np.exp(lg)
        gains = gains / float(gains @ LUMA_LINEAR)
    return gains


def estimate_illuminant(img: np.ndarray, garment_mask: np.ndarray) -> IlluminantEstimate:
    f = to_float(img)
    small_h = 384
    scale = small_h / max(f.shape[:2])
    if scale < 1:
        f = cv2.resize(f, (round(f.shape[1] * scale), round(f.shape[0] * scale)), interpolation=cv2.INTER_AREA)
        m = cv2.resize(garment_mask, (f.shape[1], f.shape[0]), interpolation=cv2.INTER_AREA)
    else:
        m = garment_mask
    # Background = far from the garment (avoid colour spill and contact shadows).
    garment = (m > 64).astype(np.uint8)
    grow = max(3, int(0.03 * max(f.shape[:2])))
    near = cv2.dilate(garment, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * grow + 1, 2 * grow + 1)))
    bg = near == 0

    lin = srgb_to_linear(f)
    lab = rgb_to_lab(f)
    L = lab[..., 0]
    valid = bg & (L > 18) & (f.max(axis=2) < 0.985)

    source = "background"
    if valid.mean() < 0.06:
        # Close-up or busy frame: fall back to bright, low-chroma pixels anywhere outside the garment,
        # then to a shades-of-gray estimate with low confidence.
        valid = (garment == 0) & (L > 30) & (f.max(axis=2) < 0.985)
        source = "neutral-pixels"
        if valid.mean() < 0.02:
            p = 6.0
            mean_lin = np.power(np.mean(np.power(np.maximum(lin, 1e-6), p), axis=(0, 1)), 1 / p)
            gains = _gains_from_rgb(mean_lin)
            return IlluminantEstimate(
                gains=tuple(float(g) for g in gains), cast_label=None, cast_strength=0.0, confidence=0.15,
                source="shades-of-gray",
            )

    a = lab[..., 1][valid]
    b = lab[..., 2][valid]
    # Robust central estimate: trim the most chromatic 20% (objects lying around, wood grain...).
    chroma = np.hypot(a, b)
    keep = chroma <= np.percentile(chroma, 80)
    a_med, b_med = float(np.median(a[keep])), float(np.median(b[keep]))
    spread = float(np.sqrt(np.var(a[keep]) + np.var(b[keep])))
    cast_strength = float(np.hypot(a_med, b_med))

    sel = np.zeros_like(valid)
    sel[valid] = keep
    mean_lin = np.median(lin[sel], axis=0) if sel.sum() > 30 else lin[valid].mean(axis=0)

    uniformity = float(np.clip(1.0 - spread / 14.0, 0.15, 1.0))
    plaus = _plausibility(a_med, b_med)
    # very strong "casts" are usually coloured surfaces, not light
    strength_trust = float(np.clip(1.15 - max(0.0, cast_strength - 14.0) / 25.0, 0.3, 1.0))
    confidence = uniformity * plaus * strength_trust * (1.0 if source == "background" else 0.6)
    if cast_strength < 1.5:
        confidence *= cast_strength / 1.5

    gains = _gains_from_rgb(mean_lin)
    return IlluminantEstimate(
        gains=tuple(float(g) for g in gains),
        cast_label=_cast_label(a_med, b_med),
        cast_strength=round(cast_strength, 2),
        confidence=round(float(np.clip(confidence, 0.0, 1.0)), 3),
        source=source,
    )


def effective_gains(est: IlluminantEstimate, strength: float) -> np.ndarray:
    """Blend measured gains towards identity by confidence × user strength."""
    k = float(np.clip(est.confidence * strength, 0.0, 1.0))
    g = np.exp(np.log(np.asarray(est.gains, np.float32)) * k)
    return (g / float(g @ LUMA_LINEAR)).astype(np.float32)
