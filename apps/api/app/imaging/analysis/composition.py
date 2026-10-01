"""Composition analysis: tilt, framing and fill of the garment.

Tilt is measured by searching the rotation that makes the silhouette most
mirror-symmetric (laid-flat garments are symmetric around their vertical
axis). Asymmetric items (a single shoe, a folded garment) fall back to the
minimum-area rectangle with a low confidence, which limits the correction.
"""

from __future__ import annotations

import cv2
import numpy as np

from app.imaging.types import BBox, CompositionPlan, Segmentation


def _symmetry(mask: np.ndarray, angle: float) -> float:
    h, w = mask.shape
    m = cv2.moments(mask, binaryImage=True)
    if m["m00"] == 0:
        return 0.0
    cx, cy = m["m10"] / m["m00"], m["m01"] / m["m00"]
    rot = cv2.getRotationMatrix2D((cx, cy), angle, 1.0)
    r = cv2.warpAffine(mask, rot, (w, h), flags=cv2.INTER_NEAREST)
    # mirror around the vertical line through the centroid
    shift = 2 * cx - (w - 1)
    flip = cv2.warpAffine(cv2.flip(r, 1), np.float32([[1, 0, shift], [0, 1, 0]]), (w, h), flags=cv2.INTER_NEAREST)
    a, b = r > 0, flip > 0
    union = np.count_nonzero(a | b)
    return np.count_nonzero(a & b) / union if union else 0.0


def estimate_tilt(mask: np.ndarray, max_angle: float = 12.0) -> tuple[float, float]:
    """Return (tilt_deg, confidence). Positive tilt = garment rotated counter-clockwise."""
    small = mask
    if max(mask.shape) > 320:
        s = 320 / max(mask.shape)
        small = cv2.resize(mask, (round(mask.shape[1] * s), round(mask.shape[0] * s)), interpolation=cv2.INTER_AREA)
    m = (small > 127).astype(np.uint8)
    if m.sum() < 200:
        return 0.0, 0.0
    coarse = np.arange(-max_angle, max_angle + 0.01, 1.0)
    scores = [_symmetry(m, a) for a in coarse]
    best = float(coarse[int(np.argmax(scores))])
    fine = np.arange(best - 0.9, best + 0.91, 0.2)
    fine_scores = [_symmetry(m, a) for a in fine]
    best = float(fine[int(np.argmax(fine_scores))])
    best_score = float(max(fine_scores))
    straight_score = _symmetry(m, 0.0)

    if best_score >= 0.82:
        # rotating by `best` makes it symmetric → the garment is tilted by -best
        gain = best_score - straight_score
        conf = float(np.clip((best_score - 0.82) / 0.12, 0.0, 1.0)) * (1.0 if gain > 0.005 or abs(best) < 0.5 else 0.5)
        return -best, round(max(conf, 0.35), 3)

    # Asymmetric silhouette: align the dominant edges of the minimum-area rectangle.
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not cnts:
        return 0.0, 0.0
    pts = np.vstack(cnts).astype(np.float32)
    (_, _), (rw, rh), ang = cv2.minAreaRect(pts)
    dev = ang if ang < 45 else ang - 90
    if abs(dev) > max_angle:
        return 0.0, 0.0
    # OpenCV's rectangle angle is clockwise in image coordinates
    return float(-dev), 0.3


def plan_composition(mask: np.ndarray, seg: Segmentation) -> CompositionPlan:
    tilt, conf = estimate_tilt(mask)
    b = seg.bbox
    return CompositionPlan(
        tilt_deg=round(tilt, 2),
        tilt_confidence=conf,
        garment_bbox=BBox(b.x, b.y, b.w, b.h),
        fill_ratio=round(b.w * b.h, 4),
        center_offset=(round(b.cx - 0.5, 4), round(b.cy - 0.5, 4)),
    )
