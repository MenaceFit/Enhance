"""Optional super-resolution through Replicate (e.g. Real-ESRGAN).

Learned super-resolution *synthesises* high-frequency detail, so it is marked
generative: the router never uses it while "Préserver l'article" is on, and
its outputs go through the same structural check as everything else.
"""

from __future__ import annotations

import base64
import time

import cv2
import httpx
import numpy as np

from app.imaging.color import to_float, to_uint8
from app.imaging.image_io import decode_rgb_fast, encode_image
from app.providers.base import Capability, ImageEnhancementProvider, ProviderError

API = "https://api.replicate.com/v1/predictions"


class ReplicateUpscaleProvider(ImageEnhancementProvider):
    name = "replicate"
    display_name = "Replicate (super-résolution)"
    version = "1"
    capabilities = frozenset({Capability.UPSCALING})
    generative = frozenset({Capability.UPSCALING})
    cost_cents = {Capability.UPSCALING: 0.25}

    def __init__(self, api_token: str | None, model_version: str | None, timeout: float = 60.0):
        self.api_token = api_token
        self.model_version = model_version
        self.timeout = timeout

    def is_available(self) -> bool:
        return bool(self.api_token and self.model_version)

    def model_for(self, capability: Capability) -> str | None:
        return self.model_version

    def upscale_image(self, image: np.ndarray, width: int, height: int) -> np.ndarray:
        if not self.is_available():
            raise ProviderError("Replicate provider is not configured")
        was_float = image.dtype != np.uint8
        u8 = to_uint8(image) if was_float else image
        scale = max(width / u8.shape[1], height / u8.shape[0])
        data_uri = "data:image/png;base64," + base64.b64encode(encode_image(u8, "png")).decode()
        headers = {"Authorization": f"Bearer {self.api_token}", "Prefer": "wait"}
        payload = {"version": self.model_version, "input": {"image": data_uri, "scale": 2 if scale <= 2 else 4}}
        deadline = time.monotonic() + self.timeout
        with httpx.Client(timeout=30.0) as client:
            r = client.post(API, json=payload, headers=headers)
            if r.status_code >= 400:
                raise ProviderError(f"replicate error {r.status_code}")
            pred = r.json()
            while pred.get("status") not in ("succeeded", "failed", "canceled"):
                if time.monotonic() > deadline:
                    raise ProviderError("replicate timeout")
                time.sleep(1.0)
                pred = client.get(pred["urls"]["get"], headers=headers).json()
            if pred["status"] != "succeeded":
                raise ProviderError(f"replicate prediction {pred['status']}")
            output = pred["output"]
            url = output[0] if isinstance(output, list) else output
            img = decode_rgb_fast(client.get(url).content)
        img = cv2.resize(img, (width, height), interpolation=cv2.INTER_AREA)
        return to_float(img) if was_float else img
