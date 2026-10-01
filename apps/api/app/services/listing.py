"""Listing draft from detected attributes (V2 "AI Listing Generator").

The local version builds an honest title/description from the analysis; the
Claude provider (capability ``listing``) writes richer copy from the photo.
Both follow the same rules: no invented brand or size, visible imperfections
are mentioned.
"""

from __future__ import annotations

from typing import Any

from app.imaging.types import ClothingAttributes, Defect


def listing_from_attributes(attrs: ClothingAttributes, defects: list[Defect] | None = None) -> dict[str, Any]:
    colors = [c.get("name") for c in attrs.dominant_colors if c.get("name")]
    color = colors[0] if colors else ""
    f = attrs.features or {}
    details = []
    if f.get("hood"):
        details.append("capuche")
    if f.get("central_closure"):
        details.append("fermeture centrale")
    if f.get("logos"):
        details.append("logo / imprimé")
    title = " ".join(x for x in [attrs.label, color, "avec " + details[0] if details else ""] if x).strip()
    condition = ""
    if defects:
        kinds = sorted({d.label.lower() for d in defects if d.kind != "speck"})
        if kinds:
            condition = "À noter : " + ", ".join(kinds) + " (voir photos)."
    description = (
        f"{attrs.label} {color}".strip()
        + (f", {attrs.pattern}" if attrs.pattern and attrs.pattern != "uni" else "")
        + (f" — {', '.join(details)}" if details else "")
        + ".\nPhotos non retouchées sur l'article : couleurs et état fidèles."
        + (f"\n{condition}" if condition else "\nBon état général.")
    )
    keywords = sorted({w for w in [attrs.label.lower(), color, attrs.pattern, *details] if w and w != "uni"})
    return {
        "title": title[:60],
        "description": description,
        "category": attrs.label,
        "color": color,
        "material": attrs.texture if attrs.texture not in ("tissu", "lisse") else "",
        "size_visible": "",
        "condition_notes": condition,
        "keywords": keywords,
        "provider": "local",
    }
