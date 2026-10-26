"""Typed process-local adapter for ordinary analytic sketch regions."""

from dataclasses import dataclass

from .analytic_profile_geometry import classify
from .errors import CADException


@dataclass(frozen=True)
class LineBoundary:
    start: tuple[float, float]
    end: tuple[float, float]
    entity_id: str
    kind: str = "line"


@dataclass(frozen=True)
class ArcBoundary:
    center: tuple[float, float]
    start: tuple[float, float]
    end: tuple[float, float]
    sweep: float
    entity_id: str
    kind: str = "arc"


@dataclass(frozen=True)
class AnalyticLoop:
    boundaries: tuple[LineBoundary | ArcBoundary, ...]


@dataclass(frozen=True)
class AnalyticRegion:
    outer: AnalyticLoop
    holes: tuple[AnalyticLoop, ...]


@dataclass(frozen=True)
class AnalyticRegions:
    regions: tuple[AnalyticRegion, ...]
    boundary_ids: tuple[str, ...]


@dataclass(frozen=True)
class AnalyticOpenPath:
    boundaries: tuple[LineBoundary | ArcBoundary, ...]
    reason_code: str = "open_profile"
    message: str = "Open line/arc path: usable for Sweep, not extrusion."


def classify_analytic_path(sketch):
    try:
        result = classify(sketch.to_dict(), open_path=True)
    except ValueError as exc:
        raise CADException("unsupported_profile_form", str(exc)) from exc
    return AnalyticOpenPath(
        tuple(
            LineBoundary(**edge) if edge["kind"] == "line" else ArcBoundary(**edge)
            for edge in result["boundaries"]
        )
    )


def classify_analytic_profile(sketch):
    try:
        result = classify(sketch.to_dict())
    except ValueError as exc:
        raise CADException("unsupported_profile_form", str(exc)) from exc

    def loop(boundaries):
        return AnalyticLoop(
            tuple(
                LineBoundary(**edge) if edge["kind"] == "line" else ArcBoundary(**edge)
                for edge in boundaries
            )
        )

    return AnalyticRegions(
        tuple(
            AnalyticRegion(loop(region["outer"]), tuple(loop(hole) for hole in region["holes"]))
            for region in result["regions"]
        ),
        tuple(result["boundary_ids"]),
    )
