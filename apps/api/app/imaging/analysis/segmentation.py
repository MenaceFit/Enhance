"""Garment segmentation without a learned model.

Seller photos are overwhelmingly "one garment on a fairly uniform surface"
(bed, floor, wall, hanger). We model the background from the image border,
score every pixel by its distance to that model, threshold it, and refine the
result with GrabCut. A confidence score is returned so that downstream steps
can refuse risky operations (e.g. background replacement) on ambiguous photos.

Learned segmenters (rembg/U²-Net, SAM, cloud APIs) plug in through the
provider layer; they must return the same ``(mask, Segmentation)`` contract.
"""

from __future__ import annotations

import cv2
import numpy as np

from app.imaging.color import rgb_to_lab
from app.imaging.image_io import resize_long_side
from app.imaging.types import BBox, Segmentation

WORK_SIZE = 640


def _border_samples(lab: np.ndarray, frac: float = 0.04) -> tuple[np.ndarray, np.ndarray]:
    """Border pixels and the side (0 top, 1 bottom, 2 left, 3 right) each comes from."""
    h, w = lab.shape[:2]
    bh, bw = max(2, int(h * frac)), max(2, int(w * frac))
    parts = [lab[:bh].reshape(-1, 3), lab[-bh:].reshape(-1, 3), lab[:, :bw].reshape(-1, 3), lab[:, -bw:].reshape(-1, 3)]
    sides = np.concatenate([np.full(len(p), i, np.int32) for i, p in enumerate(parts)])
    return np.concatenate(parts, axis=0), sides


def _background_distance(lab: np.ndarray) -> np.ndarray:
    samples, sides = _border_samples(lab)
    weights = np.array([0.45, 1.0, 1.0], dtype=np.float32)  # lightness matters less (shadows, folds)
    samples_w = samples * weights
    k = 4
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 0.5)
    _, labels, centers = cv2.kmeans(samples_w.astype(np.float32), k, None, criteria, 2, cv2.KMEANS_PP_CENTERS)
    labels = labels.ravel()
    side_counts = np.bincount(sides, minlength=4).astype(np.float64)
    keep = []
    for c in range(k):
        in_c = labels == c
        if in_c.sum() < 0.05 * len(labels):
            continue
        # share of each side covered by this cluster; the background surrounds the garment,
        # a garment that runs out of the frame only covers (part of) one side
        shares = np.bincount(sides[in_c], minlength=4) / np.maximum(side_counts, 1)
        if np.count_nonzero(shares >= 0.15) >= 2:
            keep.append(c)
    if not keep:
        counts = np.bincount(labels, minlength=k)
        keep = [int(np.argmax(counts))]
    centers = centers[keep]
    flat = (lab * weights).reshape(-1, 3)
    d = np.min(np.linalg.norm(flat[:, None, :] - centers[None, :, :], axis=2), axis=1)
    return d.reshape(lab.shape[:2]).astype(np.float32)


def _fill_holes(mask: np.ndarray) -> np.ndarray:
    # Pad so the flood always starts from background, even if the garment touches a corner.
    padded = cv2.copyMakeBorder(mask, 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=0)
    h, w = padded.shape
    ff_mask = np.zeros((h + 2, w + 2), np.uint8)
    cv2.floodFill(padded, ff_mask, (0, 0), 255)
    # pixels not reached from outside and not in the mask are holes
    holes = cv2.bitwise_not(padded)[1:-1, 1:-1]
    return cv2.bitwise_or(mask, holes)


def _keep_main_components(mask: np.ndarray, rel_min: float = 0.15) -> tuple[np.ndarray, int]:
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if n <= 1:
        return mask, 0
    areas = stats[1:, cv2.CC_STAT_AREA]
    largest = areas.max()
    keep_ids = [i + 1 for i, a in enumerate(areas) if a >= rel_min * largest and a >= 0.004 * mask.size]
    out = np.isin(labels, keep_ids).astype(np.uint8) * 255
    return out, len(keep_ids)


def segment_garment(img: np.ndarray) -> tuple[np.ndarray, Segmentation, list[BBox]]:
    """Return (soft mask uint8 at input resolution, segmentation info, small interior holes).

    The interior holes are background-coloured regions fully enclosed by the
    garment; small ones are reported to defect detection as possible holes.
    """
    h0, w0 = img.shape[:2]
    small = resize_long_side(img, WORK_SIZE)
    sh, sw = small.shape[:2]
    f = small.astype(np.float32) / 255.0 if small.dtype == np.uint8 else small
    lab = rgb_to_lab(f)
    lab_blur = cv2.GaussianBlur(lab, (0, 0), 1.2)

    dist = _background_distance(lab_blur)
    dist = cv2.GaussianBlur(dist, (0, 0), 1.5)
    d8 = np.clip(dist * (255.0 / max(np.percentile(dist, 99.5), 1e-3)), 0, 255).astype(np.uint8)
    otsu_t, _ = cv2.threshold(d8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    otsu_t = max(otsu_t, 18)
    init = (d8 > otsu_t).astype(np.uint8) * 255

    # Separability: how distinct garment and background distances are.
    fg_vals = d8[init > 0]
    bg_vals = d8[init == 0]
    if fg_vals.size < 50 or bg_vals.size < 50:
        separability = 0.0
    else:
        separability = float((fg_vals.mean() - bg_vals.mean()) / (fg_vals.std() + bg_vals.std() + 1e-3))

    init = cv2.morphologyEx(init, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    init, _ = _keep_main_components(init, rel_min=0.12)

    method = "border-model"
    mask = init
    if init.any():
        gc = np.full((sh, sw), cv2.GC_PR_BGD, np.uint8)
        gc[d8 > otsu_t] = cv2.GC_PR_FGD
        core = cv2.erode(init, np.ones((9, 9), np.uint8))
        gc[core > 0] = cv2.GC_FGD
        gc[d8 < otsu_t * 0.35] = cv2.GC_BGD
        border = max(2, int(min(sh, sw) * 0.01))
        edge_band = np.zeros_like(gc, dtype=bool)
        edge_band[:border] = edge_band[-border:] = True
        edge_band[:, :border] = edge_band[:, -border:] = True
        gc[edge_band & (init == 0)] = cv2.GC_BGD
        bgd_model = np.zeros((1, 65), np.float64)
        fgd_model = np.zeros((1, 65), np.float64)
        try:
            cv2.grabCut((f * 255).astype(np.uint8), gc, None, bgd_model, fgd_model, 3, cv2.GC_INIT_WITH_MASK)
            refined = np.where((gc == cv2.GC_FGD) | (gc == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
            # GrabCut occasionally collapses; keep the initial estimate when it does.
            if refined.sum() > 0.4 * init.sum():
                mask = refined
                method = "border-model+grabcut"
        except cv2.error:
            pass

    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
    confidence = float(np.clip((separability - 0.6) / 1.6, 0.0, 1.0))
    return _finalize(mask, (w0, h0), confidence, method)


def _finalize(mask: np.ndarray, out_size: tuple[int, int], confidence: float, method: str):
    """Common post-processing for any segmenter: components, holes, bbox, touches, confidence."""
    sh, sw = mask.shape
    w0, h0 = out_size
    mask, components = _keep_main_components(mask)
    filled = _fill_holes(mask)

    holes_bbox: list[BBox] = []
    garment_area = max(1, int((filled > 0).sum()))
    holes = cv2.subtract(filled, mask)
    if holes.any():
        n, labels, stats, _ = cv2.connectedComponentsWithStats(holes, connectivity=8)
        big = np.zeros_like(holes)
        for i in range(1, n):
            x, y, w, h, a = stats[i]
            ratio = a / garment_area
            # Large enclosed regions are legitimate (between arm and body); only report small ones.
            if 0.0002 <= ratio <= 0.01 and max(w, h) < 4 * max(1, min(w, h)):
                holes_bbox.append(BBox(x / sw, y / sh, w / sw, h / sh))
            if ratio > 0.01:
                big[labels == i] = 255  # keep big enclosed background regions out of the garment
        filled = cv2.subtract(filled, big)

    mask = filled
    fraction = float((mask > 0).mean())
    ys, xs = np.nonzero(mask)
    if xs.size == 0:
        bbox = BBox(0.0, 0.0, 1.0, 1.0)
        touches = {"left": True, "top": True, "right": True, "bottom": True}
    else:
        x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
        bbox = BBox(x0 / sw, y0 / sh, (x1 - x0 + 1) / sw, (y1 - y0 + 1) / sh)
        tol = max(1, int(0.006 * max(sh, sw)))
        touches = {
            "left": bool(x0 <= tol),
            "top": bool(y0 <= tol),
            "right": bool(x1 >= sw - 1 - tol),
            "bottom": bool(y1 >= sh - 1 - tol),
        }

    if fraction < 0.03 or fraction > 0.93:
        confidence *= 0.3
    if sum(touches.values()) >= 3:
        confidence *= 0.6

    # Soft edges at full resolution; renderers refine further with a guided filter.
    mask_full = cv2.resize(mask, (w0, h0), interpolation=cv2.INTER_LINEAR)
    mask_full = cv2.GaussianBlur(mask_full, (0, 0), max(0.8, max(h0, w0) / 1400))
    info = Segmentation(
        confidence=round(confidence, 3),
        garment_fraction=round(fraction, 4),
        bbox=bbox,
        touches=touches,
        components=int(components),
        method=method,
    )
    return mask_full, info, holes_bbox


def segmentation_from_mask(mask: np.ndarray, out_size: tuple[int, int], method: str, confidence: float):
    """Adapter for external segmenters (rembg, SAM, cloud APIs) returning a soft mask."""
    small = mask if max(mask.shape) <= WORK_SIZE else cv2.resize(
        mask, (round(mask.shape[1] * WORK_SIZE / max(mask.shape)), round(mask.shape[0] * WORK_SIZE / max(mask.shape))),
        interpolation=cv2.INTER_AREA,
    )
    binary = (small > 127).astype(np.uint8) * 255
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    return _finalize(binary, out_size, confidence, method)


def quick_mask(img: np.ndarray) -> np.ndarray:
    """Cheap segmentation (no GrabCut) used by the structural check on outputs."""
    small = resize_long_side(img, 384)
    f = small.astype(np.float32) / 255.0 if small.dtype == np.uint8 else small
    lab = cv2.GaussianBlur(rgb_to_lab(f), (0, 0), 1.0)
    dist = cv2.GaussianBlur(_background_distance(lab), (0, 0), 1.2)
    d8 = np.clip(dist * (255.0 / max(np.percentile(dist, 99.5), 1e-3)), 0, 255).astype(np.uint8)
    t, _ = cv2.threshold(d8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    m = (d8 > max(t, 18)).astype(np.uint8) * 255
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    m, _ = _keep_main_components(m)
    return _fill_holes(m)
