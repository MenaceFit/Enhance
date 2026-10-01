"""Detection of potential imperfections of the article (anti-dissimulation).

Detected zones are *only reported* to the seller with the recommendation to
keep them visible. They are excluded from wrinkle smoothing and dust removal
so that no automatic step can make them disappear.

Heuristics (deliberately conservative, each zone carries a confidence):
* stains / discolourations: compact, soft-edged colour or lightness anomalies
  relative to the surrounding fabric. Sharp-edged anomalies are prints/logos.
* holes: small background-coloured regions enclosed by the garment.
* wear / pilling: patches whose fine-texture energy is much higher than the
  rest of the garment while carrying no structure (no print, no seam).
* ambiguous specks: small dark marks on the garment that might be dust or a
  tiny stain/hole; the user decides.
"""

from __future__ import annotations

import uuid

import cv2
import numpy as np

from app.imaging.color import rgb_to_lab, to_float
from app.imaging.filters import local_std, masked_blur
from app.imaging.types import BBox, Defect, Speck

LABELS = {
    "stain": "Tache possible",
    "discoloration": "Tache claire ou décoloration possible",
    "hole": "Trou possible",
    "wear": "Zone d'usure possible",
    "pilling": "Bouloches possibles",
    "snag": "Accroc possible",
    "speck": "Petite marque à vérifier",
}

REFERENCE_SIZE = 1600.0
MAX_DEFECTS = 8
MAX_AMBIGUOUS = 3
MIN_REPORT_CONFIDENCE = 0.6
SHARPNESS_LIMIT = 0.2  # edge gradient / contrast; diffuse stains sit well below, prints above


def _iou(a: BBox, b: BBox) -> float:
    x0, y0 = max(a.x, b.x), max(a.y, b.y)
    x1, y1 = min(a.x + a.w, b.x + b.w), min(a.y + a.h, b.y + b.h)
    inter = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    union = a.w * a.h + b.w * b.h - inter
    return inter / union if union > 0 else 0.0


def _contains(outer: BBox, inner: BBox) -> bool:
    return (
        inner.cx >= outer.x and inner.cx <= outer.x + outer.w and inner.cy >= outer.y and inner.cy <= outer.y + outer.h
    )


def detect_defects(
    img: np.ndarray,
    garment_mask: np.ndarray,
    specks: list[Speck],
    holes: list[BBox] | None = None,
    *,
    detect_wear: bool = False,
) -> list[Defect]:
    """Report potential imperfections.

    ``detect_wear`` enables the texture-energy heuristic for wear/pilling. It is
    off for the classical engine because woven textures (denim twill, ribs,
    zips) trigger it too often; vision providers report wear more reliably.
    """
    h, w = img.shape[:2]
    s = max(h, w) / REFERENCE_SIZE
    f = to_float(img)
    lab = rgb_to_lab(cv2.GaussianBlur(f, (0, 0), max(0.8, 1.2 * s)))
    garment = (garment_mask > 127).astype(np.uint8)
    if garment.sum() < 0.01 * h * w:
        return []
    er = max(2, int(7 * s))
    interior = cv2.erode(garment, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * er + 1, 2 * er + 1)))
    garment_area = float(garment.sum())

    defects: list[Defect] = []

    # --- stains & discolourations --------------------------------------------------------
    sigma = 0.022 * max(h, w)
    ref = masked_blur(lab, interior, sigma)
    dL = lab[..., 0] - ref[..., 0]
    da = lab[..., 1] - ref[..., 1]
    db = lab[..., 2] - ref[..., 2]
    e = np.sqrt((dL / 1.4) ** 2 + da**2 + db**2) * interior
    vals = e[interior > 0]
    if vals.size > 100:
        mad = float(np.median(np.abs(vals - np.median(vals))) * 1.4826)
        thr = max(6.5, float(np.median(vals)) + 4.0 * mad)
        cand = ((e > thr) & (interior > 0)).astype(np.uint8)
        cand = cv2.morphologyEx(cand, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        n, labels, stats, centroids = cv2.connectedComponentsWithStats(cand, connectivity=8)
        # Gradient of the same perceptual vector as the anomaly score, so that colour-only
        # edges (orange stitching on denim) count as crisp edges too.
        vec = np.dstack([lab[..., 0] / 1.4, lab[..., 1], lab[..., 2]])
        gx = cv2.Sobel(vec, cv2.CV_32F, 1, 0, ksize=3) / 8.0
        gy = cv2.Sobel(vec, cv2.CV_32F, 0, 1, ksize=3) / 8.0
        grad = np.sqrt((gx**2 + gy**2).sum(axis=2))
        min_area = 90 * s * s
        max_area = 0.04 * garment_area
        for i in range(1, n):
            x, y, bw, bh, area = (int(v) for v in stats[i])
            if area < min_area or area > max_area:
                continue
            pad = max(3, int(4 * s))
            x0, y0, x1, y1 = max(0, x - pad), max(0, y - pad), min(w, x + bw + pad), min(h, y + bh + pad)
            comp = (labels[y0:y1, x0:x1] == i).astype(np.uint8)
            cy_, cx_ = np.nonzero(comp)
            cov = np.cov(np.stack([cx_, cy_]).astype(np.float32)) if cx_.size > 2 else np.eye(2)
            ev = np.linalg.eigvalsh(cov)
            elong = float(np.sqrt(max(ev[1], 1e-6) / max(ev[0], 1e-6)))
            fill = area / max(1, bw * bh)
            if elong > 2.6 or fill < 0.3:
                continue  # seams, folds, drawstrings, stitching: elongated or thin structures
            ring = cv2.dilate(comp, np.ones((2 * pad + 1, 2 * pad + 1), np.uint8)) - cv2.erode(comp, np.ones((3, 3), np.uint8))
            ring_vals = grad[y0:y1, x0:x1][ring > 0]
            contrast = float(np.mean(e[y0:y1, x0:x1][comp > 0]))
            if ring_vals.size == 0 or contrast <= 0:
                continue
            sharpness = float(np.percentile(ring_vals, 90)) * s / contrast
            if sharpness > SHARPNESS_LIMIT:
                continue  # crisp edges: print, logo, label, rivet, pocket — part of the article
            mean_dL = float(np.mean(dL[y0:y1, x0:x1][comp > 0]))
            ref_c = float(np.mean(np.hypot(ref[y0:y1, x0:x1, 1], ref[y0:y1, x0:x1, 2])[comp > 0]))
            cur_c = float(np.mean(np.hypot(lab[y0:y1, x0:x1, 1], lab[y0:y1, x0:x1, 2])[comp > 0]))
            kind = "discoloration" if mean_dL > 0 and cur_c <= ref_c + 2 else "stain"
            strength = float(np.mean(e[y0:y1, x0:x1][comp > 0]) / thr)
            conf = float(np.clip(0.35 + 0.18 * strength + 0.25 * (SHARPNESS_LIMIT - sharpness) / SHARPNESS_LIMIT, 0.2, 0.95))
            defects.append(
                Defect(
                    id=uuid.uuid4().hex[:10],
                    kind=kind,  # type: ignore[arg-type]
                    label=LABELS[kind],
                    bbox=BBox(x / w, y / h, bw / w, bh / h),
                    confidence=round(conf, 3),
                    area=area / (h * w),
                )
            )

    # --- holes ---------------------------------------------------------------------------
    # Several enclosed "holes" close to each other are letter counters or a print, not damage.
    holes = list(holes or [])
    isolated = [
        hb for hb in holes
        if not any(o is not hb and np.hypot(o.cx - hb.cx, o.cy - hb.cy) < 0.08 for o in holes)
    ]
    for hb in isolated:
        defects.append(
            Defect(id=uuid.uuid4().hex[:10], kind="hole", label=LABELS["hole"], bbox=hb, confidence=0.5, area=hb.w * hb.h)
        )

    # --- wear / pilling: unusual fine-texture energy without structure --------------------
    if detect_wear:
        defects.extend(_detect_wear(lab, interior, specks, s))

    # --- ambiguous specks on the garment ---------------------------------------------------
    for sp in specks:
        if sp.region != "garment":
            continue
        if sp.confidence < 0.55 or (sp.polarity == "dark" and sp.area * h * w > 28 * s * s):
            defects.append(
                Defect(
                    id=uuid.uuid4().hex[:10], kind="speck", label=LABELS["speck"], bbox=sp.bbox,
                    confidence=round(0.35 + 0.3 * (1 - sp.confidence), 3), area=sp.area,
                    removable_as_dust=True, speck_id=sp.id,
                )
            )
    return _merge(defects)


def _detect_wear(lab: np.ndarray, interior: np.ndarray, specks: list[Speck], s: float) -> list[Defect]:
    h, w = interior.shape
    out: list[Defect] = []
    L = lab[..., 0]
    hp = np.abs(L - cv2.GaussianBlur(L, (0, 0), 1.6 * max(1.0, s)))
    block = max(16, int(40 * s))
    structure = local_std(cv2.GaussianBlur(L, (0, 0), 3 * max(1.0, s)), max(3, int(8 * s)))
    speck_zone = np.zeros((h, w), np.uint8)
    for sp in specks:
        x0, y0 = int(sp.bbox.x * w) - block // 2, int(sp.bbox.y * h) - block // 2
        speck_zone[max(0, y0) : y0 + int(sp.bbox.h * h) + block, max(0, x0) : x0 + int(sp.bbox.w * w) + block] = 1
    energies = []
    for by in range(0, h - block + 1, block):
        for bx in range(0, w - block + 1, block):
            if interior[by : by + block, bx : bx + block].mean() < 0.9:
                continue
            if speck_zone[by : by + block, bx : bx + block].any():
                continue  # a hair or dust grain, already handled
            # A percentile (not the mean) so that a single hair or grain does not trigger it:
            # pilling and wear raise the texture energy of the whole patch.
            energies.append(
                (
                    float(np.percentile(hp[by : by + block, bx : bx + block], 60)),
                    float(structure[by : by + block, bx : bx + block].mean()),
                    bx,
                    by,
                )
            )
    if len(energies) >= 12:
        en = np.array([x[0] for x in energies])
        med_e = float(np.median(en))
        mad_e = float(np.median(np.abs(en - med_e)) * 1.4826) + 1e-3
        flagged = [
            (x[2], x[3], (x[0] - med_e) / mad_e)
            for x in energies
            if x[0] > max(1.8 * med_e, med_e + 8 * mad_e) and x[1] < 3.0
        ]
        flagged.sort(key=lambda t: -t[2])
        for bx, by, z in flagged[:2]:
            out.append(
                Defect(
                    id=uuid.uuid4().hex[:10], kind="wear", label=LABELS["wear"],
                    bbox=BBox(bx / w, by / h, block / w, block / h),
                    confidence=round(float(np.clip(0.3 + 0.02 * z, 0.3, 0.55)), 3), area=block * block / (h * w),
                )
            )
    return out


def _merge(defects: list[Defect]) -> list[Defect]:
    """Merge fragments of the same zone; keep the most confident; cap the list."""
    defects = [d for d in defects if d.kind not in ("stain", "discoloration") or d.confidence >= MIN_REPORT_CONFIDENCE]
    defects.sort(key=lambda d: -d.confidence)
    merged: list[Defect] = []
    for d in defects:
        target = next((m for m in merged if _near(m.bbox, d.bbox)), None)
        if target is None:
            merged.append(d)
        elif d.kind != "speck" and target.kind != "speck":
            target.bbox = _union(target.bbox, d.bbox)
            target.area += d.area
    ambiguous = [d for d in merged if d.kind == "speck"][:MAX_AMBIGUOUS]
    real = [d for d in merged if d.kind != "speck"]
    return (real + ambiguous)[:MAX_DEFECTS]


def _near(a: BBox, b: BBox) -> bool:
    if _iou(a, b) > 0.1 or _contains(a, b) or _contains(b, a):
        return True
    gap = max(a.w, a.h, b.w, b.h) * 0.8
    return abs(a.cx - b.cx) < (a.w + b.w) / 2 + gap and abs(a.cy - b.cy) < (a.h + b.h) / 2 + gap


def _union(a: BBox, b: BBox) -> BBox:
    x0, y0 = min(a.x, b.x), min(a.y, b.y)
    x1, y1 = max(a.x + a.w, b.x + b.w), max(a.y + a.h, b.y + b.h)
    return BBox(x0, y0, x1 - x0, y1 - y0)


def protected_speck_ids(defects: list[Defect]) -> set[int]:
    return {d.speck_id for d in defects if d.speck_id is not None}


def defect_protection_mask(defects: list[Defect], width: int, height: int, grow: float = 0.5) -> np.ndarray:
    """Float mask (1 = protected) covering every potential defect, slightly enlarged."""
    m = np.zeros((height, width), np.float32)
    for d in defects:
        if d.kind == "speck":
            continue
        gx, gy = d.bbox.w * grow, d.bbox.h * grow
        x0 = int(max(0, (d.bbox.x - gx) * width))
        y0 = int(max(0, (d.bbox.y - gy) * height))
        x1 = int(min(width, (d.bbox.x + d.bbox.w + gx) * width))
        y1 = int(min(height, (d.bbox.y + d.bbox.h + gy) * height))
        m[y0:y1, x0:x1] = 1.0
    if m.any():
        m = cv2.GaussianBlur(m, (0, 0), max(1.0, 0.004 * max(width, height)))
    return m
