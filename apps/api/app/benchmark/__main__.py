"""CLI: compare provider profiles on synthetic or local images.

    python -m app.benchmark --profiles local,rembg --synthetic 10
    python -m app.benchmark --profiles local --images ./photos --out report.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.benchmark.runner import PRESET_PROFILES, BenchmarkImage, run_benchmark, synthetic_set
from app.imaging.image_io import SUPPORTED_EXT, decode_image
from app.providers.registry import build_providers, parse_routing


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profiles", default="local", help=f"comma-separated presets {list(PRESET_PROFILES)} or name=JSON")
    ap.add_argument("--synthetic", type=int, default=0, help="number of synthetic scenes")
    ap.add_argument("--images", type=Path, help="directory of photos")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)

    profiles: dict[str, dict[str, str]] = {}
    for item in args.profiles.split(","):
        if "=" in item:
            name, raw = item.split("=", 1)
            profiles[name] = parse_routing(raw)
        else:
            profiles[item] = PRESET_PROFILES[item]

    images = synthetic_set(args.synthetic) if args.synthetic else []
    if args.images:
        for p in sorted(args.images.iterdir()):
            if p.suffix.lower() in SUPPORTED_EXT:
                images.append(BenchmarkImage(p.name, decode_image(p.read_bytes()).pixels))
    if not images:
        images = synthetic_set(5)

    report = run_benchmark(images, profiles, build_providers(), progress=lambda f: print(f"\r{f:5.0%}", end="", file=sys.stderr))
    print(file=sys.stderr)
    for row in report["summary"]:
        print(json.dumps(row, ensure_ascii=False))
    if args.out:
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
