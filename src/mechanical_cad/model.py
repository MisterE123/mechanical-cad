"""Versioned feature DAG and atomic, human-readable document persistence.

This module is independent of Blender, tessellation and Open CASCADE. Feature
identities are explicit IDs, never Blender names or mesh indices.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any

from .errors import CADException
from .expressions import CONSTANTS, FUNCTIONS, Scalar, resolve_parameters
from .sketch_model import (
    SUPPORTED_SKETCH_SCHEMA_VERSIONS,
    SketchDefinition,
    sketch_capabilities,
)

SCHEMA_VERSION = 1  # Existing primitive documents keep their original serializer/hash.
LATEST_SCHEMA_VERSION = 2
SUPPORTED_SCHEMA_VERSIONS = {1, 2}
MAX_DOCUMENT_BYTES = 2 * 1024 * 1024
MAX_FEATURES = 256
MAX_PARAMETERS = 128
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
FEATURE_ID = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")
KINDS = {
    "spur_gear": (
        {"module", "tooth_count", "thickness"},
        {
            "pressure_angle": 20,
            "bore_diameter": 0,
            "backlash": 0.1,
            "clearance": 0.25,
            "profile_tolerance": 0.01,
        },
        {},
    ),
    "import_step": (set(), {}, {}),
    "sketch_rectangle": ({"width", "height"}, {"x": 0, "y": 0, "z": 0}, {}),
    "sketch_circle": ({"radius"}, {"x": 0, "y": 0, "z": 0}, {}),
    "sketch_constrained": (set(), {}, {}),
    "extrude": ({"length"}, {}, {"profile": "profile"}),
    "extrude_symmetric": ({"length"}, {}, {"profile": "profile"}),
    "extrude_through": ({"direction"}, {}, {"profile": "profile", "base": "solid"}),
    "extrude_to_face": ({"direction"}, {"offset": 0}, {"profile": "profile", "target": "solid"}),
    "cut": (set(), {}, {"base": "solid", "tool": "solid"}),
    "union": (set(), {}, {"base": "solid", "tool": "solid"}),
    "intersection": (set(), {}, {"base": "solid", "tool": "solid"}),
    "revolve": (
        {"angle"},
        {"axis_x": 0, "axis_y": 0, "axis_z": 1, "x": 0, "y": 0, "z": 0},
        {"profile": "profile"},
    ),
    # Whole-boundary selection is explicit design intent, not an edge index.
    "fillet": ({"radius"}, {}, {"base": "solid"}),
    "chamfer": ({"distance"}, {}, {"base": "solid"}),
    "transform": (set(), {"x": 0, "y": 0, "z": 0, "rx": 0, "ry": 0, "rz": 0}, {"base": "solid"}),
    "mirror": (
        set(),
        {"axis_x": 0, "axis_y": 0, "axis_z": 1, "x": 0, "y": 0, "z": 0},
        {"base": "solid"},
    ),
    "linear_pattern": ({"count"}, {"dx": 10, "dy": 0, "dz": 0}, {"base": "solid"}),
    "circular_pattern": (
        {"count", "angle"},
        {"axis_x": 0, "axis_y": 0, "axis_z": 1, "x": 0, "y": 0, "z": 0},
        {"base": "solid"},
    ),
    "linear_cut_pattern": (
        {"count"},
        {"dx": 10, "dy": 0, "dz": 0},
        {"base": "solid", "tool": "solid"},
    ),
    "circular_cut_pattern": (
        {"count", "angle"},
        {"axis_x": 0, "axis_y": 0, "axis_z": 1, "x": 0, "y": 0, "z": 0},
        {"base": "solid", "tool": "solid"},
    ),
    "shell": ({"thickness"}, {}, {"base": "solid"}),
    "loft": (set(), {"ruled": 0}, {"start": "profile", "end": "profile"}),
    "sweep": (set(), {}, {"profile": "profile", "path": "profile"}),
    "sketch_face_rectangle": (
        {"width", "height"},
        {"x": 0, "y": 0, "z": 0, "angle": 0},
        {"support": "solid"},
    ),
    "sketch_face_circle": ({"radius"}, {"x": 0, "y": 0, "z": 0, "angle": 0}, {"support": "solid"}),
}


def feature_input_schema(feature):
    """Optional face attachment remains an explicit typed feature-DAG edge."""
    if feature.kind == "sketch_constrained":
        from .sketch_projection import projection_input_types

        return {
            **({"support": "solid"} if feature.support_face is not None else {}),
            **(projection_input_types(feature.projections) if feature.projections else {}),
        }
    if feature.loft_sections is not None:
        return {port: "profile" for port in feature.loft_sections["ports"]}
    return KINDS[feature.kind][2]


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict:
    """Ambiguous JSON must not silently discard a dimension or reference."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key '{key}'")
        result[key] = value
    return result


def output_type(kind: str) -> str:
    return "profile" if kind.startswith("sketch_") else "solid"


def _keys(data: dict, allowed: set[str], required: set[str], what: str) -> None:
    if not isinstance(data, dict):
        raise CADException("invalid_document", f"{what} must be an object.")
    extra, missing = set(data) - allowed, required - set(data)
    if extra or missing:
        detail = f"unknown keys {sorted(extra)}" if extra else f"missing keys {sorted(missing)}"
        raise CADException("invalid_document", f"{what}: {detail}.")


def _text(value: Any, what: str, limit: int = 256) -> str:
    if not isinstance(value, str) or not value or len(value) > limit:
        raise CADException(
            "invalid_document", f"{what} must be nonempty text up to {limit} characters."
        )
    return value


@dataclass(frozen=True)
class Feature:
    id: str
    kind: str
    label: str
    params: dict[str, Scalar] = field(default_factory=dict)
    inputs: dict[str, str] = field(default_factory=dict)
    sketch: SketchDefinition | None = None
    edge_faces: tuple[str, str] | None = None
    support_face: str | None = None
    projections: tuple[dict, ...] = ()
    step_data: dict | None = None
    opening_faces: tuple[str, ...] | None = None
    support_intent: dict | None = None
    sweep_placement: dict | None = None
    end_face: str | None = None
    edge_pairs: tuple[tuple[str, str], ...] | None = None
    loft_sections: dict | None = None

    def __post_init__(self) -> None:
        if self.loft_sections is not None:
            from .loft_sections import validate_sections

            try:
                if self.kind != "loft":
                    raise ValueError("Only Loft accepts ordered sections")
                intent = dict(self.loft_sections)
                intent["ports"] = list(intent["ports"])
                validate_sections(intent, self.inputs)
                object.__setattr__(
                    self,
                    "loft_sections",
                    MappingProxyType({"version": 1, "ports": tuple(intent["ports"])}),
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise CADException("invalid_loft_sections", str(exc)) from exc
        if self.edge_pairs is not None:
            from .blend_selection import validate_edge_pairs

            try:
                if self.kind not in {"fillet", "chamfer"} or self.edge_faces is not None:
                    raise ValueError("Multiple edges require a blend without legacy edge_faces")
                if not isinstance(self.edge_pairs, (tuple, list)) or any(
                    not isinstance(pair, (tuple, list)) for pair in self.edge_pairs
                ):
                    raise ValueError("Edges must be a list of explicit face pairs")
                pairs = validate_edge_pairs([list(pair) for pair in self.edge_pairs])
                object.__setattr__(self, "edge_pairs", tuple(tuple(pair) for pair in pairs))
            except (TypeError, ValueError) as exc:
                raise CADException("invalid_edge_selection", str(exc)) from exc
        if self.sweep_placement is not None:
            from .sweep_placement import validate_placement

            try:
                if self.kind != "sweep":
                    raise ValueError("Only Sweep accepts section placement intent.")
                validate_placement(self.sweep_placement)
            except ValueError as exc:
                raise CADException("invalid_sweep_placement", str(exc)) from exc
            object.__setattr__(
                self, "sweep_placement", MappingProxyType(dict(self.sweep_placement))
            )
        if self.support_intent is not None:
            from .support_intent import validate_intent

            validate_intent(self.support_intent)
            if self.kind != "sketch_constrained" or self.support_face is None:
                raise CADException(
                    "invalid_support_intent",
                    "Support intent requires an attached constrained sketch.",
                )
            intent = dict(self.support_intent)
            for field_name in ("signature", "source_signature"):
                if field_name not in intent:
                    continue
                signature = dict(intent[field_name])
                for key in ("normal", "centroid"):
                    signature[key] = tuple(signature[key])
                intent[field_name] = MappingProxyType(signature)
            if "orientation" in intent:
                intent["orientation"] = MappingProxyType(
                    {
                        **dict(intent["orientation"]),
                        "tangent": tuple(intent["orientation"]["tangent"]),
                    }
                )
            object.__setattr__(self, "support_intent", MappingProxyType(intent))
        object.__setattr__(self, "params", MappingProxyType(copy.deepcopy(dict(self.params))))
        object.__setattr__(self, "inputs", MappingProxyType(dict(self.inputs)))
        object.__setattr__(
            self,
            "projections",
            tuple(
                MappingProxyType(
                    {
                        **dict(row),
                        **(
                            {
                                "faces": tuple(row["faces"]),
                                **(
                                    {
                                        "endpoint_faces": tuple(
                                            tuple(v) for v in row["endpoint_faces"]
                                        )
                                    }
                                    if "endpoint_faces" in row
                                    else {}
                                ),
                            }
                            if "faces" in row
                            else {}
                        ),
                    }
                )
                for row in self.projections
            ),
        )
        if self.step_data is not None:
            object.__setattr__(
                self, "step_data", MappingProxyType(copy.deepcopy(dict(self.step_data)))
            )
        if self.opening_faces is not None:
            object.__setattr__(self, "opening_faces", tuple(self.opening_faces))
        if self.edge_faces is not None:
            object.__setattr__(self, "edge_faces", tuple(self.edge_faces))

    @classmethod
    def from_dict(cls, data: dict) -> Feature:
        _keys(
            data,
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
                "support_intent",
                "sweep_placement",
                "loft_sections",
                "end_face",
                "projections",
                "step_data",
            },
            {"id", "kind"},
            "Feature",
        )
        identifier = _text(data["id"], "Feature ID", 128)
        if not FEATURE_ID.fullmatch(identifier):
            raise CADException("invalid_document", f"Invalid feature ID '{identifier}'.")
        kind = data["kind"]
        if not isinstance(kind, str) or kind not in KINDS:
            raise CADException("unsupported_feature", f"Unsupported feature kind '{kind}'.")
        if kind == "sketch_constrained":
            if "sketch" not in data:
                raise CADException(
                    "invalid_document", "Constrained sketch feature needs a typed sketch payload."
                )
            sketch = SketchDefinition.from_dict(data["sketch"])
        else:
            if "sketch" in data:
                raise CADException(
                    "invalid_document", "Only constrained sketch features accept a sketch payload."
                )
            sketch = None
        step_data = data.get("step_data")
        if kind == "import_step":
            from .step_asset import decode_step

            try:
                decode_step(step_data)
            except ValueError as exc:
                raise CADException("invalid_step_data", str(exc)) from exc
        elif "step_data" in data:
            raise CADException("invalid_step_data", "Only STEP import accepts embedded STEP bytes.")
        support_face = data.get("support_face")
        if kind in {"sketch_face_rectangle", "sketch_face_circle"} or (
            kind == "sketch_constrained" and "support_face" in data
        ):
            if (
                type(support_face) is not str
                or not support_face
                or len(support_face) > 512
                or support_face.startswith(("snapshot:", "pending:"))
            ):
                raise CADException(
                    "invalid_support_face",
                    "Face sketch requires a stable semantic support face ID.",
                )
        elif "support_face" in data:
            raise CADException(
                "invalid_support_face",
                "Only face profiles or constrained sketches accept a support face.",
            )
        end_face = data.get("end_face")
        if kind == "extrude_to_face":
            if (
                type(end_face) is not str
                or not end_face
                or len(end_face) > 512
                or end_face.startswith(("snapshot:", "pending:"))
            ):
                raise CADException(
                    "invalid_end_face", "Up to Face requires a stable semantic end face ID."
                )
        elif "end_face" in data:
            raise CADException("invalid_end_face", "Only Up to Face accepts an end face.")
        sweep_placement = data.get("sweep_placement")
        if "sweep_placement" in data:
            from .sweep_placement import validate_placement

            try:
                if kind != "sweep":
                    raise ValueError("Only Sweep accepts section placement intent.")
                validate_placement(sweep_placement)
            except ValueError as exc:
                raise CADException("invalid_sweep_placement", str(exc)) from exc
        support_intent = data.get("support_intent")
        if "support_intent" in data:
            from .support_intent import validate_intent

            try:
                validate_intent(support_intent)
            except (ValueError, TypeError) as exc:
                raise CADException("invalid_support_intent", str(exc)) from exc
            if kind != "sketch_constrained" or support_face is None:
                raise CADException(
                    "invalid_support_intent",
                    "Support intent requires an attached constrained sketch.",
                )
        opening_faces = data.get("opening_faces")
        if "opening_faces" in data:
            if (
                kind != "shell"
                or type(opening_faces) is not list
                or not 1 <= len(opening_faces) <= 64
                or any(
                    type(v) is not str
                    or not v
                    or len(v) > 512
                    or v.startswith(("snapshot:", "pending:"))
                    for v in opening_faces
                )
                or len(set(opening_faces)) != len(opening_faces)
            ):
                raise CADException(
                    "invalid_shell_opening",
                    "Open shell requires 1–64 distinct stable planar opening faces; omit for a closed shell.",
                )
        edge_pairs = data.get("edge_pairs")
        if "edge_pairs" in data:
            from .blend_selection import validate_edge_pairs

            try:
                if kind not in {"fillet", "chamfer"} or "edge_faces" in data:
                    raise ValueError("Multiple edges require a blend without legacy edge_faces")
                edge_pairs = validate_edge_pairs(edge_pairs)
            except ValueError as exc:
                raise CADException("invalid_edge_selection", str(exc)) from exc
        edge_faces = data.get("edge_faces")
        if "edge_faces" in data:
            if (
                kind not in {"fillet", "chamfer"}
                or type(edge_faces) is not list
                or len(edge_faces) != 2
                or any(
                    type(v) is not str
                    or not v
                    or len(v) > 512
                    or v.startswith(("snapshot:", "pending:"))
                    for v in edge_faces
                )
                or edge_faces[0] == edge_faces[1]
            ):
                raise CADException(
                    "invalid_edge_selection",
                    "An edge requires two distinct stable semantic face IDs on a fillet or chamfer.",
                )
        projections = data.get("projections", [])
        if "projections" in data:
            from .sketch_projection import validate_projections

            try:
                if kind != "sketch_constrained" or type(projections) is not list:
                    raise ValueError("Only constrained sketches accept projection references.")
                validate_projections(projections)
            except ValueError as exc:
                raise CADException("invalid_sketch_projection", str(exc)) from exc
        required, defaults, input_schema = KINDS[kind]
        if kind == "sketch_constrained" and support_face is not None:
            input_schema = {"support": "solid"}
        if projections:
            from .sketch_projection import projection_input_types

            input_schema = {
                **input_schema,
                **projection_input_types(projections),
            }
        loft_sections = data.get("loft_sections")
        if "loft_sections" in data:
            from .loft_sections import validate_sections

            try:
                if kind != "loft":
                    raise ValueError("Only Loft accepts ordered sections")
                ports = validate_sections(loft_sections, data.get("inputs", {}))
                input_schema = {port: "profile" for port in ports}
            except (TypeError, ValueError) as exc:
                raise CADException("invalid_loft_sections", str(exc)) from exc
        params, inputs = data.get("params", {}), data.get("inputs", {})
        _keys(params, required | set(defaults), required, f"Parameters for {identifier}")
        _keys(inputs, set(input_schema), set(input_schema), f"Inputs for {identifier}")
        for name, value in params.items():
            if isinstance(value, bool) or not isinstance(value, (int, float, str)):
                raise CADException(
                    "invalid_document",
                    f"Parameter {identifier}.{name} must be a number or formula.",
                )
        if kind in {"extrude_through", "extrude_to_face"} and (
            type(params["direction"]) not in (int, float) or params["direction"] not in (-1, 1)
        ):
            raise CADException("invalid_direction", "Extrusion direction must be literal +1 or -1.")
        for target in inputs.values():
            _text(target, "Input feature ID", 128)
        return cls(
            identifier,
            kind,
            _text(data.get("label", identifier), "Feature label"),
            {**defaults, **copy.deepcopy(params)},
            dict(inputs),
            sketch,
            tuple(edge_faces) if edge_faces is not None else None,
            support_face,
            tuple(copy.deepcopy(projections)),
            step_data,
            tuple(opening_faces) if opening_faces is not None else None,
            support_intent,
            sweep_placement,
            end_face,
            tuple(tuple(pair) for pair in edge_pairs) if edge_pairs is not None else None,
            loft_sections,
        )

    def to_dict(self) -> dict:
        result = {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "params": dict(self.params),
            "inputs": dict(self.inputs),
        }
        if self.loft_sections is not None:
            result["loft_sections"] = {"version": 1, "ports": list(self.loft_sections["ports"])}
        if self.end_face is not None:
            result["end_face"] = self.end_face
        if self.sweep_placement is not None:
            result["sweep_placement"] = dict(self.sweep_placement)
        if self.step_data is not None:
            result["step_data"] = dict(self.step_data)
        if self.projections:
            result["projections"] = [
                {
                    **dict(row),
                    **(
                        {
                            "faces": list(row["faces"]),
                            **(
                                {"endpoint_faces": [list(v) for v in row["endpoint_faces"]]}
                                if "endpoint_faces" in row
                                else {}
                            ),
                        }
                        if "faces" in row
                        else {}
                    ),
                }
                for row in self.projections
            ]
        if self.opening_faces is not None:
            result["opening_faces"] = list(self.opening_faces)
        if self.support_intent is not None:
            intent = dict(self.support_intent)
            for field_name in ("signature", "source_signature"):
                if field_name not in intent:
                    continue
                signature = dict(intent[field_name])
                for key in ("normal", "centroid"):
                    signature[key] = list(signature[key])
                intent[field_name] = signature
            if "orientation" in intent:
                intent["orientation"] = {
                    **dict(intent["orientation"]),
                    "tangent": list(intent["orientation"]["tangent"]),
                }
            result["support_intent"] = intent
        if self.support_face is not None:
            result["support_face"] = self.support_face
        if self.edge_pairs is not None:
            result["edge_pairs"] = [list(pair) for pair in self.edge_pairs]
        if self.edge_faces is not None:
            result["edge_faces"] = list(self.edge_faces)
        if self.sketch is not None:
            if not isinstance(self.sketch, SketchDefinition):
                raise CADException("invalid_document", "Expected a typed SketchDefinition payload.")
            result["sketch"] = self.sketch.to_dict()
        return result


def _has_bounded_sketch_data(data: Any) -> bool:
    """Opt-in input policy; document schema 2 alone does not migrate old sketches."""
    return (
        type(data) is dict
        and type(data.get("features")) is list
        and any(
            type(feature) is dict
            and type(feature.get("sketch")) is dict
            and type(feature["sketch"].get("schema_version")) is int
            and feature["sketch"]["schema_version"] in SUPPORTED_SKETCH_SCHEMA_VERSIONS
            and sketch_capabilities(feature["sketch"]["schema_version"]).bounded_payload
            for feature in data["features"]
        )
    )


def _check_bounded_document_budget(data: dict, *, persisted: bool = False) -> None:
    if _has_bounded_sketch_data(data):
        from .sketch_model import _check_object_budget

        _check_object_budget(
            data,
            max_bytes=MAX_DOCUMENT_BYTES,
            max_depth=32,
            label="Document",
            size_code="document_too_large",
        )
        if persisted:
            check_persisted_document_budget(data)


def check_persisted_document_budget(data: dict) -> None:
    """Count exact canonical bytes after a caller's bounded structural preflight.

    New services may require a persistable candidate even for legacy embedded
    sketches. Old model acceptance does not call this helper unless opted in.
    ensure_ascii=True makes character count equal encoded byte count.
    """
    size = 1  # The canonical trailing newline.
    encoder = json.JSONEncoder(sort_keys=True, indent=2, allow_nan=False)
    for chunk in encoder.iterencode(data):
        size += len(chunk)
        if size > MAX_DOCUMENT_BYTES:
            raise CADException("document_too_large", "Document exceeds the 2 MiB limit.")


@dataclass(frozen=True)
class Document:
    id: str
    name: str
    parameters: dict[str, Scalar]
    features: tuple[Feature, ...]
    active_feature: str | None = None
    units: str = "mm"
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "features", tuple(self.features))
        if any(
            isinstance(feature, Feature)
            and isinstance(feature.sketch, SketchDefinition)
            and sketch_capabilities(feature.sketch.schema_version).bounded_payload
            for feature in self.features
        ):
            self.to_dict()  # Bound raw and persisted opted-in data before deepcopy/acceptance.
        object.__setattr__(
            self, "parameters", MappingProxyType(copy.deepcopy(dict(self.parameters)))
        )

    @classmethod
    def from_dict(cls, data: dict) -> Document:
        _check_bounded_document_budget(data)
        _keys(
            data,
            {"schema_version", "id", "name", "units", "parameters", "features", "active_feature"},
            {"schema_version", "id", "name", "units", "parameters", "features"},
            "Document",
        )
        if (
            type(data["schema_version"]) is not int
            or data["schema_version"] not in SUPPORTED_SCHEMA_VERSIONS
        ):
            raise CADException("unsupported_schema", "Only document schemas 1 and 2 are supported.")
        if data["units"] != "mm":
            raise CADException("unsupported_units", "This version accepts millimetres ('mm') only.")
        parameters, features = data["parameters"], data["features"]
        if not isinstance(parameters, dict) or len(parameters) > MAX_PARAMETERS:
            raise CADException(
                "invalid_document",
                f"Parameters must be an object with at most {MAX_PARAMETERS} entries.",
            )
        for name in parameters:
            if (
                not isinstance(name, str)
                or not IDENTIFIER.fullmatch(name)
                or len(name) > 64
                or name in CONSTANTS
                or name in FUNCTIONS
            ):
                raise CADException(
                    "invalid_document", f"Invalid or reserved parameter name '{name}'."
                )
        if not isinstance(features, list) or len(features) > MAX_FEATURES:
            raise CADException(
                "invalid_document", f"Features must be a list of at most {MAX_FEATURES} entries."
            )
        active = data.get("active_feature")
        if active is not None:
            _text(active, "Active feature ID", 128)
        document = cls(
            _text(data["id"], "Document ID", 128),
            _text(data["name"], "Document name"),
            copy.deepcopy(parameters),
            tuple(Feature.from_dict(f) for f in features),
            data.get("active_feature"),
            schema_version=data["schema_version"],
        )
        document.validate()
        return document

    @classmethod
    def from_json(cls, text: str) -> Document:
        if len(text.encode("utf-8")) > MAX_DOCUMENT_BYTES:
            raise CADException("document_too_large", "Document exceeds the 2 MiB limit.")
        try:
            data = json.loads(
                text,
                object_pairs_hook=reject_duplicate_keys,
                parse_constant=lambda value: (_ for _ in ()).throw(
                    ValueError(f"Non-finite constant {value}")
                ),
            )
        except (ValueError, RecursionError) as exc:
            raise CADException("invalid_json", f"Cannot read document JSON: {exc}") from exc
        # Preserve legacy accepted number spellings. Only an explicitly embedded
        # bounded sketch capability opts the containing document into the bounded numeric-lexeme
        # policy; a later from_dict call cannot recover the original spelling.
        if _has_bounded_sketch_data(data):
            from .sketch_model import _parse_number

            data = json.loads(
                text,
                object_pairs_hook=reject_duplicate_keys,
                parse_int=lambda token: _parse_number(token, integer=True),
                parse_float=_parse_number,
            )
        return cls.from_dict(data)

    def to_dict(self) -> dict:
        data = {
            "schema_version": self.schema_version,
            "id": self.id,
            "name": self.name,
            "units": self.units,
            "parameters": dict(self.parameters),
            "features": [feature.to_dict() for feature in self.features],
            "active_feature": self.active_feature,
        }
        _check_bounded_document_budget(data, persisted=True)
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, indent=2, allow_nan=False) + "\n"

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.to_json().encode()).hexdigest()

    def validate(self) -> None:
        _text(self.id, "Document ID", 128)
        _text(self.name, "Document name")
        if (
            type(self.schema_version) is not int
            or self.schema_version not in SUPPORTED_SCHEMA_VERSIONS
        ):
            raise CADException("unsupported_schema", "Unsupported document schema.")
        if self.units != "mm":
            raise CADException("unsupported_units", "This version accepts millimetres ('mm') only.")
        if len(self.parameters) > MAX_PARAMETERS or len(self.features) > MAX_FEATURES:
            raise CADException(
                "invalid_document", "Document exceeds its parameter or feature limit."
            )
        if any(
            isinstance(feature, Feature)
            and isinstance(feature.sketch, SketchDefinition)
            and sketch_capabilities(feature.sketch.schema_version).bounded_payload
            for feature in self.features
        ):
            self.to_dict()  # Validate actual canonical bytes before callers may solve.
        if any(feature.kind == "import_step" for feature in self.features):
            check_persisted_document_budget(self.to_dict())
        for name in self.parameters:
            if (
                not isinstance(name, str)
                or not IDENTIFIER.fullmatch(name)
                or len(name) > 64
                or name in CONSTANTS
                or name in FUNCTIONS
            ):
                raise CADException(
                    "invalid_document", f"Invalid or reserved parameter name '{name}'."
                )
        for feature in self.features:
            if not isinstance(feature, Feature):
                raise CADException("invalid_document", "Expected Feature instances.")
            Feature.from_dict(feature.to_dict())
            if feature.kind == "sketch_constrained" and self.schema_version < 2:
                raise CADException(
                    "migration_required",
                    "Constrained sketches require explicit migration to document schema 2.",
                )
        if self.active_feature is not None:
            _text(self.active_feature, "Active feature ID", 128)
        resolve_parameters(self.parameters)
        ordered = self.topological_features()
        by_id = {feature.id: feature for feature in ordered}
        if self.active_feature is not None and self.active_feature not in by_id:
            raise CADException(
                "missing_active_feature", f"Active feature '{self.active_feature}' does not exist."
            )
        from .sketch_projection import extended_projections, projection_input_types

        positions = {feature.id: i for i, feature in enumerate(self.features)}
        for feature in ordered:
            if (
                feature.kind == "extrude_to_face"
                and positions[feature.inputs["target"]] >= positions[feature.id]
            ):
                raise CADException(
                    "invalid_end_target", "Up to Face target must be an earlier solid feature."
                )
            if extended_projections(feature.projections):
                sources = [feature.inputs[p] for p in projection_input_types(feature.projections)]
                if len(set(sources)) != len(sources) or any(
                    positions[s] >= positions[feature.id] for s in sources
                ):
                    raise CADException(
                        "invalid_sketch_projection",
                        "Projection sources must be distinct earlier features.",
                    )
            for input_name, expected_type in feature_input_schema(feature).items():
                actual = by_id[feature.inputs[input_name]]
                if (
                    input_name in projection_input_types(feature.projections)
                    and expected_type == "profile"
                    and actual.kind != "sketch_constrained"
                ):
                    raise CADException(
                        "input_type_mismatch",
                        "External projection source must be a constrained sketch.",
                    )
                if output_type(actual.kind) != expected_type:
                    raise CADException(
                        "input_type_mismatch",
                        f"{feature.id}.{input_name} requires {expected_type}, not {actual.kind}.",
                    )

    def topological_features(self) -> tuple[Feature, ...]:
        by_id = {feature.id: feature for feature in self.features}
        if len(by_id) != len(self.features):
            raise CADException("duplicate_feature", "Every feature must have a unique ID.")
        for feature in self.features:
            for target in feature.inputs.values():
                if target not in by_id:
                    raise CADException(
                        "missing_reference",
                        f"Feature '{feature.id}' refers to missing feature '{target}'.",
                    )
        ordered: list[Feature] = []
        pending = list(self.features)
        completed: set[str] = set()
        while pending:
            ready = [feature for feature in pending if set(feature.inputs.values()) <= completed]
            if not ready:
                raise CADException("feature_cycle", "Feature graph contains a dependency cycle.")
            for feature in ready:
                ordered.append(feature)
                completed.add(feature.id)
                pending.remove(feature)
        return tuple(ordered)

    def migrate_to_v2(self) -> Document:
        """Explicitly opt into typed sketches; preserve existing IDs and feature intent.

        Loading/replaying schema 1 never calls this automatically. The version
        change intentionally changes the document hash; no primitive is converted.
        """
        self.validate()
        if self.schema_version == LATEST_SCHEMA_VERSION:
            return self
        data = self.to_dict()
        data["schema_version"] = LATEST_SCHEMA_VERSION
        return self.from_dict(data)

    def with_parameter(self, name: str, value: Scalar) -> Document:
        """Return a validated copy, leaving the previous document unchanged."""
        data = self.to_dict()
        data["parameters"][name] = value
        return self.from_dict(data)

    def with_feature(self, feature: Feature, *, make_active: bool = True) -> Document:
        data = self.to_dict()
        data["features"] = [
            feature.to_dict() if item.id == feature.id else item.to_dict() for item in self.features
        ]
        if not any(item.id == feature.id for item in self.features):
            data["features"].append(feature.to_dict())
        if make_active:
            data["active_feature"] = feature.id
        return self.from_dict(data)

    def without_feature(self, feature_id: str) -> Document:
        """Remove only unreferenced nodes; never silently cascade design deletion."""
        if not any(feature.id == feature_id for feature in self.features):
            raise CADException("missing_reference", f"Feature '{feature_id}' does not exist.")
        users = [feature.id for feature in self.features if feature_id in feature.inputs.values()]
        if users:
            raise CADException(
                "feature_in_use", f"Feature '{feature_id}' is used by {', '.join(users)}."
            )
        data = self.to_dict()
        data["features"] = [item for item in data["features"] if item["id"] != feature_id]
        if data["active_feature"] == feature_id:
            data["active_feature"] = data["features"][-1]["id"] if data["features"] else None
        return self.from_dict(data)


def load_document(path: str | Path) -> Document:
    path = Path(path)
    if path.stat().st_size > MAX_DOCUMENT_BYTES:
        raise CADException("document_too_large", "Document exceeds the 2 MiB limit.")
    return Document.from_json(path.read_text(encoding="utf-8"))


def save_document(document: Document, path: str | Path) -> None:
    """Atomic replacement: a failed write preserves the previous model document."""
    document.validate()
    path = Path(path)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(document.to_json())
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
