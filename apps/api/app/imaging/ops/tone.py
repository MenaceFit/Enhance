"""Light and colour operations (white balance, exposure, contrast, vibrance, hue).

Every operation is designed to be *hue-preserving* unless explicitly asked:
exposure scales linear RGB by a luminance ratio (no per-channel clipping that
would shift hues), contrast works on L* only, vibrance only scales chroma.
"""

from __future__ import annotations

import cv2
import numpy as np

from app.imaging.color import LUMA_LINEAR, lab_to_lch, lch_to_lab, linear_to_srgb, srgb_to_linear


def white_balance_linear(lin: np.ndarray, gains: np.ndarray) -> np.ndarray:
    return lin * gains.reshape(1, 1, 3)


def _shoulder(y: np.ndarray, knee: float = 0.78) -> np.ndarray:
    """Identity below the knee, smooth exponential roll-off to 1 above (C1-continuous)."""
    span = 1.0 - knee
    over = np.maximum(y - knee, 0.0)
    return np.where(y <= knee, y, knee + span * (1.0 - np.exp(-over / span)))


def _y_to_lstar(y: np.ndarray) -> np.ndarray:
    return np.where(y > 0.008856, 116.0 * np.cbrt(y) - 16.0, 903.3 * y)


def _lstar_to_y(L: np.ndarray) -> np.ndarray:
    return np.where(L > 8.0, ((L + 16.0) / 116.0) ** 3, L / 903.3)


def exposure_linear(lin: np.ndarray, gain: float, shadow_lift: float) -> np.ndarray:
    """Apply an exposure gain with highlight roll-off and a gentle shadow lift.

    The new luminance is applied as a ratio to all channels (hue and saturation
    preserved); channels that would exceed 1 are compressed towards the grey
    axis instead of being clipped individually.
    """
    Y = np.maximum(lin @ LUMA_LINEAR, 1e-6)
    Y2 = _shoulder(Y * gain)
    if shadow_lift > 0:
        L = _y_to_lstar(Y2)
        # at most ~ +3.5 L* in the deepest shadows, nothing above L* 35: blacks stay black
        L = L + shadow_lift * 3.5 * np.clip(1.0 - L / 35.0, 0.0, 1.0) ** 2
        Y2 = _lstar_to_y(L)
    out = lin * (Y2 / Y)[..., None]
    peak = out.max(axis=2)
    over = peak > 1.0
    if np.any(over):
        y2 = Y2[over][:, None]
        t = (1.0 - y2) / np.maximum(peak[over][:, None] - y2, 1e-6)
        out[over] = y2 + (out[over] - y2) * np.clip(t, 0.0, 1.0)
    return np.clip(out, 0.0, 1.0)


def contrast_lab(lab: np.ndarray, strength: float, black_point_p: float) -> np.ndarray:
    """Black point, mild global S-curve and local contrast (CLAHE) on L* only."""
    if strength <= 0:
        return lab
    L = lab[..., 0]
    # black point: remove haze when the darkest tones are greyish
    bp = float(np.clip(black_point_p - 3.0, 0.0, 8.0)) * strength
    if bp > 0:
        L = (L - bp) * (100.0 / (100.0 - bp))
    # global S-curve around the median (amount ≤ 12 %)
    pivot = float(np.median(L))
    amount = 0.12 * strength
    x = (L - pivot) / 50.0
    L = pivot + 50.0 * (x + amount * x * (1 - np.abs(np.clip(x, -1, 1))))
    # local contrast
    L8 = np.clip(L * 2.55, 0, 255).astype(np.uint8)
    tiles = max(4, int(round(max(L.shape) / 220)))
    clahe = cv2.createCLAHE(clipLimit=1.6, tileGridSize=(tiles, tiles))
    Lc = clahe.apply(L8).astype(np.float32) / 2.55
    alpha = 0.32 * strength
    L = (1 - alpha) * L + alpha * Lc
    out = lab.copy()
    out[..., 0] = np.clip(L, 0.0, 100.0)
    return out


def vibrance_hue_lab(lab: np.ndarray, vibrance: float, hue_deg: float) -> np.ndarray:
    """Vibrance boosts low-chroma colours more than saturated ones; hue is a tiny rotation."""
    if vibrance == 0 and hue_deg == 0:
        return lab
    lch = lab_to_lch(lab)
    C = lch[..., 1]
    if vibrance:
        lch[..., 1] = C * (1.0 + vibrance * (1.0 - np.clip(C / 90.0, 0.0, 1.0)))
    if hue_deg:
        lch[..., 2] = (lch[..., 2] + hue_deg) % 360.0
    return lch_to_lab(lch)


def to_linear(img: np.ndarray) -> np.ndarray:
    return srgb_to_linear(img)


def from_linear(lin: np.ndarray) -> np.ndarray:
    return linear_to_srgb(lin)
