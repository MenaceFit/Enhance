"""Multi-photo consistency for one listing ("Cohérence entre les photos").

Photos of the same garment should share white balance, brightness and colour
temperature. Each photo's own estimate is blended with the group consensus
according to how reliable it is: a close-up of a label (no background to read
the light from) borrows the white balance measured on the full shots.
"""

from __future__ import annotations

import numpy as np

from app.imaging.color import LUMA_LINEAR
from app.imaging.types import Analysis


def _lstar_to_y(L: float) -> float:
    return ((L + 16.0) / 116.0) ** 3 if L > 8 else L / 903.3


def harmonize(analyses: list[Analysis]) -> list[dict]:
    if len(analyses) < 2:
        return [{} for _ in analyses]

    logs = np.array([np.log(np.asarray(a.illuminant.gains, np.float64)) for a in analyses])
    conf = np.array([max(0.05, a.illuminant.confidence) for a in analyses])
    group_log = (logs * conf[:, None]).sum(axis=0) / conf.sum()

    # Garment brightness after each photo's own exposure correction.
    y_after = np.array([_lstar_to_y(a.exposure.garment_p50) * a.exposure.gain for a in analyses])
    weights = np.array([0.3 + a.segmentation.confidence for a in analyses])
    order = np.argsort(y_after)
    cum = np.cumsum(weights[order])
    target = float(y_after[order][np.searchsorted(cum, cum[-1] / 2)])  # weighted median

    out = []
    for i, a in enumerate(analyses):
        c = float(np.clip(a.illuminant.confidence, 0.0, 1.0))
        g = np.exp(logs[i] * c + group_log * (1 - c))
        g = g / float(g @ LUMA_LINEAR.astype(np.float64))
        factor = float(np.clip(target / max(y_after[i], 1e-4), 0.8, 1.25) ** 0.7)
        out.append({
            "gains": [round(float(v), 5) for v in g],
            "exposure_factor": round(factor, 4),
            "group_size": len(analyses),
        })
    return out
