"""Deterministic graph replay with explicit failure and downstream blocking.

Opaque B-rep handles exist only inside this engine process. The public result
contains portable JSON data. No shape, mesh index or Python pickle is persisted
as the canonical design.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from .errors import CADException
from .expressions import evaluate, resolve_parameters
from .model import Document, Feature, feature_input_schema, output_type
from .outputs import (
    AvailableProfile,
    FeatureOutput,
    OpenProfile,
    ProfileOutput,
    SketchOutput,
    SolidOutput,
    describe_output,
    native_shape,
    require_profile,
    require_solid,
)
from .result_policy import validate_result_version

MIN_LENGTH = 1e-6
MAX_LENGTH = 1e6


class Kernel(Protocol):
    """The narrow modelling port; independent of one binding or CAD library."""

    def spur_gear(self, **params: float) -> Any: ...

    def rectangle(
        self, width: float, height: float, x: float = 0, y: float = 0, z: float = 0
    ) -> Any: ...
    def circle(self, radius: float, x: float = 0, y: float = 0, z: float = 0) -> Any: ...
    def polygon(
        self, points: tuple, edge_ids: tuple, *, origin: tuple, quaternion: tuple
    ) -> Any: ...
    def circle_profile(
        self, center: tuple, radius: float, circle_id: str, *, origin: tuple, quaternion: tuple
    ) -> Any: ...
    def sector_profile(self, sketch: Any) -> Any: ...
    def extrude_sector(self, profile: Any, length: float) -> Any: ...
    def extrude(self, profile: Any, length: float) -> Any: ...
    def extrude_symmetric(self, profile: Any, length: float) -> Any: ...
    def extrude_through(self, profile: Any, base: Any, direction: float) -> Any: ...
    def extrude_to_face(
        self, profile: Any, target: Any, end_face: str, direction: float, offset: float = 0
    ) -> Any: ...
    def cut(self, base: Any, tool: Any) -> Any: ...
    def union(self, base: Any, tool: Any) -> Any: ...
    def intersection(self, base: Any, tool: Any) -> Any: ...
    def revolve(self, profile: Any, angle: float, **axis: float) -> Any: ...
    def fillet(
        self,
        base: Any,
        radius: float,
        *,
        edge_faces: tuple | None = None,
        edge_pairs: tuple | None = None,
    ) -> Any: ...
    def chamfer(
        self,
        base: Any,
        distance: float,
        *,
        edge_faces: tuple | None = None,
        edge_pairs: tuple | None = None,
    ) -> Any: ...
    def transform(self, base: Any, **placement: float) -> Any: ...
    def loft(self, start: Any, end: Any, ruled: float = 0) -> Any: ...

    def loft_sections(self, sections: list[Any], ruled: float = 0) -> Any: ...
    def sweep(self, profile: Any, path: Any, *, placement=None) -> Any: ...
    def mirror(self, base: Any, **plane: float) -> Any: ...
    def linear_pattern(self, base: Any, count: float, **spacing: float) -> Any: ...
    def circular_pattern(self, base: Any, count: float, angle: float, **axis: float) -> Any: ...
    def shell(self, base: Any, thickness: float, *, opening_faces: tuple | None = None) -> Any: ...
    def region_profile(self, regions: tuple, *, origin: tuple, quaternion: tuple) -> Any: ...
    def face_rectangle(self, support: Any, support_face: str, **params: float) -> Any: ...
    def face_circle(self, support: Any, support_face: str, **params: float) -> Any: ...
    def inspect(self, shape: Any) -> dict: ...
    def tessellate(self, shape: Any, linear_deflection: float = 0.1) -> dict: ...
    def topology(
        self, shape: Any, feature_id: str, kind: str, params: dict, inputs: dict | None = None
    ) -> list: ...


@dataclass
class Replay:
    """Result plus process-local handles, for explicit exports in the CLI."""

    result: dict
    shapes: dict[str, Any]
    outputs: dict[str, FeatureOutput] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.result["status"] == "ok"


def _parameters(feature: Feature, values: dict[str, float]) -> dict[str, float]:
    result = {}
    for name, expression in feature.params.items():
        try:
            value = evaluate(expression, values)
        except CADException as exc:
            raise CADException(exc.code, f"{feature.id}.{name}: {exc}") from exc
        if name in {"width", "height", "radius", "length", "distance", "thickness"}:
            if not MIN_LENGTH <= (abs(value) if name == "length" else value) <= MAX_LENGTH:
                raise CADException(
                    "invalid_dimension",
                    f"{feature.id}.{name} must be between {MIN_LENGTH:g} and {MAX_LENGTH:g} mm; got {value:g}.",
                )
        elif name in {"x", "y", "z", "dx", "dy", "dz", "offset"} and abs(value) > MAX_LENGTH:
            raise CADException(
                "invalid_coordinate", f"{feature.id}.{name} must be within ±{MAX_LENGTH:g} mm."
            )
        if feature.kind == "extrude_symmetric" and name == "length" and value <= 0:
            raise CADException("invalid_dimension", "Symmetric total depth must be positive.")
        if name == "direction" and value not in (-1, 1):
            raise CADException("invalid_direction", "Extrusion direction must be +1 or -1.")
        if name == "ruled" and value not in (0, 1):
            raise CADException("invalid_loft_mode", "Loft ruled must be 0 (smooth) or 1 (ruled).")
        if name == "count" and (value != int(value) or not 2 <= value <= 64):
            raise CADException(
                "invalid_count", "Pattern count must be an integer between 2 and 64."
            )
        if (
            name == "angle"
            and feature.kind in {"revolve", "circular_pattern", "circular_cut_pattern"}
            and not 1e-6 <= abs(value) <= 360
        ):
            raise CADException(
                "invalid_angle", "Revolution angle must be nonzero and within ±360 degrees."
            )
        if name in {"rx", "ry", "rz", "angle"} and abs(value) > 360000:
            raise CADException("invalid_angle", "Rotation must be within ±360000 degrees.")
        if name.startswith("axis_") and abs(value) > MAX_LENGTH:
            raise CADException("invalid_axis", "Axis components must be within ±1000000.")
        result[name] = value
    return result


def _sketch_output(feature, values, kernel, item):
    from .profile_region import closed_profile
    from .sketch_evaluation import evaluate_sketch

    report, item["sketch"] = evaluate_sketch(feature.sketch, values)
    if not report.success:
        detail = (
            "Diagnostic candidates (not proven causes): " + ", ".join(report.failed_constraints)
            if report.failed_constraints
            else "Inspect the sketch relations and seed geometry."
        )
        raise CADException(
            "sketch_solve_failed", f"{feature.id}: {report.status.name.lower()}. {detail}"
        )
    if getattr(feature.sketch, "schema_version", 1) == 2:
        from .profile_region import (
            CircleProfile,
            OpenChainProfile,
            ProfileRegions,
            classify_profile,
        )

        region = classify_profile(report.sketch)
        if isinstance(region, OpenChainProfile):
            return SketchOutput(report.sketch, OpenProfile(region.reason_code, region.message))
        if isinstance(region, ProfileRegions):
            shape = kernel.region_profile(
                region.regions,
                origin=report.sketch.plane.origin,
                quaternion=report.sketch.plane.quaternion,
            )
            return SketchOutput(
                report.sketch, AvailableProfile(shape, "regions", region.boundary_ids)
            )
        if isinstance(region, CircleProfile):
            shape = kernel.circle_profile(
                region.center,
                region.radius,
                region.circle_id,
                origin=report.sketch.plane.origin,
                quaternion=report.sketch.plane.quaternion,
            )
            return SketchOutput(
                report.sketch, AvailableProfile(shape, "circle", (region.circle_id,))
            )
    else:
        # Old embedded sketches retain their exact closed-profile policy.
        region = closed_profile(report.sketch)
    shape = kernel.polygon(
        region.points,
        region.edge_ids,
        origin=report.sketch.plane.origin,
        quaternion=report.sketch.plane.quaternion,
    )
    return SketchOutput(report.sketch, AvailableProfile(shape, "line_loop", region.edge_ids))


def _sketch_output_v3(feature, values, kernel, item):
    from .profile_adapter_v3 import sketch_output_v3

    return sketch_output_v3(feature, values, kernel, item, legacy_output=_sketch_output)


def _extrude_output_v3(output, profile, length, kernel):
    if (
        isinstance(output, SketchOutput)
        and isinstance(output.profile, AvailableProfile)
        and output.profile.region_kind == "curve_loop"
    ):
        from .profile_adapter_v3 import sector_native_call

        return sector_native_call(kernel.extrude_sector, profile, length)
    return kernel.extrude(profile, length)


def _is_curve_loop_output(output):
    return (
        isinstance(output, SketchOutput)
        and isinstance(output.profile, AvailableProfile)
        and output.profile.region_kind == "curve_loop"
    )


def _finalize_sector_meshes_v3(pending, kernel, linear_deflection, results, shapes, outputs):
    """Display only after the retained checked sector continuation has finished."""
    for feature_id, shape in pending:
        item = results[feature_id]
        if item["status"] != "ok":
            continue
        try:
            item["mesh"] = kernel.tessellate(shape, linear_deflection=linear_deflection)
        except Exception as exc:
            item.update(status="failed", stats=None, mesh=None, topology=[], output=None)
            if isinstance(exc, CADException) and exc.code == "profile_unavailable":
                item["status"] = "blocked"
            item["error"] = (
                exc.to_dict()
                if isinstance(exc, CADException)
                else {
                    "code": "kernel_error",
                    "message": f"{feature_id}: {type(exc).__name__}: {exc}",
                }
            )
            shapes.pop(feature_id, None)
            outputs.pop(feature_id, None)
            # The admitted arc graph has only this profile and at most one
            # direct solid. Walk topological insertion order so no provisional
            # descendant remains usable after an upstream display failure.
            for descendant in results.values():
                blocked_by = [
                    target
                    for target in descendant["inputs"].values()
                    if results[target]["status"] != "ok"
                ]
                if blocked_by:
                    descendant.update(
                        status="blocked",
                        stats=None,
                        mesh=None,
                        topology=[],
                        output=None,
                        resolved_params={},
                        error={
                            "code": "upstream_failed",
                            "message": f"Waiting for valid input: {', '.join(blocked_by)}.",
                        },
                    )
                    shapes.pop(descendant["id"], None)
                    outputs.pop(descendant["id"], None)


def regenerate(
    document: Document,
    kernel: Kernel,
    *,
    linear_deflection: float = 0.1,
    result_version: int = 1,
) -> Replay:
    """Replay every node, report all errors, and never reuse stale geometry.

    List order is retained in the document, while execution obeys dependencies.
    Independent branches continue after a failure. Any failed branch makes the
    whole replay status failed, even if the currently selected output succeeded.
    """
    document.validate()
    is_v3 = type(result_version) is int and result_version == 3
    if is_v3:
        from .result_policy_v3 import validate_replay_v3

        validate_replay_v3(document, result_version)
    else:
        validate_result_version(document, result_version)
    # Optional adapter policy: native-free/fake kernels need no new method.
    # Legacy result-v1 retains its historical snapshot-only Cut tool walls.
    topology_policy = getattr(kernel, "set_topology_result_version", None)
    if topology_policy is not None:
        topology_policy(result_version)
    document_hash = document.content_hash
    if (
        isinstance(linear_deflection, bool)
        or not isinstance(linear_deflection, (int, float))
        or not 0.001 <= linear_deflection <= 10
    ):
        raise CADException("invalid_tolerance", "Mesh linear deflection must be 0.001–10 mm.")
    values = resolve_parameters(document.parameters)
    shapes: dict[str, Any] = {}
    outputs: dict[str, FeatureOutput] = {}
    results: dict[str, dict] = {}
    deferred_sector_meshes = []
    for feature in document.topological_features():
        item = {
            "id": feature.id,
            "label": feature.label,
            "kind": feature.kind,
            "status": "ok",
            "error": None,
            "stats": None,
            "mesh": None,
            "topology": [],
            "resolved_params": {},
            "inputs": dict(feature.inputs),
        }
        if result_version in (2, 3) and feature.kind == "cut":
            item["cut_ancestry"] = None
        if feature.kind == "sketch_constrained" and feature.support_face is not None:
            item["support_plane"] = None
        from .sketch_projection import has_solid_projections, projection_input_types

        if has_solid_projections(feature.projections):
            item["projection_edges"] = None
        if result_version == 2 or is_v3:
            item["output"] = None
        results[feature.id] = item
        blocked_by = [
            target for target in feature.inputs.values() if results[target]["status"] != "ok"
        ]
        if blocked_by:
            item["status"] = "blocked"
            item["error"] = {
                "code": "upstream_failed",
                "message": f"Waiting for valid input: {', '.join(blocked_by)}.",
            }
            continue
        try:
            params = _parameters(feature, values)
            item["resolved_params"] = params
            inputs = {
                name: (
                    outputs[target].solved_sketch
                    if (
                        feature.kind == "sweep"
                        and name == "path"
                        or feature.kind == "sketch_constrained"
                        and projection_input_types(feature.projections).get(name) == "profile"
                    )
                    and isinstance(outputs[target], SketchOutput)
                    else require_profile(outputs[target], target)
                    if feature_input_schema(feature)[name] == "profile"
                    else require_solid(outputs[target], target)
                )
                for name, target in feature.inputs.items()
            }
            if feature.kind == "spur_gear":
                shape = kernel.spur_gear(**params)
            elif feature.kind == "import_step":
                shape = kernel.import_step_data(dict(feature.step_data))
            elif feature.kind == "sketch_rectangle":
                shape = kernel.rectangle(**params)
            elif feature.kind == "sketch_circle":
                shape = kernel.circle(**params)
            elif feature.kind in {"sketch_face_rectangle", "sketch_face_circle"}:
                operation = (
                    kernel.face_rectangle
                    if feature.kind == "sketch_face_rectangle"
                    else kernel.face_circle
                )
                shape = operation(inputs["support"], feature.support_face, **params)
            elif feature.kind == "sketch_constrained":
                if feature.support_face is not None:
                    from .sketch_support import resolve_supported_feature

                    feature, item["support_plane"] = resolve_supported_feature(
                        feature, kernel, inputs["support"], results=list(results.values())
                    )
                if feature.projections:
                    from .sketch_support import resolve_projection_inputs

                    feature, projection_edges = resolve_projection_inputs(feature, kernel, inputs)
                    if has_solid_projections(feature.projections):
                        item["projection_edges"] = projection_edges
                evaluated = (
                    _sketch_output_v3(feature, values, kernel, item)
                    if is_v3
                    else _sketch_output(feature, values, kernel, item)
                )
                if isinstance(evaluated.profile, OpenProfile):
                    outputs[feature.id] = evaluated
                    item["output"] = describe_output(evaluated)
                    continue
                shape = native_shape(evaluated)
            elif feature.kind == "extrude_symmetric":
                if _is_curve_loop_output(outputs[feature.inputs["profile"]]):
                    raise CADException(
                        "unsupported_profile",
                        "Symmetric extrusion does not support the bounded sector-form profile contract.",
                    )
                shape = kernel.extrude_symmetric(inputs["profile"], params["length"])
            elif feature.kind == "extrude_to_face":
                if _is_curve_loop_output(outputs[feature.inputs["profile"]]):
                    raise CADException(
                        "unsupported_profile",
                        "Up to Face does not support the bounded sector-form profile contract.",
                    )
                shape = kernel.extrude_to_face(
                    inputs["profile"],
                    inputs["target"],
                    feature.end_face,
                    params["direction"],
                    params.get("offset", 0),
                )
            elif feature.kind == "extrude_through":
                if _is_curve_loop_output(outputs[feature.inputs["profile"]]):
                    raise CADException(
                        "unsupported_profile",
                        "Through All does not support the bounded sector-form profile contract.",
                    )
                shape = kernel.extrude_through(
                    inputs["profile"], inputs["base"], params["direction"]
                )
            elif feature.kind == "extrude":
                shape = (
                    _extrude_output_v3(
                        outputs[feature.inputs["profile"]],
                        inputs["profile"],
                        params["length"],
                        kernel,
                    )
                    if is_v3
                    else kernel.extrude(inputs["profile"], params["length"])
                )
            elif feature.kind in {"cut", "union", "intersection"}:
                shape = getattr(kernel, feature.kind)(inputs["base"], inputs["tool"])
            elif feature.kind in {"linear_cut_pattern", "circular_cut_pattern"}:
                shape = getattr(kernel, feature.kind)(inputs["base"], inputs["tool"], **params)
            elif feature.kind == "loft":
                if feature.loft_sections is None:
                    shape = kernel.loft(inputs["start"], inputs["end"], **params)
                else:
                    shape = kernel.loft_sections(
                        [inputs[p] for p in feature.loft_sections["ports"]], **params
                    )
            elif feature.kind == "sweep":
                shape = kernel.sweep(
                    inputs["profile"],
                    inputs["path"],
                    **(
                        {"placement": feature.sweep_placement}
                        if feature.sweep_placement is not None
                        else {}
                    ),
                )
            elif feature.kind == "revolve":
                shape = kernel.revolve(inputs["profile"], **params)
            elif feature.kind == "shell" and feature.opening_faces is not None:
                shape = kernel.shell(inputs["base"], opening_faces=feature.opening_faces, **params)
            elif feature.kind in {"fillet", "chamfer"} and feature.edge_pairs is not None:
                shape = getattr(kernel, feature.kind)(
                    inputs["base"], edge_pairs=feature.edge_pairs, **params
                )
            elif feature.kind in {"fillet", "chamfer"} and feature.edge_faces is not None:
                shape = getattr(kernel, feature.kind)(
                    inputs["base"], edge_faces=feature.edge_faces, **params
                )
            elif feature.kind in {
                "fillet",
                "chamfer",
                "transform",
                "mirror",
                "linear_pattern",
                "circular_pattern",
                "shell",
            }:
                shape = getattr(kernel, feature.kind)(inputs["base"], **params)
            else:  # Document validation owns the public unsupported-feature error.
                raise CADException("unsupported_feature", feature.kind)
            if shape is None:
                raise CADException("kernel_error", "The kernel did not produce a native shape.")
            item["topology"] = kernel.topology(shape, feature.id, feature.kind, params, inputs)
            if "cut_ancestry" in item:
                ancestry = getattr(kernel, "cut_ancestry", None)
                item["cut_ancestry"] = ancestry(shape) if ancestry else None
            if output_type(feature.kind) == "solid":
                item["stats"] = kernel.inspect(shape)
                if item["stats"].get("solids", 0) != 1:
                    raise CADException(
                        "unsupported_solid_count",
                        "This slice requires exactly one solid per feature; the operation produced zero or multiple solids.",
                    )
            if is_v3 and (
                (feature.kind == "sketch_constrained" and _is_curve_loop_output(evaluated))
                or (
                    feature.kind == "extrude"
                    and _is_curve_loop_output(outputs[feature.inputs["profile"]])
                )
            ):
                deferred_sector_meshes.append((feature.id, shape))
            else:
                item["mesh"] = kernel.tessellate(shape, linear_deflection=linear_deflection)
            shapes[feature.id] = shape
            if feature.kind != "sketch_constrained":
                evaluated = (
                    SolidOutput(shape)
                    if output_type(feature.kind) == "solid"
                    else ProfileOutput(shape)
                )
            outputs[feature.id] = evaluated
            if result_version == 2 or is_v3:
                item["output"] = describe_output(evaluated)
        except Exception as exc:
            item.update(status="failed", stats=None, mesh=None, topology=[])
            if "cut_ancestry" in item:
                item["cut_ancestry"] = None
            if isinstance(exc, CADException):
                if exc.code == "profile_unavailable":
                    item["status"] = "blocked"
                item["error"] = exc.to_dict()
            else:
                item["error"] = {
                    "code": "kernel_error",
                    "message": f"{feature.id}: {type(exc).__name__}: {exc}",
                }
    if deferred_sector_meshes:
        _finalize_sector_meshes_v3(
            deferred_sector_meshes, kernel, linear_deflection, results, shapes, outputs
        )
    status = "ok" if all(item["status"] == "ok" for item in results.values()) else "failed"
    result = {
        "document_id": document.id,
        "document_hash": document_hash,
        "active_feature": document.active_feature,
        "status": status,
        "units": "mm",
        "parameters": values,
        "features": [results[feature.id] for feature in document.features],
    }
    if result_version == 2 or is_v3:
        result["result_version"] = result_version
    return Replay(result, shapes, outputs)
