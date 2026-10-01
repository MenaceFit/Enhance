"""Color Fidelity Score — "🎨 Fidélité couleur : 98 %".

The reference is the original photo with only the *light* corrected (white
balance + exposure): that is the best estimate of the article's real colour.
Everything else the pipeline does (contrast, vibrance, hue, wrinkle
smoothing, background spill...) must leave the garment's colour unchanged.
We measure CIEDE2000 between reference and output on garment pixels, with
lightness down-weighted (kL = 2) because tonal adjustments are legitimate.
"""

from __future__ import annotations

import cv2
import numpy as np

from app.imaging.color import delta_e_2000, rgb_to_hex, rgb_to_lab, to_float
from app.imaging.types import FidelityReport

PASS_SCORE = 90
SCALE = 6.0  # score = 100 - SCALE * mean ΔE00(kL=2)


def _prep(img: np.ndarray, size: int = 384) -> np.ndarray:
    f = to_float(img)
    s = size / max(f.shape[:2])
    if s < 1:
        f = cv2.resize(f, (round(f.shape[1] * s), round(f.shape[0] * s)), interpolation=cv2.INTER_AREA)
    return f


def color_fidelity(reference: np.ndarray, output: np.ndarray, garment_mask: np.ndarray) -> FidelityReport:
    ref = _prep(reference)
    out = cv2.resize(_prep(output), (ref.shape[1], ref.shape[0]), interpolation=cv2.INTER_AREA)
    m = cv2.resize(garment_mask, (ref.shape[1], ref.shape[0]), interpolation=cv2.INTER_AREA)
    m = m.astype(np.float32) / 255.0 if m.dtype == np.uint8 else m
    core = cv2.erode((m > 0.5).astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    if core.sum() < 50:
        core = m > 0.5
    if core.sum() < 20:
        return FidelityReport(100, 0.0, 0.0, 1.0, "#000000", "#000000", True, None)

    # compare locally averaged colours: per-pixel noise/sharpening is not a colour change
    ref_b = cv2.GaussianBlur(ref, (0, 0), 1.5)
    out_b = cv2.GaussianBlur(out, (0, 0), 1.5)
    lab_r = rgb_to_lab(ref_b)[core]
    lab_o = rgb_to_lab(out_b)[core]
    de = delta_e_2000(lab_r, lab_o, kL=2.0)
    mean_de = float(np.mean(de))
    p90 = float(np.percentile(de, 90))

    # dominant colour shift (median a*, b*)
    a_r, b_r = float(np.median(lab_r[:, 1])), float(np.median(lab_r[:, 2]))
    a_o, b_o = float(np.median(lab_o[:, 1])), float(np.median(lab_o[:, 2]))
    c_r, c_o = np.hypot(a_r, b_r), np.hypot(a_o, b_o)
    hue_shift = 0.0
    if c_r > 6 and c_o > 6:
        hue_shift = float((np.degrees(np.arctan2(b_o, a_o) - np.arctan2(b_r, a_r)) + 180) % 360 - 180)
    chroma_ratio = float(c_o / c_r) if c_r > 1 else 1.0

    score = 100.0 - SCALE * mean_de - 1.5 * max(0.0, p90 - 4.0)
    score = int(round(float(np.clip(score, 0, 100))))
    passed = score >= PASS_SCORE and abs(hue_shift) <= 6 and 0.8 <= chroma_ratio <= 1.2
    warning = None
    if not passed:
        warning = "La correction couleur semble trop importante."
    return FidelityReport(
        score=score,
        mean_delta_e=round(mean_de, 3),
        hue_shift_deg=round(hue_shift, 2),
        chroma_ratio=round(chroma_ratio, 3),
        dominant_before=rgb_to_hex(np.median(ref_b[core], axis=0)),
        dominant_after=rgb_to_hex(np.median(out_b[core], axis=0)),
        passed=passed,
        warning=warning,
    )
