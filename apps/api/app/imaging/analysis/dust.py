"""Detection of parasite elements: dust, crumbs, hairs, lint.

Specks are found as small, high-contrast residuals against a median-filtered
background. Safety rules (the engine must never erase part of the article):

* only tiny components qualify (larger ones go to defect detection instead);
* candidates inside busy areas (prints, logos, seams, rivets) are ignored;
* strongly coloured dots that differ from their surroundings are treated as
  details of the article, not dust;
* ambiguous specks on the garment are reported to the user as possible
  defects; they are only retouched if the user explicitly confirms it (and
  never in "Préserver l'article" mode).
"""

from __future__ import annotations

import cv2
import numpy as np

from app.imaging.color import rgb_to_lab, to_float
from app.imaging.filters import local_std
from app.imaging.types import BBox, Speck

REFERENCE_SIZE = 1600.0


def detect_specks(img: np.ndarray, garment_mask: np.ndarray) -> tuple[np.ndarray, list[Speck]]:
    """Return (uint16 label map, specks). Label ids match ``Speck.id``."""
    h, w = img.shape[:2]
    s = max(h, w) / REFERENCE_SIZE
    f = to_float(img)
    lab = rgb_to_lab(f)
    L = lab[..., 0]
    L8 = np.clip(L * 2.55, 0, 255).astype(np.uint8)
    k = max(5, int(round(11 * s)) | 1)
    med = cv2.medianBlur(L8, k).astype(np.float32) / 2.55
    resid = L - med

    sigma = float(1.4826 * np.median(np.abs(resid)))
    thr = max(5.5, 4.2 * sigma)

    # Context: structure of the median image (prints/seams are busy, plain fabric is not).
    busy = local_std(cv2.GaussianBlur(med, (0, 0), 1.0), max(3, int(6 * s)))
    a8 = np.clip(lab[..., 1] + 128, 0, 255).astype(np.uint8)
    b8 = np.clip(lab[..., 2] + 128, 0, 255).astype(np.uint8)
    a_bg = cv2.medianBlur(a8, k).astype(np.float32) - 128
    b_bg = cv2.medianBlur(b8, k).astype(np.float32) - 128

    garment = garment_mask > 127
    m8 = garment.astype(np.uint8)
    band_r = max(2, int(5 * s))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * band_r + 1, 2 * band_r + 1))
    edge_band = (cv2.dilate(m8, kernel) - cv2.erode(m8, kernel)) > 0

    # Hysteresis: components of the low-threshold map that contain at least one strong
    # pixel. Shapes are judged on the *whole* component, so a hair broken into fragments
    # at the strong threshold is still one hair, and a zip or seam (a long chain) is
    # rejected as a structure of the article.
    strong = (np.abs(resid) > thr) & ~edge_band
    low = ((np.abs(resid) > 0.5 * thr) & ~edge_band).astype(np.uint8)
    low = cv2.morphologyEx(low, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    n, labels, stats, centroids = cv2.connectedComponentsWithStats(low, connectivity=8)
    if n <= 1:
        return np.zeros((h, w), np.uint16), []

    flat = labels.ravel()
    strong_flat = strong.ravel().astype(np.float64)
    n_strong = np.bincount(flat, weights=strong_flat, minlength=n)
    counts = np.maximum(n_strong, 1)
    abs_r = np.abs(resid).ravel()
    mean_abs = np.bincount(flat, weights=abs_r * strong_flat, minlength=n) / counts
    mean_res = np.bincount(flat, weights=resid.ravel() * strong_flat, minlength=n) / counts
    mean_a = np.bincount(flat, weights=lab[..., 1].ravel() * strong_flat, minlength=n) / counts
    mean_b = np.bincount(flat, weights=lab[..., 2].ravel() * strong_flat, minlength=n) / counts

    dust_max_area = 110 * s * s
    hair_max_area = 900 * s * s
    hair_max_len = 110 * s
    specks: list[Speck] = []
    keep_ids: list[int] = []
    for i in range(1, n):
        if n_strong[i] < max(2, 1.5 * s * s):
            continue
        x, y, bw, bh, area = (int(v) for v in stats[i])
        long_side = max(bw, bh)
        cx, cy = centroids[i]
        ix, iy = min(w - 1, int(cx)), min(h - 1, int(cy))
        thickness = area / max(long_side, 1)
        if area <= dust_max_area and long_side <= 16 * s + 2:
            kind = "dust"
        elif area <= hair_max_area and 12 * s <= long_side <= hair_max_len and thickness <= 4.0 * s + 1:
            kind = "hair"
        else:
            continue  # too large or too long: a defect candidate or a structure of the article
        if busy[iy, ix] > (9.0 if kind == "hair" else 6.5):
            continue  # inside a print / logo / seam: probably part of the article
        chroma = float(np.hypot(mean_a[i], mean_b[i]))
        bg_chroma = float(np.hypot(a_bg[iy, ix], b_bg[iy, ix]))
        d_chroma = float(np.hypot(mean_a[i] - a_bg[iy, ix], mean_b[i] - b_bg[iy, ix]))
        if chroma > 16 and d_chroma > 10 and chroma > bg_chroma:
            continue  # coloured detail (rivet, embroidery dot, print)
        region = "garment" if garment[iy, ix] else "background"
        contrast = float(mean_abs[i]) / thr
        conf = 0.45 + 0.25 * min(contrast - 1.0, 1.6)
        if kind == "hair":
            conf -= 0.05
        if region == "garment":
            conf -= 0.05
            # Larger dark marks on the garment can be small stains or holes: keep them ambiguous.
            if mean_res[i] < 0 and n_strong[i] > 28 * s * s:
                conf = min(conf, 0.5)
        else:
            conf += 0.1
        conf = float(np.clip(conf, 0.05, 0.98))
        specks.append(
            Speck(
                id=len(keep_ids) + 1,
                kind=kind,  # type: ignore[arg-type]
                bbox=BBox(x / w, y / h, bw / w, bh / h),
                area=float(n_strong[i]) / (w * h),
                region=region,  # type: ignore[arg-type]
                polarity="light" if mean_res[i] > 0 else "dark",
                confidence=round(conf, 3),
            )
        )
        keep_ids.append(i)

    lut = np.zeros(n, np.uint16)
    for new_id, old in enumerate(keep_ids, start=1):
        lut[old] = new_id
    label_map = lut[labels]
    return label_map, specks


def speck_removal_ids(specks: list[Speck], cleaning: float, retouch: list[int], protected: set[int]) -> list[int]:
    """Choose which specks to remove for a cleaning strength in [0, 1].

    ``protected`` holds ambiguous specks reported to the user as possible
    defects: they are skipped by the automatic cleaning and only removed when
    the user explicitly confirmed them as dust (``retouch``).
    """
    ids = [i for i in retouch if i in protected]
    if cleaning <= 0:
        return sorted(set(ids))
    min_conf = 0.9 - 0.35 * cleaning  # 0.55 at full strength
    for sp in specks:
        if sp.id in protected:
            continue
        if sp.kind == "hair" and cleaning < 0.5:
            continue
        threshold = min_conf - (0.08 if sp.region == "background" else 0.0)
        if sp.confidence >= threshold:
            ids.append(sp.id)
    return sorted(set(ids))
