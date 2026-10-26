"""Pure native-free Part canonicalization and exact-request identity contracts.

These helpers recognize only the core serializer's allowlisted normalizations.
They never launch a process, import the core, solve, or publish model state.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math

from .request_contracts import MAX_INTEGER_BITS, MAX_RESPONSE_BYTES, snapshot_request
from .sketch_bridge import normalize_sketch_v2


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _keys(data, allowed, required=None):
    _require(type(data) is dict, "expected an object")
    _require(len(data) <= len(allowed), "unexpected fields")
    required = allowed if required is None else required
    _require(not (set(data) - allowed or required - set(data)), "unexpected or missing fields")


def _bounded_response(value, *, max_bytes=MAX_RESPONSE_BYTES, max_integer_bits=MAX_INTEGER_BITS):
    """Bound expanded JSON before walking/copying a direct Python response.

    Real transport already caps bytes. This memoized preflight also handles
    cycles/shared-container DAGs supplied by callers/tests without exponential
    traversal. Responses include both canonical object and text, so use the
    transport's 64 MiB cap rather than the 2 MiB request budget.
    """
    memo, active = {}, set()
    max_nodes = 4_000_000

    def visit(item, depth):
        _require(depth <= 32, "snapshot JSON nesting exceeds limit")
        kind = type(item)
        if kind in (dict, list):
            identity = id(item)
            _require(identity not in active, "cyclic snapshot JSON containers")
            if identity in memo:
                size, nodes, height = memo[identity]
                _require(depth + height <= 32, "snapshot JSON nesting exceeds limit")
                return size, nodes, height
            _require(len(item) < max_nodes, "snapshot JSON node limit exceeded")
            active.add(identity)
            size, nodes, height = 2, 1, 0
            try:
                entries = item.items() if kind is dict else enumerate(item)
                for index, (key, child) in enumerate(entries):
                    if index:
                        size += 2
                    if kind is dict:
                        _require(type(key) is str, "JSON keys must be strings")
                        size += visit(key, depth + 1)[0] + 2
                    child_size, child_nodes, child_height = visit(child, depth + 1)
                    size += child_size
                    nodes += child_nodes
                    height = max(height, child_height + 1)
                    _require(size <= max_bytes, "snapshot response exceeds 64 MiB limit")
                    _require(nodes <= max_nodes, "snapshot JSON node limit exceeded")
            finally:
                active.remove(identity)
            memo[identity] = size, nodes, height
            return memo[identity]
        if kind is str:
            _require(len(item) + 2 <= max_bytes, "snapshot string exceeds response limit")
            size = 2
            for character in item:
                code = ord(character)
                if character in '\\"\b\f\n\r\t':
                    size += 2
                elif 0x20 <= code <= 0x7E:
                    size += 1
                else:
                    size += 6 if code <= 0xFFFF else 12
                _require(size <= max_bytes, "snapshot string exceeds response limit")
        elif kind is int:
            _require(
                item.bit_length() <= max_integer_bits,
                "snapshot integer exceeds numeric resource limit",
            )
            size = len(str(item))
        elif kind is float:
            _require(math.isfinite(item), "JSON numbers must be finite")
            size = len(repr(item))
        else:
            _require(kind in (bool, type(None)), "expected JSON data")
            size = 5 if item is False else 4
        return size, 1, 0

    visit(value, 0)


def _json(value, *, canonical=False):
    if canonical:
        return json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n"
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def document_hash(canonical_document):
    """Hash the canonical Part serializer's exact indented bytes."""
    return hashlib.sha256(_json(canonical_document, canonical=True).encode("utf-8")).hexdigest()


def input_fingerprint(request):
    """Raw request-tree identity, distinct from canonical Part source identity."""
    request = snapshot_request(request)
    return hashlib.sha256(_json(request).encode("utf-8")).hexdigest()


def _numeric(value):
    _require(type(value) in (int, float), "expected a finite sketch number")
    number = float(value)
    _require(math.isfinite(number), "expected a finite sketch number")
    # Core sketch limits are below exact-integer double range. Do not accept
    # lossy conversion merely because both values round to the same float.
    _require(number == value, "numeric normalization changed the authored value")
    return number


def _vector(value, size):
    _require(type(value) is list and len(value) == size, "invalid sketch vector")
    return [_numeric(item) for item in value]


def _normalize_sketch(sketch):
    """Explicit dispatch; frozen v1 normalization never acquires empty v2 fields."""
    if (
        type(sketch) is dict
        and type(sketch.get("schema_version")) is int
        and sketch["schema_version"] == 2
    ):
        normalized = normalize_sketch_v2(sketch)
        sketch.clear()
        sketch.update(normalized)
        return
    _normalize_sketch_v1(sketch)


def _normalize_sketch_v1(sketch):
    fields = {"schema_version", "id", "units", "plane", "points", "lines", "constraints"}
    _keys(sketch, fields)
    _require(
        type(sketch["schema_version"]) is int and sketch["schema_version"] == 1,
        "unsupported sketch schema",
    )
    _require(
        type(sketch["id"]) is str and sketch["id"] and sketch["units"] == "mm",
        "invalid sketch identity/units",
    )
    plane = sketch["plane"]
    _keys(plane, {"id", "origin", "quaternion"})
    _require(type(plane["id"]) is str and plane["id"], "invalid plane identity")
    plane["origin"] = _vector(plane["origin"], 3)
    plane["quaternion"] = _vector(plane["quaternion"], 4)
    for name in ("points", "lines", "constraints"):
        records = sketch[name]
        _require(type(records) is list, "sketch records must be arrays")
        ids = []
        for record in records:
            _require(
                type(record) is dict and type(record.get("id")) is str,
                "sketch record requires a stable ID",
            )
            ids.append(record["id"])
            if name == "points":
                _keys(record, {"id", "u", "v"})
                record["u"], record["v"] = _numeric(record["u"]), _numeric(record["v"])
            elif name == "lines":
                _keys(record, {"id", "start", "end", "construction"}, {"id", "start", "end"})
                if "construction" in record:
                    _require(
                        type(record["construction"]) is bool, "construction flag must be boolean"
                    )
                    if not record["construction"]:
                        record.pop("construction")
                _require(
                    all(type(record[field]) is str and record[field] for field in ("start", "end")),
                    "invalid line references",
                )
            else:
                _keys(record, {"id", "kind", "refs", "value", "target"}, {"id", "kind", "refs"})
                _require(
                    type(record["kind"]) is str
                    and record["kind"]
                    in (
                        "horizontal",
                        "vertical",
                        "coincident",
                        "distance",
                        "fixed",
                        "parallel",
                        "perpendicular",
                        "equal",
                        "angle",
                        "point_on_line",
                        "midpoint",
                        "symmetry",
                    ),
                    "invalid constraint kind",
                )
                _require(
                    type(record["refs"]) is list
                    and all(type(ref) is str and ref for ref in record["refs"]),
                    "invalid constraint references",
                )
                record.setdefault("value", None)
                record.setdefault("target", None)
                if record["value"] is not None and type(record["value"]) is not str:
                    record["value"] = _numeric(record["value"])
                if record["target"] is not None:
                    record["target"] = _vector(record["target"], 2)
        _require(len(set(ids)) == len(ids), "duplicate sketch record IDs")
        records.sort(key=lambda item: item["id"])


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


def _validate_extrude_to_face_sources(document):
    """Keep the selected target exact and earlier; profiles retain DAG ordering."""
    profiles = {
        "sketch_rectangle",
        "sketch_circle",
        "sketch_constrained",
        "sketch_face_rectangle",
        "sketch_face_circle",
    }
    solids = {
        "extrude",
        "extrude_through",
        "extrude_symmetric",
        "extrude_to_face",
        "cut",
        "union",
        "intersection",
        "revolve",
        "fillet",
        "chamfer",
        "transform",
        "mirror",
        "linear_pattern",
        "linear_cut_pattern",
        "circular_cut_pattern",
        "circular_pattern",
        "shell",
        "import_step",
        "spur_gear",
        "loft",
        "sweep",
    }
    features = {feature["id"]: feature for feature in document["features"]}
    positions = {feature["id"]: index for index, feature in enumerate(document["features"])}
    for feature in document["features"]:
        if feature["kind"] != "extrude_to_face":
            continue
        profile = features.get(feature["inputs"]["profile"])
        target = features.get(feature["inputs"]["target"])
        _require(
            profile is not None and profile["kind"] in profiles,
            "up-to-face extrusion requires a profile input",
        )
        _require(
            target is not None
            and target["kind"] in solids
            and positions[target["id"]] < positions[feature["id"]],
            "up-to-face extrusion requires an explicitly selected earlier solid target",
        )


def canonical_equivalent(raw_document, canonical_document):
    """Pure, no-cache intent comparison against an already accepted snapshot.

    This supplies no authority/receipt and performs no transport. Capture/update
    must still request a fresh sidecar receipt. Unsupported/malformed shapes are
    different, never guessed to be a canonical-equivalent current source.
    """
    try:
        expected = _json(_expected_document(raw_document), canonical=True)
        _bounded_response(canonical_document)
        candidate = _json(canonical_document, canonical=True)
        canonical = _json(
            _expected_document(canonical_document, request_bound=False), canonical=True
        )
        return expected == candidate == canonical
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return False
