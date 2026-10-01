"""Provider registry built from configuration.

``AI_ROUTING`` maps capabilities to provider names, e.g.::

    AI_ROUTING='{"segmentation": "rembg", "clothing_detection": "anthropic", "*": "local"}'

Unavailable providers (missing API key or optional dependency) are skipped
transparently and the local engine is used instead.
"""

from __future__ import annotations

import json
from functools import lru_cache

from app.providers.base import ImageEnhancementProvider
from app.providers.local_cv import LocalCVProvider
from app.providers.router import ProviderRouter


def build_providers() -> dict[str, ImageEnhancementProvider]:
    from app.core.config import get_settings
    from app.providers.anthropic_vision import AnthropicVisionProvider
    from app.providers.rembg_segmentation import RembgSegmentationProvider
    from app.providers.replicate_upscaler import ReplicateUpscaleProvider

    cfg = get_settings()
    providers: list[ImageEnhancementProvider] = [
        LocalCVProvider(),
        RembgSegmentationProvider(model=cfg.rembg_model),
        AnthropicVisionProvider(api_key=cfg.anthropic_api_key, model=cfg.anthropic_model),
        ReplicateUpscaleProvider(api_token=cfg.replicate_api_token, model_version=cfg.replicate_upscale_version),
    ]
    return {p.name: p for p in providers}


@lru_cache
def get_providers() -> dict[str, ImageEnhancementProvider]:
    return build_providers()


def parse_routing(raw: str | dict | None) -> dict[str, str]:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items()}
    return {str(k): str(v) for k, v in json.loads(raw).items()}


def get_router(routing: dict[str, str] | None = None, *, preserve_article: bool = True) -> ProviderRouter:
    from app.core.config import get_settings

    cfg = get_settings()
    return ProviderRouter(
        get_providers(),
        routing if routing is not None else parse_routing(cfg.ai_routing),
        fallback="local",
        preserve_article=preserve_article,
    )


def local_router() -> ProviderRouter:
    """A router with only the local engine (tests, CLI, benchmarks baseline)."""
    return ProviderRouter({"local": LocalCVProvider()}, {}, fallback="local")
