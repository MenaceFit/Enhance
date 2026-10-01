"""Provider layer: routing, fallback, preserve-mode guard, Claude adapter contract."""

from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np
import pytest

from app.imaging.analysis.segmentation import segment_garment
from app.imaging.synthetic import make_scene
from app.providers.anthropic_vision import AnthropicVisionProvider
from app.providers.base import Capability, ImageEnhancementProvider, ProviderError
from app.providers.local_cv import LocalCVProvider
from app.providers.replicate_upscaler import ReplicateUpscaleProvider
from app.providers.router import ProviderRouter


class Broken(ImageEnhancementProvider):
    name = "broken"
    capabilities = frozenset({Capability.SEGMENTATION})
    cost_cents = {Capability.SEGMENTATION: 1.5}

    def segment(self, image):
        raise ProviderError("boom")


class FakeGenerativeUpscaler(ImageEnhancementProvider):
    name = "gen"
    capabilities = frozenset({Capability.UPSCALING})
    generative = frozenset({Capability.UPSCALING})


def test_router_falls_back_to_local_and_records_both_calls():
    img, _ = make_scene("tshirt", 300, 400, seed=1)
    router = ProviderRouter({"local": LocalCVProvider(), "broken": Broken()}, {"segmentation": "broken"})
    mask, seg, _ = router.call(Capability.SEGMENTATION, "segment", img)
    assert mask.shape == img.shape[:2] and seg.confidence > 0
    recs = router.drain_records()
    assert [(r.provider, r.details["success"]) for r in recs] == [("broken", False), ("local", True)]
    assert recs[0].cost_cents == 0.0  # failed calls are not billed
    assert recs[1].details["fallback_from"] == "broken"


def test_generative_providers_are_blocked_in_preserve_mode():
    providers = {"local": LocalCVProvider(), "gen": FakeGenerativeUpscaler()}
    preserve = ProviderRouter(providers, {"upscaling": "gen"}, preserve_article=True)
    free = ProviderRouter(providers, {"upscaling": "gen"}, preserve_article=False)
    assert preserve.provider_for(Capability.UPSCALING).name == "local"
    assert free.provider_for(Capability.UPSCALING).name == "gen"
    assert preserve.upscaler() is None


def test_unavailable_providers_are_skipped():
    providers = {"local": LocalCVProvider(), "anthropic": AnthropicVisionProvider(api_key=None),
                 "replicate": ReplicateUpscaleProvider(None, None)}
    router = ProviderRouter(providers, {"clothing_detection": "anthropic", "upscaling": "replicate"}, preserve_article=False)
    assert router.provider_for(Capability.CLOTHING_DETECTION).name == "local"
    assert router.provider_for(Capability.UPSCALING).name == "local"


def _fake_anthropic(payload: dict, stop_reason: str = "end_turn"):
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            stop_reason=stop_reason,
            stop_details=SimpleNamespace(category="cyber") if stop_reason == "refusal" else None,
            content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=json.dumps(payload))],
            usage=SimpleNamespace(input_tokens=2500, output_tokens=600),
            model="claude-opus-5-5",
        )

    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
    return client, calls


CLAUDE_PAYLOAD = {
    "category": "hoodie", "label_fr": "Hoodie zippé", "confidence": 0.93,
    "colors": [{"name_fr": "bleu marine", "share": 0.85}], "pattern": "uni", "material_guess": "coton molletonné",
    "brand_visible": "", "logos": [{"description": "texte ENHANCE", "position": "poitrine"}],
    "sleeves": "long", "sleeve_count": 2, "pocket_count": 1, "closure": "none", "hood": True,
    "visible_defects": [{"type": "stain", "description_fr": "Petite tache claire", "x": 0.1, "y": 0.8, "w": 0.05, "h": 0.04, "confidence": 0.7}],
    "background": "drap clair",
}


@pytest.fixture()
def claude(monkeypatch):
    p = AnthropicVisionProvider(api_key="test-key")
    client, calls = _fake_anthropic(CLAUDE_PAYLOAD)
    monkeypatch.setattr(p, "_client_or_raise", lambda: client)
    return p, calls


def test_claude_clothing_detection_contract(claude):
    p, calls = claude
    img, _ = make_scene("hoodie", 450, 600, seed=2)
    mask, _, _ = segment_garment(img)
    attrs = p.detect_clothing(img, mask)
    assert attrs.category == "hoodie" and attrs.provider == "anthropic"
    assert attrs.features["sleeve_count"] == 2 and attrs.features["pocket_count"] == 1
    assert attrs.dominant_colors and attrs.dominant_colors[0]["hex"].startswith("#")  # pixel-accurate swatches
    req = calls[0]
    assert req["model"] == "claude-opus-5-5"
    assert req["output_config"]["format"]["type"] == "json_schema"
    assert req["fallbacks"] == "default" and "server-side-fallback-2026-07-01" in req["betas"]
    image_block = req["messages"][0]["content"][0]
    assert image_block["type"] == "image" and image_block["source"]["media_type"] == "image/jpeg"
    assert p.call_cost(Capability.CLOTHING_DETECTION) == pytest.approx((2500 * 4 + 600 * 20) / 1e6 * 92, rel=1e-6)

    # the same image is not sent twice: defects reuse the cached description
    defects = p.detect_defects(img, mask, [], [])
    assert len(calls) == 1
    assert any(d.label == "Petite tache claire" for d in defects)


def test_claude_refusal_raises_for_fallback(monkeypatch):
    p = AnthropicVisionProvider(api_key="test-key")
    client, _ = _fake_anthropic(CLAUDE_PAYLOAD, stop_reason="refusal")
    monkeypatch.setattr(p, "_client_or_raise", lambda: client)
    img = np.full((200, 150, 3), 128, np.uint8)
    with pytest.raises(ProviderError, match="declined"):
        p.detect_clothing(img, np.zeros((200, 150), np.uint8))
