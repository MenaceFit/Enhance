"""Compare AI provider configurations on the same images.

A *profile* is a routing table (capability → provider). Every profile runs the
full pipeline on every image; we record quality gain, colour fidelity,
structural score, duration, cost and failures. On synthetic images (ground
truth known) we also measure dust recall, whether the stain was kept and the
garment colour error against the true colour.

Used by the admin dashboard (``POST /admin/benchmarks``) and the CLI
(``python -m app.benchmark``).
"""

from __future__ import annotations

import statistics
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

import cv2
import numpy as np

from app.imaging.color import delta_e_2000, rgb_to_lab
from app.imaging.pipeline import analyze, enhance
from app.imaging.render import RenderSource
from app.imaging.settings import EnhancementSettings
from app.imaging.synthetic import CATEGORIES, SceneTruth, make_scene
from app.providers.base import ImageEnhancementProvider
from app.providers.router import ProviderRouter

PRESET_PROFILES: dict[str, dict[str, str]] = {
    "local": {},
    "rembg": {"segmentation": "rembg"},
    "claude": {"clothing_detection": "anthropic", "defect_detection": "anthropic"},
    "rembg+claude": {"segmentation": "rembg", "clothing_detection": "anthropic", "defect_detection": "anthropic"},
    "replicate-sr": {"upscaling": "replicate"},
}


@dataclass
class BenchmarkImage:
    name: str
    pixels: np.ndarray
    truth: SceneTruth | None = None


@dataclass
class ImageResult:
    image: str
    profile: str
    ok: bool
    duration_ms: float = 0.0
    cost_cents: float = 0.0
    quality_before: int | None = None
    quality_after: int | None = None
    fidelity: int | None = None
    structure: int | None = None
    auto_adjusted: bool = False
    needs_validation: bool = False
    category: str | None = None
    providers: dict[str, str] = field(default_factory=dict)
    truth: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


def synthetic_set(count: int = 10, size: tuple[int, int] = (900, 1200), seed: int = 100) -> list[BenchmarkImage]:
    rng = np.random.default_rng(seed)
    images = []
    for i in range(count):
        cat = CATEGORIES[i % len(CATEGORIES)]
        cast = (float(rng.uniform(0.95, 1.15)), 1.0, float(rng.uniform(0.75, 1.05)))
        img, truth = make_scene(
            cat, size[0], size[1], seed=seed + i, cast=cast, exposure=float(rng.uniform(0.7, 1.0)),
            tilt=float(rng.uniform(-6, 6)), scale=float(rng.uniform(0.6, 0.85)),
        )
        images.append(BenchmarkImage(f"synthetic-{i:02d}-{cat}", img, truth))
    return images


def _truth_metrics(img: BenchmarkImage, bundle, result) -> dict[str, Any]:
    t = img.truth
    if t is None:
        return {}
    h, w = img.pixels.shape[:2]
    specks = bundle.analysis.specks
    found = sum(any(abs(s.bbox.cx - x) * w < 7 and abs(s.bbox.cy - y) * h < 7 for s in specks) for x, y in t.specks)
    stain_kept = None
    if t.stain_bbox is not None:
        sb = t.stain_bbox
        stain_kept = any(abs(d.bbox.cx - sb.cx) < 0.04 and abs(d.bbox.cy - sb.cy) < 0.04 for d in bundle.analysis.defects)
    m = cv2.erode((result.mask > 127).astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
    color_error = None
    if m.sum() > 100:
        out_lab = np.median(rgb_to_lab(cv2.GaussianBlur(result.after.astype(np.float32) / 255, (0, 0), 2))[m], axis=0)
        true_lab = rgb_to_lab(np.array([[t.garment_rgb]], np.float32))[0, 0]
        # compare chroma/hue only: the scene shading darkens the garment's flat albedo
        color_error = float(delta_e_2000(out_lab, np.array([out_lab[0], true_lab[1], true_lab[2]])))
    return {
        "dust_recall": round(found / max(1, len(t.specks)), 3),
        "stain_reported": stain_kept,
        "category_correct": bundle.analysis.clothing.category == t.category,
        "garment_color_error": round(color_error, 2) if color_error is not None else None,
    }


def run_benchmark(
    images: list[BenchmarkImage],
    profiles: dict[str, dict[str, str]],
    providers: dict[str, ImageEnhancementProvider],
    *,
    settings: EnhancementSettings | None = None,
    target_long_side: int = 1200,
    progress: Callable[[float], None] | None = None,
) -> dict[str, Any]:
    settings = settings or EnhancementSettings()
    results: list[ImageResult] = []
    total = max(1, len(images) * len(profiles))
    done = 0
    for profile_name, routing in profiles.items():
        router = ProviderRouter(providers, routing, fallback="local", preserve_article=settings.preserve_article)
        for img in images:
            t0 = time.perf_counter()
            try:
                bundle = analyze(img.pixels, router)
                outcome = enhance(
                    RenderSource(img.pixels, bundle.mask, bundle.labels, bundle.analysis), settings, router,
                    target_long_side=target_long_side,
                )
                r = outcome.result
                stages = bundle.stages + outcome.stages
                results.append(
                    ImageResult(
                        image=img.name,
                        profile=profile_name,
                        ok=True,
                        duration_ms=round((time.perf_counter() - t0) * 1000, 1),
                        cost_cents=round(sum(s.cost_cents for s in stages), 4),
                        quality_before=bundle.analysis.quality.score,
                        quality_after=r.quality.score if r.quality else None,
                        fidelity=r.fidelity.score if r.fidelity else None,
                        structure=r.structure.score if r.structure else None,
                        auto_adjusted=bool(outcome.auto_adjustments),
                        needs_validation=outcome.needs_validation,
                        category=bundle.analysis.clothing.category,
                        providers={s.name: s.provider for s in stages if s.provider},
                        truth=_truth_metrics(img, bundle, r),
                    )
                )
            except Exception as exc:  # noqa: BLE001 - a failing provider is a benchmark result
                results.append(
                    ImageResult(img.name, profile_name, ok=False, duration_ms=round((time.perf_counter() - t0) * 1000, 1), error=str(exc)[:300])
                )
            done += 1
            if progress:
                progress(done / total)
    return {"results": [asdict(r) for r in results], "summary": summarize(results)}


def _mean(values) -> float | None:
    vals = [v for v in values if v is not None]
    return round(statistics.fmean(vals), 2) if vals else None


def summarize(results: list[ImageResult]) -> list[dict[str, Any]]:
    out = []
    for profile in dict.fromkeys(r.profile for r in results):
        rs = [r for r in results if r.profile == profile]
        ok = [r for r in rs if r.ok]
        durations = sorted(r.duration_ms for r in ok)
        out.append({
            "profile": profile,
            "images": len(rs),
            "error_rate": round(1 - len(ok) / len(rs), 3) if rs else 0.0,
            "quality_gain": _mean((r.quality_after or 0) - (r.quality_before or 0) for r in ok),
            "quality_after": _mean(r.quality_after for r in ok),
            "fidelity": _mean(r.fidelity for r in ok),
            "structure": _mean(r.structure for r in ok),
            "auto_adjusted_rate": round(sum(r.auto_adjusted for r in ok) / len(ok), 3) if ok else None,
            "duration_ms_p50": durations[len(durations) // 2] if durations else None,
            "duration_ms_p95": durations[min(len(durations) - 1, int(len(durations) * 0.95))] if durations else None,
            "cost_cents_total": round(sum(r.cost_cents for r in ok), 3),
            "cost_cents_per_image": _mean(r.cost_cents for r in ok),
            "dust_recall": _mean(r.truth.get("dust_recall") for r in ok),
            "stain_reported_rate": _mean(
                (1.0 if r.truth.get("stain_reported") else 0.0) for r in ok if r.truth.get("stain_reported") is not None
            ),
            "category_accuracy": _mean(
                (1.0 if r.truth.get("category_correct") else 0.0) for r in ok if "category_correct" in r.truth
            ),
            "garment_color_error": _mean(r.truth.get("garment_color_error") for r in ok),
        })
    return out
