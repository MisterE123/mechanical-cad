"""Process-local evaluated outputs, separate from saved intent and display JSON.

A successfully solved sketch need not have a closed profile. Consumers request
the port they need rather than assuming every successful feature owns a shape.
Native handles never cross the sidecar boundary or enter canonical documents.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .errors import CADException

if TYPE_CHECKING:
    from .sketch_model import Sketch


@dataclass(frozen=True)
class AvailableProfile:
    shape: Any
    region_kind: str
    boundary_ids: tuple[str, ...]


@dataclass(frozen=True)
class OpenProfile:
    reason_code: str = "open_profile"
    message: str = "Close this line chain before extrusion."


@dataclass(frozen=True)
class SketchOutput:
    solved_sketch: Sketch
    profile: AvailableProfile | OpenProfile


@dataclass(frozen=True)
class ProfileOutput:
    shape: Any


@dataclass(frozen=True)
class SolidOutput:
    shape: Any


FeatureOutput = SketchOutput | ProfileOutput | SolidOutput


def native_shape(output: FeatureOutput) -> Any | None:
    """Compatibility projection; an open sketch deliberately has no shape."""
    if isinstance(output, SketchOutput):
        return output.profile.shape if isinstance(output.profile, AvailableProfile) else None
    return output.shape


def require_profile(output: FeatureOutput, feature_id: str) -> Any:
    if isinstance(output, ProfileOutput):
        return output.shape
    if isinstance(output, SketchOutput):
        if isinstance(output.profile, AvailableProfile):
            return output.profile.shape
        raise CADException("profile_unavailable", f"{feature_id}: {output.profile.message}")
    raise CADException("invalid_input_type", f"{feature_id} does not supply a profile.")


def require_solid(output: FeatureOutput, feature_id: str) -> Any:
    if not isinstance(output, SolidOutput):
        raise CADException("not_a_solid", f"{feature_id} is not an evaluated solid feature.")
    return output.shape


def describe_output(output: FeatureOutput) -> dict:
    """Result-v2 discriminant; no derived state is added to the saved model."""
    if isinstance(output, SketchOutput):
        if isinstance(output.profile, AvailableProfile):
            profile = {"state": "available", "region_kind": output.profile.region_kind}
        else:
            profile = {
                "state": "unavailable",
                "reason": {
                    "code": output.profile.reason_code,
                    "message": output.profile.message,
                },
            }
        return {"kind": "sketch", "display": "solved_sketch", "profile": profile}
    return {
        "kind": "solid" if isinstance(output, SolidOutput) else "profile",
        "display": "mesh",
    }
