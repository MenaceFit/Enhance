"""Clothing attributes from the garment silhouette and colours (classical engine).

The local engine infers the garment category from shape cues (legs, sleeves,
hood, a pair of shoes, central closure) and reports dominant colours, pattern
and logo/print regions. It is intentionally modest about its confidence; a
vision provider (see ``app.providers.anthropic_vision``) can replace it for
fine-grained attributes (brand logos, pockets count, material).
"""

from __future__ import annotations

import cv2
import numpy as np

from app.imaging.color import color_name, linear_to_srgb, rgb_to_hex, rgb_to_lab, srgb_to_linear, to_float
from app.imaging.types import BBox, ClothingAttributes

CATEGORY_LABELS = {
    "hoodie": "Hoodie",
    "sweat": "Sweat",
    "pull": "Pull",
    "tshirt": "T-shirt",
    "veste": "Veste",
    "jean": "Jean",
    "pantalon": "Pantalon",
    "short": "Short",
    "sneakers": "Sneakers",
    "robe": "Robe",
    "vetement": "Vêtement",
}


def _runs(row: np.ndarray, min_gap: int) -> int:
    """Number of foreground runs in a binary row, merging gaps narrower than min_gap."""
    idx = np.flatnonzero(row)
    if idx.size == 0:
        return 0
    gaps = np.diff(idx)
    return int(1 + np.sum(gaps > min_gap))


def _shape_features(mask: np.ndarray) -> dict:
    m = (mask > 127).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    comps = sorted(
        [(int(stats[i, cv2.CC_STAT_AREA]), i) for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] > 0.01 * m.size],
        reverse=True,
    )
    ys, xs = np.nonzero(m)
    if xs.size == 0:
        return {"empty": True}
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    crop = m[y0 : y1 + 1, x0 : x1 + 1]
    hh, ww = crop.shape
    min_gap = max(2, int(0.03 * ww))
    runs = np.array([_runs(crop[r], min_gap) for r in range(hh)])
    widths = np.array([np.count_nonzero(crop[r]) for r in range(hh)], dtype=np.float32)
    extents = np.array(
        [(np.flatnonzero(crop[r]).max() - np.flatnonzero(crop[r]).min() + 1) if widths[r] else 0 for r in range(hh)],
        dtype=np.float32,
    )

    def band(a: np.ndarray, lo: float, hi: float) -> np.ndarray:
        return a[int(lo * hh) : max(int(lo * hh) + 1, int(hi * hh))]

    pair = False
    if len(comps) >= 2 and comps[1][0] > 0.5 * comps[0][0]:
        boxes = [stats[i] for _, i in comps[:2]]
        pair = all(b[cv2.CC_STAT_WIDTH] > 1.2 * b[cv2.CC_STAT_HEIGHT] for b in boxes)

    # Hanging sleeves give three runs (sleeve | body | sleeve); legs give exactly two runs and
    # reach the bottom of the silhouette.
    arms_hanging = float(np.mean(band(runs, 0.35, 0.8) >= 3))
    legs = float(np.mean(band(runs, 0.7, 0.97) == 2)) if arms_hanging < 0.25 else 0.0
    top_ext = float(np.median(band(extents, 0.12, 0.3)))
    low_ext = float(np.median(band(extents, 0.65, 0.9)))
    # A hood is a narrow single lobe that persists over the top ~10 % (a collar notch does not).
    head = band(extents, 0.03, 0.1)
    hood = bool(np.median(head) < 0.42 * extents.max() and np.mean(band(runs, 0.0, 0.1) == 1) > 0.8)
    return {
        "empty": False,
        "components": len(comps),
        "pair": pair,
        "aspect": hh / max(1, ww),
        "legs": legs,
        "arms_hanging": arms_hanging,
        "shoulder_ratio": top_ext / max(1.0, low_ext),
        "hood": hood,
        "fill": float(crop.mean()),
    }


def _central_closure(img_f: np.ndarray, mask: np.ndarray) -> bool:
    """A long vertical dark/bright line in the middle of the body (zip, button placket)."""
    m = mask > 127
    ys, xs = np.nonzero(m)
    if xs.size == 0:
        return False
    cx = int(np.median(xs))
    y0, y1 = np.percentile(ys, 30), np.percentile(ys, 90)
    half = max(3, int(0.06 * (xs.max() - xs.min())))
    L = rgb_to_lab(img_f)[..., 0]
    strip = L[int(y0) : int(y1), max(0, cx - half) : cx + half]
    if strip.size == 0 or strip.shape[1] < 5:
        return False
    profile = strip.mean(axis=0)
    base = np.median(profile)
    peak = np.max(np.abs(profile - base))
    col = int(np.argmax(np.abs(profile - base)))
    consistency = np.mean(np.abs(strip[:, col] - np.median(strip, axis=1)) > 0.5 * peak)
    return bool(peak > 6 and consistency > 0.6)


def _dominant_colors(img_f: np.ndarray, mask: np.ndarray, gains) -> tuple[list[dict], float]:
    m = mask > 127
    px = img_f[m]
    if px.shape[0] < 50:
        return [], 0.0
    if gains is not None:
        px = linear_to_srgb(np.clip(srgb_to_linear(px) * np.asarray(gains, np.float32), 0, 1))
    if px.shape[0] > 20000:
        px = px[np.random.default_rng(0).choice(px.shape[0], 20000, replace=False)]
    lab = rgb_to_lab(px.reshape(-1, 1, 3)).reshape(-1, 3)
    k = 4
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 25, 0.5)
    _, labels, centers = cv2.kmeans(lab.astype(np.float32), k, None, criteria, 2, cv2.KMEANS_PP_CENTERS)
    counts = np.bincount(labels.ravel(), minlength=k)
    order = np.argsort(-counts)
    out = []
    for i in order:
        share = counts[i] / counts.sum()
        if share < 0.08:
            continue
        rgb = np.median(px[labels.ravel() == i], axis=0)
        out.append({"hex": rgb_to_hex(rgb), "name": color_name(rgb), "share": round(float(share), 3)})
    # merge entries with the same name (shading of the same colour)
    merged: dict[str, dict] = {}
    for c in out:
        if c["name"] in merged:
            merged[c["name"]]["share"] = round(merged[c["name"]]["share"] + c["share"], 3)
        else:
            merged[c["name"]] = dict(c)
    colors = sorted(merged.values(), key=lambda c: -c["share"])[:3]
    spread = float(np.sqrt(lab[:, 1].var() + lab[:, 2].var()))
    return colors, spread


def _logo_regions(img_f: np.ndarray, mask: np.ndarray) -> list[BBox]:
    """Compact, high-contrast, edge-dense regions inside the garment: logos or prints."""
    h, w = mask.shape
    m = (mask > 127).astype(np.uint8)
    interior = cv2.erode(m, np.ones((9, 9), np.uint8))
    gray = cv2.cvtColor((img_f * 255).astype(np.uint8), cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (0, 0), 1.0), 40, 110) * interior
    dense = cv2.dilate(edges, np.ones((7, 7), np.uint8))
    dense = cv2.morphologyEx(dense, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    n, _, stats, _ = cv2.connectedComponentsWithStats((dense > 0).astype(np.uint8), connectivity=8)
    garment_area = max(1, int(m.sum()))
    out = []
    for i in range(1, n):
        x, y, bw, bh, area = stats[i]
        ratio = area / garment_area
        if 0.004 <= ratio <= 0.2 and max(bw, bh) / max(1, min(bw, bh)) < 8:
            density = edges[y : y + bh, x : x + bw].astype(bool).mean()
            if density > 0.06:
                out.append(BBox(x / w, y / h, bw / w, bh / h))
    return out[:5]


def analyze_clothing(img: np.ndarray, mask: np.ndarray, illuminant_gains=None) -> ClothingAttributes:
    f = to_float(img)
    if max(f.shape[:2]) > 768:
        s = 768 / max(f.shape[:2])
        size = (round(f.shape[1] * s), round(f.shape[0] * s))
        f = cv2.resize(f, size, interpolation=cv2.INTER_AREA)
        mask = cv2.resize(mask, size, interpolation=cv2.INTER_LINEAR)
    feats = _shape_features(mask)
    colors, spread = _dominant_colors(f, mask, illuminant_gains)
    logos = _logo_regions(f, mask)

    if feats.get("empty"):
        return ClothingAttributes(category="vetement", label=CATEGORY_LABELS["vetement"], confidence=0.1)

    scores: dict[str, float] = {k: 0.05 for k in CATEGORY_LABELS}
    closure = _central_closure(f, mask)
    denim_like = False
    if colors:
        lab = rgb_to_lab(np.array([[[int(colors[0]["hex"][i : i + 2], 16) / 255 for i in (1, 3, 5)]]], np.float32))[0, 0]
        hue = np.degrees(np.arctan2(lab[2], lab[1])) % 360
        denim_like = 220 <= hue <= 300 and 8 <= np.hypot(lab[1], lab[2]) <= 40 and 20 <= lab[0] <= 65

    if feats["pair"]:
        scores["sneakers"] += 0.75
    if feats["legs"] > 0.55:
        if feats["aspect"] > 1.25:
            scores["jean" if denim_like else "pantalon"] += 0.6
            scores["pantalon" if denim_like else "jean"] += 0.15
        else:
            scores["short"] += 0.55
    elif feats["arms_hanging"] > 0.3 or feats["shoulder_ratio"] > 1.3:
        long_sleeves = feats["arms_hanging"] > 0.3
        if long_sleeves and closure and not feats["hood"]:
            scores["veste"] += 0.55
            scores["sweat"] += 0.1
        elif long_sleeves and feats["hood"]:
            scores["hoodie"] += 0.65
            if closure:
                scores["veste"] += 0.2
        elif long_sleeves:
            scores["sweat"] += 0.4
            scores["pull"] += 0.3
            scores["veste"] += 0.1
        else:
            scores["tshirt"] += 0.6
    elif feats["aspect"] > 1.7:
        scores["robe"] += 0.35
    else:
        scores["vetement"] += 0.3

    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    total = sum(v for _, v in ranked)
    best, best_score = ranked[0]
    confidence = float(np.clip(best_score / total * 1.4, 0.1, 0.8))
    candidates = [{"category": k, "label": CATEGORY_LABELS[k], "score": round(v / total, 3)} for k, v in ranked[:3]]

    pattern = "uni"
    if logos:
        pattern = "logo ou imprimé"
    elif spread > 14 or (len(colors) > 1 and colors[0]["share"] < 0.6):
        pattern = "motif"

    return ClothingAttributes(
        category=best,
        label=CATEGORY_LABELS[best],
        confidence=round(confidence, 3),
        candidates=candidates,
        dominant_colors=colors,
        pattern=pattern,
        texture="denim" if denim_like and feats["legs"] > 0.55 else "tissu",
        features={
            "hood": feats["hood"],
            "legs": feats["legs"] > 0.55,
            "long_sleeves": feats["arms_hanging"] > 0.3,
            "central_closure": closure,
            "pair": feats["pair"],
            "logos": [{"x": b.x, "y": b.y, "w": b.w, "h": b.h} for b in logos],
        },
        provider="local",
    )
