"""Dormant canonical Part envelope with a genuine embedded schema-3 binding.

Only the pinned canonical-envelope function is duplicated. Original module
bindings, legacy serializers and all existing callers remain untouched.
"""

from __future__ import annotations

import copy

from . import part_contracts as legacy
from .part_contracts import (
    _bounded_response,
    _keys,
    _require,
    _validate_extrude_to_face_sources,
    snapshot_request,
)
from .part_contracts import _json as _json
from .part_contracts import document_hash as document_hash
from .part_contracts import input_fingerprint as input_fingerprint
from .sketch_contracts_v3 import normalize_sketch_v3


def _normalize_sketch(sketch):
    _require(type(sketch) is dict, "sketch must be an object")
    version = sketch.get("schema_version")
    _require(type(version) is int and version in (1, 2, 3), "unsupported sketch schema")
    if version in (1, 2):
        legacy._normalize_sketch(sketch)
    else:
        normalized = normalize_sketch_v3(sketch)
        sketch.clear()
        sketch.update(normalized)


def _expected_document(document, *, request_bound=True):
    """Allowlisted serialization changes only; full validity belongs to sidecar."""
    if request_bound:
        data = snapshot_request(document)
    else:
        _bounded_response(document)
        data = copy.deepcopy(document)
    fields = {"schema_version", "id", "name", "units", "parameters", "features", "active_feature"}
    _keys(data, fields, fields - {"active_feature"})
    _require(
        type(data["schema_version"]) is int and data["schema_version"] in (1, 2),
        "unsupported Part schema",
    )
    _require(type(data["id"]) is str and data["id"], "missing document identity")
    _require(
        type(data["parameters"]) is dict and type(data["features"]) is list,
        "invalid Part parameters/features",
    )
    _require(
        type(data["name"]) is str and data["name"] and data["units"] == "mm",
        "invalid Part name/units",
    )
    _require(
        len(data["features"]) <= 256 and len(data["parameters"]) <= 128,
        "Part record limit exceeded",
    )
    _require(
        all(type(value) in (str, int, float) for value in data["parameters"].values()),
        "Part parameters must be numbers or formulas",
    )
    data.setdefault("active_feature", None)
    _require(
        data["active_feature"] is None or type(data["active_feature"]) is str,
        "invalid active feature identity",
    )
    schemas = {
        "sketch_rectangle": ({"width", "height", "x", "y", "z"}, {"width", "height"}, set()),
        "sketch_circle": ({"radius", "x", "y", "z"}, {"radius"}, set()),
        "sketch_constrained": (set(), set(), set()),
        "import_step": (set(), set(), set()),
        "spur_gear": (
            {
                "module",
                "tooth_count",
                "thickness",
                "pressure_angle",
                "bore_diameter",
                "backlash",
                "clearance",
                "profile_tolerance",
            },
            {"module", "tooth_count", "thickness"},
            set(),
        ),
        "sketch_face_rectangle": (
            {"width", "height", "x", "y", "z", "angle"},
            {"width", "height"},
            {"support"},
        ),
        "sketch_face_circle": ({"radius", "x", "y", "z", "angle"}, {"radius"}, {"support"}),
        "extrude": ({"length"}, {"length"}, {"profile"}),
        "extrude_symmetric": ({"length"}, {"length"}, {"profile"}),
        "extrude_through": ({"direction"}, {"direction"}, {"profile", "base"}),
        "extrude_to_face": ({"direction", "offset"}, {"direction"}, {"profile", "target"}),
        "cut": (set(), set(), {"base", "tool"}),
        "union": (set(), set(), {"base", "tool"}),
        "linear_pattern": ({"count", "dx", "dy", "dz"}, {"count"}, {"base"}),
        "linear_cut_pattern": ({"count", "dx", "dy", "dz"}, {"count"}, {"base", "tool"}),
        "circular_cut_pattern": (
            {"count", "angle", "axis_x", "axis_y", "axis_z", "x", "y", "z"},
            {"count", "angle"},
            {"base", "tool"},
        ),
        "circular_pattern": (
            {"count", "angle", "axis_x", "axis_y", "axis_z", "x", "y", "z"},
            {"count", "angle"},
            {"base"},
        ),
        "intersection": (set(), set(), {"base", "tool"}),
        "revolve": ({"angle", "axis_x", "axis_y", "axis_z", "x", "y", "z"}, {"angle"}, {"profile"}),
        "fillet": ({"radius"}, {"radius"}, {"base"}),
        "shell": ({"thickness"}, {"thickness"}, {"base"}),
        "loft": ({"ruled"}, set(), {"start", "end"}),
        "sweep": (set(), set(), {"profile", "path"}),
        "chamfer": ({"distance"}, {"distance"}, {"base"}),
        "mirror": ({"axis_x", "axis_y", "axis_z", "x", "y", "z"}, set(), {"base"}),
        "transform": ({"x", "y", "z", "rx", "ry", "rz"}, set(), {"base"}),
    }
    feature_ids = set()
    for feature in data["features"]:
        _keys(
            feature,
            {
                "id",
                "kind",
                "label",
                "params",
                "inputs",
                "sketch",
                "edge_faces",
                "edge_pairs",
                "opening_faces",
                "support_face",
                "end_face",
                "support_intent",
                "sweep_placement",
                "loft_sections",
                "projections",
                "step_data",
            },
            {"id", "kind"},
        )
        _require(
            type(feature["id"]) is str and feature["id"] and feature["id"] not in feature_ids,
            "feature requires a unique stable ID",
        )
        feature_ids.add(feature["id"])
        kind = feature["kind"]
        _require(type(kind) is str and kind in schemas, "unsupported feature kind")
        if kind == "import_step":
            from .step_asset import decode_step

            decode_step(feature.get("step_data"))
        else:
            _require("step_data" not in feature, "unexpected embedded STEP data")
        if "sweep_placement" in feature:
            from .sweep_placement import validate_placement

            _require(kind == "sweep", "only Sweep accepts section placement intent")
            validate_placement(feature["sweep_placement"])
        if "support_intent" in feature:
            from .support_intent import validate_intent

            _require(
                kind == "sketch_constrained" and "support_face" in feature,
                "support intent requires an attached constrained sketch",
            )
            validate_intent(feature["support_intent"])
        if kind in {"sketch_face_rectangle", "sketch_face_circle"} or (
            kind == "sketch_constrained" and "support_face" in feature
        ):
            face = feature.get("support_face")
            _require(
                type(face) is str
                and 0 < len(face) <= 512
                and not face.startswith(("snapshot:", "pending:")),
                "face profile requires a stable semantic support face",
            )
        else:
            _require("support_face" not in feature, "unexpected support face")
        if kind == "extrude_to_face":
            face = feature.get("end_face")
            _require(
                type(face) is str
                and 0 < len(face) <= 512
                and not face.startswith(("snapshot:", "pending:")),
                "up-to-face extrusion requires a stable semantic end face",
            )
        else:
            _require("end_face" not in feature, "unexpected extrusion end face")
        if "opening_faces" in feature:
            faces = feature["opening_faces"]
            _require(
                kind == "shell"
                and type(faces) is list
                and 1 <= len(faces) <= 64
                and all(
                    type(value) is str
                    and 0 < len(value) <= 512
                    and not value.startswith(("snapshot:", "pending:"))
                    for value in faces
                )
                and len(set(faces)) == len(faces),
                "open shell requires 1–64 distinct stable planar opening faces",
            )
        if "edge_pairs" in feature:
            from .blend_selection import validate_edge_pairs

            _require(
                kind in {"fillet", "chamfer"} and "edge_faces" not in feature,
                "multiple edges require a blend without legacy edge_faces",
            )
            feature["edge_pairs"] = validate_edge_pairs(feature["edge_pairs"])
        if "edge_faces" in feature:
            faces = feature["edge_faces"]
            _require(
                kind in {"fillet", "chamfer"}
                and type(faces) is list
                and len(faces) == 2
                and all(
                    type(value) is str
                    and 0 < len(value) <= 512
                    and not value.startswith(("snapshot:", "pending:"))
                    for value in faces
                )
                and faces[0] != faces[1],
                "selected blend requires two distinct stable semantic face identities",
            )
        feature.setdefault("label", feature["id"])
        feature.setdefault("params", {})
        feature.setdefault("inputs", {})
        allowed, required, inputs = schemas[kind]
        if "loft_sections" in feature:
            from .loft_sections import validate_sections

            _require(kind == "loft", "Only Loft accepts ordered sections")
            inputs = set(validate_sections(feature["loft_sections"], feature["inputs"]))
        if "projections" in feature:
            _require(kind == "sketch_constrained", "projection requires constrained sketch")
            from .sketch_projection import (
                projection_input_types,
                validate_projections,
            )

            _require(type(feature["projections"]) is list, "projections must be a JSON list")
            validate_projections(feature["projections"])
        if kind == "sketch_constrained":
            inputs = ({"support"} if "support_face" in feature else set()) | (
                set(projection_input_types(feature["projections"]))
                if "projections" in feature
                else set()
            )
        _keys(feature["params"], allowed, required)
        _keys(feature["inputs"], inputs)
        _require(type(feature["label"]) is str and feature["label"], "invalid feature label")
        _require(
            all(type(value) in (str, int, float) for value in feature["params"].values()),
            "feature parameters must be numbers or formulas",
        )
        _require(
            all(type(value) is str and value for value in feature["inputs"].values()),
            "feature inputs must be stable IDs",
        )
        if kind == "extrude_to_face":
            _require(
                type(feature["params"]["direction"]) in (int, float)
                and feature["params"]["direction"] in (-1, 1),
                "up-to-face extrusion direction must be literal +1 or -1",
            )
            feature["params"].setdefault("offset", 0)
        if kind in ("sketch_rectangle", "sketch_circle"):
            for axis in ("x", "y", "z"):
                feature["params"].setdefault(axis, 0)
        if kind in {"revolve", "circular_pattern", "circular_cut_pattern"}:
            for key, default in {
                "axis_x": 0,
                "axis_y": 0,
                "axis_z": 1,
                "x": 0,
                "y": 0,
                "z": 0,
            }.items():
                feature["params"].setdefault(key, default)
        if kind in {"sketch_face_rectangle", "sketch_face_circle"}:
            for key in ("x", "y", "z", "angle"):
                feature["params"].setdefault(key, 0)
        if kind == "spur_gear":
            for key, default in {
                "pressure_angle": 20,
                "bore_diameter": 0,
                "backlash": 0.1,
                "clearance": 0.25,
                "profile_tolerance": 0.01,
            }.items():
                feature["params"].setdefault(key, default)
        if kind == "loft":
            feature["params"].setdefault("ruled", 0)
        if kind in {"linear_pattern", "linear_cut_pattern"}:
            for key, default in {"dx": 10, "dy": 0, "dz": 0}.items():
                feature["params"].setdefault(key, default)
        if kind == "mirror":
            for key, default in {
                "axis_x": 0,
                "axis_y": 0,
                "axis_z": 1,
                "x": 0,
                "y": 0,
                "z": 0,
            }.items():
                feature["params"].setdefault(key, default)
        if kind == "transform":
            for key in ("x", "y", "z", "rx", "ry", "rz"):
                feature["params"].setdefault(key, 0)
        if kind == "sketch_constrained":
            _require(
                data["schema_version"] == 2 and "sketch" in feature,
                "constrained sketch requires explicit schema 2",
            )
            _normalize_sketch(feature["sketch"])
        else:
            _require("sketch" not in feature, "unexpected sketch payload")
    from .sketch_projection import validate_projection_sources

    validate_projection_sources(data)
    _validate_extrude_to_face_sources(data)
    return data
