"""Associative sketch context: immutable local source and proven world placement."""

from __future__ import annotations

from dataclasses import replace

from .errors import CADException
from .model import Document
from .sketch_model import Plane
from .support_plane import resolve_plane


def ancestor_document(document, feature):
    """Exact upstream closure only; selected/downstream drafts need not be valid solids."""
    support = feature.inputs.get("support", next(iter(feature.inputs.values()), None))
    features = {row.id: row for row in document.features}
    keep, pending = set(), list(feature.inputs.values())
    while pending:
        identifier = pending.pop()
        if identifier in keep:
            continue
        keep.add(identifier)
        pending.extend(features[identifier].inputs.values())
    return Document(
        document.id,
        document.name,
        dict(document.parameters),
        tuple(row for row in document.features if row.id in keep),
        support,
        units=document.units,
        schema_version=document.schema_version,
    )


def resolve_supported_feature(feature, kernel, support_shape, *, results=None):
    """Return a temporary feature with a world plane; never rewrite canonical data."""
    try:
        if feature.support_intent is not None and "source_feature" in feature.support_intent:
            from .cut_support_ancestry import resolve_replay_support

            signature, _ = resolve_replay_support(
                feature.support_face, feature.support_intent, feature.inputs["support"], results
            )
        elif feature.support_intent is not None:
            signature = kernel.support_face_signature(
                support_shape, feature.support_face, feature.support_intent
            )
        else:
            signature = kernel.support_face_signature(support_shape, feature.support_face)
        plane = resolve_plane(signature, feature.sketch.to_dict()["plane"])
        resolved = replace(
            feature.sketch,
            plane=Plane(tuple(plane["origin"]), tuple(plane["quaternion"]), plane["id"]),
        )
        return replace(feature, sketch=resolved), plane
    except CADException:
        raise
    except (ValueError, KeyError) as exc:
        raise CADException("invalid_sketch_support", f"{feature.id}: {exc}") from exc


def prepare_solve_support(document, feature, result_version, *, kernel=None):
    """Replay support ancestry only, with full source evidence for independent clients.

    Independent solve-only sketches never call this path or import OCCT.
    """
    from .engine import regenerate

    if kernel is None:
        from .kernel_ocp import OCPKernel

        kernel = OCPKernel()
    upstream = ancestor_document(document, feature)
    replay = regenerate(upstream, kernel, result_version=result_version)
    if not replay.ok:
        failure = next(row for row in replay.result["features"] if row["status"] != "ok")
        raise CADException(
            "upstream_failed",
            f"Sketch support cannot rebuild: {failure['id']}: {failure['error']['message']}",
        )
    context = {"document": upstream.to_dict(), "replay": replay.result}
    resolved = feature
    if feature.support_face is not None:
        resolved, context["plane"] = resolve_supported_feature(
            feature,
            kernel,
            replay.shapes[feature.inputs["support"]],
            results=replay.result["features"],
        )
    if feature.projections:
        from .sketch_projection import has_solid_projections, projection_input_types

        inputs = {
            port: replay.shapes[feature.inputs[port]]
            if kind == "solid"
            else replay.outputs[feature.inputs[port]].solved_sketch
            for port, kind in projection_input_types(feature.projections).items()
        }
        resolved, edges = resolve_projection_inputs(resolved, kernel, inputs)
        if has_solid_projections(feature.projections):
            context["projection_edges"] = edges
    return resolved, context


def resolve_projected_feature(feature, solved):
    from .sketch_model import SketchDefinition
    from .sketch_projection import project_sketch

    try:
        sketch = project_sketch(
            feature.sketch.to_dict(), solved.to_dict(), [dict(row) for row in feature.projections]
        )
        return replace(feature, sketch=SketchDefinition.from_dict(sketch))
    except (ValueError, KeyError) as exc:
        raise CADException("invalid_sketch_projection", f"{feature.id}: {exc}") from exc


def resolve_solid_projected_feature(feature, kernel, shape):
    from .sketch_model import SketchDefinition
    from .sketch_projection import project_solid_edges

    try:
        rows = [dict(row) for row in feature.projections]
        edges = kernel.projected_edges(shape, rows)
        sketch = project_solid_edges(feature.sketch.to_dict(), edges, rows)
        return replace(feature, sketch=SketchDefinition.from_dict(sketch)), edges
    except CADException:
        raise
    except (ValueError, KeyError) as exc:
        raise CADException("invalid_sketch_projection", f"{feature.id}: {exc}") from exc


def resolve_projection_inputs(feature, kernel, inputs):
    """Evaluate independently source-bound rows without flattening solid identity."""
    from .sketch_projection import (
        extended_projections,
        is_solid_projection,
        projection_groups,
        validate_projection_ownership,
    )

    validate_projection_ownership(feature.sketch.to_dict(), feature.projections)
    resolved = feature
    evidence = {}
    for port, rows in projection_groups(feature.projections).items():
        selected = replace(resolved, projections=tuple(rows))
        if is_solid_projection(rows):
            resolved, evidence[port] = resolve_solid_projected_feature(
                selected, kernel, inputs[port]
            )
        else:
            resolved = resolve_projected_feature(selected, inputs[port])
    return replace(resolved, projections=feature.projections), (
        evidence if extended_projections(feature.projections) else evidence.get("external")
    )
