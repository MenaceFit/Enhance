"""End-to-end pipeline: analysis → non-destructive enhancement → guards.

    UPLOAD → IMAGE QUALITY → CLOTHING DETECTION → SEGMENTATION → DEFECTS → DUST
    → COLOR → LIGHTING → COMPOSITION → ENHANCEMENT → COLOR FIDELITY CHECK
    → STRUCTURE (ANTI-HALLUCINATION) CHECK → FINAL QUALITY CHECK

Each AI capability is resolved through the provider router, so stages can be
served by different models. If a guard fails, the render is retried with a
reduced intensity before being flagged to the user for validation.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

import cv2
import numpy as np

from app.imaging.analysis.composition import plan_composition
from app.imaging.analysis.exposure import analyze_exposure
from app.imaging.analysis.illuminant import estimate_illuminant
from app.imaging.analysis.quality import assess_quality
from app.imaging.image_io import resize_long_side
from app.imaging.render import RenderResult, RenderSource
from app.imaging.settings import PRESETS, EnhancementSettings
from app.imaging.types import Analysis, StageRecord
from app.providers.base import Capability
from app.providers.router import ProviderRouter

ANALYSIS_LONG_SIDE = 1600

ProgressFn = Callable[[str, str, float], None]

# (stage key, user-facing label, progress at the end of the stage)
ANALYSIS_STAGES = [
    ("quality", "Analyse de la qualité de la photo", 0.08),
    ("segmentation", "Détection du vêtement", 0.22),
    ("clothing_detection", "Identification du vêtement", 0.3),
    ("dust_detection", "Recherche des poussières", 0.4),
    ("defect_detection", "Détection des imperfections", 0.5),
    ("color", "Analyse des couleurs", 0.56),
    ("lighting", "Analyse de la lumière", 0.6),
    ("composition", "Analyse du cadrage", 0.65),
]
ENHANCE_STAGES = [
    ("enhancement", "Amélioration non destructive", 0.85),
    ("fidelity", "Contrôle de la fidélité des couleurs", 0.92),
    ("final", "Contrôle qualité final", 1.0),
]


@dataclass
class AnalysisBundle:
    analysis: Analysis
    mask: np.ndarray
    labels: np.ndarray
    stages: list[StageRecord] = field(default_factory=list)


@dataclass
class EnhanceOutcome:
    result: RenderResult
    settings: EnhancementSettings
    auto_adjustments: list[str]
    needs_validation: bool
    stages: list[StageRecord]


def _noop(stage: str, label: str, progress: float) -> None:  # pragma: no cover - trivial
    pass


def analyze(image: np.ndarray, router: ProviderRouter, progress: ProgressFn | None = None) -> AnalysisBundle:
    progress = progress or _noop
    stages: list[StageRecord] = []
    img = resize_long_side(image, ANALYSIS_LONG_SIDE)
    h, w = img.shape[:2]

    def local_stage(key: str, label: str, t0: float, **details) -> None:
        stages.append(StageRecord(key, label, round((time.perf_counter() - t0) * 1000, 1), "local", None, 0.0, details))

    labels_by_key = {k: (lbl, p) for k, lbl, p in ANALYSIS_STAGES}

    progress("quality", labels_by_key["quality"][0], 0.02)
    progress("segmentation", labels_by_key["segmentation"][0], 0.08)
    mask, seg, holes = router.call(Capability.SEGMENTATION, "segment", img)
    progress("clothing_detection", labels_by_key["clothing_detection"][0], 0.22)

    t0 = time.perf_counter()
    illuminant = estimate_illuminant(img, mask)
    local_stage("color", labels_by_key["color"][0], t0, cast=illuminant.cast_label, confidence=illuminant.confidence)

    # Garment attributes are read on a straightened view (central zips, symmetry...).
    composition = plan_composition(mask, seg)
    c_img, c_mask = img, mask
    if composition.tilt_confidence >= 0.3 and abs(composition.tilt_deg) >= 0.6:
        rot = cv2.getRotationMatrix2D((w / 2, h / 2), -composition.tilt_deg, 1.0)
        c_img = cv2.warpAffine(img, rot, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        c_mask = cv2.warpAffine(mask, rot, (w, h), flags=cv2.INTER_LINEAR)
    clothing = router.call(Capability.CLOTHING_DETECTION, "detect_clothing", c_img, c_mask, illuminant.gains)
    progress("dust_detection", labels_by_key["dust_detection"][0], 0.3)
    labels, specks = router.call(Capability.DUST_DETECTION, "detect_dust", img, mask)
    progress("defect_detection", labels_by_key["defect_detection"][0], 0.4)
    defects = router.call(Capability.DEFECT_DETECTION, "detect_defects", img, mask, specks, holes)
    progress("color", labels_by_key["color"][0], 0.5)

    t0 = time.perf_counter()
    exposure = analyze_exposure(img, mask, illuminant.gains)
    local_stage("lighting", labels_by_key["lighting"][0], t0, gain=exposure.gain)
    progress("lighting", labels_by_key["lighting"][0], 0.56)

    local_stage("composition", labels_by_key["composition"][0], time.perf_counter(), tilt=composition.tilt_deg)
    progress("composition", labels_by_key["composition"][0], 0.6)

    t0 = time.perf_counter()
    quality = assess_quality(
        img, mask,
        cast_strength=illuminant.cast_strength if illuminant.confidence > 0.2 else 0.0,
        tilt_deg=composition.tilt_deg if composition.tilt_confidence >= 0.3 else 0.0,
        speck_count=len(specks),
        source_long_side=max(image.shape[:2]),
    )
    local_stage("quality", labels_by_key["quality"][0], t0, score=quality.score)

    warnings: list[str] = []
    if seg.confidence < 0.45:
        warnings.append("Le vêtement est difficile à distinguer du fond : le fond propre est désactivé.")
    if sum(seg.touches.values()) >= 2:
        warnings.append("Le vêtement touche les bords de la photo : rien ne sera inventé hors cadre.")
    if quality.breakdown.get("nettete", 100) < 35:
        warnings.append("Photo floue : reprendre la photo donnera un meilleur résultat.")
    if max(image.shape[:2]) < 800:
        warnings.append("Résolution faible : l'amélioration de résolution sera appliquée.")

    analysis = Analysis(
        width=w, height=h, quality=quality, segmentation=seg, clothing=clothing, illuminant=illuminant,
        exposure=exposure, composition=composition, specks=specks, defects=defects, warnings=warnings,
    )
    stages = router.drain_records() + stages
    progress("composition", labels_by_key["composition"][0], 0.65)
    return AnalysisBundle(analysis=analysis, mask=mask, labels=labels, stages=stages)


def _reduced(settings: EnhancementSettings, factor: float, *, structural: bool) -> EnhancementSettings:
    preset = PRESETS[settings.intensity]

    def scaled(name: str) -> int:
        v = getattr(settings, name)
        v = preset[name] if v is None else v
        return int(round(v * factor))

    update: dict = {"color": scaled("color"), "hue": 0}
    if structural:
        update.update({"wrinkles": "off", "sharpness": scaled("sharpness"), "upscale": "off" if settings.upscale == "2x" else settings.upscale})
    return settings.model_copy(update=update)


def enhance(
    source: RenderSource,
    settings: EnhancementSettings,
    router: ProviderRouter,
    *,
    target_long_side: int = 1280,
    use_consistency: bool = False,
    progress: ProgressFn | None = None,
    auto_guard: bool = True,
) -> EnhanceOutcome:
    progress = progress or _noop
    progress("enhancement", ENHANCE_STAGES[0][1], 0.7)
    router = router.with_options(preserve_article=settings.preserve_article)
    upscaler = router.upscaler()

    def run(s: EnhancementSettings) -> RenderResult:
        return router.call(
            Capability.ENHANCEMENT, "enhance_image", source, s, target_long_side,
            upscaler=upscaler, use_consistency=use_consistency,
        )

    result = run(settings)
    progress("fidelity", ENHANCE_STAGES[1][1], 0.88)
    adjustments: list[str] = []
    current = settings
    if auto_guard:
        for attempt in range(2):
            color_bad = result.fidelity is not None and not result.fidelity.passed
            struct_bad = result.structure is not None and not result.structure.passed
            if not (color_bad or struct_bad):
                break
            factor = 0.5 if attempt == 0 else 0.25
            current = _reduced(current, factor, structural=struct_bad)
            if color_bad:
                adjustments.append("Correction couleur réduite automatiquement pour rester fidèle à l'article.")
            if struct_bad:
                adjustments.append("Intensité réduite automatiquement : modification potentiellement excessive détectée.")
            result = run(current)

    needs_validation = bool(
        (result.fidelity and not result.fidelity.passed) or (result.structure and not result.structure.passed)
    )
    if needs_validation:
        result.warnings.append("⚠️ Modification potentiellement excessive détectée : vérifie le résultat avant de l'utiliser.")
    progress("final", ENHANCE_STAGES[2][1], 0.97)
    return EnhanceOutcome(
        result=result,
        settings=current,
        auto_adjustments=list(dict.fromkeys(adjustments)),
        needs_validation=needs_validation,
        stages=router.drain_records(),
    )
