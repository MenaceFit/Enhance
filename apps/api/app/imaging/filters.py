"""Low-level edge-aware filters shared by several operations."""

from __future__ import annotations

import cv2
import numpy as np


def box(img: np.ndarray, r: int) -> np.ndarray:
    k = 2 * r + 1
    return cv2.boxFilter(img, -1, (k, k), borderType=cv2.BORDER_REFLECT)


def guided_filter(guide: np.ndarray, src: np.ndarray, r: int, eps: float) -> np.ndarray:
    """Grey-guide guided filter (He et al.). O(1) per pixel thanks to box filters.

    With ``guide is src`` it is an edge-preserving smoother: regions whose local
    variance is below ``eps`` are flattened, stronger edges are kept intact.
    """
    r = max(1, int(r))
    guide = guide.astype(np.float32, copy=False)
    src = src.astype(np.float32, copy=False)
    mean_i = box(guide, r)
    mean_p = box(src, r)
    var_i = box(guide * guide, r) - mean_i * mean_i
    cov_ip = box(guide * src, r) - mean_i * mean_p
    a = cov_ip / (var_i + eps)
    b = mean_p - a * mean_i
    return box(a, r) * guide + box(b, r)


def fast_guided_filter(guide: np.ndarray, src: np.ndarray, r: int, eps: float, subsample: int = 4) -> np.ndarray:
    """Guided filter computed at reduced resolution (He & Sun 2015) for large radii."""
    if subsample <= 1 or min(guide.shape[:2]) < 64 * subsample:
        return guided_filter(guide, src, r, eps)
    h, w = guide.shape[:2]
    small = (max(1, w // subsample), max(1, h // subsample))
    g_s = cv2.resize(guide, small, interpolation=cv2.INTER_AREA)
    p_s = cv2.resize(src, small, interpolation=cv2.INTER_AREA)
    rs = max(1, r // subsample)
    mean_i = box(g_s, rs)
    mean_p = box(p_s, rs)
    var_i = box(g_s * g_s, rs) - mean_i * mean_i
    cov_ip = box(g_s * p_s, rs) - mean_i * mean_p
    a = cov_ip / (var_i + eps)
    b = mean_p - a * mean_i
    mean_a = cv2.resize(box(a, rs), (w, h), interpolation=cv2.INTER_LINEAR)
    mean_b = cv2.resize(box(b, rs), (w, h), interpolation=cv2.INTER_LINEAR)
    return mean_a * guide + mean_b


def masked_blur(img: np.ndarray, weight: np.ndarray, sigma: float) -> np.ndarray:
    """Normalised convolution: Gaussian blur that only averages pixels where weight > 0.

    Used to estimate "what the garment looks like around here" without the
    background bleeding in, and to propagate colours across mask borders.
    """
    sigma = max(0.5, float(sigma))
    w = weight.astype(np.float32)
    if sigma > 12:
        # Large kernels: blur at reduced resolution (Gaussian is band-limited, so this is exact enough).
        k = sigma / 6.0
        h, wd = w.shape[:2]
        size = (max(1, int(wd / k)), max(1, int(h / k)))
        small = masked_blur(cv2.resize(img, size, interpolation=cv2.INTER_AREA), cv2.resize(w, size, interpolation=cv2.INTER_AREA), 6.0)
        return cv2.resize(small, (wd, h), interpolation=cv2.INTER_LINEAR)
    if img.ndim == 3:
        num = cv2.GaussianBlur(img * w[..., None], (0, 0), sigma)
        den = cv2.GaussianBlur(w, (0, 0), sigma)[..., None]
    else:
        num = cv2.GaussianBlur(img * w, (0, 0), sigma)
        den = cv2.GaussianBlur(w, (0, 0), sigma)
    return num / np.maximum(den, 1e-6)


def local_std(img: np.ndarray, r: int) -> np.ndarray:
    mean = box(img, r)
    var = box(img * img, r) - mean * mean
    return np.sqrt(np.maximum(var, 0))


def robust_noise_sigma(gray: np.ndarray) -> float:
    """Noise estimate from the median absolute Laplacian (Immerkær-style)."""
    lap = cv2.Laplacian(gray.astype(np.float32), cv2.CV_32F, ksize=3)
    return float(np.median(np.abs(lap)) * 1.4826 / 6.0)
