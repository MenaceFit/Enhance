"""Engine tests against synthetic scenes with known ground truth.

They encode the product's promises: dust goes away, defects stay, the garment's
colour is preserved while the light is corrected, framing never cuts the
garment, and the guards catch tampering.
"""

from __future__ import annotations

import io
from functools import lru_cache

import cv2
import numpy as np
import pytest
from PIL import Image

from app.imaging.analysis.composition import estimate_tilt
from app.imaging.analysis.illuminant import estimate_illuminant
from app.imaging.analysis.segmentation import segment_garment
from app.imaging.checks.fidelity import color_fidelity
from app.imaging.checks.structure import structural_check
from app.imaging.color import delta_e_2000, rgb_to_lab
from app.imaging.consistency import harmonize
from app.imaging.image_io import ImageDecodeError, decode_image, encode_image
from app.imaging.ops.geometry import plan_geometry
from app.imaging.pipeline import analyze, enhance
from app.imaging.render import RenderSource, render
from app.imaging.settings import EnhancementSettings
from app.imaging.synthetic import make_scene
from app.providers.registry import local_router


@lru_cache
def scene(category: str, seed: int = 0, **kw):
    return make_scene(category, seed=seed, **kw)


@lru_cache
def analysed(category: str, seed: int = 0):
    img, truth = scene(category, seed)
    bundle = analyze(img, local_router())
    return img, truth, bundle


def source(category: str, seed: int = 0) -> RenderSource:
    img, _, b = analysed(category, seed)
    return RenderSource(img, b.mask, b.labels, b.analysis)


# --- colour science -------------------------------------------------------------------


def test_delta_e_2000_reference_pairs():
    # Sharma, Wu & Dalal (2005) test data
    pairs = [
        ((50.0, 2.6772, -79.7751), (50.0, 0.0, -82.7485), 2.0425),
        ((50.0, 3.1571, -77.2803), (50.0, 0.0, -82.7485), 2.8615),
        ((50.0, 2.5, 0.0), (73.0, 25.0, -18.0), 27.1492),
        ((60.2574, -34.0099, 36.2677), (60.4626, -34.1751, 39.4387), 1.2644),
    ]
    for a, b, expected in pairs:
        de = float(delta_e_2000(np.array(a), np.array(b)))
        assert de == pytest.approx(expected, abs=1e-3)


# --- analysis -------------------------------------------------------------------------


@pytest.mark.parametrize("category", ["hoodie", "jean", "tshirt", "sneakers"])
def test_segmentation_matches_ground_truth(category):
    img, truth = scene(category)
    mask, seg, _ = segment_garment(img)
    gt, pm = truth.garment_mask > 127, mask > 127
    iou = (gt & pm).sum() / (gt | pm).sum()
    assert iou > 0.95
    assert seg.confidence > 0.6


def test_white_balance_reads_the_background_not_the_garment():
    img, truth = scene("hoodie")
    mask, _, _ = segment_garment(img)
    est = estimate_illuminant(img, mask)
    expected = 1 / np.asarray(truth.cast_gains)
    expected /= expected @ [0.2126, 0.7152, 0.0722]
    assert np.allclose(est.gains, expected, rtol=0.06)
    assert est.cast_label == "lumière jaune"
    assert est.confidence > 0.7


def test_red_garment_filling_the_frame_is_not_neutralised():
    # Classic gray-world would push a big red T-shirt towards cyan. We must not.
    img, _ = make_scene("tshirt", seed=3, cast=(1.0, 1.0, 1.0), exposure=1.0, scale=1.25, offset=(0, 0))
    mask, _, _ = segment_garment(img)
    est = estimate_illuminant(img, mask)
    g = np.asarray(est.gains)
    assert g.max() / g.min() < 1.12
    b = analyze(img, local_router())
    res = render(RenderSource(img, b.mask, b.labels, b.analysis), EnhancementSettings(), 900)
    assert res.fidelity.passed


def test_tilt_is_measured():
    img, truth = scene("hoodie")
    tilt, conf = estimate_tilt(truth.garment_mask)
    assert tilt == pytest.approx(truth.tilt_deg, abs=0.6)
    assert conf >= 0.6


def test_dust_detected_without_touching_rivets():
    img, truth, b = analysed("jean")
    h, w = img.shape[:2]
    specks = b.analysis.specks
    found = sum(any(abs(s.bbox.cx - x) * w < 7 and abs(s.bbox.cy - y) * h < 7 for s in specks) for x, y in truth.specks)
    assert found / len(truth.specks) >= 0.6
    for rx, ry in truth.details["rivets"]:
        assert not any(abs(s.bbox.cx - rx) * w < 8 and abs(s.bbox.cy - ry) * h < 8 for s in specks), "rivet taken for dust"


@pytest.mark.parametrize("category", ["hoodie", "tshirt", "jean", "veste"])
def test_stain_is_reported_as_possible_defect(category):
    _, truth, b = analysed(category)
    sb = truth.stain_bbox
    assert any(abs(d.bbox.cx - sb.cx) < 0.04 and abs(d.bbox.cy - sb.cy) < 0.04 for d in b.analysis.defects)


@pytest.mark.parametrize("category,expected", [("hoodie", "hoodie"), ("jean", "jean"), ("tshirt", "tshirt"), ("sneakers", "sneakers"), ("veste", "veste")])
def test_clothing_category(category, expected):
    _, _, b = analysed(category)
    assert b.analysis.clothing.category == expected


# --- rendering ------------------------------------------------------------------------


def _garment_lab(img: np.ndarray, mask: np.ndarray) -> np.ndarray:
    m = cv2.erode((mask > 127).astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
    f = cv2.GaussianBlur(img.astype(np.float32) / 255, (0, 0), 2)
    return np.median(rgb_to_lab(f)[m], axis=0)


@pytest.mark.parametrize("category", ["hoodie", "tshirt", "jean"])
def test_naturel_render_corrects_light_and_keeps_true_colour(category):
    img, truth, b = analysed(category)
    res = render(source(category), EnhancementSettings(intensity="naturel"), 1000)
    clean, _ = make_scene(category, seed=0, cast=(1, 1, 1), exposure=1.0, tilt=0, dust=0, hairs=0, noise=0, jpeg_quality=0)
    true_lab = _garment_lab(clean, truth.garment_mask)  # tilt=0 mask differs slightly; median is robust
    before_lab = _garment_lab(img, truth.garment_mask)
    after_lab = _garment_lab(res.after, res.mask)
    de_before = float(delta_e_2000(before_lab, true_lab, kL=2))
    de_after = float(delta_e_2000(after_lab, true_lab, kL=2))
    assert de_after < de_before, (de_before, de_after)
    assert res.fidelity.score >= 90
    assert res.structure.passed
    assert res.quality.score > b.analysis.quality.score + 10


def test_dust_removed_but_stain_kept():
    img, truth, b = analysed("tshirt")
    src = source("tshirt")
    res = render(src, EnhancementSettings(intensity="premium", aspect="original", placement=0), max(img.shape[:2]))
    assert len(res.removed_specks) >= 0.6 * len([s for s in truth.specks])
    # speck sites are now close to their neighbourhood
    h, w = img.shape[:2]
    removed = [s for s in b.analysis.specks if s.id in res.removed_specks]
    resid_before, resid_after = [], []
    for s in removed[:10]:
        x, y = int(s.bbox.cx * w), int(s.bbox.cy * h)
        for im, acc in ((img, resid_before), (res.after, resid_after)):
            patch = cv2.cvtColor(im[max(0, y - 9) : y + 10, max(0, x - 9) : x + 10], cv2.COLOR_RGB2GRAY).astype(np.float32)
            acc.append(abs(float(patch[9, 9]) - float(np.median(patch))))
    assert np.mean(resid_after) < 0.5 * np.mean(resid_before)
    # the stain still stands out from the fabric
    sb = truth.stain_bbox
    x0, y0, x1, y1 = int(sb.x * w), int(sb.y * h), int((sb.x + sb.w) * w), int((sb.y + sb.h) * h)

    def stain_contrast(im):
        lab = rgb_to_lab(im.astype(np.float32) / 255)
        inner = lab[y0 + (y1 - y0) // 3 : y1 - (y1 - y0) // 3, x0 + (x1 - x0) // 3 : x1 - (x1 - x0) // 3].reshape(-1, 3).mean(0)
        ring = np.concatenate([lab[y0 - 15 : y0 - 5, x0:x1].reshape(-1, 3), lab[y1 + 5 : y1 + 15, x0:x1].reshape(-1, 3)]).mean(0)
        return float(delta_e_2000(inner, ring))

    assert stain_contrast(res.after) > 0.7 * stain_contrast(img)


def test_render_straightens_and_frames():
    img, truth, b = analysed("hoodie")
    res = render(source("hoodie"), EnhancementSettings(intensity="naturel", aspect="3:4"), 1000)
    tilt, conf = estimate_tilt(res.mask)
    assert abs(tilt) < 1.0
    h, w = res.after.shape[:2]
    assert w / h == pytest.approx(0.75, abs=0.01)
    # garment entirely visible with a margin
    ys, xs = np.nonzero(res.mask > 127)
    assert xs.min() > 0.02 * w and xs.max() < 0.98 * w and ys.min() > 0.02 * h and ys.max() < 0.98 * h


def test_original_intensity_is_untouched():
    img, _, _ = analysed("hoodie")
    res = render(source("hoodie"), EnhancementSettings(intensity="original"), max(img.shape[:2]))
    assert res.after.shape == img.shape
    assert np.abs(res.after.astype(int) - img.astype(int)).mean() < 0.6


def test_neutral_background_has_no_halo():
    img, truth, b = analysed("hoodie")
    res = render(source("hoodie"), EnhancementSettings(intensity="studio"), 1000)
    m = res.mask > 127
    ring = (cv2.dilate(m.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0) & ~(
        cv2.dilate(m.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    )
    far = ~(cv2.dilate(m.astype(np.uint8), np.ones((61, 61), np.uint8)) > 0)
    L = rgb_to_lab(res.after.astype(np.float32) / 255)[..., 0]
    # just outside the garment the surface may be shadowed, never brighter (halo) than the open surface
    assert np.percentile(L[ring], 95) <= np.percentile(L[far], 99) + 1.0
    assert res.structure.passed


def test_garment_touching_border_is_never_extended():
    img, truth = make_scene("tshirt", seed=4, offset=(0.0, 0.33), scale=0.9, tilt=0)
    b = analyze(img, local_router())
    assert b.analysis.segmentation.touches["bottom"]
    H, W = img.shape[:2]
    plan = plan_geometry(
        b.mask, W, H, tilt_deg=0, tilt_confidence=0, touches=b.analysis.segmentation.touches,
        placement=1.0, aspect="3:4", allow_padding=True,
    )
    assert plan.y0 + plan.height <= H + 0.5  # nothing invented below the cut-off garment
    res = render(RenderSource(img, b.mask, b.labels, b.analysis), EnhancementSettings(intensity="studio"), 900)
    assert (res.mask[-2:] > 127).any()  # still cut by the frame, not completed


def test_preserve_mode_caps_settings():
    s = EnhancementSettings(intensity="studio", wrinkles="fort", color=90, hue=10, retouch_specks=[1, 2])
    r = s.resolved()
    assert r.wrinkles == "leger" and r.color <= 0.55 and abs(r.hue_deg) <= 1.8 and r.retouch_specks == []
    assert set(r.capped) == {"color", "wrinkles", "hue", "retouch_specks"}
    free = s.model_copy(update={"preserve_article": False}).resolved()
    assert free.wrinkles == "fort" and free.retouch_specks == [1, 2]


# --- guards ---------------------------------------------------------------------------


def test_guards_catch_tampering():
    img, truth, b = analysed("hoodie")
    res = render(source("hoodie"), EnhancementSettings(intensity="naturel"), 900)
    ref = res.before
    # 1) colour falsified: rotate hue strongly on the garment
    lab = rgb_to_lab(res.after.astype(np.float32) / 255)
    m = res.mask > 127
    a, bb = lab[..., 1].copy(), lab[..., 2].copy()
    ang = np.radians(40)
    lab[..., 1] = np.where(m, a * np.cos(ang) - bb * np.sin(ang), a)
    lab[..., 2] = np.where(m, a * np.sin(ang) + bb * np.cos(ang), bb)
    lab[..., 1:] *= np.where(m, 1.6, 1.0)[..., None]
    falsified = (np.clip(cv2.cvtColor(lab, cv2.COLOR_Lab2RGB), 0, 1) * 255).astype(np.uint8)
    assert not color_fidelity(ref, falsified, res.mask).passed
    # 2) logo erased (generative "cleaning" of a print)
    tampered = res.after.copy()
    ys, xs = np.nonzero(m)
    cy, cx = int(np.median(ys)), int(np.median(xs))
    region = (slice(cy - 120, cy - 40), slice(cx - 160, cx + 160))
    fill = np.median(res.after[cy + 60 : cy + 90, cx - 40 : cx + 40].reshape(-1, 3), axis=0)
    tampered[region] = fill.astype(np.uint8)
    rep = structural_check(ref, tampered, res.mask)
    assert rep.edge_recall < structural_check(ref, res.after, res.mask).edge_recall


def test_pipeline_auto_reduces_excessive_provider_output():
    from app.providers.base import Capability
    from app.providers.local_cv import LocalCVProvider
    from app.providers.router import ProviderRouter

    class OverEagerProvider(LocalCVProvider):
        name = "eager"
        calls = 0

        def enhance_image(self, source, settings, target_long_side, *, upscaler=None, use_consistency=False):
            res = super().enhance_image(source, settings, target_long_side)
            OverEagerProvider.calls += 1
            if OverEagerProvider.calls == 1:  # first output oversaturates the garment
                lab = rgb_to_lab(res.after.astype(np.float32) / 255)
                lab[..., 1:] *= 1.8
                res.after = (np.clip(cv2.cvtColor(lab, cv2.COLOR_Lab2RGB), 0, 1) * 255).astype(np.uint8)
                res.fidelity = color_fidelity(res.before, res.after, res.mask)
            return res

    router = ProviderRouter({"local": LocalCVProvider(), "eager": OverEagerProvider()}, {Capability.ENHANCEMENT.value: "eager"})
    out = enhance(source("tshirt"), EnhancementSettings(), router, target_long_side=800)
    assert OverEagerProvider.calls == 2
    assert out.auto_adjustments
    assert out.result.fidelity.passed
    assert any(r.provider == "eager" for r in out.stages)


def test_consistency_shares_white_balance():
    a = analysed("hoodie", 0)[2].analysis
    c = analysed("tshirt", 0)[2].analysis
    out = harmonize([a, c])
    assert len(out) == 2 and all("gains" in o and 0.8 <= o["exposure_factor"] <= 1.25 for o in out)


# --- image I/O ------------------------------------------------------------------------


def test_decode_applies_exif_orientation_and_export_strips_metadata():
    img = np.zeros((80, 120, 3), np.uint8)
    img[:, :60] = 255
    pil = Image.fromarray(img)
    exif = pil.getexif()
    exif[0x0112] = 6  # rotate 90° CW on display
    exif[0x8825] = {2: (48.0, 51.0, 24.0)}  # GPS block
    buf = io.BytesIO()
    pil.save(buf, "JPEG", exif=exif)
    dec = decode_image(buf.getvalue())
    assert dec.pixels.shape[:2] == (120, 80)
    out = encode_image(dec.pixels, "jpg", 90)
    assert not Image.open(io.BytesIO(out)).getexif()


def test_decode_rejects_non_images():
    with pytest.raises(ImageDecodeError):
        decode_image(b"%PDF-1.4 not an image")
