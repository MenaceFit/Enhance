"""Optional learned segmentation with rembg (U²-Net / ISNet / BiRefNet, ONNX, CPU).

Install with ``pip install -e ".[rembg]"`` and route it with
``AI_ROUTING='{"segmentation": "rembg"}'``. Models are downloaded on first use.
"""

from __future__ import annotations

import threading

import numpy as np

from app.imaging.analysis.segmentation import segmentation_from_mask
from app.imaging.image_io import resize_long_side
from app.providers.base import Capability, ImageEnhancementProvider


class RembgSegmentationProvider(ImageEnhancementProvider):
    name = "rembg"
    display_name = "rembg (segmentation apprise)"
    version = "2"
    capabilities = frozenset({Capability.SEGMENTATION})
    generative = frozenset()
    cost_cents = {Capability.SEGMENTATION: 0.0}

    def __init__(self, model: str = "isnet-general-use"):
        self.model = model
        self._session = None
        self._lock = threading.Lock()

    def is_available(self) -> bool:
        try:
            import rembg  # noqa: F401
        except Exception:
            return False
        return True

    def model_for(self, capability: Capability) -> str | None:
        return self.model

    def segment(self, image: np.ndarray):
        from rembg import new_session, remove

        with self._lock:
            if self._session is None:
                self._session = new_session(self.model)
        h, w = image.shape[:2]
        small = resize_long_side(image, 1024)
        alpha = remove(small, session=self._session, only_mask=True)
        alpha = np.asarray(alpha, dtype=np.uint8)
        if alpha.ndim == 3:
            alpha = alpha[..., 0]
        # confidence from how decisive the matte is (few mid-grey pixels)
        undecided = float(((alpha > 40) & (alpha < 215)).mean())
        confidence = float(np.clip(1.0 - undecided * 8, 0.3, 0.98))
        return segmentation_from_mask(alpha, (w, h), f"rembg:{self.model}", confidence)
