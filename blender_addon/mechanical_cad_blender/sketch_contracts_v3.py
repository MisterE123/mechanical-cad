"""Dormant native-free schema-3 source, solver and profile evidence contracts.

The shared geometry policy checks complete genuine geometry. Nothing here solves,
imports a core model, launches transport or supplies publication authority.
"""

from __future__ import annotations

import json
import math

from .arc_geometry import arc_geometry
from .arc_profile_primitives import PrimitiveContext
from .arc_profile_sector_policy import classify_sector_geometry
from .arc_profile_sector_source import (
    SectorArc,
    SectorCircle,
    SectorGeometrySource,
    SectorLine,
    SectorPoint,
)
from .fillet_intent import validate_solved as validate_fillet_solution
from .fillet_intent import validate_structure as validate_fillet_structure
from .request_contracts import snapshot_request
from .sketch_bridge import (
    _STATUSES,
    _SUCCESS,
    _identifier,
    _keys,
    _line_connectivity,
    _mesh_evidence,
    _number,
    _records,
    _require,
    _vector,
    validate_output,
    validate_sketch_report_v2,
)
from .sketch_relations import (
    PAIR_RELATIONS,
    angle_residual,
    auxiliary_scalar_count,
    equation_count,
    pair_residual,
    valid_pair,
)

LEGACY_PROFILE_ERRORS = frozenset(
    {
        "open_profile",
        "invalid_profile",
        "degenerate_profile",
        "self_intersecting_profile",
        "unresolved_coincidence",
        "branched_profile",
        "mixed_profile_regions",
        "multiple_profile_regions",
    }
)
SECTOR_PROFILE_ERRORS = frozenset(
    {
        "unsupported_profile_form",
        "unsupported_profile_coincidence",
        "unsupported_profile_scale",
        "unsupported_profile_sweep",
        "unsupported_profile_nontransverse",
        "unsupported_profile_contact",
        "unsupported_endpoint_discrepancy",
        "unsupported_endpoint_incidence",
        "numerically_ambiguous_profile",
    }
)


def _error(error):
    _keys(error, {"code", "message"})
    _require(
        all(type(value) is str and 0 < len(value) <= 100_000 for value in error.values()),
        "error requires bounded readable code/message",
    )


def normalize_sketch_v3(sketch, *, numeric=False):
    """Build the genuine schema-3 normal form, preserving authored expressions."""
    # The old request leaf bounds cycles and expanded shared DAGs before copying.
    # Its spaced JSON accounting may exceed compact accounting, so this first
    # cap is deliberately generous; exact compact sketch bytes are checked below.
    sketch = snapshot_request(sketch, max_bytes=3 * 256 * 1024, max_depth=8, max_integer_bits=512)
    _keys(
        sketch,
        {
            "schema_version",
            "id",
            "units",
            "plane",
            "points",
            "lines",
            "circles",
            "arcs",
            "constraints",
        },
    )
    _require(
        type(sketch["schema_version"]) is int and sketch["schema_version"] == 3,
        "expected explicit sketch schema 3",
    )
    _identifier(sketch["id"])
    _require(sketch["units"] == "mm", "invalid sketch units")
    plane = sketch["plane"]
    _keys(plane, {"id", "origin", "quaternion"})
    _identifier(plane["id"])
    origin, quaternion = _vector(plane["origin"], 3), _vector(plane["quaternion"], 4)
    _require(abs(sum(v * v for v in quaternion) - 1) <= 1e-9, "non-unit workplane quaternion")
    points, lines, circles, arcs, constraints = (
        _records(sketch[name], limit)
        for name, limit in (
            ("points", 256),
            ("lines", 256),
            ("circles", 256),
            ("arcs", 256),
            ("constraints", 512),
        )
    )
    identifiers = [plane["id"], *points, *lines, *circles, *arcs, *constraints]
    _require(
        len(set(identifiers)) == len(identifiers), "duplicate shared entity/constraint/plane ID"
    )
    _require(len(lines) + len(circles) + len(arcs) <= 256, "aggregate curve limit exceeded")
    _require(2 * len(points) + len(circles) <= 512, "active scalar limit exceeded")
    result = {
        "schema_version": 3,
        "id": sketch["id"],
        "units": "mm",
        "plane": {"id": plane["id"], "origin": origin, "quaternion": quaternion},
        "points": [],
        "lines": [],
        "circles": [],
        "arcs": [],
        "constraints": [],
    }
    for identifier, point in sorted(points.items()):
        _keys(point, {"id", "u", "v"})
        result["points"].append(
            {"id": identifier, "u": _number(point["u"]), "v": _number(point["v"])}
        )
    for line in sorted(lines.values(), key=lambda item: item["id"]):
        _keys(line, {"id", "start", "end"} | {"construction"}, {"id", "start", "end"})
        _require(type(line.get("construction", False)) is bool, "invalid construction flag")
        for key in ("start", "end"):
            _identifier(line[key])
        _require(
            line["start"] in points and line["end"] in points and line["start"] != line["end"],
            "line requires distinct existing points",
        )
        result["lines"].append(
            {key: value for key, value in line.items() if key != "construction" or value}
        )
    for circle in sorted(circles.values(), key=lambda item: item["id"]):
        _keys(circle, {"id", "center", "radius"} | {"construction"}, {"id", "center", "radius"})
        _require(type(circle.get("construction", False)) is bool, "invalid construction flag")
        _identifier(circle["center"])
        _require(circle["center"] in points, "circle requires an existing point center")
        result["circles"].append(
            {
                **{key: value for key, value in circle.items() if key != "construction" or value},
                "radius": _number(circle["radius"], minimum=1e-6),
            }
        )
    positions = {point["id"]: (point["u"], point["v"]) for point in result["points"]}
    for arc in sorted(arcs.values(), key=lambda item: item["id"]):
        _keys(
            arc,
            {"id", "center", "start", "end", "direction"} | {"construction", "fillet_intent"},
            {"id", "center", "start", "end", "direction"},
        )
        _require(type(arc.get("construction", False)) is bool, "invalid construction flag")
        refs = [arc[key] for key in ("center", "start", "end")]
        for reference in refs:
            _identifier(reference)
        _require(
            len(set(refs)) == 3 and all(ref in points for ref in refs),
            "arc requires three distinct existing points",
        )
        arc_geometry(
            *(positions[ref] for ref in refs), arc["direction"], require_equal_radii=numeric
        )
        result["arcs"].append(
            {key: value for key, value in arc.items() if key != "construction" or value}
        )
    equations = len(arcs)
    fields = {"id", "kind", "refs", "value", "target"}
    for constraint in sorted(constraints.values(), key=lambda item: item["id"]):
        _keys(constraint, fields, fields if numeric else {"id", "kind", "refs"})
        kind, refs = constraint["kind"], constraint["refs"]
        _require(
            type(kind) is str and type(refs) is list and len(refs) <= 3,
            "invalid constraint kind/references",
        )
        for reference in refs:
            _identifier(reference)
        if kind in ("horizontal", "vertical"):
            valid = len(refs) == 1 and refs[0] in lines
        elif kind in ("distance", "coincident"):
            valid = len(refs) == 2 and refs[0] != refs[1] and all(ref in points for ref in refs)
        elif kind in PAIR_RELATIONS or kind == "angle":
            valid = valid_pair(kind, refs, lines, circles, arcs, points)
        elif kind == "fixed":
            valid = len(refs) == 1 and refs[0] in points
        elif kind == "radius":
            valid = len(refs) == 1 and (refs[0] in circles or refs[0] in arcs)
        else:
            raise ValueError("unsupported constraint kind")
        _require(valid, "invalid constraint references")
        value, target = constraint.get("value"), constraint.get("target")
        if kind in ("distance", "radius", "angle"):
            if not numeric and type(value) is str:
                _require(0 < len(value) <= 256, "invalid dimension expression length")
                value.encode("utf-8")
            else:
                value = _number(value, minimum=1e-6, bound=180 if kind == "angle" else 1e6)
        else:
            _require(value is None, "unexpected constraint value")
        if kind == "fixed":
            target = _vector(target, 2)
        else:
            _require(target is None, "unexpected constraint target")
        equations += equation_count(kind)
        result["constraints"].append(
            {
                "id": constraint["id"],
                "kind": kind,
                "refs": list(refs),
                "value": value,
                "target": target,
            }
        )
    _require(equations <= 1024, "native equation limit exceeded")
    _require(
        2 * len(points)
        + len(circles)
        + sum(auxiliary_scalar_count(c["kind"]) for c in result["constraints"])
        <= 512,
        "native scalar limit exceeded",
    )
    _require(
        len(json.dumps(sketch, separators=(",", ":"), allow_nan=False).encode("utf-8"))
        <= 256 * 1024,
        "sketch exceeds 256 KiB limit",
    )
    for arc in result["arcs"]:
        validate_fillet_structure(arc, points, lines, result["constraints"], arcs)
    if numeric:
        validate_fillet_solution(result)
    return result


def _arc_geometry(solved):
    positions = {point["id"]: (point["u"], point["v"]) for point in solved["points"]}
    return {
        arc["id"]: arc_geometry(
            *(positions[arc[key]] for key in ("center", "start", "end")),
            arc["direction"],
            require_equal_radii=True,
        )
        for arc in solved["arcs"]
    }


def _residual(solved):
    points = {point["id"]: (point["u"], point["v"]) for point in solved["points"]}
    lines = {line["id"]: line for line in solved["lines"]}
    circles = {circle["id"]: circle for circle in solved["circles"]}
    radii = {circle["id"]: circle["radius"] for circle in solved["circles"]}
    arcs = _arc_geometry(solved)
    radii.update({identifier: arc.start_radius for identifier, arc in arcs.items()})
    residuals = [0.0, *(abs(arc.start_radius - arc.end_radius) for arc in arcs.values())]
    for constraint in solved["constraints"]:
        kind, refs = constraint["kind"], constraint["refs"]
        if kind in ("horizontal", "vertical"):
            line = lines[refs[0]]
            a, b = points[line["start"]], points[line["end"]]
            axis = int(kind == "horizontal")
            value = abs(a[axis] - b[axis])
        elif kind in ("distance", "coincident"):
            value = abs(
                math.dist(points[refs[0]], points[refs[1]])
                - (constraint["value"] if kind == "distance" else 0)
            )
        elif kind == "angle":
            value = angle_residual(refs, constraint["value"], points, lines)
        elif kind in PAIR_RELATIONS:
            value = pair_residual(
                kind, refs, points, lines, circles, {item["id"]: item for item in solved["arcs"]}
            )
        elif kind == "radius":
            value = abs(radii[refs[0]] - constraint["value"])
        else:
            value = math.dist(points[refs[0]], constraint["target"])
        residuals.append(value)
    return max(residuals)


def validate_sketch_report_v3(feature, source):
    """Bind native evidence to original schema, topology, intent and residuals."""
    if (
        source.get("kind") != "sketch_constrained"
        or source.get("sketch", {}).get("schema_version") != 3
    ):
        return validate_sketch_report_v2(feature, source)
    _require(type(feature) is dict and type(source) is dict, "missing source feature")
    _identifier(feature.get("id"))
    _identifier(source.get("id"))
    _require(
        feature.get("id") == source.get("id") and feature.get("kind") == source.get("kind"),
        "sketch feature differs from source",
    )
    _require(
        type(feature.get("status")) is str and feature["status"] in {"ok", "failed", "blocked"},
        "invalid feature status",
    )
    definition = normalize_sketch_v3(source.get("sketch"))
    report = feature.get("sketch")
    if report is None:
        _require(feature["status"] != "ok", "successful sketch lacks its report")
        return
    _keys(
        report,
        {
            "solver",
            "solver_version",
            "status",
            "remaining_dof",
            "failed_constraints",
            "redundant_constraints",
            "max_residual_mm",
            "solved",
            "dimensions",
        },
    )
    _require(
        report["solver"] == "libslvs"
        and report["solver_version"] == "3.2"
        and type(report["status"]) is str
        and report["status"] in _STATUSES,
        "unknown native solve contract",
    )
    constraints = {item["id"]: item for item in definition["constraints"]}
    for field in ("failed_constraints", "redundant_constraints"):
        ids = report[field]
        _require(
            type(ids) is list
            and len(ids) <= 512
            and all(type(item) is str and item in constraints for item in ids)
            and len(set(ids)) == len(ids),
            "invalid diagnostic constraint IDs",
        )
    success = report["status"] in _SUCCESS
    _require(
        report["status"] != "okay" or not report["redundant_constraints"],
        "unreported redundant equations",
    )
    # libslvs REDUNDANT_OKAY retains Jacobian-repair candidates in this wire
    # field, not proven unsatisfied constraints or exact skipped duplicates.
    # Keep those bounded authored IDs intact; independent checks below still
    # establish source intent, topology and the actual successful residual.
    _require(
        report["status"] != "okay" or not report["failed_constraints"],
        "okay solve reports failed constraints",
    )
    residual = report["max_residual_mm"]
    if residual is not None:
        _number(residual, minimum=0, bound=1e12)
    dimensions = report["dimensions"]
    expected = {
        key for key, item in constraints.items() if item["kind"] in ("distance", "radius", "angle")
    }
    _keys(dimensions, expected)
    for identifier, value in dimensions.items():
        _number(value, minimum=1e-6)
        authored = constraints[identifier]["value"]
        _require(type(authored) is str or value == authored, "resolved literal dimension changed")
    if not success:
        _require(
            report["remaining_dof"] is None
            and report["solved"] is None
            and feature["status"] != "ok",
            "failed solver claims solved geometry/DoF",
        )
        return
    dof = report["remaining_dof"]
    _require(
        type(dof) is int
        and 0 <= dof <= 2 * len(definition["points"]) + len(definition["circles"])
        and residual is not None
        and residual <= 1e-7,
        "invalid successful DoF/residual",
    )
    solved = normalize_sketch_v3(report["solved"], numeric=True)
    for field in ("schema_version", "id", "units", "plane", "lines", "arcs"):
        _require(
            solved[field] == definition[field],
            "solved sketch changed persistent schema/topology/frame",
        )
    _require(
        [point["id"] for point in solved["points"]]
        == [point["id"] for point in definition["points"]],
        "solved point identities changed",
    )
    _require(
        [
            (circle["id"], circle["center"], circle.get("construction", False))
            for circle in solved["circles"]
        ]
        == [
            (circle["id"], circle["center"], circle.get("construction", False))
            for circle in definition["circles"]
        ],
        "solved circle identity/center changed",
    )
    expected_constraints = [
        {**item, "value": dimensions[item["id"]]} if item["id"] in dimensions else item
        for item in definition["constraints"]
    ]
    _require(solved["constraints"] == expected_constraints, "solved constraint intent changed")
    measured = _residual(solved)
    _require(
        measured <= 1e-7 and measured <= residual + 1e-12,
        "solved geometry contradicts independently measured residual",
    )


def _alias_sector(sketch):
    """Diagnostic connectivity only: coincidence/coordinate aliases never join geometry."""
    if len(sketch["arcs"]) != 1 or sketch["circles"] or len(sketch["lines"]) not in (1, 2):
        return False
    points = {point["id"]: (point["u"], point["v"]) for point in sketch["points"]}
    groups = {identifier: {identifier} for identifier in points}
    pairs = [item["refs"] for item in sketch["constraints"] if item["kind"] == "coincident"]
    by_position = {}
    for identifier, position in points.items():
        if position in by_position:
            pairs.append((identifier, by_position[position]))
        by_position[position] = identifier
    for left, right in pairs:
        merged = groups[left] | groups[right]
        for identifier in merged:
            groups[identifier] = merged
    arc = sketch["arcs"][0]
    wanted = (
        [(arc["start"], arc["end"])]
        if len(sketch["lines"]) == 1
        else [(arc["center"], arc["start"]), (arc["center"], arc["end"])]
    )
    if {frozenset(pair) for pair in wanted} == {
        frozenset((line["start"], line["end"])) for line in sketch["lines"]
    }:
        return False
    remaining = list(sketch["lines"])
    for left, right in wanted:
        match = next(
            (
                line
                for line in remaining
                if (line["start"] in groups[left] and line["end"] in groups[right])
                or (line["end"] in groups[left] and line["start"] in groups[right])
            ),
            None,
        )
        if match is None:
            return False
        remaining.remove(match)
    return True


def sector_readiness(solved, *, context=None):
    """Classify all normalized geometry once in one non-resetting context."""
    solved = normalize_sketch_v3(solved, numeric=True)
    source = SectorGeometrySource(
        tuple(SectorPoint(**point) for point in solved["points"]),
        tuple(SectorLine(**line) for line in solved["lines"]),
        tuple(SectorArc(**{k: v for k, v in arc.items() if k != "fillet_intent"}) for arc in solved["arcs"]),
        tuple(SectorCircle(**circle) for circle in solved["circles"]),
    )
    result = classify_sector_geometry(
        source, context=PrimitiveContext() if context is None else context
    )
    if result.status == "certified_sector":
        return None
    if result.status == "numerical_ambiguity":
        return "numerically_ambiguous_profile"
    if (
        result.code == "unsupported_profile_form"
        and result.incidence.form is None
        and _alias_sector(solved)
    ):
        return "unsupported_profile_coincidence"
    return result.code


def validate_profile_check(profile, solved):
    _keys(profile, {"ready", "error"})
    _require(type(profile["ready"]) is bool, "profile readiness must be boolean")
    from .analytic_profile_geometry import classify, is_sector_form
    from .sketch_bridge import profile_geometry

    active = profile_geometry(solved)
    arcs = active.get("arcs", [])
    if arcs and not is_sector_form(solved):
        try:
            classify(active)
            valid = True
        except ValueError:
            valid = False
        if profile["ready"]:
            _require(valid and profile["error"] is None, "invalid analytic profile claimed ready")
        else:
            _error(profile["error"])
            try:
                classify(active, open_path=True)
                open_path = True
            except ValueError:
                open_path = False
            _require(
                not valid
                and profile["error"]["code"]
                == ("open_profile" if open_path else "unsupported_profile_form"),
                "analytic profile diagnostic contradicts geometry",
            )
        return
    if arcs:
        code = sector_readiness(active)
        if profile["ready"]:
            _require(profile["error"] is None and code is None, "unsupported sector claimed ready")
        else:
            _error(profile["error"])
            reported = profile["error"]["code"]
            _require(reported in SECTOR_PROFILE_ERRORS, "unknown sector readiness error")
            _require(
                reported == code or reported == "numerically_ambiguous_profile",
                "sector readiness diagnostic contradicts source",
            )
        return
    circles = active.get("circles", [])
    if profile["ready"]:
        _require(profile["error"] is None, "ready profile also contains error")
        from .region_profile_bridge import expected_region_kind

        expected_region_kind(solved)
    else:
        _error(profile["error"])
        _require(profile["error"]["code"] in LEGACY_PROFILE_ERRORS, "unknown legacy profile error")
        if profile["error"]["code"] == "open_profile":
            _require(not circles, "circle cannot be open")
            _line_connectivity(solved, closed=False)


def validate_output_v3(feature, source):
    if (
        source.get("kind") != "sketch_constrained"
        or source.get("sketch", {}).get("schema_version") != 3
    ):
        return validate_output(feature, source)
    validate_sketch_report_v3(feature, source)
    status, output = feature["status"], feature["output"]
    if status != "ok":
        _require(
            output is None
            and feature["mesh"] is None
            and feature["stats"] is None
            and feature["topology"] == [],
            "failed feature carries usable output",
        )
        _error(feature["error"])
        return
    _require(feature["error"] is None, "successful feature has an error")
    _keys(output, {"kind", "display", "profile"})
    _require(
        output["kind"] == "sketch" and output["display"] == "solved_sketch",
        "invalid sketch output discriminant",
    )
    from .sketch_bridge import profile_geometry

    solved, profile = feature["sketch"]["solved"], output["profile"]
    _require(type(profile) is dict, "missing profile state")
    if profile.get("state") == "unavailable":
        _keys(profile, {"state", "reason"})
        _error(profile["reason"])
        _require(
            profile["reason"]["code"] == "open_profile",
            "only validated open chains are unavailable",
        )
        active = profile_geometry(solved)
        if active["arcs"]:
            from .analytic_profile_geometry import classify

            try:
                classify(active, open_path=True)
            except ValueError as exc:
                raise ValueError("Invalid open analytic path: " + str(exc)) from exc
        else:
            _require(not active["circles"], "circle cannot be an open chain")
            _line_connectivity(solved, closed=False)
        _require(
            feature["mesh"] is None and feature["stats"] is None and feature["topology"] == [],
            "open profile carries geometry",
        )
        return
    _keys(profile, {"state", "region_kind"})
    _require(profile["state"] == "available", "unknown profile availability")
    from .analytic_profile_geometry import is_sector_form
    from .region_profile_bridge import expected_region_kind

    active = profile_geometry(solved)
    expected = (
        ("curve_loop" if is_sector_form(solved) else "analytic_regions")
        if active["arcs"]
        else expected_region_kind(solved)
    )
    _require(profile["region_kind"] == expected, "profile region differs from genuine source")
    validate_profile_check({"ready": True, "error": None}, solved)
    _mesh_evidence(feature, solid=False)
