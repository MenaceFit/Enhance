"""AI provider abstraction.

Every model/vendor is wrapped in an :class:`ImageEnhancementProvider` that
declares which *capabilities* it serves, which of them are *generative*
(synthesise new pixels — forbidden when "Préserver l'article" is on), and
what each call costs. The :class:`~app.providers.router.ProviderRouter`
chooses a provider per capability from configuration, falls back to the local
engine on failure, and records duration and cost of every call so they can be
tracked in the admin dashboard and compared in benchmarks.

Swapping a model therefore means writing one adapter and changing one line of
configuration (``AI_ROUTING``) — the rest of the application is unaware.
"""

from __future__ import annotations

from abc import ABC
from enum import StrEnum
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from app.imaging.render import RenderResult, RenderSource, Upscaler
    from app.imaging.settings import EnhancementSettings
    from app.imaging.types import BBox, ClothingAttributes, Defect, Segmentation, Speck


class Capability(StrEnum):
    SEGMENTATION = "segmentation"
    CLOTHING_DETECTION = "clothing_detection"
    DUST_DETECTION = "dust_detection"
    DEFECT_DETECTION = "defect_detection"
    ENHANCEMENT = "enhancement"
    UPSCALING = "upscaling"
    LISTING = "listing"  # V2: title/description generation from the photo


class ProviderError(RuntimeError):
    pass


class ImageEnhancementProvider(ABC):  # noqa: B024 - capabilities are opt-in, not abstract
    name: str = "base"
    display_name: str = "Base"
    version: str = "0"
    capabilities: frozenset[Capability] = frozenset()
    generative: frozenset[Capability] = frozenset()
    #: estimated cost per call in euro cents, per capability
    cost_cents: dict[Capability, float] = {}

    def is_available(self) -> bool:
        return True

    def model_for(self, capability: Capability) -> str | None:
        return None

    def call_cost(self, capability: Capability) -> float:
        """Cost of the call that just finished (providers with usage-based billing override this)."""
        return float(self.cost_cents.get(capability, 0.0))

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "version": self.version,
            "available": self.is_available(),
            "capabilities": sorted(c.value for c in self.capabilities),
            "generative": sorted(c.value for c in self.generative),
            "cost_cents": {c.value: v for c, v in self.cost_cents.items()},
            "models": {c.value: self.model_for(c) for c in self.capabilities},
        }

    # --- capability methods (override the ones you declare) ---------------------------------
    def segment(self, image: np.ndarray) -> tuple[np.ndarray, Segmentation, list[BBox]]:
        raise NotImplementedError

    def detect_clothing(self, image: np.ndarray, mask: np.ndarray, gains: Any = None) -> ClothingAttributes:
        raise NotImplementedError

    def detect_dust(self, image: np.ndarray, mask: np.ndarray) -> tuple[np.ndarray, list[Speck]]:
        raise NotImplementedError

    def remove_dust(self, image: np.ndarray, labels: np.ndarray, ids: list[int]) -> np.ndarray:
        raise NotImplementedError

    def detect_defects(
        self, image: np.ndarray, mask: np.ndarray, specks: list[Speck], holes: list[BBox] | None = None
    ) -> list[Defect]:
        raise NotImplementedError

    def correct_colors(self, image: np.ndarray, source: RenderSource, settings: EnhancementSettings) -> np.ndarray:
        raise NotImplementedError

    def enhance_image(
        self,
        source: RenderSource,
        settings: EnhancementSettings,
        target_long_side: int,
        *,
        upscaler: Upscaler | None = None,
        use_consistency: bool = False,
    ) -> RenderResult:
        raise NotImplementedError

    def upscale_image(self, image: np.ndarray, width: int, height: int) -> np.ndarray:
        raise NotImplementedError

    def generate_listing(self, image: np.ndarray, attributes: ClothingAttributes) -> dict[str, Any]:
        raise NotImplementedError
