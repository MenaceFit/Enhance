"""Marketplace profiles.

The product targets Vinted first, but everything marketplace-specific (frame
ratio, recommended resolution, file naming) lives here so Depop, Vestiaire
Collective, eBay, Grailed or Leboncoin can be enabled by adding a profile.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Marketplace:
    slug: str
    name: str
    aspect: str  # default frame ratio for "Placement"
    max_long_side: int  # recommended upload size for the "Standard" export
    enabled: bool = True


MARKETPLACES: dict[str, Marketplace] = {
    "vinted": Marketplace("vinted", "Vinted", "3:4", 1600),
    "depop": Marketplace("depop", "Depop", "1:1", 1600, enabled=False),
    "vestiaire": Marketplace("vestiaire", "Vestiaire Collective", "4:5", 2000, enabled=False),
    "ebay": Marketplace("ebay", "eBay", "1:1", 1600, enabled=False),
    "grailed": Marketplace("grailed", "Grailed", "4:5", 2000, enabled=False),
    "leboncoin": Marketplace("leboncoin", "Leboncoin", "3:4", 1600, enabled=False),
}


def get_marketplace(slug: str | None) -> Marketplace:
    return MARKETPLACES.get(slug or "vinted", MARKETPLACES["vinted"])


def export_filename(slug: str | None, position: int, fmt: str) -> str:
    ext = "jpg" if fmt in ("jpg", "jpeg") else fmt
    return f"{get_marketplace(slug).slug}_ai_{position:02d}.{ext}"
