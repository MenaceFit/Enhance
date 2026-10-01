"""Procedural "amateur seller photo" generator with ground truth.

Used for three things:
* unit tests: every scene comes with the true garment mask, colour, tilt,
  stain position and dust positions, so we can assert that the engine removes
  dust, keeps the stain, corrects the cast without altering the garment colour
  and straightens the tilt;
* the benchmark runner (a reproducible image set to compare AI providers);
* the landing page demo pairs (the "after" is produced by the real engine).

Scenes are drawn in a 1000 x 1333 design space and degraded like a phone
photo: warm indoor cast, under-exposure, tilt, sensor noise, JPEG.
"""

from __future__ import annotations

import io
import math
from dataclasses import dataclass, field

import cv2
import numpy as np
from PIL import Image

from app.imaging.color import linear_to_srgb, srgb_to_linear
from app.imaging.types import BBox

DESIGN_W, DESIGN_H = 1000.0, 1333.0
CATEGORIES = ("hoodie", "tshirt", "jean", "veste", "sneakers")


@dataclass
class SceneTruth:
    category: str
    garment_mask: np.ndarray  # uint8, final image coordinates
    garment_rgb: tuple[float, float, float]  # true base colour (sRGB, before cast)
    stain_bbox: BBox | None
    specks: list[tuple[float, float]]  # normalised centres of injected dust/hairs
    garment_specks: list[tuple[float, float]]
    tilt_deg: float
    cast_gains: tuple[float, float, float]
    details: dict = field(default_factory=dict)


def _chaikin(pts: np.ndarray, iterations: int = 2) -> np.ndarray:
    for _ in range(iterations):
        nxt = np.roll(pts, -1, axis=0)
        q = 0.75 * pts + 0.25 * nxt
        r = 0.25 * pts + 0.75 * nxt
        pts = np.empty((len(pts) * 2, 2), dtype=np.float64)
        pts[0::2] = q
        pts[1::2] = r
    return pts


def _mirror(left: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Build a symmetric closed outline from its left half (top-centre → bottom-centre)."""
    right = [(DESIGN_W - x, y) for x, y in reversed(left[1:-1])]
    return left + right


class _Canvas:
    def __init__(self, width: int, height: int, margin: float, scale: float, offset: tuple[float, float], ss: int = 2):
        self.W, self.H = width, height
        self.cw, self.ch = int(round(width * (1 + 2 * margin))), int(round(height * (1 + 2 * margin)))
        self.mx, self.my = (self.cw - width) / 2, (self.ch - height) / 2
        self.scale = scale
        self.offset = offset
        self.ss = ss
        self.px_per_unit = scale * width / DESIGN_W

    def pt(self, x: float, y: float) -> tuple[float, float]:
        fx = (x / DESIGN_W - 0.5) * self.scale * self.W + self.W / 2 + self.offset[0] * self.W
        fy = (y / DESIGN_H - 0.5) * self.scale * self.H + self.H / 2 + self.offset[1] * self.H
        return fx + self.mx, fy + self.my

    def pts(self, pts) -> np.ndarray:
        return np.array([self.pt(x, y) for x, y in pts], dtype=np.float64)

    def poly(self, pts, smooth: int = 2) -> np.ndarray:
        p = self.pts(pts)
        if smooth:
            p = _chaikin(p, smooth)
        big = np.zeros((self.ch * self.ss, self.cw * self.ss), np.uint8)
        cv2.fillPoly(big, [np.round(p * self.ss).astype(np.int32)], 255, lineType=cv2.LINE_AA)
        return cv2.resize(big, (self.cw, self.ch), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0

    def ellipse(self, cx: float, cy: float, ax: float, ay: float, angle: float = 0.0) -> np.ndarray:
        big = np.zeros((self.ch * self.ss, self.cw * self.ss), np.uint8)
        c = self.pt(cx, cy)
        axes = (int(ax * self.px_per_unit * self.ss), int(ay * self.px_per_unit * self.ss))
        cv2.ellipse(big, (int(c[0] * self.ss), int(c[1] * self.ss)), axes, angle, 0, 360, 255, -1, cv2.LINE_AA)
        return cv2.resize(big, (self.cw, self.ch), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0

    def stroke(self, pts, width: float, smooth: int = 1, dashed: bool = False) -> np.ndarray:
        p = self.pts(pts)
        if smooth and len(p) > 2:
            # open-curve smoothing: keep endpoints
            for _ in range(smooth):
                q = 0.75 * p[:-1] + 0.25 * p[1:]
                r = 0.25 * p[:-1] + 0.75 * p[1:]
                mid = np.empty((2 * len(q), 2))
                mid[0::2], mid[1::2] = q, r
                p = np.vstack([p[:1], mid, p[-1:]])
        big = np.zeros((self.ch * self.ss, self.cw * self.ss), np.uint8)
        thickness = max(1, int(round(width * self.px_per_unit * self.ss)))
        pi = np.round(p * self.ss).astype(np.int32)
        if dashed:
            seg_len = 0.0
            on = True
            for a, b in zip(pi[:-1], pi[1:], strict=False):
                seg_len += float(np.hypot(*(b - a)))
                if on:
                    cv2.line(big, tuple(a), tuple(b), 255, thickness, cv2.LINE_AA)
                if seg_len > 9 * self.ss * self.px_per_unit:
                    on, seg_len = not on, 0.0
        else:
            cv2.polylines(big, [pi], False, 255, thickness, cv2.LINE_AA)
        return cv2.resize(big, (self.cw, self.ch), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0

    def text(self, label: str, cx: float, cy: float, height: float, thickness: float) -> np.ndarray:
        big = np.zeros((self.ch * self.ss, self.cw * self.ss), np.uint8)
        font = cv2.FONT_HERSHEY_DUPLEX
        target_h = height * self.px_per_unit * self.ss
        (tw, th), _ = cv2.getTextSize(label, font, 1.0, 1)
        fs = target_h / th
        th_px = max(1, int(thickness * self.px_per_unit * self.ss))
        (tw, th), _ = cv2.getTextSize(label, font, fs, th_px)
        c = self.pt(cx, cy)
        org = (int(c[0] * self.ss - tw / 2), int(c[1] * self.ss + th / 2))
        cv2.putText(big, label, org, font, fs, 255, th_px, cv2.LINE_AA)
        return cv2.resize(big, (self.cw, self.ch), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0


def _noise(shape: tuple[int, int], sigma: float, rng: np.random.Generator) -> np.ndarray:
    n = rng.standard_normal(shape).astype(np.float32)
    return cv2.GaussianBlur(n, (0, 0), sigma) * sigma * 2.0 if sigma > 0 else n


def _folds(cv: _Canvas, mask: np.ndarray, rng: np.random.Generator, count: int, amp: float) -> np.ndarray:
    """Fold shading: derivative-of-Gaussian profiles across random fold lines."""
    ys, xs = np.nonzero(mask > 0.5)
    field_ = np.zeros(mask.shape, np.float32)
    if xs.size == 0:
        return field_
    H, W = mask.shape
    for _ in range(count):
        i = rng.integers(0, xs.size)
        cx, cy = float(xs[i]), float(ys[i])
        ang = rng.uniform(0, math.pi)
        length = rng.uniform(60, 260) * cv.px_per_unit
        width = rng.uniform(5, 16) * cv.px_per_unit
        amp_k = rng.uniform(0.6, 1.0) * amp
        reach = int(length / 2 * 1.3 + 4 * width)
        x0, x1 = max(0, int(cx) - reach), min(W, int(cx) + reach)
        y0, y1 = max(0, int(cy) - reach), min(H, int(cy) + reach)
        yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
        dx, dy = math.cos(ang), math.sin(ang)
        along = (xx - cx) * dx + (yy - cy) * dy
        across = -(xx - cx) * dy + (yy - cy) * dx
        env = np.exp(-((along / (length / 2)) ** 4))
        prof = (across / width) * np.exp(-(across**2) / (2 * width**2))
        field_[y0:y1, x0:x1] += amp_k * env * prof
    return field_ * mask


def _hoodie(cv: _Canvas, color: np.ndarray, rng, logo: str, has_hood: bool = True):
    if has_hood:
        left = [(500, 175), (430, 188), (385, 238), (372, 300), (300, 320)]
    else:
        left = [(500, 262), (440, 255), (395, 262), (300, 300)]
    left += [
        (240, 360), (190, 450), (150, 580), (120, 720), (105, 860), (110, 935), (205, 945),
        (210, 870), (240, 720), (270, 600), (305, 520), (315, 640), (318, 800), (320, 960),
        (318, 1052), (500, 1056),
    ]
    mask = cv.poly(_mirror(left))
    albedo = np.ones(mask.shape + (3,), np.float32) * color
    shade = np.ones(mask.shape, np.float32)
    if has_hood:
        opening = cv.ellipse(500, 268, 78, 66)
        shade *= 1 - 0.45 * opening
        shade *= 1 - 0.2 * cv.stroke([(372, 300), (430, 330), (500, 338), (570, 330), (628, 300)], 4)
        strings = cv.stroke([(462, 330), (458, 430), (452, 530)], 7) + cv.stroke([(538, 330), (542, 430), (548, 530)], 7)
        strings = np.clip(strings, 0, 1)
        albedo = albedo * (1 - strings[..., None]) + np.array([0.86, 0.85, 0.82], np.float32) * strings[..., None]
    else:
        collar = cv.poly([(395, 262), (500, 300), (605, 262), (590, 300), (500, 345), (410, 300)], smooth=1)
        shade *= 1 - 0.18 * collar
        zip_line = cv.stroke([(500, 300), (500, 1052)], 5)
        teeth = cv.stroke([(500, 300), (500, 1052)], 12, dashed=True)
        shade *= 1 - 0.35 * zip_line - 0.12 * teeth
        for x0 in (360, 560):
            flap = cv.poly([(x0, 420), (x0 + 90, 420), (x0 + 90, 470), (x0 + 45, 490), (x0, 470)], smooth=1)
            shade *= 1 - 0.12 * cv.stroke([(x0, 470), (x0 + 45, 490), (x0 + 90, 470)], 3)
            shade *= 1 - 0.05 * flap
    pocket = cv.stroke([(330, 965), (380, 790), (620, 790), (670, 965)], 4) if has_hood else 0
    shade *= 1 - 0.25 * pocket
    # rib bands (cuffs + hem)
    rib_mask = np.clip(
        cv.poly([(320, 965), (680, 965), (682, 1056), (318, 1056)], smooth=0)
        + cv.poly([(105, 865), (210, 873), (205, 945), (110, 935)], smooth=0)
        + cv.poly([(895, 865), (790, 873), (795, 945), (890, 935)], smooth=0),
        0,
        1,
    )
    xx = np.arange(mask.shape[1], dtype=np.float32)[None, :]
    rib = 0.06 * np.sin(2 * np.pi * xx / max(2.5, 5 * cv.px_per_unit))
    shade *= 1 + rib * rib_mask
    shade *= 1 - 0.2 * cv.stroke([(320, 965), (680, 965)], 3)
    if logo:
        text = cv.text(logo, 500, 600 if has_hood else 650, 46, 7)
        lum = float(np.dot(color, [0.3, 0.59, 0.11]))
        ink = np.array([0.93, 0.92, 0.9] if lum < 0.5 else [0.08, 0.08, 0.09], np.float32)
        albedo = albedo * (1 - text[..., None]) + ink * text[..., None]
    return mask, albedo, shade, {"stain_center": (560, 820), "garment_points": [(420, 700), (600, 520), (400, 880), (250, 650), (750, 650)]}


def _tshirt(cv: _Canvas, color: np.ndarray, rng, logo: str):
    left = [
        (500, 300), (430, 292), (390, 285), (280, 320), (150, 420), (205, 545), (300, 495),
        (305, 700), (310, 900), (312, 1050), (500, 1055),
    ]
    mask = cv.poly(_mirror(left))
    albedo = np.ones(mask.shape + (3,), np.float32) * color
    shade = np.ones(mask.shape, np.float32)
    shade *= 1 - 0.3 * cv.ellipse(500, 300, 92, 44)
    shade *= 1 - 0.18 * cv.stroke([(395, 290), (450, 340), (500, 352), (550, 340), (605, 290)], 6)
    if logo:
        text = cv.text(logo, 500, 560, 52, 8)
        albedo = albedo * (1 - text[..., None]) + np.array([0.95, 0.95, 0.93], np.float32) * text[..., None]
    return mask, albedo, shade, {"stain_center": (430, 820), "garment_points": [(420, 700), (600, 450), (400, 950), (600, 850)]}


def _jean(cv: _Canvas, color: np.ndarray, rng, logo: str):
    outline = [
        (300, 170), (700, 170), (715, 500), (710, 800), (700, 1130), (690, 1240), (520, 1240),
        (510, 900), (500, 565), (490, 900), (480, 1240), (310, 1240), (300, 1130), (290, 800), (285, 500),
    ]
    mask = cv.poly(outline, smooth=1)
    yy, xx = np.mgrid[0 : mask.shape[0], 0 : mask.shape[1]].astype(np.float32)
    twill = 0.05 * np.sin(2 * np.pi * (xx + yy) / max(3.0, 6 * cv.px_per_unit))
    fade = np.zeros(mask.shape, np.float32)
    for cx in (395, 605):
        c = cv.pt(cx, 760)
        fade += np.exp(-(((xx - c[0]) / (70 * cv.px_per_unit)) ** 2) - (((yy - c[1]) / (330 * cv.px_per_unit)) ** 2))
    albedo = np.ones(mask.shape + (3,), np.float32) * color
    albedo = albedo * (1 + 0.28 * fade[..., None])
    shade = (1 + twill).astype(np.float32)
    thread = np.array([0.80, 0.56, 0.26], np.float32)
    stitches = np.clip(
        cv.stroke([(300, 232), (700, 232)], 2.5, dashed=True)
        + cv.stroke([(310, 240), (360, 300), (405, 345)], 2.5, dashed=True)
        + cv.stroke([(690, 240), (640, 300), (595, 345)], 2.5, dashed=True)
        + cv.stroke([(500, 232), (500, 420), (470, 455), (455, 420), (455, 240)], 2.5, dashed=True)
        + cv.stroke([(292, 500), (292, 1180)], 2.5, dashed=True)
        + cv.stroke([(708, 500), (708, 1180)], 2.5, dashed=True),
        0,
        1,
    )
    albedo = albedo * (1 - stitches[..., None]) + thread * stitches[..., None]
    shade *= 1 - 0.25 * cv.stroke([(300, 228), (700, 228)], 3)
    shade *= 1 - 0.3 * cv.stroke([(500, 232), (500, 440)], 3)
    for x in (350, 440, 560, 650):
        shade *= 1 - 0.2 * cv.poly([(x - 8, 165), (x + 8, 165), (x + 8, 240), (x - 8, 240)], smooth=0)
    rivets = np.clip(cv.ellipse(405, 345, 7, 7) + cv.ellipse(595, 345, 7, 7), 0, 1)
    albedo = albedo * (1 - rivets[..., None]) + np.array([0.72, 0.48, 0.25], np.float32) * rivets[..., None]
    shade *= 1 + 0.25 * cv.poly([(470, 600), (500, 580), (530, 600), (510, 640), (490, 640)], smooth=1)
    return mask, albedo, shade.astype(np.float32), {
        "stain_center": (620, 980),
        "garment_points": [(390, 700), (610, 650), (400, 1000), (600, 1050)],
        "rivets": [(405, 345), (595, 345)],
    }


def _sneakers(cv: _Canvas, color: np.ndarray, rng, logo: str):
    def shoe(dy: float):
        return [
            (200, 560 + dy), (212, 645 + dy), (800, 655 + dy), (848, 615 + dy), (810, 560 + dy),
            (630, 500 + dy), (525, 430 + dy), (335, 418 + dy), (235, 440 + dy),
        ]

    masks, sole_m, stripe_m, lace_m = [], [], [], []
    for dy in (-200, 260):
        masks.append(cv.poly(shoe(dy)))
        sole_m.append(cv.poly([(205, 600 + dy), (845, 612 + dy), (802, 657 + dy), (212, 648 + dy)], smooth=1))
        stripe_m.append(
            cv.stroke([(330, 600 + dy), (430, 560 + dy), (540, 520 + dy), (650, 500 + dy)], 22, smooth=2)
        )
        lace_m.append(
            np.clip(
                sum(cv.stroke([(540 + 30 * k, 445 + 14 * k + dy), (575 + 30 * k, 470 + 14 * k + dy)], 5) for k in range(4)),
                0,
                1,
            )
        )
    mask = np.clip(sum(masks), 0, 1)
    sole = np.clip(sum(sole_m), 0, 1) * mask
    stripe = np.clip(sum(stripe_m), 0, 1) * mask * (1 - sole)
    laces = np.clip(sum(lace_m), 0, 1) * mask
    albedo = np.ones(mask.shape + (3,), np.float32) * color
    albedo = albedo * (1 - sole[..., None]) + np.array([0.92, 0.91, 0.88], np.float32) * sole[..., None]
    albedo = albedo * (1 - stripe[..., None]) + np.array([0.12, 0.13, 0.15], np.float32) * stripe[..., None]
    albedo = albedo * (1 - laces[..., None]) + np.array([0.95, 0.95, 0.94], np.float32) * laces[..., None]
    shade = np.ones(mask.shape, np.float32)
    for dy in (-200, 260):
        shade *= 1 - 0.3 * cv.ellipse(300, 428 + dy, 55, 14)
        shade *= 1 - 0.25 * cv.stroke([(208, 602 + dy), (845, 612 + dy)], 3)
    return mask, albedo, shade, {"stain_center": (720, 840), "garment_points": [(400, 520), (700, 1010), (450, 860)]}


def make_scene(
    category: str = "hoodie",
    width: int = 900,
    height: int = 1200,
    seed: int = 0,
    *,
    color: tuple[float, float, float] | None = None,
    cast: tuple[float, float, float] = (1.12, 1.0, 0.78),
    exposure: float = 0.78,
    tilt: float = 4.0,
    scale: float = 0.74,
    offset: tuple[float, float] = (0.04, 0.03),
    dust: int = 14,
    hairs: int = 2,
    stain: bool = True,
    noise: float = 0.012,
    jpeg_quality: int = 86,
    logo: str = "ENHANCE",
    background: tuple[float, float, float] | None = None,
) -> tuple[np.ndarray, SceneTruth]:
    if category not in CATEGORIES:
        raise ValueError(f"unknown category {category}")
    rng = np.random.default_rng(seed)
    default_colors = {
        "hoodie": (0.13, 0.16, 0.24),
        "tshirt": (0.70, 0.14, 0.16),
        "jean": (0.20, 0.29, 0.46),
        "veste": (0.40, 0.41, 0.28),
        "sneakers": (0.93, 0.92, 0.90),
    }
    base = np.array(color or default_colors[category], np.float32)
    if background is None:
        # sneakers are usually shot on the floor; garments on a bed sheet
        background = (0.60, 0.585, 0.56) if category == "sneakers" else (0.90, 0.885, 0.86)
    cv = _Canvas(width, height, margin=0.12, scale=scale, offset=offset)

    if category == "hoodie":
        mask, albedo, shade, meta = _hoodie(cv, base, rng, logo)
    elif category == "veste":
        mask, albedo, shade, meta = _hoodie(cv, base, rng, "", has_hood=False)
    elif category == "tshirt":
        mask, albedo, shade, meta = _tshirt(cv, base, rng, logo)
    elif category == "jean":
        mask, albedo, shade, meta = _jean(cv, base, rng, logo)
    else:
        mask, albedo, shade, meta = _sneakers(cv, base, rng, logo)

    ch, cw = mask.shape
    # --- background: bed sheet with folds and weave ------------------------------------
    bg = np.ones((ch, cw, 3), np.float32) * np.array(background, np.float32)
    bg_shade = 1 + 0.05 * _noise((ch, cw), 60, rng) + 0.012 * _noise((ch, cw), 0.8, rng)
    yy, xx = np.mgrid[0:ch, 0:cw].astype(np.float32)
    bg_shade += 0.05 * (1 - (xx / cw + yy / ch))  # window light from the top-left
    sheet_folds = _folds(cv, np.ones((ch, cw), np.float32), rng, 6, 0.10)
    bg_shade += sheet_folds
    # contact shadow of the garment on the sheet
    sh = cv2.GaussianBlur(mask, (0, 0), 10 * cv.px_per_unit + 1)
    sh = np.roll(np.roll(sh, int(6 * cv.px_per_unit), axis=1), int(10 * cv.px_per_unit), axis=0)
    bg_shade *= 1 - 0.32 * sh * (1 - mask)

    # --- garment: fabric texture, folds, volume ---------------------------------------
    m8 = (mask > 0.5).astype(np.uint8)
    dist = cv2.distanceTransform(m8, cv2.DIST_L2, 5)
    volume = 1 - 0.10 * np.exp(-dist / (14 * cv.px_per_unit + 1))
    fabric = 1 + 0.03 * _noise((ch, cw), 0.7, rng) + 0.02 * _noise((ch, cw), 3.0, rng)
    folds = _folds(cv, mask, rng, 12, 0.16)
    g_shade = shade * volume * fabric * (1 + folds)
    garment = albedo * g_shade[..., None]

    stain_bbox_canvas = None
    if stain:
        sx, sy = cv.pt(*meta["stain_center"])
        r = 15 * cv.px_per_unit
        blob = np.exp(-(((xx - sx) / r) ** 2 + ((yy - sy) / (r * 0.8)) ** 2))
        blob += 0.6 * np.exp(-(((xx - sx - r * 0.9) / (r * 0.5)) ** 2 + ((yy - sy + r * 0.4) / (r * 0.45)) ** 2))
        blob = np.clip(blob, 0, 1) * mask
        stain_color = np.array([0.55, 0.42, 0.25], np.float32)
        lum = float(np.dot(base, [0.3, 0.59, 0.11]))
        if lum < 0.35:  # stains on dark fabric read as lighter, desaturated marks
            stain_color = np.array([0.42, 0.40, 0.36], np.float32)
        garment = garment * (1 - 0.65 * blob[..., None]) + stain_color * 0.65 * blob[..., None] * g_shade[..., None]
        stain_bbox_canvas = (sx - 1.6 * r, sy - 1.4 * r, 3.4 * r, 2.8 * r)

    scene = bg * bg_shade[..., None] * (1 - mask[..., None]) + garment * mask[..., None]

    # --- dust and hairs -----------------------------------------------------------------
    speck_pts: list[tuple[float, float, bool]] = []
    ys, xs = np.nonzero(m8)
    fx0, fy0 = cv.mx, cv.my
    for i in range(dust):
        on_garment = i % 3 != 2 and xs.size > 0
        if on_garment:
            j = rng.integers(0, xs.size)
            px, py = float(xs[j]), float(ys[j])
        else:
            px, py = rng.uniform(fx0 + 30, fx0 + width - 30), rng.uniform(fy0 + 30, fy0 + height - 30)
            if m8[int(py), int(px)]:
                continue
        rad = rng.uniform(1.2, 2.4) * max(1.0, width / 900)
        local = scene[int(py), int(px)]
        lum = float(np.dot(local, [0.3, 0.59, 0.11]))
        col = np.array([0.92, 0.91, 0.89] if lum < 0.55 else [0.18, 0.16, 0.15], np.float32)
        pad = int(rad) + 6
        x0, y0 = max(0, int(px) - pad), max(0, int(py) - pad)
        x1, y1 = min(cw, int(px) + pad + 1), min(ch, int(py) + pad + 1)
        spot = np.zeros((y1 - y0, x1 - x0), np.float32)
        cv2.circle(spot, (int((px - x0) * 4), int((py - y0) * 4)), int(rad * 4), 1.0, -1, cv2.LINE_AA, shift=2)
        spot = cv2.GaussianBlur(spot, (0, 0), 0.6)[..., None]
        scene[y0:y1, x0:x1] = scene[y0:y1, x0:x1] * (1 - spot) + col * spot
        speck_pts.append((px, py, on_garment))
    for _ in range(hairs):
        if xs.size == 0:
            break
        j = rng.integers(0, xs.size)
        px, py = float(xs[j]), float(ys[j])
        ang = rng.uniform(0, math.pi)
        length = rng.uniform(25, 45) * max(1.0, width / 900)
        t = np.linspace(0, 1, 12)
        bend = rng.uniform(-0.25, 0.25)
        pts = np.stack(
            [px + np.cos(ang) * length * (t - 0.5) - np.sin(ang) * bend * length * (t - 0.5) ** 2,
             py + np.sin(ang) * length * (t - 0.5) + np.cos(ang) * bend * length * (t - 0.5) ** 2],
            axis=1,
        )
        pad = int(length) + 4
        x0, y0 = max(0, int(px) - pad), max(0, int(py) - pad)
        x1, y1 = min(cw, int(px) + pad + 1), min(ch, int(py) + pad + 1)
        hair = np.zeros((y1 - y0, x1 - x0), np.float32)
        local_pts = np.round((pts - [x0, y0]) * 4).astype(np.int32)
        cv2.polylines(hair, [local_pts], False, 1.0, 1, cv2.LINE_AA, shift=2)
        local = scene[int(py), int(px)]
        lum = float(np.dot(local, [0.3, 0.59, 0.11]))
        col = np.array([0.85, 0.83, 0.80] if lum < 0.5 else [0.10, 0.08, 0.07], np.float32)
        hair = np.clip(hair, 0, 0.85)[..., None]
        scene[y0:y1, x0:x1] = scene[y0:y1, x0:x1] * (1 - hair) + col * hair
        speck_pts.append((px, py, True))

    # --- camera: illuminant cast + exposure in linear light ----------------------------
    lin = srgb_to_linear(np.clip(scene, 0, 1))
    lin = lin * np.array(cast, np.float32) * exposure
    vign = 1 - 0.18 * (((xx - cw / 2) / (cw / 2)) ** 2 + ((yy - ch / 2) / (ch / 2)) ** 2)
    lin = lin * vign[..., None]
    shot = linear_to_srgb(np.clip(lin, 0, 1))

    # --- tilt (rotate whole canvas) then crop the final frame ---------------------------
    centre = (cw / 2, ch / 2)
    rot = cv2.getRotationMatrix2D(centre, tilt, 1.0)
    shot = cv2.warpAffine(shot, rot, (cw, ch), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    mask_r = cv2.warpAffine(mask, rot, (cw, ch), flags=cv2.INTER_LINEAR)
    x0, y0 = int(round(cv.mx)), int(round(cv.my))
    shot = shot[y0 : y0 + height, x0 : x0 + width]
    mask_r = mask_r[y0 : y0 + height, x0 : x0 + width]

    def tr(px: float, py: float) -> tuple[float, float]:
        v = rot @ np.array([px, py, 1.0])
        return float((v[0] - x0) / width), float((v[1] - y0) / height)

    # --- sensor: slight softness, noise, JPEG ------------------------------------------
    shot = cv2.GaussianBlur(shot, (0, 0), 0.55)
    shot = shot + rng.normal(0, noise, shot.shape).astype(np.float32)
    shot = shot + cv2.GaussianBlur(rng.normal(0, noise * 0.8, shot.shape).astype(np.float32), (0, 0), 1.2)
    img = np.clip(shot * 255 + 0.5, 0, 255).astype(np.uint8)
    if jpeg_quality:
        buf = io.BytesIO()
        Image.fromarray(img).save(buf, "JPEG", quality=jpeg_quality)
        img = np.asarray(Image.open(io.BytesIO(buf.getvalue())).convert("RGB")).copy()

    stain_bbox = None
    if stain_bbox_canvas:
        bx, by, bw, bh = stain_bbox_canvas
        corners = [tr(bx, by), tr(bx + bw, by), tr(bx, by + bh), tr(bx + bw, by + bh)]
        cx_ = [c[0] for c in corners]
        cy_ = [c[1] for c in corners]
        stain_bbox = BBox(min(cx_), min(cy_), max(cx_) - min(cx_), max(cy_) - min(cy_))

    specks_n = [tr(px, py) for px, py, _ in speck_pts]
    garment_specks = [tr(px, py) for px, py, g in speck_pts if g]
    truth = SceneTruth(
        category=category,
        garment_mask=(mask_r > 0.5).astype(np.uint8) * 255,
        garment_rgb=tuple(float(c) for c in base),
        stain_bbox=stain_bbox,
        specks=[p for p in specks_n if 0 <= p[0] <= 1 and 0 <= p[1] <= 1],
        garment_specks=[p for p in garment_specks if 0 <= p[0] <= 1 and 0 <= p[1] <= 1],
        tilt_deg=tilt,
        cast_gains=cast,
        details={k: [tr(*cv.pt(*p)) for p in v] for k, v in meta.items() if k == "rivets"},
    )
    return img, truth


def clean_reference(category: str, width: int = 900, height: int = 1200, seed: int = 0, **kw) -> np.ndarray:
    """Same scene without degradations: what a perfect enhancer would converge to."""
    img, _ = make_scene(
        category, width, height, seed, cast=(1.0, 1.0, 1.0), exposure=1.0, tilt=0.0, dust=0, hairs=0,
        noise=0.0, jpeg_quality=0, **kw,
    )
    return img
