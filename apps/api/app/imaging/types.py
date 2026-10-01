"""Typed results exchanged between analysis, rendering, providers and the API.

All geometric values are normalised to [0, 1] relative to the analysed image so
they stay valid at any rendering resolution.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

DefectKind = Literal["stain", "discoloration", "hole", "snag", "wear", "pilling", "speck"]
SpeckKind = Literal["dust", "hair", "lint"]


@dataclass(slots=True)
class BBox:
    x: float
    y: float
    w: float
    h: float

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2


@dataclass(slots=True)
class Speck:
    """A parasite element (dust, hair, lint) that may be removed safely."""

    id: int  # label id in the dust label map
    kind: SpeckKind
    bbox: BBox
    area: float  # fraction of image area
    region: Literal["garment", "background"]
    polarity: Literal["light", "dark"]
    confidence: float


@dataclass(slots=True)
class Defect:
    """A potential imperfection of the article. Never removed automatically."""

    id: str
    kind: DefectKind
    label: str
    bbox: BBox
    confidence: float
    area: float
    removable_as_dust: bool = False  # only tiny ambiguous specks may be retouched, on explicit request
    speck_id: int | None = None


@dataclass(slots=True)
class QualityReport:
    score: int
    breakdown: dict[str, int]
    issues: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ClothingAttributes:
    category: str  # e.g. "hoodie", "jean", "sneakers"
    label: str  # French display label
    confidence: float
    candidates: list[dict[str, Any]] = field(default_factory=list)
    dominant_colors: list[dict[str, Any]] = field(default_factory=list)
    pattern: str = "uni"
    texture: str = "lisse"
    features: dict[str, Any] = field(default_factory=dict)  # sleeves, hood, legs, closure, logos...
    background: str = "uni"
    provider: str = "local"


@dataclass(slots=True)
class Segmentation:
    confidence: float
    garment_fraction: float
    bbox: BBox
    touches: dict[str, bool]  # left/top/right/bottom
    components: int
    method: str


@dataclass(slots=True)
class IlluminantEstimate:
    gains: tuple[float, float, float]  # linear-RGB multipliers that neutralise the cast
    cast_label: str | None  # "lumière jaune", ...
    cast_strength: float  # chroma of the estimated cast (Lab units)
    confidence: float
    source: str


@dataclass(slots=True)
class ExposureStats:
    p01: float
    p50: float
    p99: float
    garment_p50: float
    clipped_high: float
    clipped_low: float
    gain: float  # suggested linear exposure gain


@dataclass(slots=True)
class CompositionPlan:
    tilt_deg: float  # measured deviation from axis (positive = counter-clockwise)
    tilt_confidence: float
    garment_bbox: BBox
    fill_ratio: float
    center_offset: tuple[float, float]


@dataclass(slots=True)
class Analysis:
    width: int
    height: int
    quality: QualityReport
    segmentation: Segmentation
    clothing: ClothingAttributes
    illuminant: IlluminantEstimate
    exposure: ExposureStats
    composition: CompositionPlan
    specks: list[Speck]
    defects: list[Defect]
    warnings: list[str] = field(default_factory=list)
    consistency: dict[str, Any] | None = None
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Analysis:
        def bbox(d: dict) -> BBox:
            return BBox(**d)

        seg = dict(data["segmentation"])
        seg["bbox"] = bbox(seg["bbox"])
        comp = dict(data["composition"])
        comp["garment_bbox"] = bbox(comp["garment_bbox"])
        comp["center_offset"] = tuple(comp["center_offset"])
        ill = dict(data["illuminant"])
        ill["gains"] = tuple(ill["gains"])
        specks = [Speck(**{**s, "bbox": bbox(s["bbox"])}) for s in data.get("specks", [])]
        defects = [Defect(**{**d, "bbox": bbox(d["bbox"])}) for d in data.get("defects", [])]
        return cls(
            width=data["width"],
            height=data["height"],
            quality=QualityReport(**data["quality"]),
            segmentation=Segmentation(**seg),
            clothing=ClothingAttributes(**data["clothing"]),
            illuminant=IlluminantEstimate(**ill),
            exposure=ExposureStats(**data["exposure"]),
            composition=CompositionPlan(**comp),
            specks=specks,
            defects=defects,
            warnings=list(data.get("warnings", [])),
            consistency=data.get("consistency"),
            version=data.get("version", 1),
        )


@dataclass(slots=True)
class FidelityReport:
    score: int  # 0-100, "Fidélité couleur"
    mean_delta_e: float
    hue_shift_deg: float
    chroma_ratio: float
    dominant_before: str
    dominant_after: str
    passed: bool
    warning: str | None = None


@dataclass(slots=True)
class StructureReport:
    score: int
    silhouette_iou: float
    edge_recall: float
    detail_correlation: float
    aspect_delta: float
    passed: bool
    issues: list[str] = field(default_factory=list)


@dataclass(slots=True)
class StageRecord:
    name: str
    label: str
    duration_ms: float
    provider: str
    model: str | None = None
    cost_cents: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)
