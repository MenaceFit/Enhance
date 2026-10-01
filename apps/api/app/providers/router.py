"""Per-capability routing with fallback, preserve-mode guard and cost tracking."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from app.imaging.types import StageRecord
from app.providers.base import Capability, ImageEnhancementProvider, ProviderError

log = logging.getLogger(__name__)

STAGE_LABELS = {
    Capability.SEGMENTATION: "Détection du vêtement",
    Capability.CLOTHING_DETECTION: "Identification du vêtement",
    Capability.DUST_DETECTION: "Détection des poussières",
    Capability.DEFECT_DETECTION: "Détection des imperfections",
    Capability.ENHANCEMENT: "Amélioration non destructive",
    Capability.UPSCALING: "Amélioration de la résolution",
    Capability.LISTING: "Génération de l'annonce",
}


class ProviderRouter:
    def __init__(
        self,
        providers: dict[str, ImageEnhancementProvider],
        routing: dict[str, str] | None = None,
        *,
        fallback: str = "local",
        preserve_article: bool = True,
    ):
        if fallback not in providers:
            raise ValueError(f"fallback provider {fallback!r} is not registered")
        self.providers = providers
        self.routing = dict(routing or {})
        self.fallback = fallback
        self.preserve_article = preserve_article
        self.records: list[StageRecord] = []

    def with_options(self, *, preserve_article: bool | None = None, routing: dict[str, str] | None = None) -> ProviderRouter:
        return ProviderRouter(
            self.providers,
            routing if routing is not None else self.routing,
            fallback=self.fallback,
            preserve_article=self.preserve_article if preserve_article is None else preserve_article,
        )

    def provider_for(self, capability: Capability) -> ImageEnhancementProvider:
        name = self.routing.get(capability.value) or self.routing.get("*") or self.fallback
        p = self.providers.get(name)
        if p is None or capability not in p.capabilities or not p.is_available():
            return self.providers[self.fallback]
        if self.preserve_article and capability in p.generative:
            # Generative models are never used while "Préserver l'article" is on.
            return self.providers[self.fallback]
        return p

    def call(self, capability: Capability, method: str, *args: Any, **kwargs: Any) -> Any:
        provider = self.provider_for(capability)
        t0 = time.perf_counter()
        try:
            result = getattr(provider, method)(*args, **kwargs)
            self._record(capability, provider, t0, success=True)
            return result
        except Exception as exc:  # noqa: BLE001 - any provider failure falls back to local
            self._record(capability, provider, t0, success=False, error=str(exc)[:300])
            if provider.name == self.fallback:
                raise
            log.warning("provider %s failed for %s (%s); falling back to %s", provider.name, capability, exc, self.fallback)
            fb = self.providers[self.fallback]
            t1 = time.perf_counter()
            result = getattr(fb, method)(*args, **kwargs)
            self._record(capability, fb, t1, success=True, details={"fallback_from": provider.name})
            return result

    def upscaler(self) -> Callable | None:
        p = self.provider_for(Capability.UPSCALING)
        if p.name == self.fallback:
            return None

        def _up(img, w, h):
            return self.call(Capability.UPSCALING, "upscale_image", img, w, h)

        return _up

    def _record(
        self,
        capability: Capability,
        provider: ImageEnhancementProvider,
        t0: float,
        *,
        success: bool,
        error: str | None = None,
        details: dict | None = None,
    ) -> None:
        d = dict(details or {})
        d["success"] = success
        if error:
            d["error"] = error
        self.records.append(
            StageRecord(
                name=capability.value,
                label=STAGE_LABELS.get(capability, capability.value),
                duration_ms=round((time.perf_counter() - t0) * 1000, 1),
                provider=provider.name,
                model=provider.model_for(capability),
                cost_cents=float(provider.cost_cents.get(capability, 0.0)) if success else 0.0,
                details=d,
            )
        )

    def drain_records(self) -> list[StageRecord]:
        recs, self.records = self.records, []
        return recs


__all__ = ["ProviderRouter", "ProviderError", "STAGE_LABELS"]
