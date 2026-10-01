"""Anti-hallucination structural comparison.

Compares the light-corrected original (same framing) with the output:

* silhouette IoU — the garment's outline and proportions must not change;
* strong-edge recall — logos, prints, seams, pockets, zips are the strongest
  edges of a garment; they must all still be there;
* fine-detail correlation — texture must be the original one, not a
  re-synthesised one;
* aspect delta — the garment must keep its proportions.

The classical engine passes by construction; the check exists so that any
generative provider plugged in later is held to the same contract. Failing
outputs are automatically re-rendered at lower intensity, then flagged.
"""

from __future__ import annotations

import cv2
import numpy as np

from app.imaging.analysis.segmentation import quick_mask
from app.imaging.color import rgb_to_lab, to_float
from app.imaging.types import StructureReport

THRESHOLDS = {"iou": 0.9, "edge_recall": 0.8, "detail": 0.45, "aspect": 0.06}


def _prep(img: np.ndarray, size: int) -> np.ndarray:
    f = to_float(img)
    s = size / max(f.shape[:2])
    if s < 1:
        f = cv2.resize(f, (round(f.shape[1] * s), round(f.shape[0] * s)), interpolation=cv2.INTER_AREA)
    return f


def _bbox_aspect(m: np.ndarray) -> float:
    ys, xs = np.nonzero(m)
    if xs.size == 0:
        return 1.0
    return (ys.max() - ys.min() + 1) / max(1, xs.max() - xs.min() + 1)


def structural_check(reference: np.ndarray, output: np.ndarray, garment_mask: np.ndarray) -> StructureReport:
    ref = _prep(reference, 512)
    out = cv2.resize(_prep(output, 512), (ref.shape[1], ref.shape[0]), interpolation=cv2.INTER_AREA)
    gm = cv2.resize(garment_mask, (ref.shape[1], ref.shape[0]), interpolation=cv2.INTER_AREA) > 127
    issues: list[str] = []

    # silhouette
    m_ref = quick_mask((ref * 255).astype(np.uint8)) > 0
    m_out = quick_mask((out * 255).astype(np.uint8)) > 0
    if m_ref.shape != gm.shape:
        m_ref = cv2.resize(m_ref.astype(np.uint8), (gm.shape[1], gm.shape[0]), interpolation=cv2.INTER_NEAREST) > 0
        m_out = cv2.resize(m_out.astype(np.uint8), (gm.shape[1], gm.shape[0]), interpolation=cv2.INTER_NEAREST) > 0
    union = np.count_nonzero(m_ref | m_out)
    iou = np.count_nonzero(m_ref & m_out) / union if union else 1.0
    aspect_delta = abs(_bbox_aspect(m_out) / max(_bbox_aspect(m_ref), 1e-6) - 1.0)

    region = cv2.dilate(gm.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    if region.sum() < 100:
        region = np.ones_like(gm)
    L_ref = rgb_to_lab(cv2.GaussianBlur(ref, (0, 0), 0.8))[..., 0]
    L_out = rgb_to_lab(cv2.GaussianBlur(out, (0, 0), 0.8))[..., 0]

    def grad(L: np.ndarray) -> np.ndarray:
        gx = cv2.Sobel(L, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(L, cv2.CV_32F, 0, 1, ksize=3)
        return np.hypot(gx, gy)

    g_ref, g_out = grad(L_ref), grad(L_out)
    # tolerate one-pixel shifts
    g_out_max = cv2.dilate(g_out, np.ones((3, 3), np.uint8))
    vals = g_ref[region]
    strong = region & (g_ref >= max(np.percentile(vals, 92), 8.0))
    edge_recall = float(np.mean(g_out_max[strong] >= 0.45 * g_ref[strong])) if strong.any() else 1.0

    hp_ref = (L_ref - cv2.GaussianBlur(L_ref, (0, 0), 2.0))[region]
    hp_out = (L_out - cv2.GaussianBlur(L_out, (0, 0), 2.0))[region]
    flat = hp_ref.std() < 1e-3 or hp_out.std() < 1e-3
    detail = 1.0 if flat else float(np.corrcoef(hp_ref, hp_out)[0, 1])

    if iou < THRESHOLDS["iou"]:
        issues.append("La silhouette du vêtement a changé.")
    if edge_recall < THRESHOLDS["edge_recall"]:
        issues.append("Des détails marquants (logo, coutures, imprimé) semblent modifiés.")
    if detail < THRESHOLDS["detail"]:
        issues.append("La texture du vêtement semble régénérée.")
    if aspect_delta > THRESHOLDS["aspect"]:
        issues.append("Les proportions du vêtement ont changé.")

    score = 100 * (
        0.35 * min(1.0, iou / 0.98)
        + 0.35 * min(1.0, edge_recall / 0.95)
        + 0.2 * float(np.clip(detail / 0.9, 0, 1))
        + 0.1 * float(np.clip(1 - aspect_delta / 0.1, 0, 1))
    )
    return StructureReport(
        score=int(round(score)),
        silhouette_iou=round(float(iou), 4),
        edge_recall=round(edge_recall, 4),
        detail_correlation=round(detail, 4),
        aspect_delta=round(float(aspect_delta), 4),
        passed=not issues,
        issues=issues,
    )
