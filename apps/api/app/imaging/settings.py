"""User-facing enhancement settings, presets and the "Préserver l'article" guard.

Settings are stored with every version, so a render is fully reproducible from
(photo analysis, settings). Module sliders are 0-100; ``None`` means "use the
value of the selected global intensity preset".
"""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Intensity = Literal["original", "leger", "naturel", "premium", "studio"]
WrinkleLevel = Literal["off", "leger", "moyen", "fort"]
BackgroundMode = Literal["keep", "clean", "neutral"]
BackgroundColor = Literal["auto", "off_white", "light_gray", "light_beige"]
Aspect = Literal["original", "3:4", "4:5", "1:1"]
UpscaleMode = Literal["auto", "off", "2x"]

INTENSITY_ORDER: list[Intensity] = ["original", "leger", "naturel", "premium", "studio"]
INTENSITY_LABELS = {
    "original": "Original",
    "leger": "Léger",
    "naturel": "Naturel",
    "premium": "Premium",
    "studio": "Studio",
}

# Values chosen to stay natural: even "studio" never exceeds what a careful
# photographer would do in post-production.
PRESETS: dict[str, dict] = {
    "original": dict(cleaning=0, placement=0, light=0, color=0, sharpness=0, wrinkles="off", background="keep"),
    "leger": dict(cleaning=50, placement=40, light=40, color=25, sharpness=20, wrinkles="leger", background="keep"),
    "naturel": dict(cleaning=70, placement=60, light=60, color=40, sharpness=35, wrinkles="leger", background="clean"),
    "premium": dict(cleaning=85, placement=75, light=72, color=55, sharpness=45, wrinkles="moyen", background="clean"),
    "studio": dict(cleaning=100, placement=85, light=80, color=62, sharpness=55, wrinkles="moyen", background="neutral"),
}

WRINKLE_STRENGTH = {"off": 0.0, "leger": 0.28, "moyen": 0.45, "fort": 0.62}

BACKGROUND_COLORS = {
    "off_white": (0.953, 0.945, 0.925),  # blanc cassé
    "light_gray": (0.905, 0.905, 0.898),  # gris clair
    "light_beige": (0.937, 0.910, 0.866),  # beige très léger
}

HUE_LIMIT = 10  # slider units; 1 unit = 0.3° of hue rotation (±3° max)
HUE_DEG_PER_UNIT = 0.3

# Hard limits applied when "🔒 Préserver l'article" is on (default).
PRESERVE_CAPS = dict(color=55, wrinkles="leger", hue=6)


class EnhancementSettings(BaseModel):
    intensity: Intensity = "naturel"
    preserve_article: bool = True
    cleaning: int | None = Field(default=None, ge=0, le=100)
    placement: int | None = Field(default=None, ge=0, le=100)
    light: int | None = Field(default=None, ge=0, le=100)
    color: int | None = Field(default=None, ge=0, le=100)
    sharpness: int | None = Field(default=None, ge=0, le=100)
    wrinkles: WrinkleLevel | None = None
    background: BackgroundMode | None = None
    background_color: BackgroundColor = "auto"
    hue: int = Field(default=0, ge=-HUE_LIMIT, le=HUE_LIMIT)
    aspect: Aspect = "3:4"
    upscale: UpscaleMode = "auto"
    # Speck ids the user explicitly confirmed as dust (never allowed in preserve mode).
    retouch_specks: list[int] = Field(default_factory=list, max_length=50)

    @field_validator("retouch_specks")
    @classmethod
    def _unique(cls, v: list[int]) -> list[int]:
        return sorted(set(v))

    def resolved(self) -> ResolvedSettings:
        return resolve(self)

    def cache_key(self) -> str:
        payload = json.dumps(self.model_dump(mode="json"), sort_keys=True)
        return hashlib.sha1(payload.encode()).hexdigest()[:16]


class ResolvedSettings(BaseModel):
    """Concrete values used by the renderer after presets and caps."""

    intensity: Intensity
    preserve_article: bool
    cleaning: float  # 0-1
    placement: float
    light: float
    color: float
    sharpness: float
    wrinkles: WrinkleLevel
    wrinkle_strength: float
    background: BackgroundMode
    background_color: BackgroundColor
    hue_deg: float
    aspect: Aspect
    upscale: UpscaleMode
    retouch_specks: list[int]
    capped: list[str]  # which values were limited by the preserve guard


def resolve(s: EnhancementSettings) -> ResolvedSettings:
    preset = PRESETS[s.intensity]
    capped: list[str] = []

    def pick(name: str):
        v = getattr(s, name)
        return preset[name] if v is None else v

    color = pick("color")
    wrinkles: str = pick("wrinkles")
    hue = s.hue
    retouch = list(s.retouch_specks)

    if s.preserve_article:
        if color > PRESERVE_CAPS["color"]:
            color = PRESERVE_CAPS["color"]
            capped.append("color")
        order = list(WRINKLE_STRENGTH)
        if order.index(wrinkles) > order.index(PRESERVE_CAPS["wrinkles"]):
            wrinkles = PRESERVE_CAPS["wrinkles"]
            capped.append("wrinkles")
        if abs(hue) > PRESERVE_CAPS["hue"]:
            hue = PRESERVE_CAPS["hue"] if hue > 0 else -PRESERVE_CAPS["hue"]
            capped.append("hue")
        if retouch:
            retouch = []
            capped.append("retouch_specks")

    return ResolvedSettings(
        intensity=s.intensity,
        preserve_article=s.preserve_article,
        cleaning=pick("cleaning") / 100,
        placement=pick("placement") / 100,
        light=pick("light") / 100,
        color=color / 100,
        sharpness=pick("sharpness") / 100,
        wrinkles=wrinkles,  # type: ignore[arg-type]
        wrinkle_strength=WRINKLE_STRENGTH[wrinkles],
        background=pick("background"),
        background_color=s.background_color,
        hue_deg=hue * HUE_DEG_PER_UNIT,
        aspect=s.aspect,
        upscale=s.upscale,
        retouch_specks=retouch,
        capped=capped,
    )


def vinted_preset() -> EnhancementSettings:
    """The "✨ Amélioration Vinted" one-click preset."""
    return EnhancementSettings(intensity="naturel", preserve_article=True, aspect="3:4", upscale="auto")


def explicit(s: EnhancementSettings) -> EnhancementSettings:
    """Return settings with every preset-derived slider made explicit (for the editor UI)."""
    preset = PRESETS[s.intensity]
    data = s.model_dump()
    for k in ("cleaning", "placement", "light", "color", "sharpness", "wrinkles", "background"):
        if data[k] is None:
            data[k] = preset[k]
    return EnhancementSettings(**data)
