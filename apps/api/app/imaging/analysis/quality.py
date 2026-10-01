"""Image Quality Score (0-100) with a per-criterion breakdown.

Shown to the seller as "Qualité : 63/100 → 91/100". Criteria are the ones a
buyer perceives: sharpness, light, colour cast, noise, framing, cleanliness
and resolution.
"""

from __future__ import annotations

import cv2
import numpy as np

from app.imaging.color import rgb_to_lab, to_float
from app.imaging.filters import robust_noise_sigma
from app.imaging.types import QualityReport

WEIGHTS = {
    "nettete": 0.20,
    "lumiere": 0.20,
    "couleurs": 0.15,
    "bruit": 0.08,
    "cadrage": 0.17,
    "proprete": 0.10,
    "resolution": 0.10,
}


def assess_quality(
    img: np.ndarray,
    garment_mask: np.ndarray | None,
    *,
    cast_strength: float,
    tilt_deg: float,
    speck_count: int,
    source_long_side: int | None = None,
) -> QualityReport:
    f = to_float(img)
    long_side = source_long_side or max(f.shape[:2])
    if max(f.shape[:2]) > 768:
        s = 768 / max(f.shape[:2])
        size = (round(f.shape[1] * s), round(f.shape[0] * s))
        f = cv2.resize(f, size, interpolation=cv2.INTER_AREA)
        if garment_mask is not None:
            garment_mask = cv2.resize(garment_mask, size, interpolation=cv2.INTER_AREA)
    L = rgb_to_lab(f)[..., 0]
    m = garment_mask > 127 if garment_mask is not None else np.ones(L.shape, bool)
    if m.sum() < 100:
        m = np.ones(L.shape, bool)
    issues: list[str] = []

    # Sharpness: Laplacian energy on the garment, relative to its contrast so that a plain
    # black hoodie is not penalised for having little texture.
    lap = cv2.Laplacian(cv2.GaussianBlur(L, (0, 0), 0.6), cv2.CV_32F)
    energy = float(np.var(lap[m]))
    contrast = float(np.std(L[m])) + 4.0
    sharp_ratio = energy / contrast
    nettete = float(np.clip((np.log10(sharp_ratio + 1e-3) + 0.2) / 1.0, 0, 1))
    if nettete < 0.45:
        issues.append("Photo un peu floue")

    # Light: highlights should reach near-white, without clipping; midtones not muddy.
    p99 = float(np.percentile(L, 99))
    p50 = float(np.percentile(L, 50))
    clip_hi = float((f.max(axis=2) > 0.995).mean())
    clip_lo = float((f.max(axis=2) < 0.01).mean())
    lumiere = 1.0 - np.clip((90 - p99) / 32, 0, 1) * 0.65 - np.clip((45 - p50) / 40, 0, 1) * 0.25
    lumiere -= min(0.3, clip_hi * 6) + min(0.3, clip_lo * 6)
    lumiere = float(np.clip(lumiere, 0, 1))
    if p99 < 80:
        issues.append("Photo sous-exposée")
    if clip_hi > 0.03:
        issues.append("Hautes lumières brûlées")

    couleurs = float(np.clip(1 - max(0.0, cast_strength - 1.5) / 11, 0, 1))
    if cast_strength > 5:
        issues.append("Dominante de couleur visible")

    sigma = robust_noise_sigma(L)
    bruit = float(np.clip(1 - max(0.0, sigma - 0.6) / 3.5, 0, 1))
    if bruit < 0.5:
        issues.append("Bruit numérique visible")

    # Framing: garment size in frame, centring, straightness.
    ys, xs = np.nonzero(m)
    h, w = L.shape
    bw = (xs.max() - xs.min() + 1) / w
    bh = (ys.max() - ys.min() + 1) / h
    fill = max(bw, bh)
    off = np.hypot((xs.min() + xs.max()) / 2 / w - 0.5, (ys.min() + ys.max()) / 2 / h - 0.5)
    cadrage = 1.0 - np.clip((0.82 - fill) / 0.45, 0, 1) * 0.55 - np.clip((off - 0.03) / 0.2, 0, 1) * 0.25
    cadrage -= np.clip((abs(tilt_deg) - 0.7) / 6, 0, 1) * 0.25
    cadrage = float(np.clip(cadrage, 0, 1))
    if fill < 0.6:
        issues.append("Vêtement trop petit dans l'image")
    if abs(tilt_deg) > 2:
        issues.append("Vêtement légèrement incliné")

    proprete = float(np.clip(1 - speck_count / 22, 0, 1))
    if speck_count >= 4:
        issues.append("Poussières ou cheveux visibles")

    resolution = float(np.clip((long_side - 600) / 1000, 0.3, 1.0))
    if long_side < 1000:
        issues.append("Résolution faible")

    breakdown = {
        "nettete": nettete,
        "lumiere": lumiere,
        "couleurs": couleurs,
        "bruit": bruit,
        "cadrage": cadrage,
        "proprete": proprete,
        "resolution": resolution,
    }
    score = sum(WEIGHTS[k] * v for k, v in breakdown.items())
    return QualityReport(
        score=int(round(score * 100)),
        breakdown={k: int(round(v * 100)) for k, v in breakdown.items()},
        issues=issues,
    )
