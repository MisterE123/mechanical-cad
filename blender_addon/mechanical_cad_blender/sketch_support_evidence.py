"""Bind attached sketch world planes to exact canonical upstream replay evidence."""

import copy

from .assembly_frame_evidence import compose, face_frame, same_frame
from .sketch_bridge import _keys, _require


def attached(source):
    return source["kind"] == "sketch_constrained" and "support_face" in source


def contextual(source):
    return attached(source) or "projections" in source


def resolved_source(source, feature, results):
    """Derive transient solve input from current evidence, never saved caches."""
    derived = source
    if not attached(source):
        _require("support_plane" not in feature, "unexpected resolved sketch support")
    else:
        _require("support_plane" in feature, "attached sketch lacks explicit support resolution")
        plane = feature["support_plane"]
        if plane is None:
            _require(
                feature["status"] != "ok" and feature.get("sketch") is None,
                "unresolved sketch support publishes solve evidence",
            )
            return source
        _keys(plane, {"id", "origin", "quaternion"})
        expected_plane = world_plane(source, results)
        expected = {"xyz_mm": expected_plane["origin"], "wxyz": expected_plane["quaternion"]}
        _require(
            plane["id"] == source["sketch"]["plane"]["id"]
            and same_frame({"xyz_mm": plane["origin"], "wxyz": plane["quaternion"]}, expected),
            "resolved sketch plane differs from current support and saved local placement",
        )
        derived = copy.deepcopy(source)
        derived["sketch"]["plane"] = copy.deepcopy(plane)
    if "projections" in source:
        if feature["status"] != "ok" and feature.get("sketch") is None:
            return derived
        from .sketch_projection import (
            extended_projections,
            is_solid_projection,
            project_sketch,
            project_solid_edges,
            projection_groups,
            validate_projection_ownership,
            validate_solid_edges,
        )

        validate_projection_ownership(derived["sketch"], source["projections"])
        groups = projection_groups(source["projections"])
        extended = extended_projections(source["projections"])
        if extended and any(is_solid_projection(rows) for rows in groups.values()):
            _keys(
                feature.get("projection_edges"),
                {port for port, rows in groups.items() if is_solid_projection(rows)},
            )
        derived = copy.deepcopy(derived)
        for port, rows in groups.items():
            upstream = next((row for row in results if row["id"] == source["inputs"][port]), None)
            _require(
                upstream is not None and upstream["status"] == "ok",
                "projection requires a current successful bound source",
            )
            if is_solid_projection(rows):
                _require(
                    upstream["output"]["kind"] == "solid",
                    "edge projection needs a bound upstream solid",
                )
                edges = feature.get("projection_edges")
                if extended:
                    edges = edges[port]
                validate_solid_edges(edges, rows, upstream["topology"])
                derived["sketch"] = project_solid_edges(derived["sketch"], edges, rows)
            else:
                _require(
                    upstream["kind"] == "sketch_constrained"
                    and type(upstream.get("sketch")) is dict
                    and type(upstream["sketch"].get("solved")) is dict,
                    "projected sketch requires current bound solved geometry",
                )
                derived["sketch"] = project_sketch(
                    derived["sketch"], upstream["sketch"]["solved"], rows
                )

    return derived


def world_plane(source, results):
    """Compute display/ray plane from already validated current upstream rows.

    Callers retain guarded freshness of results; this returns geometry only,
    never publication authority or a replacement for the saved local plane.
    """
    _require(attached(source), "world support plane requires an attached sketch")
    by_id = {item["id"]: item for item in results}
    support = by_id.get(source["inputs"]["support"])
    _require(
        support is not None and support["status"] == "ok" and support["output"]["kind"] == "solid",
        "attached sketch requires a successful upstream solid",
    )
    from .cut_support_ancestry import resolve_replay_support

    signature, _ = resolve_replay_support(
        source["support_face"], source.get("support_intent"), support["id"], results
    )
    local = source["sketch"]["plane"]
    frame = face_frame({key: value for key, value in signature.items() if key != "tangent"})
    if "tangent" in signature:
        from .assembly_frame_evidence import _basis_quaternion
        from .support_intent import frame_basis

        frame["wxyz"] = _basis_quaternion(*frame_basis(signature))
    expected = compose(
        frame,
        {"xyz_mm": local["origin"], "wxyz": local["quaternion"]},
    )
    return {"id": local["id"], "origin": expected["xyz_mm"], "quaternion": expected["wxyz"]}


def ancestor_document(canonical, source):
    by_id = {feature["id"]: feature for feature in canonical["features"]}
    pending = list(source["inputs"].values())
    ancestors = set()
    while pending:
        identifier = pending.pop()
        _require(
            identifier in by_id and identifier != source["id"], "invalid sketch support ancestry"
        )
        if identifier not in ancestors:
            ancestors.add(identifier)
            pending.extend(by_id[identifier]["inputs"].values())
    document = copy.deepcopy(canonical)
    document["features"] = [
        copy.deepcopy(feature) for feature in canonical["features"] if feature["id"] in ancestors
    ]
    document["active_feature"] = source["inputs"].get(
        "support", next(iter(source["inputs"].values()), None)
    )
    return document


def validate_solve_context(canonical, source, context, validate_replay):
    """Validate one flat ancestor replay, not nested solver-context snapshots."""
    _require(contextual(source), "support context requires an associative sketch")
    from .sketch_projection import has_solid_projections

    solid_projection = has_solid_projections(source.get("projections", []))
    _keys(
        context,
        {"document", "replay"}
        | ({"plane"} if attached(source) else set())
        | ({"projection_edges"} if solid_projection else set()),
    )
    expected = ancestor_document(canonical, source)
    _require(
        context["document"] == expected,
        "solve support context differs from exact canonical ancestors",
    )
    replay = context["replay"]
    _require(
        type(replay) is dict and replay.get("status") == "ok",
        "solve context requires successful upstream replay",
    )
    validate_replay(expected, replay)
    return resolved_source(
        source,
        {
            "status": "ok",
            **({"support_plane": context["plane"]} if attached(source) else {}),
            **({"projection_edges": context["projection_edges"]} if solid_projection else {}),
        },
        replay["features"],
    )
