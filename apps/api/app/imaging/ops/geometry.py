"""Straightening and framing ("Placement").

Rules enforced here:
* the crop never cuts into the garment;
* if the garment already touches a side of the photo (e.g. a sleeve out of
  frame), that side stays on the photo border — nothing is invented beyond it;
* outside the clean-background mode the crop stays inside the real photo (no
  padding, no invented background); with the neutral background, the new
  surface may extend the frame on sides where the garment is fully visible.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np

ASPECTS = {"3:4": 3 / 4, "4:5": 4 / 5, "1:1": 1.0}
TARGET_MARGIN = 0.075  # free space around the garment, as a fraction of the frame


@dataclass(slots=True)
class GeometryPlan:
    angle: float  # degrees, applied counter-clockwise (= -tilt)
    x0: float  # crop in rotated source pixel coordinates
    y0: float
    width: float
    height: float
    src_w: int
    src_h: int
    padded: bool

    @property
    def is_identity(self) -> bool:
        return (
            abs(self.angle) < 1e-3
            and abs(self.x0) < 0.5
            and abs(self.y0) < 0.5
            and abs(self.width - self.src_w) < 1
            and abs(self.height - self.src_h) < 1
        )

    def scaled(self, k: float) -> GeometryPlan:
        return GeometryPlan(
            self.angle, self.x0 * k, self.y0 * k, self.width * k, self.height * k,
            max(1, round(self.src_w * k)), max(1, round(self.src_h * k)), self.padded,
        )

    def matrix(self, out_w: int, out_h: int) -> np.ndarray:
        cx, cy = self.src_w / 2.0, self.src_h / 2.0
        rot = cv2.getRotationMatrix2D((cx, cy), self.angle, 1.0)
        rot3 = np.vstack([rot, [0, 0, 1]])
        sx, sy = out_w / self.width, out_h / self.height
        crop = np.array([[sx, 0, -self.x0 * sx], [0, sy, -self.y0 * sy], [0, 0, 1]], np.float64)
        return (crop @ rot3)[:2]

    def to_dict(self) -> dict:
        return {
            "angle": round(self.angle, 3),
            "crop": [round(self.x0 / self.src_w, 4), round(self.y0 / self.src_h, 4),
                     round(self.width / self.src_w, 4), round(self.height / self.src_h, 4)],
            "padded": self.padded,
        }


def _rotated_bbox(mask: np.ndarray, angle: float, W: int, H: int) -> tuple[float, float, float, float]:
    m = (mask > 127).astype(np.uint8)
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return 0.0, 0.0, float(W), float(H)
    pts = np.vstack(cnts).reshape(-1, 2).astype(np.float64)
    pts[:, 0] *= W / mask.shape[1]
    pts[:, 1] *= H / mask.shape[0]
    rot = cv2.getRotationMatrix2D((W / 2.0, H / 2.0), angle, 1.0)
    p = pts @ rot[:, :2].T + rot[:, 2]
    return float(p[:, 0].min()), float(p[:, 1].min()), float(p[:, 0].max()), float(p[:, 1].max())


def _inside_source(x0: float, y0: float, x1: float, y1: float, angle: float, W: int, H: int) -> bool:
    if abs(angle) < 1e-3:
        return x0 >= -0.5 and y0 >= -0.5 and x1 <= W + 0.5 and y1 <= H + 0.5
    inv = cv2.getRotationMatrix2D((W / 2.0, H / 2.0), -angle, 1.0)
    corners = np.array([[x0, y0], [x1, y0], [x0, y1], [x1, y1]], np.float64)
    src = corners @ inv[:, :2].T + inv[:, 2]
    return bool((src[:, 0] >= -1).all() and (src[:, 1] >= -1).all() and (src[:, 0] <= W + 1).all() and (src[:, 1] <= H + 1).all())


def plan_geometry(
    mask: np.ndarray,
    W: int,
    H: int,
    *,
    tilt_deg: float,
    tilt_confidence: float,
    touches: dict[str, bool],
    placement: float,
    aspect: str,
    allow_padding: bool,
) -> GeometryPlan:
    ratio = ASPECTS.get(aspect, W / H)
    if placement <= 0 and aspect == "original":
        return GeometryPlan(0.0, 0.0, 0.0, float(W), float(H), W, H, False)

    angle = 0.0
    # A garment cut by the frame is not rotated onto a new surface: its cut edge would
    # appear slanted over invented background.
    cut_by_frame = allow_padding and any(touches.values())
    if placement > 0 and not cut_by_frame and tilt_confidence >= 0.3 and 0.6 <= abs(tilt_deg) <= 12:
        limit = 12.0 if tilt_confidence >= 0.6 else 4.0
        angle = -float(np.clip(tilt_deg, -limit, limit)) * min(1.0, placement / 0.4)

    gx0, gy0, gx1, gy1 = _rotated_bbox(mask, angle, W, H)
    gw, gh = gx1 - gx0, gy1 - gy0
    gcx, gcy = (gx0 + gx1) / 2, (gy0 + gy1) / 2

    # Minimal crop with the requested ratio (largest frame of that ratio inside the photo).
    fw = H * ratio if ratio < W / H else float(W)
    # Target crop: garment + margin.
    m = TARGET_MARGIN
    tw = max(gw / (1 - 2 * m), gh / (1 - 2 * m) * ratio)
    t = float(np.clip(placement, 0, 1))
    cw = fw + (tw - fw) * t if tw < fw or allow_padding else fw
    ch = cw / ratio
    # The crop must contain the garment.
    if cw < gw or ch < gh:
        cw = max(gw, gh * ratio)
        ch = cw / ratio

    # Centre on the garment, blended with the minimal-crop centre at low placement.
    cx = W / 2 + (gcx - W / 2) * max(t, 0.5 if aspect != "original" else t)
    cy = H / 2 + (gcy - H / 2) * max(t, 0.5 if aspect != "original" else t)
    x0, y0 = cx - cw / 2, cy - ch / 2
    # garment containment
    x0 = min(x0, gx0)
    y0 = min(y0, gy0)
    x0 = max(x0, gx1 - cw)
    y0 = max(y0, gy1 - ch)

    padded = False
    if allow_padding:
        # Sides where the garment touches the photo border stay on that border.
        if touches.get("left"):
            x0 = max(x0, 0.0)
        if touches.get("top"):
            y0 = max(y0, 0.0)
        if touches.get("right"):
            x0 = min(x0, W - cw)
        if touches.get("bottom"):
            y0 = min(y0, H - ch)
        padded = x0 < -0.5 or y0 < -0.5 or x0 + cw > W + 0.5 or y0 + ch > H + 0.5
    else:
        # Stay inside the real photo. If the requested ratio cannot be met without cutting the
        # garment, keep the garment whole and accept a different ratio.
        cw, ch = min(cw, float(W)), min(ch, float(H))

        def place(v: float, lo_g: float, hi_g: float, size: float, limit: float) -> float:
            lo, hi = max(0.0, hi_g - size), min(lo_g, limit - size)
            return float(np.clip(v, lo, hi)) if lo <= hi else float(np.clip(v, 0.0, limit - size))

        x0 = place(x0, gx0, gx1, cw, W)
        y0 = place(y0, gy0, gy1, ch, H)
        if abs(angle) > 1e-3:
            # avoid the empty corners created by the rotation
            for _ in range(30):
                if _inside_source(x0, y0, x0 + cw, y0 + ch, angle, W, H):
                    break
                ncw, nch = cw * 0.985, ch * 0.985
                if ncw < gw or nch < gh:
                    # cannot shrink without cutting the garment: reduce the rotation instead
                    angle *= 0.5
                    if abs(angle) < 0.3:
                        angle = 0.0
                    gx0, gy0, gx1, gy1 = _rotated_bbox(mask, angle, W, H)
                    gw, gh = gx1 - gx0, gy1 - gy0
                    continue
                x0 += (cw - ncw) / 2
                y0 += (ch - nch) / 2
                cw, ch = ncw, nch
                x0 = float(np.clip(min(x0, gx0), max(0.0, gx1 - cw), W - cw))
                y0 = float(np.clip(min(y0, gy0), max(0.0, gy1 - ch), H - ch))

    return GeometryPlan(angle, x0, y0, cw, ch, W, H, padded)


def output_size(plan: GeometryPlan, long_side: int) -> tuple[int, int]:
    k = long_side / max(plan.width, plan.height)
    return max(1, int(round(plan.width * k))), max(1, int(round(plan.height * k)))


def apply_geometry(
    img: np.ndarray,
    plan: GeometryPlan,
    out_w: int,
    out_h: int,
    *,
    border_value: tuple[float, ...] | float | None = None,
    interpolation: int = cv2.INTER_LINEAR,
) -> np.ndarray:
    if plan.is_identity and (out_w, out_h) == (img.shape[1], img.shape[0]):
        return img
    M = plan.matrix(out_w, out_h)
    scale = out_w / plan.width
    interp = interpolation
    if scale < 0.75 and interpolation == cv2.INTER_LINEAR:
        interp = cv2.INTER_AREA  # warpAffine ignores AREA; pre-shrink instead
        k = max(scale * 1.25, 1e-3)
        small = cv2.resize(img, (max(1, round(img.shape[1] * k)), max(1, round(img.shape[0] * k))), interpolation=cv2.INTER_AREA)
        plan_k = plan.scaled(small.shape[1] / img.shape[1])
        M = plan_k.matrix(out_w, out_h)
        img = small
        interp = cv2.INTER_LINEAR
    if border_value is None:
        return cv2.warpAffine(img, M, (out_w, out_h), flags=interp, borderMode=cv2.BORDER_REFLECT101)
    return cv2.warpAffine(img, M, (out_w, out_h), flags=interp, borderMode=cv2.BORDER_CONSTANT, borderValue=border_value)


def residual_tilt(tilt_deg: float, plan: GeometryPlan) -> float:
    return tilt_deg + plan.angle if math.isfinite(tilt_deg) else 0.0
