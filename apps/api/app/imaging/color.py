"""Colour-science primitives used across the engine.

Conventions: images are float32 RGB arrays in [0, 1] (sRGB-encoded unless the
name says ``linear``). Lab uses OpenCV's float convention: L in [0, 100],
a/b roughly in [-128, 127], D65 white.
"""

from __future__ import annotations

import cv2
import numpy as np

LUMA_LINEAR = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


def to_float(img: np.ndarray) -> np.ndarray:
    if img.dtype == np.uint8:
        return img.astype(np.float32) / 255.0
    return img.astype(np.float32, copy=False)


def to_uint8(img: np.ndarray) -> np.ndarray:
    return np.clip(img * 255.0 + 0.5, 0, 255).astype(np.uint8)


def srgb_to_linear(img: np.ndarray) -> np.ndarray:
    img = np.clip(img, 0.0, 1.0)
    return np.where(img <= 0.04045, img / 12.92, ((img + 0.055) / 1.055) ** 2.4).astype(np.float32)


def linear_to_srgb(img: np.ndarray) -> np.ndarray:
    img = np.clip(img, 0.0, 1.0)
    return np.where(img <= 0.0031308, img * 12.92, 1.055 * np.power(img, 1 / 2.4) - 0.055).astype(np.float32)


def rgb_to_lab(img: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(np.clip(img, 0, 1).astype(np.float32), cv2.COLOR_RGB2Lab)


def lab_to_rgb(lab: np.ndarray) -> np.ndarray:
    return np.clip(cv2.cvtColor(lab.astype(np.float32), cv2.COLOR_Lab2RGB), 0.0, 1.0)


def lab_to_lch(lab: np.ndarray) -> np.ndarray:
    L, a, b = lab[..., 0], lab[..., 1], lab[..., 2]
    C = np.sqrt(a * a + b * b)
    h = np.degrees(np.arctan2(b, a)) % 360.0
    return np.stack([L, C, h], axis=-1).astype(np.float32)


def lch_to_lab(lch: np.ndarray) -> np.ndarray:
    L, C, h = lch[..., 0], lch[..., 1], np.radians(lch[..., 2])
    return np.stack([L, C * np.cos(h), C * np.sin(h)], axis=-1).astype(np.float32)


def luminance_linear(linear_rgb: np.ndarray) -> np.ndarray:
    return linear_rgb @ LUMA_LINEAR


def delta_e_2000(lab1: np.ndarray, lab2: np.ndarray, kL: float = 1.0, kC: float = 1.0, kH: float = 1.0) -> np.ndarray:
    """Vectorised CIEDE2000 colour difference (Sharma et al. 2005).

    ``kL`` > 1 down-weights lightness differences; the fidelity check uses this
    because legitimate exposure correction changes lightness, not the article's
    colour.
    """
    L1, a1, b1 = (lab1[..., i].astype(np.float64) for i in range(3))
    L2, a2, b2 = (lab2[..., i].astype(np.float64) for i in range(3))

    C1 = np.hypot(a1, b1)
    C2 = np.hypot(a2, b2)
    C_bar = (C1 + C2) / 2.0
    C_bar7 = C_bar**7
    G = 0.5 * (1 - np.sqrt(C_bar7 / (C_bar7 + 25.0**7)))
    a1p = (1 + G) * a1
    a2p = (1 + G) * a2
    C1p = np.hypot(a1p, b1)
    C2p = np.hypot(a2p, b2)
    h1p = np.degrees(np.arctan2(b1, a1p)) % 360.0
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360.0

    dLp = L2 - L1
    dCp = C2p - C1p
    dhp = h2p - h1p
    dhp = np.where(dhp > 180, dhp - 360, dhp)
    dhp = np.where(dhp < -180, dhp + 360, dhp)
    dhp = np.where(C1p * C2p == 0, 0.0, dhp)
    dHp = 2 * np.sqrt(C1p * C2p) * np.sin(np.radians(dhp) / 2.0)

    Lp_bar = (L1 + L2) / 2.0
    Cp_bar = (C1p + C2p) / 2.0
    hsum = h1p + h2p
    hp_bar = np.where(
        C1p * C2p == 0,
        hsum,
        np.where(np.abs(h1p - h2p) <= 180, hsum / 2.0, np.where(hsum < 360, (hsum + 360) / 2.0, (hsum - 360) / 2.0)),
    )
    T = (
        1
        - 0.17 * np.cos(np.radians(hp_bar - 30))
        + 0.24 * np.cos(np.radians(2 * hp_bar))
        + 0.32 * np.cos(np.radians(3 * hp_bar + 6))
        - 0.20 * np.cos(np.radians(4 * hp_bar - 63))
    )
    d_theta = 30 * np.exp(-(((hp_bar - 275) / 25) ** 2))
    Cp_bar7 = Cp_bar**7
    R_C = 2 * np.sqrt(Cp_bar7 / (Cp_bar7 + 25.0**7))
    S_L = 1 + (0.015 * (Lp_bar - 50) ** 2) / np.sqrt(20 + (Lp_bar - 50) ** 2)
    S_C = 1 + 0.045 * Cp_bar
    S_H = 1 + 0.015 * Cp_bar * T
    R_T = -np.sin(np.radians(2 * d_theta)) * R_C

    tL = dLp / (kL * S_L)
    tC = dCp / (kC * S_C)
    tH = dHp / (kH * S_H)
    return np.sqrt(tL**2 + tC**2 + tH**2 + R_T * tC * tH).astype(np.float32)


def rgb_to_hex(rgb: np.ndarray | tuple[float, float, float]) -> str:
    r, g, b = (int(round(float(np.clip(c, 0, 1)) * 255)) for c in rgb)
    return f"#{r:02X}{g:02X}{b:02X}"


# Reference swatches for naming garment colours in French (sRGB 0-255).
_COLOR_NAMES: list[tuple[str, tuple[int, int, int]]] = [
    ("noir", (25, 25, 27)),
    ("anthracite", (60, 62, 66)),
    ("gris", (128, 128, 128)),
    ("gris clair", (190, 190, 190)),
    ("blanc", (245, 245, 242)),
    ("écru", (238, 230, 210)),
    ("beige", (215, 195, 160)),
    ("camel", (190, 140, 85)),
    ("marron", (110, 72, 45)),
    ("kaki", (110, 110, 70)),
    ("vert", (50, 130, 70)),
    ("vert sapin", (30, 75, 50)),
    ("bleu marine", (30, 40, 75)),
    ("bleu", (45, 90, 170)),
    ("bleu ciel", (140, 185, 225)),
    ("denim", (70, 95, 130)),
    ("turquoise", (40, 170, 170)),
    ("violet", (110, 60, 140)),
    ("lilas", (190, 160, 210)),
    ("rose", (230, 150, 175)),
    ("fuchsia", (200, 40, 120)),
    ("rouge", (190, 35, 40)),
    ("bordeaux", (110, 25, 40)),
    ("orange", (230, 120, 40)),
    ("jaune", (235, 200, 50)),
    ("moutarde", (200, 160, 40)),
]
_NAME_LAB = rgb_to_lab(np.array([[c for _, c in _COLOR_NAMES]], dtype=np.float32) / 255.0)[0]


def color_name(rgb: np.ndarray | tuple[float, float, float]) -> str:
    lab = rgb_to_lab(np.array([[rgb]], dtype=np.float32))[0, 0]
    d = delta_e_2000(np.broadcast_to(lab, _NAME_LAB.shape), _NAME_LAB)
    return _COLOR_NAMES[int(np.argmin(d))][0]
