"""Claude vision provider: fine-grained clothing attributes, visible defects, listings.

The classical engine infers the garment category from its silhouette; Claude
reads the photo like a seller would (logos, pockets, closure, material, visible
defects). Pixels are never generated here — this provider only *describes*, so
it is allowed in "Préserver l'article" mode.

One vision call per image serves both clothing and defect detection (results
are cached by image hash). Refusals and API errors raise ``ProviderError`` so
the router falls back to the local engine.
"""

from __future__ import annotations

import base64
import hashlib
import json
import threading
from collections import OrderedDict
from typing import Any

import numpy as np

from app.imaging.analysis.clothing import CATEGORY_LABELS, analyze_clothing
from app.imaging.analysis.defects import LABELS as DEFECT_LABELS
from app.imaging.analysis.defects import detect_defects
from app.imaging.image_io import encode_image, resize_long_side
from app.imaging.types import BBox, ClothingAttributes, Defect
from app.providers.base import Capability, ImageEnhancementProvider, ProviderError

# $ per million tokens for cost tracking (input, output). Update with pricing changes.
PRICING_USD_PER_MTOK = {
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
}
USD_TO_EUR_CENTS = 92.0  # 1 USD ≈ 0.92 EUR → cents

CATEGORIES = [
    "hoodie", "sweat", "pull", "tshirt", "chemise", "veste", "manteau", "jean", "pantalon", "short",
    "jupe", "robe", "sneakers", "chaussures", "accessoire", "autre",
]
EXTRA_LABELS = {
    "chemise": "Chemise", "manteau": "Manteau", "jupe": "Jupe", "chaussures": "Chaussures",
    "accessoire": "Accessoire", "autre": "Vêtement",
}

CLOTHING_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": CATEGORIES},
        "label_fr": {"type": "string"},
        "confidence": {"type": "number"},
        "colors": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"name_fr": {"type": "string"}, "share": {"type": "number"}},
                "required": ["name_fr", "share"],
                "additionalProperties": False,
            },
        },
        "pattern": {"type": "string"},
        "material_guess": {"type": "string"},
        "brand_visible": {"type": "string"},
        "logos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"description": {"type": "string"}, "position": {"type": "string"}},
                "required": ["description", "position"],
                "additionalProperties": False,
            },
        },
        "sleeves": {"type": "string", "enum": ["none", "short", "long", "not_applicable"]},
        "sleeve_count": {"type": "integer"},
        "pocket_count": {"type": "integer"},
        "closure": {"type": "string", "enum": ["none", "zip", "buttons", "laces", "other"]},
        "hood": {"type": "boolean"},
        "visible_defects": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["stain", "hole", "discoloration", "pilling", "snag", "wear", "other"]},
                    "description_fr": {"type": "string"},
                    "x": {"type": "number"},
                    "y": {"type": "number"},
                    "w": {"type": "number"},
                    "h": {"type": "number"},
                    "confidence": {"type": "number"},
                },
                "required": ["type", "description_fr", "x", "y", "w", "h", "confidence"],
                "additionalProperties": False,
            },
        },
        "background": {"type": "string"},
    },
    "required": [
        "category", "label_fr", "confidence", "colors", "pattern", "material_guess", "brand_visible", "logos",
        "sleeves", "sleeve_count", "pocket_count", "closure", "hood", "visible_defects", "background",
    ],
    "additionalProperties": False,
}

LISTING_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "description": {"type": "string"},
        "category": {"type": "string"},
        "color": {"type": "string"},
        "material": {"type": "string"},
        "size_visible": {"type": "string"},
        "condition_notes": {"type": "string"},
        "keywords": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "description", "category", "color", "material", "size_visible", "condition_notes", "keywords"],
    "additionalProperties": False,
}

ANALYSIS_PROMPT = """Tu analyses une photo de vente d'un article de seconde main (Vinted).
Décris uniquement ce qui est réellement visible, sans rien supposer.
- category / label_fr : type d'article.
- colors : couleurs dominantes réelles de l'article (pas du fond), part approximative de 0 à 1.
- brand_visible : marque lisible sur l'article, sinon chaîne vide. N'invente jamais une marque.
- logos : logos ou imprimés visibles et leur position.
- sleeve_count, pocket_count : nombres visibles sur la photo (0 si non applicable).
- visible_defects : taches, trous, décolorations, bouloches, accrocs ou usure visibles sur l'article,
  avec une boîte approximative en coordonnées normalisées 0-1 (x, y = coin haut-gauche) et une confiance 0-1.
  Ne signale pas les plis, les poussières ni les éléments du fond.
- background : description courte du fond."""

LISTING_PROMPT = """Rédige une annonce Vinted honnête en français pour cet article, à partir de la photo et des
attributs fournis. Règles : ne mentionne une marque que si elle est lisible sur la photo ; ne mentionne une
taille que si elle est lisible ; signale clairement les imperfections visibles dans condition_notes et dans
la description ; ton simple et direct ; titre de 60 caractères maximum ; 5 à 10 mots-clés.
Attributs détectés : {attributes}"""


class AnthropicVisionProvider(ImageEnhancementProvider):
    name = "anthropic"
    display_name = "Claude (vision)"
    version = "1"
    capabilities = frozenset({Capability.CLOTHING_DETECTION, Capability.DEFECT_DETECTION, Capability.LISTING})
    generative = frozenset()
    cost_cents = {Capability.CLOTHING_DETECTION: 3.0, Capability.DEFECT_DETECTION: 0.0, Capability.LISTING: 3.0}

    def __init__(self, api_key: str | None, model: str = "claude-opus-5-5", max_side: int = 1568):
        self.api_key = api_key
        self.model = model
        self.max_side = max_side
        self._client = None
        self._cache: OrderedDict[str, dict] = OrderedDict()
        self._lock = threading.Lock()
        self._last_cost = threading.local()

    # --- plumbing -----------------------------------------------------------------------
    def is_available(self) -> bool:
        if not self.api_key:
            return False
        try:
            import anthropic  # noqa: F401
        except ImportError:
            return False
        return True

    def model_for(self, capability: Capability) -> str | None:
        return self.model

    def call_cost(self, capability: Capability) -> float:
        cost = getattr(self._last_cost, "cents", None)
        self._last_cost.cents = None
        return float(cost) if cost is not None else float(self.cost_cents.get(capability, 0.0))

    def _client_or_raise(self):
        if not self.is_available():
            raise ProviderError("Anthropic provider is not configured")
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic(api_key=self.api_key, max_retries=2, timeout=90.0)
        return self._client

    def _image_block(self, image: np.ndarray) -> dict:
        small = resize_long_side(image, self.max_side)
        data = base64.standard_b64encode(encode_image(small, "jpg", 88)).decode("ascii")
        return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}}

    def _ask(self, image: np.ndarray, prompt: str, schema: dict, effort: str) -> dict:
        import anthropic

        client = self._client_or_raise()
        try:
            response = client.beta.messages.create(
                model=self.model,
                max_tokens=16000,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
                messages=[{"role": "user", "content": [self._image_block(image), {"type": "text", "text": prompt}]}],
            )
        except anthropic.RateLimitError as exc:
            raise ProviderError(f"rate limited: {exc.message}") from exc
        except anthropic.APIStatusError as exc:
            raise ProviderError(f"API error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderError("connection error") from exc

        if response.stop_reason == "refusal":
            category = getattr(response.stop_details, "category", None) if response.stop_details else None
            raise ProviderError(f"request declined ({category})")
        if response.stop_reason == "max_tokens":
            raise ProviderError("response truncated")
        text = next((b.text for b in response.content if b.type == "text"), None)
        if not text:
            raise ProviderError("empty response")

        usage = response.usage
        price_in, price_out = PRICING_USD_PER_MTOK.get(response.model, PRICING_USD_PER_MTOK.get(self.model, (4.0, 20.0)))
        usd = (usage.input_tokens * price_in + usage.output_tokens * price_out) / 1_000_000
        self._last_cost.cents = round(usd * USD_TO_EUR_CENTS, 4)
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProviderError("invalid JSON from model") from exc

    def _describe(self, image: np.ndarray) -> dict:
        key = hashlib.sha1(np.ascontiguousarray(resize_long_side(image, 256)).tobytes()).hexdigest()
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                self._last_cost.cents = 0.0
                return self._cache[key]
        data = self._ask(image, ANALYSIS_PROMPT, CLOTHING_SCHEMA, effort="low")
        with self._lock:
            self._cache[key] = data
            while len(self._cache) > 64:
                self._cache.popitem(last=False)
        return data

    # --- capabilities --------------------------------------------------------------------
    def detect_clothing(self, image, mask, gains=None) -> ClothingAttributes:
        data = self._describe(image)
        local = analyze_clothing(image, mask, gains)  # precise colour swatches + logo boxes from pixels
        category = data["category"]
        label = data.get("label_fr") or CATEGORY_LABELS.get(category) or EXTRA_LABELS.get(category, "Vêtement")
        features = dict(local.features)
        features.update({
            "hood": bool(data["hood"]),
            "long_sleeves": data["sleeves"] == "long",
            "sleeves": data["sleeves"],
            "sleeve_count": int(data["sleeve_count"]),
            "pocket_count": int(data["pocket_count"]),
            "closure": data["closure"],
            "central_closure": data["closure"] in ("zip", "buttons"),
            "brand_visible": data["brand_visible"],
            "material_guess": data["material_guess"],
            "logo_descriptions": data["logos"],
            "visible_defects": data["visible_defects"],
        })
        return ClothingAttributes(
            category=category,
            label=label,
            confidence=round(float(np.clip(data["confidence"], 0, 1)), 3),
            candidates=[{"category": category, "label": label, "score": round(float(data["confidence"]), 3)}] + local.candidates[:2],
            dominant_colors=local.dominant_colors or [{"hex": None, "name": c["name_fr"], "share": c["share"]} for c in data["colors"]],
            pattern=data["pattern"] or local.pattern,
            texture=data["material_guess"] or local.texture,
            features=features,
            background=data["background"],
            provider=self.name,
        )

    def detect_defects(self, image, mask, specks, holes=None) -> list[Defect]:
        local = detect_defects(image, mask, specks, holes)
        data = self._describe(image)
        out = list(local)
        for d in data["visible_defects"]:
            kind = d["type"] if d["type"] in DEFECT_LABELS else "wear"
            bbox = BBox(*(float(np.clip(d[k], 0, 1)) for k in ("x", "y", "w", "h")))
            if bbox.w <= 0 or bbox.h <= 0:
                continue
            if any(abs(o.bbox.cx - bbox.cx) < 0.05 and abs(o.bbox.cy - bbox.cy) < 0.05 for o in out):
                continue  # already found locally
            out.append(
                Defect(
                    id=hashlib.sha1(json.dumps(d, sort_keys=True).encode()).hexdigest()[:10],
                    kind=kind,  # type: ignore[arg-type]
                    label=d["description_fr"][:80] or DEFECT_LABELS[kind],
                    bbox=bbox,
                    confidence=round(float(np.clip(d["confidence"], 0, 1)), 3),
                    area=bbox.w * bbox.h,
                )
            )
        return out[:10]

    def generate_listing(self, image: np.ndarray, attributes: ClothingAttributes) -> dict[str, Any]:
        attrs = {
            "type": attributes.label,
            "couleurs": [c.get("name") for c in attributes.dominant_colors],
            "motif": attributes.pattern,
            "matière": attributes.texture,
            "caractéristiques": {k: v for k, v in attributes.features.items() if k not in ("logos", "visible_defects")},
        }
        data = self._ask(image, LISTING_PROMPT.format(attributes=json.dumps(attrs, ensure_ascii=False)), LISTING_SCHEMA, effort="medium")
        data["provider"] = self.name
        return data
