"""Non-destructive renderer: (working image, analysis, settings) → enhanced image.

A render is a pure function of its inputs, so every version stored in the
history can be reproduced exactly at any resolution (preview, export). The
order of operations matters for quality:

  dust removal → white balance → exposure → wrinkles → contrast → vibrance/hue
  → background → geometry (straighten/frame) → upscale → sharpen → checks
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

import cv2
import numpy as np

from app.imaging.analysis.defects import defect_protection_mask, protected_speck_ids
from app.imaging.analysis.dust import speck_removal_ids
from app.imaging.analysis.illuminant import effective_gains, estimate_illuminant
from app.imaging.analysis.quality import assess_quality
from app.imaging.checks.fidelity import color_fidelity
from app.imaging.checks.structure import structural_check
from app.imaging.color import (
    LUMA_LINEAR,
    lab_to_rgb,
    linear_to_srgb,
    rgb_to_lab,
    srgb_to_linear,
    to_float,
    to_uint8,
)
from app.imaging.filters import masked_blur
from app.imaging.ops.background import (
    clean_background,
    neutral_background,
    pick_background_color,
    refine_alpha,
)
from app.imaging.ops.detail import classical_upscale, sharpen
from app.imaging.ops.dust_removal import removal_mask, remove_specks
from app.imaging.ops.geometry import apply_geometry, output_size, plan_geometry, residual_tilt
from app.imaging.ops.tone import contrast_lab, exposure_linear, vibrance_hue_lab
from app.imaging.ops.wrinkles import reduce_wrinkles
from app.imaging.settings import EnhancementSettings, ResolvedSettings
from app.imaging.types import Analysis, FidelityReport, QualityReport, StructureReport

MAX_OUTPUT_LONG_SIDE = 3072
MIN_SEGMENTATION_CONFIDENCE_FOR_NEUTRAL = 0.45
PAD_PLACEHOLDER = (0.93, 0.93, 0.92)

Upscaler = Callable[[np.ndarray, int, int], np.ndarray]


@dataclass
class RenderSource:
    image: np.ndarray  # uint8 RGB working image (already oriented, sRGB)
    mask: np.ndarray  # uint8 soft garment mask (any resolution)
    labels: np.ndarray  # uint16 speck label map (analysis resolution)
    analysis: Analysis


@dataclass
class RenderResult:
    after: np.ndarray  # uint8
    before: np.ndarray  # uint8, original pixels with the same framing (for the comparator)
    mask: np.ndarray  # uint8, aligned garment mask
    settings: ResolvedSettings
    fidelity: FidelityReport | None
    structure: StructureReport | None
    quality: QualityReport | None
    applied: dict[str, bool]
    removed_specks: list[int]
    geometry: dict
    upscale_factor: float
    warnings: list[str] = field(default_factory=list)
    timings: dict[str, float] = field(default_factory=dict)


def _resize(img: np.ndarray, w: int, h: int, interp: int | None = None) -> np.ndarray:
    if img.shape[1] == w and img.shape[0] == h:
        return img
    if interp is None:
        interp = cv2.INTER_AREA if w * h < img.shape[0] * img.shape[1] else cv2.INTER_LINEAR
    return cv2.resize(img, (w, h), interpolation=interp)


def render(
    src: RenderSource,
    settings: EnhancementSettings,
    target_long_side: int = 1280,
    *,
    checks: bool = True,
    upscaler: Upscaler | None = None,
    use_consistency: bool = False,
) -> RenderResult:
    t_start = time.perf_counter()
    timings: dict[str, float] = {}

    def tick(name: str, t0: float) -> float:
        now = time.perf_counter()
        timings[name] = round((now - t0) * 1000, 1)
        return now

    r = settings.resolved()
    A = src.analysis
    warnings: list[str] = []
    if r.capped:
        warnings.append("Certains réglages ont été limités par « Préserver l'article ».")
    original_mode = r.intensity == "original"
    aspect = "original" if original_mode else r.aspect

    H0, W0 = src.image.shape[:2]
    background = r.background
    if background == "neutral" and A.segmentation.confidence < MIN_SEGMENTATION_CONFIDENCE_FOR_NEUTRAL:
        background = "clean"
        warnings.append("Fond propre désactivé : le détourage du vêtement est incertain sur cette photo.")

    t0 = time.perf_counter()
    plan = plan_geometry(
        src.mask, W0, H0,
        tilt_deg=A.composition.tilt_deg,
        tilt_confidence=A.composition.tilt_confidence,
        touches=A.segmentation.touches,
        placement=0.0 if original_mode else r.placement,
        aspect=aspect,
        allow_padding=background == "neutral",
    )
    crop_long = max(plan.width, plan.height)

    factor = 1.0
    if not original_mode:
        if r.upscale == "2x":
            factor = min(2.0, MAX_OUTPUT_LONG_SIDE / crop_long)
        elif r.upscale == "auto" and crop_long < 0.9 * min(target_long_side, 1600):
            factor = min(2.0, target_long_side / crop_long)
    out_long = int(round(min(crop_long * max(1.0, factor), target_long_side, MAX_OUTPUT_LONG_SIDE)))
    factor = max(1.0, out_long / crop_long)
    work_scale = min(1.0, out_long / crop_long)

    img = src.image
    if work_scale < 0.999:
        Ww, Hw = max(1, round(W0 * work_scale)), max(1, round(H0 * work_scale))
        img = _resize(img, Ww, Hw)
        plan = plan.scaled(Ww / W0)
    Hw, Ww = img.shape[:2]
    if factor > 1:
        geo_w, geo_h = max(1, round(plan.width)), max(1, round(plan.height))
        out_w, out_h = output_size(plan, out_long)
    else:
        geo_w, geo_h = output_size(plan, out_long)
        out_w, out_h = geo_w, geo_h
    t0 = tick("plan", t0)

    original = to_float(img)
    f = original
    alpha = refine_alpha(original, src.mask)
    t0 = tick("alpha", t0)

    # 1. dust and hair (only confirmed parasites; defects are protected)
    protected = protected_speck_ids(A.defects)
    ids = [] if original_mode else speck_removal_ids(A.specks, r.cleaning, r.retouch_specks, protected)
    if ids:
        dm = removal_mask(src.labels, ids, Ww, Hw)
        f = to_float(remove_specks(to_uint8(f), dm))
    t0 = tick("dust", t0)

    # 2-3. light: white balance (from background) + exposure, in linear light
    lin = srgb_to_linear(f)
    wb_strength = 0.0 if original_mode else min(1.0, r.light * 1.5)
    consistency = A.consistency if (use_consistency and A.consistency) else None
    if consistency and consistency.get("gains"):
        g = np.asarray(consistency["gains"], np.float32)
        g = np.exp(np.log(g) * wb_strength)
        gains = (g / float(g @ LUMA_LINEAR)).astype(np.float32)
    else:
        gains = effective_gains(A.illuminant, wb_strength)
    exp_strength = 0.0 if original_mode else min(1.0, r.light * 1.3)
    exp_gain = 1.0 + (A.exposure.gain - 1.0) * exp_strength
    if consistency and consistency.get("exposure_factor"):
        exp_gain *= float(consistency["exposure_factor"]) ** exp_strength
    lin = lin * gains.reshape(1, 1, 3)
    if exp_strength > 0 or abs(exp_gain - 1) > 1e-3:
        lin = exposure_linear(lin, exp_gain, shadow_lift=0.6 * r.light)
    lit = linear_to_srgb(lin)
    t0 = tick("light", t0)

    # 4-6. shape-preserving tonal work on L*, then chroma
    out = lit
    if not original_mode and (r.wrinkle_strength > 0 or r.color > 0 or r.hue_deg):
        lab = rgb_to_lab(lit)
        if r.wrinkle_strength > 0:
            protect = defect_protection_mask(A.defects, Ww, Hw)
            lab = reduce_wrinkles(lab, alpha, r.wrinkle_strength, protect)
        t0 = tick("wrinkles", t0)
        lab = contrast_lab(lab, r.color, black_point_p=A.exposure.p01)
        lab = vibrance_hue_lab(lab, vibrance=0.12 * r.color, hue_deg=r.hue_deg)
        out = lab_to_rgb(lab)
        t0 = tick("color", t0)

    # 7. background
    bg_color = None
    if not original_mode and background == "clean":
        out = clean_background(out, alpha, strength=0.45 + 0.45 * r.cleaning)
    elif not original_mode and background == "neutral":
        garment_L = float(np.median(rgb_to_lab(out)[..., 0][alpha > 0.5])) if (alpha > 0.5).any() else 50.0
        bg_color = pick_background_color(r.background_color, garment_L)
        out = neutral_background(out, alpha, bg_color)
    t0 = tick("background", t0)

    # 8. geometry (same transform for every aligned layer)
    border = tuple(float(c) for c in bg_color) if bg_color else None
    after = apply_geometry(out, plan, geo_w, geo_h, border_value=border)
    before = apply_geometry(original, plan, geo_w, geo_h, border_value=border or (PAD_PLACEHOLDER if plan.padded else None))
    ref = apply_geometry(lit, plan, geo_w, geo_h, border_value=border)
    mask_al = apply_geometry(alpha, plan, geo_w, geo_h, border_value=0.0)
    t0 = tick("geometry", t0)

    # 9. upscale (provider hook; classical Lanczos + detail recovery by default)
    if factor > 1 and (out_w, out_h) != (geo_w, geo_h):
        after = (upscaler or classical_upscale)(np.clip(after, 0, 1), out_w, out_h)
        before = _resize(before, out_w, out_h, cv2.INTER_LANCZOS4)
        ref = _resize(ref, out_w, out_h, cv2.INTER_LINEAR)
        mask_al = _resize(mask_al, out_w, out_h, cv2.INTER_LINEAR)
    t0 = tick("upscale", t0)

    # 10. sharpen at output resolution
    if not original_mode and r.sharpness > 0:
        after = sharpen(np.clip(after, 0, 1), 0.9 * r.sharpness)
    t0 = tick("sharpen", t0)

    after_u8 = to_uint8(after)
    before_u8 = to_uint8(before)
    mask_u8 = to_uint8(np.clip(mask_al, 0, 1))

    fidelity = structure = quality = None
    if checks:
        fidelity = color_fidelity(ref, after, mask_u8)
        structure_ref = ref
        if background == "neutral":
            # Compare like with like: put the reference on the output's new surface so that the
            # background change itself is not mistaken for a silhouette change.
            a = np.clip(mask_al, 0, 1)[..., None]
            far = (mask_al < 0.02).astype(np.float32)
            surface = masked_blur(after, far, 0.02 * max(after.shape[:2]))
            structure_ref = ref * a + surface * (1 - a)
        structure = structural_check(structure_ref, after, mask_u8)
        residual = estimate_illuminant(after_u8, mask_u8)
        quality = assess_quality(
            after_u8, mask_u8,
            cast_strength=residual.cast_strength if residual.confidence > 0.2 else 0.0,
            tilt_deg=residual_tilt(A.composition.tilt_deg, plan) if A.composition.tilt_confidence >= 0.3 else 0.0,
            speck_count=max(0, len(A.specks) - len(ids)),
            source_long_side=max(after_u8.shape[:2]),
        )
        tick("checks", t0)

    applied = {
        "cleaned": bool(ids) or (not original_mode and r.cleaning > 0),
        "light": wb_strength > 0 or exp_strength > 0,
        "colors": not original_mode and (r.color > 0 or bool(r.hue_deg) or wb_strength > 0),
        "framing": not plan.is_identity,
        "wrinkles": not original_mode and r.wrinkle_strength > 0,
        "background": not original_mode and background != "keep",
        "upscaled": factor > 1,
        "sharpened": not original_mode and r.sharpness > 0,
    }
    timings["total"] = round((time.perf_counter() - t_start) * 1000, 1)
    return RenderResult(
        after=after_u8,
        before=before_u8,
        mask=mask_u8,
        settings=r,
        fidelity=fidelity,
        structure=structure,
        quality=quality,
        applied=applied,
        removed_specks=ids,
        geometry={**plan.to_dict(), "output": [after_u8.shape[1], after_u8.shape[0]], "background": background},
        upscale_factor=round(factor, 3),
        warnings=warnings,
        timings=timings,
    )
