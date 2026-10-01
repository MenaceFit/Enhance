"""Generate the landing-page before/after pairs with the real engine.

The "before" scenes are synthetic amateur photos (warm indoor light, tilt,
dust, under-exposure); the "after" images are produced by the actual pipeline,
so the demo never shows anything the product cannot do. Replace them with real
seller photos (with consent) when available.

    python scripts/generate_demo_assets.py ../web/public/demo
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.imaging.image_io import encode_image, resize_long_side  # noqa: E402
from app.imaging.pipeline import analyze, enhance  # noqa: E402
from app.imaging.render import RenderSource  # noqa: E402
from app.imaging.settings import EnhancementSettings  # noqa: E402
from app.imaging.synthetic import make_scene  # noqa: E402
from app.providers.registry import local_router  # noqa: E402

DEMOS = [
    ("hoodie", "hoodie", dict(seed=11, tilt=5.0, scale=0.7, offset=(0.05, 0.04)), "naturel"),
    ("sneakers", "sneakers", dict(seed=12, tilt=-4.0, scale=0.8, offset=(-0.03, 0.02), cast=(1.05, 1.0, 0.86)), "premium"),
    ("jean", "jean", dict(seed=13, tilt=3.5, scale=0.72, offset=(0.04, -0.02)), "naturel"),
    ("veste", "veste", dict(seed=14, tilt=-5.5, scale=0.7, offset=(-0.04, 0.05), cast=(1.0, 1.02, 1.12)), "studio"),
]


def main(out_dir: str) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    router = local_router()
    manifest = []
    for name, category, kw, intensity in DEMOS:
        img, _ = make_scene(category, 1200, 1600, **kw)
        bundle = analyze(img, router)
        outcome = enhance(RenderSource(img, bundle.mask, bundle.labels, bundle.analysis),
                          EnhancementSettings(intensity=intensity), router, target_long_side=1200)
        r = outcome.result
        (out / f"{name}-before.webp").write_bytes(encode_image(resize_long_side(r.before, 1200), "webp", 84))
        (out / f"{name}-after.webp").write_bytes(encode_image(resize_long_side(r.after, 1200), "webp", 86))
        manifest.append({
            "name": name, "intensity": intensity, "garment": bundle.analysis.clothing.label,
            "quality_before": bundle.analysis.quality.score, "quality_after": r.quality.score,
            "fidelity": r.fidelity.score, "defects": len([d for d in bundle.analysis.defects if d.kind != "speck"]),
            "specks_removed": len(r.removed_specks), "width": int(r.after.shape[1]), "height": int(r.after.shape[0]),
        })
        print(manifest[-1])
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "../web/public/demo")
