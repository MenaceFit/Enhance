"""Default provider: the in-house classical computer-vision engine.

Runs on CPU, costs nothing per image, is fully deterministic and — by
construction — never generates content: every operation is a measurable
transform of the original pixels. It implements every capability, so it is
also the universal fallback of the router.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from app.imaging.analysis.clothing import analyze_clothing
from app.imaging.analysis.defects import detect_defects
from app.imaging.analysis.dust import detect_specks
from app.imaging.analysis.segmentation import segment_garment
from app.imaging.color import to_float, to_uint8
from app.imaging.ops.detail import classical_upscale
from app.imaging.ops.dust_removal import removal_mask, remove_specks
from app.imaging.render import RenderResult, RenderSource, Upscaler, render
from app.imaging.settings import EnhancementSettings
from app.providers.base import Capability, ImageEnhancementProvider


class LocalCVProvider(ImageEnhancementProvider):
    name = "local"
    display_name = "Moteur local (vision classique)"
    version = "1.0"
    capabilities = frozenset(
        {
            Capability.SEGMENTATION,
            Capability.CLOTHING_DETECTION,
            Capability.DUST_DETECTION,
            Capability.DEFECT_DETECTION,
            Capability.ENHANCEMENT,
            Capability.UPSCALING,
        }
    )
    generative = frozenset()
    cost_cents = {c: 0.0 for c in capabilities}

    def model_for(self, capability: Capability) -> str | None:
        return f"local-cv-{self.version}"

    def segment(self, image):
        return segment_garment(image)

    def detect_clothing(self, image, mask, gains=None):
        return analyze_clothing(image, mask, gains)

    def detect_dust(self, image, mask):
        return detect_specks(image, mask)

    def remove_dust(self, image, labels, ids):
        h, w = image.shape[:2]
        return remove_specks(image, removal_mask(labels, ids, w, h))

    def detect_defects(self, image, mask, specks, holes=None):
        return detect_defects(image, mask, specks, holes)

    def correct_colors(self, image: np.ndarray, source: RenderSource, settings: EnhancementSettings) -> np.ndarray:
        only_color = settings.model_copy(
            update={"placement": 0, "cleaning": 0, "wrinkles": "off", "background": "keep", "sharpness": 0, "aspect": "original"}
        )
        res = render(RenderSource(image, source.mask, source.labels, source.analysis), only_color, max(image.shape[:2]), checks=False)
        return res.after

    def enhance_image(
        self,
        source: RenderSource,
        settings: EnhancementSettings,
        target_long_side: int,
        *,
        upscaler: Upscaler | None = None,
        use_consistency: bool = False,
    ) -> RenderResult:
        return render(source, settings, target_long_side, upscaler=upscaler, use_consistency=use_consistency)

    def upscale_image(self, image: np.ndarray, width: int, height: int) -> np.ndarray:
        f = to_float(image)
        out = classical_upscale(f, width, height)
        return out if image.dtype != np.uint8 else to_uint8(out)

    def generate_listing(self, image: np.ndarray, attributes: Any) -> dict[str, Any]:
        from app.services.listing import listing_from_attributes

        return listing_from_attributes(attributes)
