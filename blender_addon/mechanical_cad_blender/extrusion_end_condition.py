"""Explicit extrusion end intent and existing current-result face catalog choices.

Selection controls are convenience only. Canonical replay resolves the exact
source/semantic face again; an enum entry never grants geometry authority.
"""

EXTRUSION_KINDS = frozenset({"extrude", "extrude_symmetric", "extrude_through", "extrude_to_face"})
UP_TO_FACE_ITEM = (
    "UP_TO_FACE",
    "Up to planar face",
    "Stop at the infinite supporting plane of an explicit stable parallel face",
)
DIRECTION_ITEMS = [
    ("1", "Along sketch normal", "From the sketch along its positive normal"),
    ("-1", "Opposite sketch normal", "From the sketch opposite its normal"),
]
OFFSET_DESCRIPTION = (
    "Number or formula in mm. Positive extends past the face plane along the selected direction; "
    "negative stops short of the plane"
)
_CHOICES = {}


def end_condition(kind):
    return {
        "extrude_symmetric": "SYMMETRIC",
        "extrude_through": "THROUGH_ALL",
        "extrude_to_face": "UP_TO_FACE",
    }.get(kind, "BLIND")


def set_up_to_face(feature, *, profile, target, end_face, direction, offset="0"):
    """Replace only this feature's intent; never change project parameters."""
    if str(direction) not in {"1", "-1", "1.0", "-1.0"}:
        raise ValueError("Up to planar face requires Along or Opposite sketch normal")
    if not target or target == "NONE":
        raise ValueError("Select an explicit earlier target solid for Up to planar face")
    if (
        not isinstance(end_face, str)
        or not end_face
        or end_face == "NONE"
        or len(end_face) > 512
        or end_face.startswith(("snapshot:", "pending:"))
    ):
        raise ValueError("Select one stable planar end face on the chosen target solid")
    if not str(offset).strip():
        raise ValueError("Enter an offset or formula (0 stops at the selected face plane)")
    old_offset = feature.get("params", {}).get("offset", 0)
    from .unit_input import normalize_unit_input

    normalized_offset = normalize_unit_input(offset, "length")
    sign = int(float(direction))
    old_direction = feature.get("params", {}).get("direction")
    if type(old_direction) in (int, float) and old_direction == sign:
        sign = old_direction  # Untouched literal spellings retain their canonical type.
    feature["kind"] = "extrude_to_face"
    feature["params"] = {
        "direction": sign,
        "offset": old_offset if str(old_offset) == str(offset) else normalized_offset,
    }
    feature["inputs"] = {"profile": profile, "target": target}
    feature["end_face"] = end_face


def _source_choices(self, context):
    from .common import _state
    from .document_state import _read_document
    from .solid_feature_edit import SOLID_KINDS

    values = [("NONE", "Select an earlier solid", "No source is selected automatically")]
    try:
        document = _read_document(_state(context))
        edited = getattr(self, "linked_tool_id", "") or getattr(self, "feature_id", "")
        for feature in document["features"]:
            if feature["id"] == edited:
                break
            if feature["kind"] in SOLID_KINDS:
                values.append(
                    (feature["id"], f"{feature['label']} [{feature['id']}]", feature["id"])
                )
    except Exception:
        pass
    key = ("sources", tuple(values))
    _CHOICES[key] = values
    return _CHOICES[key]


def _end_face_choices(self, context):
    from . import document_state
    from .topology_labels import face_label

    source = self.target
    values = [("NONE", "Select a stable planar face", "Rebuild or choose an earlier solid")]
    result = document_state.current_part_result(context)
    if result:
        for feature in result.get("features", []):
            if feature["id"] == source:
                values.extend(
                    (face["id"], f"{face_label(face)} [{face['id']}]", face["id"])
                    for face in feature.get("topology", [])
                    if face.get("provenance", {}).get("semantic_status") == "stable"
                    and face.get("signature", {}).get("surface") == "plane"
                )
                break
    key = ("faces", source, tuple(values))
    _CHOICES[key] = values
    return _CHOICES[key]


def draw_up_to_face(layout, operator, *, direction="direction"):
    layout.prop(operator, "target", text="Earlier target solid")
    layout.prop(operator, "end_face", text="End face")
    layout.prop(operator, direction, text="Direction")
    layout.prop(operator, "offset", text="Offset (mm)")
    layout.label(text="Stops at the infinite face plane, not its finite boundary.")
    layout.label(text="Face must be parallel and ahead of the sketch.")
    layout.label(text="Positive offset: past plane. Negative: stop short.")
