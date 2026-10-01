"""Removal of confirmed dust/hair specks by local inpainting (never generative)."""

from __future__ import annotations

import cv2
import numpy as np


def removal_mask(label_map: np.ndarray, ids: list[int], width: int, height: int) -> np.ndarray:
    if not ids or label_map.size == 0:
        return np.zeros((height, width), np.uint8)
    sel = np.isin(label_map, np.asarray(ids, dtype=label_map.dtype)).astype(np.uint8) * 255
    if sel.shape != (height, width):
        sel = cv2.resize(sel, (width, height), interpolation=cv2.INTER_NEAREST)
        sel = (sel > 0).astype(np.uint8) * 255
    grow = max(1, int(round(max(width, height) / 900)))
    return cv2.dilate(sel, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * grow + 1, 2 * grow + 1)))


def remove_specks(img_u8: np.ndarray, mask: np.ndarray) -> np.ndarray:
    if not mask.any():
        return img_u8
    radius = max(2, int(round(max(img_u8.shape[:2]) / 600)))
    # Work on the bounding box of all specks only (fast on large images).
    ys, xs = np.nonzero(mask)
    pad = radius * 4 + 4
    y0, y1 = max(0, ys.min() - pad), min(img_u8.shape[0], ys.max() + pad + 1)
    x0, x1 = max(0, xs.min() - pad), min(img_u8.shape[1], xs.max() + pad + 1)
    out = img_u8.copy()
    out[y0:y1, x0:x1] = cv2.inpaint(img_u8[y0:y1, x0:x1], mask[y0:y1, x0:x1], radius, cv2.INPAINT_TELEA)
    return out
