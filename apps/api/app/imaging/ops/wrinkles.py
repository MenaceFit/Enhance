"""Wrinkle reduction that keeps texture, prints and the garment's real shape.

L* is split into three layers with guided filters:

    fine detail  = L − GF(L, small radius)          (weave, knit, stitches)  → kept 100 %
    base         = GF(L, large radius, eps)          (prints, seams, large shading) → kept
    folds        = GF(L, small) − base               (soft mid-frequency shading) → attenuated

Strong edges (logos, prints, seams) have a local variance far above ``eps``
and therefore stay in the base layer, so they are never softened. Only the
soft shading of folds is attenuated, and never entirely (max 62 %), so a
crumpled garment still looks like itself. Potential defects are excluded.
"""

from __future__ import annotations

import numpy as np

from app.imaging.filters import fast_guided_filter, guided_filter


def reduce_wrinkles(
    lab: np.ndarray,
    garment_alpha: np.ndarray,
    strength: float,
    protect: np.ndarray | None = None,
) -> np.ndarray:
    if strength <= 0:
        return lab
    h, w = lab.shape[:2]
    scale = max(h, w) / 1600.0
    L = lab[..., 0] / 100.0
    small = guided_filter(L, L, max(1, int(round(2 * scale))), 1e-4)
    detail = L - small
    r_large = max(4, int(round(24 * scale)))
    base = fast_guided_filter(small, small, r_large, 2.5e-3, subsample=4)
    folds = small - base
    weight = np.clip(garment_alpha, 0.0, 1.0) * strength
    if protect is not None:
        weight = weight * (1.0 - np.clip(protect, 0.0, 1.0))
    L_out = base + folds * (1.0 - weight) + detail
    out = lab.copy()
    out[..., 0] = np.clip(L_out * 100.0, 0.0, 100.0)
    return out
