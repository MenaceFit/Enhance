"""Background treatments.

* ``clean``  — keeps the real background but softens its texture and folds,
  brightens and slightly neutralises it so the garment stands out.
* ``neutral`` — composites the garment on a plain off-white / light grey /
  light beige surface while keeping a *natural* shadow: the shadow of the
  original photo is transferred, plus a faint contact shadow. Edge colours are
  decontaminated (the old background's colour is removed from semi-transparent
  edge pixels) so no halo appears.
"""

from __future__ import annotations

import cv2
import numpy as np

from app.imaging.color import lab_to_rgb, rgb_to_lab
from app.imaging.filters import fast_guided_filter, guided_filter, masked_blur
from app.imaging.settings import BACKGROUND_COLORS


def refine_alpha(img: np.ndarray, soft_mask: np.ndarray) -> np.ndarray:
    """Snap an upsampled soft mask to the real garment edges (guided filter)."""
    h, w = img.shape[:2]
    m = soft_mask.astype(np.float32) / 255.0 if soft_mask.dtype == np.uint8 else soft_mask.astype(np.float32)
    if m.shape != (h, w):
        m = cv2.resize(m, (w, h), interpolation=cv2.INTER_LINEAR)
    gray = cv2.cvtColor(img.astype(np.float32), cv2.COLOR_RGB2GRAY)
    r = max(2, int(round(max(h, w) * 0.004)))
    a = guided_filter(gray, m, r, 1e-3)
    # gentle contrast on alpha so edges are crisp but not aliased
    a = np.clip((a - 0.5) * 1.5 + 0.5, 0.0, 1.0)
    return a


def pick_background_color(choice: str, garment_lightness: float) -> tuple[float, float, float]:
    if choice != "auto" and choice in BACKGROUND_COLORS:
        return BACKGROUND_COLORS[choice]
    # very light garments need a slightly darker surface to keep their contour readable
    return BACKGROUND_COLORS["light_gray" if garment_lightness > 82 else "off_white"]


def clean_background(img: np.ndarray, alpha: np.ndarray, strength: float) -> np.ndarray:
    if strength <= 0:
        return img
    h, w = img.shape[:2]
    r = max(4, int(round(max(h, w) * 0.012)))
    smooth = np.dstack([fast_guided_filter(img[..., c], img[..., c], r, 1.5e-3, subsample=4) for c in range(3)])
    lab = rgb_to_lab(smooth)
    # even out large-scale shading (folds, vignetting) a little
    L = lab[..., 0]
    bg_w = (1.0 - alpha) > 0.5
    low = masked_blur(L, bg_w.astype(np.float32), 0.06 * max(h, w))
    target = float(np.percentile(L[bg_w], 75)) if bg_w.any() else float(np.median(L))
    L = L + (target - low) * 0.35 * strength
    L = L + 4.0 * strength * (1.0 - L / 100.0)  # brighten
    lab[..., 0] = np.clip(L, 0, 100)
    lab[..., 1:] *= 1.0 - 0.25 * strength  # slight neutralisation
    cleaned = lab_to_rgb(lab)
    keep_texture = 0.35
    cleaned = cleaned * (1 - keep_texture) + img * keep_texture
    mix = np.clip(strength, 0, 1)
    bg = img * (1 - mix) + cleaned * mix
    a = alpha[..., None]
    return img * a + bg * (1 - a)


def neutral_background(
    img: np.ndarray,
    alpha: np.ndarray,
    color: tuple[float, float, float],
    *,
    seed: int = 0,
) -> np.ndarray:
    h, w = img.shape[:2]
    size = max(h, w)
    a = alpha[..., None]

    # --- new surface: very subtle vertical gradient + fine grain (avoids a flat CGI look)
    yy = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    surface = np.asarray(color, np.float32)[None, None, :] * (1.012 - 0.03 * yy)
    rng = np.random.default_rng(seed)
    grain = cv2.GaussianBlur(rng.standard_normal((h, w)).astype(np.float32), (0, 0), 0.7) * 0.004
    surface = surface + grain[..., None]

    # --- natural shadow transferred from the original photo
    L = cv2.cvtColor(img.astype(np.float32), cv2.COLOR_RGB2GRAY)
    bg_weight = (alpha < 0.05).astype(np.float32)
    far = cv2.dilate((alpha > 0.5).astype(np.uint8), np.ones((3, 3), np.uint8))
    dist = cv2.distanceTransform((1 - far).astype(np.uint8), cv2.DIST_L2, 5)
    ring = np.exp(-dist / (0.05 * size))
    bg_level = float(np.percentile(L[bg_weight > 0], 70)) if bg_weight.any() else float(L.mean())
    local_bg = masked_blur(L, bg_weight, 0.004 * size + 1)
    shade = np.clip(local_bg / max(bg_level, 1e-3), 0.5, 1.0)
    shade = 1.0 - (1.0 - shade) * ring * 0.8
    shade = cv2.GaussianBlur(shade, (0, 0), 0.006 * size + 1)

    # --- faint contact shadow (ambient occlusion right under the garment)
    hard = (alpha > 0.5).astype(np.float32)
    contact = cv2.GaussianBlur(hard, (0, 0), 0.012 * size + 1)
    contact = np.roll(contact, int(0.006 * size), axis=0)
    shade = shade * (1.0 - 0.14 * contact * (1.0 - hard))
    surface = np.clip(surface * shade[..., None], 0, 1)

    # --- edge decontamination: remove the old background colour from edge pixels
    old_bg = masked_blur(img, bg_weight, 0.006 * size + 1)
    fg_prop = masked_blur(img, (alpha > 0.95).astype(np.float32), 0.004 * size + 1)
    safe_a = np.maximum(a, 1e-3)
    fg = np.clip((img - (1 - a) * old_bg) / safe_a, 0, 1)
    edge = (a > 0.02) & (a < 0.98)
    low_alpha = a < 0.35
    fg = np.where(edge & low_alpha, fg_prop, fg)
    fg = np.where(edge, fg, img)

    out = fg * a + surface * (1 - a)
    return np.clip(out, 0, 1)


def soften_alpha_for_composite(alpha: np.ndarray) -> np.ndarray:
    size = max(alpha.shape)
    return np.clip(fast_guided_filter(alpha, alpha, max(1, int(size * 0.0015)), 1e-4, subsample=1), 0, 1)
