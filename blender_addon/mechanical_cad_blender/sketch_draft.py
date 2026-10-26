"""Pure transient rectangle state and schema-2 candidate construction.

No Blender, kernel or solver imports. Numeric geometry here is an unverified
preview; only the isolated solver's returned report can establish sketch DoF.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import dataclass, field

MIN_LENGTH_MM = 1e-6
MAX_LENGTH_MM = 1e6


class DraftError(ValueError):
    """A recoverable draft problem suitable for an inline explanation."""


def _require_legacy_document(document):
    """Rectangle codecs and seed helpers remain explicit sketch1/2 consumers."""
    for feature in document.get("features", []):
        if feature.get("kind") == "sketch_constrained":
            version = (feature.get("sketch") or {}).get("schema_version")
            if type(version) is not int or version not in (1, 2):
                raise DraftError(
                    "Rectangle authoring requires result version 2 and sketch schema 1 or 2."
                )


def _point(value):
    if len(value) != 2 or any(
        isinstance(number, bool)
        or not isinstance(number, (int, float))
        or abs(number) > MAX_LENGTH_MM
        or not math.isfinite(number)
        for number in value
    ):
        raise DraftError("XY coordinates must be finite and within ±1,000,000 mm.")
    return tuple(float(number) for number in value)


def rectangle_bounds(first, second):
    first, second = _point(first), _point(second)
    anchor = (min(first[0], second[0]), min(first[1], second[1]))
    return anchor, abs(second[0] - first[0]), abs(second[1] - first[1])


def rectangle_payload(feature_id, anchor, width, height, width_key, height_key, fix_corner=True):
    x, y = anchor
    coordinates = ((x, y), (x + width, y), (x + width, y + height), (x, y + height))
    constraints = [
        *(
            [{"id": "anchor", "kind": "fixed", "refs": ["p0"], "target": [x, y]}]
            if fix_corner
            else []
        ),
        *[
            {
                "id": f"axis{index}",
                "kind": "horizontal" if index % 2 == 0 else "vertical",
                "refs": [f"l{index}"],
            }
            for index in range(4)
        ],
        {"id": "width", "kind": "distance", "refs": ["p0", "p1"], "value": width_key},
        {"id": "height", "kind": "distance", "refs": ["p1", "p2"], "value": height_key},
    ]
    return {
        "id": feature_id,
        "kind": "sketch_constrained",
        "label": "Rectangle sketch",
        "params": {},
        "inputs": {},
        "sketch": {
            "schema_version": 1,
            "id": f"{feature_id}_geometry",
            "units": "mm",
            "plane": {"id": "xy", "origin": [0.0, 0.0, 0.0], "quaternion": [1.0, 0.0, 0.0, 0.0]},
            "points": [
                {"id": f"p{index}", "u": point[0], "v": point[1]}
                for index, point in enumerate(coordinates)
            ],
            "lines": [
                {"id": f"l{index}", "start": f"p{index}", "end": f"p{(index + 1) % 4}"}
                for index in range(4)
            ],
            "constraints": constraints,
        },
    }


def _rectangle_definition(document, feature_id):
    feature = next((item for item in document["features"] if item["id"] == feature_id), None)
    if not feature or feature["kind"] != "sketch_constrained":
        raise DraftError("Choose a constrained rectangle created by the viewport rectangle tool.")
    sketch = feature.get("sketch") or {}
    constraints = {item["id"]: item for item in sketch.get("constraints", [])}
    points = {item["id"]: item for item in sketch.get("points", [])}
    lines = {item["id"]: item for item in sketch.get("lines", [])}
    expected = {"anchor", "width", "height", "axis0", "axis1", "axis2", "axis3"}
    if (
        set(constraints) not in (expected, expected - {"anchor"})
        or set(points) != {f"p{i}" for i in range(4)}
        or set(lines) != {f"l{i}" for i in range(4)}
    ):
        raise DraftError(
            "This first editor supports the fixed-definition four-corner rectangle tool only."
        )
    if points["p1"]["u"] <= points["p0"]["u"] or points["p3"]["v"] <= points["p0"]["v"]:
        raise DraftError(
            "This viewport editor supports only the +X/+Y rectangle branch from its lower-left corner. Reversed imported point ordering is not supported; the CAD definition is unchanged."
        )
    anchor = constraints.get("anchor")
    if anchor is not None and (anchor.get("kind") != "fixed" or anchor.get("refs") != ["p0"]):
        raise DraftError(
            "This rectangle's fixed corner has been changed; use the general sketch editor when available."
        )
    plane = sketch.get("plane") or {}
    if plane.get("origin") != [0, 0, 0] or plane.get("quaternion") != [1, 0, 0, 0]:
        raise DraftError("This viewport editor supports the global XY plane only.")
    for index in range(4):
        constraint = constraints[f"axis{index}"]
        if (
            lines[f"l{index}"].get("start") != f"p{index}"
            or lines[f"l{index}"].get("end") != f"p{(index + 1) % 4}"
            or constraint.get("kind") != ("horizontal" if index % 2 == 0 else "vertical")
            or constraint.get("refs") != [f"l{index}"]
        ):
            raise DraftError(
                "The rectangle's connected horizontal/vertical definition has changed."
            )
    for dimension, refs in (("width", ["p0", "p1"]), ("height", ["p1", "p2"])):
        constraint = constraints[dimension]
        if (
            constraint.get("kind") != "distance"
            or constraint.get("refs") != refs
            or constraint.get("value") not in document["parameters"]
        ):
            raise DraftError("The rectangle must retain its named width and height dimensions.")
    if constraints["width"]["value"] == constraints["height"]["value"]:
        raise DraftError("Width and height must be independently named parameters for this tool.")
    return constraints, points


@dataclass
class RectangleDraft:
    """One optimistic transaction; rejected input never destroys the valid preview."""

    document_json: str
    feature_id: str = ""
    is_edit: bool = False
    phase: str = "FIRST_POINT"
    first: tuple | None = None
    anchor: tuple = (0.0, 0.0)
    width: float = 0.0
    height: float = 0.0
    width_text: str = ""
    height_text: str = ""
    width_key: str = ""
    height_key: str = ""
    error: str = ""
    solver_report: dict | None = None
    validated_json: str = ""
    fix_corner: bool = True
    fixed_target: tuple | None = None
    seed_bounds: tuple | None = None
    seed_override: list | None = None
    last_solved_points: list | None = None
    pending_dimensions: dict | None = None
    original_values: dict = field(default_factory=dict)
    original_text: dict = field(default_factory=dict)

    def __post_init__(self):
        # Runtime-only attributes intentionally stay outside dataclass/codec fields.
        self._guarded_evidence = None
        self._guarded_owner = None
        self._guarded_candidate = ""
        document = json.loads(self.document_json)
        _require_legacy_document(document)
        if not self.feature_id:
            used = {feature["id"] for feature in document["features"]}
            index = 1
            while f"sketch_{index}" in used or any(
                f"sketch_{index}_{suffix}" in document["parameters"]
                for suffix in ("width", "height")
            ):
                index += 1
            self.feature_id = f"sketch_{index}"
        if self.is_edit:
            constraints, points = _rectangle_definition(document, self.feature_id)
            self.fix_corner = "anchor" in constraints
            self.anchor = _point(
                constraints["anchor"]["target"]
                if self.fix_corner
                else (points["p0"]["u"], points["p0"]["v"])
            )
            self.fixed_target = self.anchor if self.fix_corner else None
            self.width = abs(points["p1"]["u"] - points["p0"]["u"])
            self.height = abs(points["p2"]["v"] - points["p1"]["v"])
            self.width_key, self.height_key = (
                constraints["width"]["value"],
                constraints["height"]["value"],
            )
            self.phase = "DIMENSIONS"
            for key in (self.width_key, self.height_key):
                value = document["parameters"][key]
                self.original_values[key] = copy.deepcopy(value)
                self.original_text[key] = value if isinstance(value, str) else repr(value)
            self.width_text, self.height_text = (
                self.original_text[self.width_key],
                self.original_text[self.height_key],
            )
        else:
            self.width_key, self.height_key = (
                f"{self.feature_id}_width",
                f"{self.feature_id}_height",
            )

    @property
    def base_hash(self):
        return hashlib.sha256(self.document_json.encode()).hexdigest()

    def require_current(self, document_json):
        if document_json != self.document_json:
            raise DraftError(
                "The committed document changed while this sketch was open. Cancel and reopen the sketch before editing it."
            )

    def first_point(self, point):
        if self.phase != "FIRST_POINT":
            raise DraftError("The first corner is already set.")
        self.first = _point(point)
        self.anchor = self.first
        self.phase = "SECOND_POINT"

    def move(self, point):
        if self.phase != "SECOND_POINT":
            return
        anchor, width, height = rectangle_bounds(self.first, point)
        self.anchor, self.width, self.height = anchor, width, height
        self.fixed_target = anchor if self.fix_corner else None
        self.width_text, self.height_text = repr(width), repr(height)
        self.solver_report = None
        self.last_solved_points = None
        self.validated_json = ""

    def second_point(self, point):
        self.move(point)
        if not all(MIN_LENGTH_MM <= value <= MAX_LENGTH_MM for value in (self.width, self.height)):
            self.error = "Width and height must each be between 0.000001 and 1,000,000 mm. Choose a different second corner."
            return False
        self.phase = "DIMENSIONS"
        self.seed_bounds = (self.anchor, self.width, self.height)
        self.error = ""
        return True

    def set_dimensions(self, width, height, fix_corner=None):
        self.pending_dimensions = None
        self.width_text, self.height_text = width, height
        if fix_corner is not None:
            if bool(fix_corner) and not self.fix_corner:
                self.fixed_target = self.anchor
            elif not fix_corner:
                if self.fix_corner:
                    # Releasing a positional constraint is an explicit edit.
                    # Seed the same point identities from the visible solution
                    # so removing only the anchor does not translate the part.
                    self.seed_override = (
                        copy.deepcopy(self.last_solved_points)
                        if self.last_solved_points
                        else [
                            {"id": f"p{index}", "u": point[0], "v": point[1]}
                            for index, point in enumerate(self.points()[:4])
                        ]
                    )
                self.fixed_target = None
            self.fix_corner = bool(fix_corner)
        self.validated_json = ""
        self.solver_report = None
        self.error = "Dimensions changed. Apply Dimensions or Finish to run the solver."

    def candidate(self):
        from .unit_input import normalize_unit_input

        if self.phase != "DIMENSIONS":
            raise DraftError("Choose both rectangle corners before finishing the sketch.")
        document = json.loads(self.document_json)
        _require_legacy_document(document)
        document["schema_version"] = 2
        for text, key in ((self.width_text, self.width_key), (self.height_text, self.height_key)):
            document["parameters"][key] = (
                copy.deepcopy(self.original_values[key])
                if self.is_edit and text == self.original_text[key]
                else normalize_unit_input(text.strip(), "length")
            )
        if not self.is_edit:
            seed_anchor, seed_width, seed_height = self.seed_bounds
            feature = rectangle_payload(
                self.feature_id,
                seed_anchor,
                seed_width,
                seed_height,
                self.width_key,
                self.height_key,
                self.fix_corner,
            )
            if self.fix_corner:
                feature["sketch"]["constraints"][0]["target"] = list(self.fixed_target)
            document["features"].append(feature)
            document["active_feature"] = self.feature_id
        else:
            feature = next(item for item in document["features"] if item["id"] == self.feature_id)
            constraints = feature["sketch"]["constraints"]
            anchor = next((item for item in constraints if item["id"] == "anchor"), None)
            if not self.fix_corner:
                constraints[:] = [item for item in constraints if item["id"] != "anchor"]
            elif anchor is None:
                constraints.insert(
                    0,
                    {
                        "id": "anchor",
                        "kind": "fixed",
                        "refs": ["p0"],
                        "target": list(self.fixed_target),
                    },
                )
            elif anchor["target"] != list(self.fixed_target):
                anchor["target"] = list(self.fixed_target)
        if self.seed_override is not None:
            feature["sketch"]["points"] = copy.deepcopy(self.seed_override)
        return document

    def invalidate_guarded(self):
        self._guarded_evidence = None
        self._guarded_owner = None
        self._guarded_candidate = ""
        self.solver_report = None
        self.validated_json = ""

    def _guarded_report(self, current_selection, *, require_success=False):
        from .guarded_evidence import GuardedEvidence

        evidence = self._guarded_evidence
        if type(evidence) is not GuardedEvidence:
            raise DraftError("Rectangle preview requires current guarded evidence.")
        if json.dumps(self.candidate(), sort_keys=True, allow_nan=False) != self._guarded_candidate:
            raise DraftError("The applied rectangle differs from its guarded solution.")
        response = evidence.revalidate(
            current_selection,
            owner_token=self._guarded_owner,
            expected_action={"replay", "check_geometry", "export_step", "export_stl"},
            expected_result_version=2,
        )
        if require_success and response["result"]["status"] != "ok":
            raise DraftError("Apply Dimensions successfully before using solved coordinates.")
        feature = next(
            (item for item in response["result"]["features"] if item["id"] == self.feature_id), {}
        )
        return feature.get("sketch")

    def guarded_is_current(self, current_selection):
        try:
            if self.pending_dimensions is not None:
                return False
            report = self._guarded_report(current_selection)
            if json.dumps(report, sort_keys=True) != json.dumps(self.solver_report, sort_keys=True):
                raise DraftError("Retained rectangle preview was changed.")
            return True
        except (ValueError, TypeError, KeyError):
            self.invalidate_guarded()
            return False

    def guarded_seed_points(self, current_selection):
        """Read the previous applied solution while raw dialog input is pending.

        Pending text never changes candidate(), and is not accepted by this read.
        Seed points come from the original guarded bytes, never mutable caches.
        """
        report = self._guarded_report(current_selection, require_success=True)
        if not report or report.get("status") not in {"okay", "redundant_okay"}:
            raise DraftError("Apply Dimensions successfully before releasing its solved corner.")
        return copy.deepcopy(report["solved"]["points"])

    def accept_guarded_replay(
        self, candidate, evidence, current_selection, *, owner_token, consume=False
    ):
        """Production acceptance keeps the original immutable owner-bound record.

        A completed Part's same-revision association may be reread for preview.
        A new preview consumes once; Finish leaves consumption to Part publication.
        """
        from .guarded_evidence import GuardedEvidence

        self.invalidate_guarded()
        if type(evidence) is not GuardedEvidence:
            raise DraftError("Rectangle preview requires guarded Part evidence.")
        _require_legacy_document(candidate)
        candidate_json = json.dumps(candidate, sort_keys=True, allow_nan=False)
        if (
            json.dumps(
                evidence.operation_request().get("document"), sort_keys=True, allow_nan=False
            )
            != candidate_json
        ):
            raise DraftError("Rectangle evidence differs from its exact candidate.")
        validate = evidence.publication.consume if consume else evidence.revalidate
        response = validate(
            current_selection,
            owner_token=owner_token,
            expected_action={"replay", "check_geometry", "export_step", "export_stl"},
            expected_result_version=2,
        )
        accepted = self.accept_replay(candidate, response["result"])
        self._guarded_evidence = evidence
        self._guarded_owner = owner_token
        self._guarded_candidate = candidate_json
        evidence.revalidate(
            current_selection,
            owner_token=owner_token,
            expected_action={"replay", "check_geometry", "export_step", "export_stl"},
            expected_result_version=2,
        )
        return accepted

    def accept_replay(self, candidate, result):
        """Legacy tooling-only validation; production uses accept_guarded_replay."""
        # This tooling path cannot keep authority from an earlier guarded read.
        self.invalidate_guarded()
        feature = next(
            (item for item in result.get("features", []) if item.get("id") == self.feature_id), {}
        )
        report = feature.get("sketch")
        report = copy.deepcopy(report) if isinstance(report, dict) else None
        failed = next(
            (item for item in result.get("features", []) if item.get("status") == "failed"), None
        )
        if result.get("status") != "ok" or feature.get("status") != "ok" or not report:
            if report and report.get("status") not in {"okay", "redundant_okay"}:
                self.solver_report = report
            error = (failed or feature).get("error") or {}
            self.error = error.get(
                "message",
                "The draft did not solve successfully. Correct its dimensions and try again.",
            )
            return False
        dimensions = report.get("dimensions") or {}
        values = (dimensions.get("width"), dimensions.get("height"))
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not MIN_LENGTH_MM <= value <= MAX_LENGTH_MM
            or not math.isfinite(value)
            for value in values
        ):
            raise DraftError("The solver returned invalid rectangle dimensions.")
        solved = report.get("solved") or {}
        points = {
            point["id"]: _point((point["u"], point["v"])) for point in solved.get("points", [])
        }
        if set(points) != {"p0", "p1", "p2", "p3"}:
            raise DraftError("The solver returned no supported four-corner rectangle preview.")
        x, y = points["p0"]
        width, height = values
        expected = ((x, y), (x + width, y), (x + width, y + height), (x, y + height))
        if (
            points["p1"][0] <= x
            or points["p3"][1] <= y
            or any(
                not math.isclose(actual, target, rel_tol=0, abs_tol=1e-7)
                for index, point in enumerate(expected)
                for actual, target in zip(points[f"p{index}"], point, strict=True)
            )
        ):
            raise DraftError(
                "This viewport editor supports only the +X/+Y rectangle branch from its lower-left corner. The solved orientation is reversed or unsupported; no sketch changes were committed."
            )
        self.width, self.height = values
        self.anchor = points["p0"]
        self.last_solved_points = copy.deepcopy(solved["points"])
        self.solver_report = report
        self.error = ""
        self.validated_json = json.dumps(candidate, allow_nan=False)
        return True

    def points(self):
        x, y = self.anchor
        return [
            (x, y),
            (x + self.width, y),
            (x + self.width, y + self.height),
            (x, y + self.height),
            (x, y),
        ]
