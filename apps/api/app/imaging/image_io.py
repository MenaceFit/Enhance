"""Decoding, normalisation and encoding of user photos.

Everything that enters the engine goes through :func:`decode_image`, which
returns an sRGB uint8 RGB array with EXIF orientation applied. Embedded ICC
profiles (e.g. Display P3 from iPhones) are converted to sRGB so that colour
fidelity is measured in a single, well-defined space. Metadata (including GPS
coordinates) is never written back on export.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image, ImageCms, ImageOps

try:  # HEIC/HEIF support is optional at runtime but installed by default.
    import pillow_heif

    pillow_heif.register_heif_opener()
    HEIF_AVAILABLE = True
except Exception:  # pragma: no cover - depends on system libs
    HEIF_AVAILABLE = False

Image.MAX_IMAGE_PIXELS = 80_000_000  # refuse decompression bombs (> ~80 MP)

SUPPORTED_MIME = {
    "image/jpeg": "jpeg",
    "image/jpg": "jpeg",
    "image/png": "png",
    "image/webp": "webp",
    "image/heic": "heic",
    "image/heif": "heic",
}
SUPPORTED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}

_SRGB_PROFILE = ImageCms.createProfile("sRGB")


class ImageDecodeError(ValueError):
    pass


@dataclass(slots=True)
class DecodedImage:
    pixels: np.ndarray  # uint8 RGB, sRGB
    source_format: str
    had_alpha: bool
    icc_converted: bool


def sniff_format(data: bytes) -> str | None:
    head = data[:16]
    if head.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    if head[4:8] == b"ftyp" and head[8:12] in {b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1", b"heim", b"heis"}:
        return "heic"
    return None


def decode_image(data: bytes) -> DecodedImage:
    fmt = sniff_format(data)
    if fmt is None:
        raise ImageDecodeError("Format non reconnu. Formats acceptés : JPG, PNG, WEBP, HEIC.")
    if fmt == "heic" and not HEIF_AVAILABLE:
        raise ImageDecodeError("Le format HEIC n'est pas disponible sur ce serveur.")
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except Image.DecompressionBombError as exc:
        raise ImageDecodeError("Image trop grande.") from exc
    except Exception as exc:
        raise ImageDecodeError("Impossible de lire cette image.") from exc

    im = ImageOps.exif_transpose(im)

    icc_converted = False
    icc = im.info.get("icc_profile")
    had_alpha = im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info)

    if had_alpha:
        im = im.convert("RGBA")
        background = Image.new("RGBA", im.size, (255, 255, 255, 255))
        im = Image.alpha_composite(background, im)
    if im.mode not in ("RGB",):
        im = im.convert("RGB")

    if icc:
        try:
            src_profile = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            desc = ImageCms.getProfileDescription(src_profile) or ""
            if "srgb" not in desc.lower().replace(" ", ""):
                im = ImageCms.profileToProfile(im, src_profile, _SRGB_PROFILE, outputMode="RGB")
                icc_converted = True
        except Exception:
            pass  # A broken profile should never block processing: assume sRGB.

    pixels = np.asarray(im, dtype=np.uint8).copy()
    if pixels.ndim != 3 or pixels.shape[2] != 3:
        raise ImageDecodeError("Image invalide.")
    if min(pixels.shape[:2]) < 64:
        raise ImageDecodeError("Image trop petite (minimum 64 px).")
    return DecodedImage(pixels=pixels, source_format=fmt, had_alpha=had_alpha, icc_converted=icc_converted)


def resize_long_side(img: np.ndarray, long_side: int, *, allow_upscale: bool = False) -> np.ndarray:
    h, w = img.shape[:2]
    current = max(h, w)
    if current == long_side or (current < long_side and not allow_upscale):
        return img
    scale = long_side / current
    size = (max(1, round(w * scale)), max(1, round(h * scale)))
    interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_LANCZOS4
    return cv2.resize(img, size, interpolation=interp)


def resize_to(img: np.ndarray, width: int, height: int) -> np.ndarray:
    h, w = img.shape[:2]
    if (w, h) == (width, height):
        return img
    interp = cv2.INTER_AREA if width * height < w * h else cv2.INTER_LINEAR
    return cv2.resize(img, (width, height), interpolation=interp)


EXPORT_FORMATS = {"jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "webp": "WEBP"}
MIME_BY_FORMAT = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


def encode_image(img: np.ndarray, fmt: str = "jpg", quality: int = 90) -> bytes:
    """Encode an RGB uint8 image. Never carries EXIF/GPS metadata; embeds sRGB."""
    fmt = fmt.lower()
    if fmt not in EXPORT_FORMATS:
        raise ValueError(f"Unsupported export format: {fmt}")
    if img.dtype != np.uint8:
        img = np.clip(img * 255.0 + 0.5, 0, 255).astype(np.uint8)
    im = Image.fromarray(img, mode="RGB")
    buf = io.BytesIO()
    icc = ImageCms.ImageCmsProfile(_SRGB_PROFILE).tobytes()
    pil_fmt = EXPORT_FORMATS[fmt]
    if pil_fmt == "JPEG":
        im.save(buf, "JPEG", quality=quality, optimize=True, progressive=True, subsampling=0 if quality >= 90 else 2, icc_profile=icc)
    elif pil_fmt == "WEBP":
        im.save(buf, "WEBP", quality=quality, method=4, icc_profile=icc)
    else:
        im.save(buf, "PNG", optimize=quality >= 95, icc_profile=icc)
    return buf.getvalue()


def encode_mask(mask: np.ndarray) -> bytes:
    """Lossless 8-bit (or 16-bit label) PNG encoding for analysis artefacts."""
    ok, buf = cv2.imencode(".png", mask)
    if not ok:  # pragma: no cover
        raise RuntimeError("PNG encoding failed")
    return buf.tobytes()


def decode_mask(data: bytes) -> np.ndarray:
    arr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_UNCHANGED)
    if arr is None:  # pragma: no cover
        raise ImageDecodeError("Invalid mask")
    return arr


def decode_rgb_fast(data: bytes) -> np.ndarray:
    """Decode an image we produced ourselves (sRGB, already oriented)."""
    arr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if arr is None:
        raise ImageDecodeError("Invalid image")
    return cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
