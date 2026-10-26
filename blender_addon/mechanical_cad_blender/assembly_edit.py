"""Pure JSON candidates for user-authored parts and assembly trees.

These helpers never publish state or certify geometry. The isolated assembly
service must validate each complete candidate before a Blender transaction accepts
it. All operations copy input data; existing stable IDs remain unchanged.
"""

from __future__ import annotations

import copy
import hashlib
import json
import uuid

from .assembly_coordinates import NO_SCALAR_COORDINATE, extra_names
from .bridge import BridgeError


def canonical_digest(value):
    """Hash an already canonical schema snapshot, never an arbitrary mesh/cache."""
    return hashlib.sha256(
        (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    ).hexdigest()


def identity(prefix):
    return prefix + "_" + uuid.uuid4().hex


def origin_frame():
    return {"xyz_mm": [0.0, 0.0, 0.0], "wxyz": [1.0, 0.0, 0.0, 0.0]}


def _part_source(document):
    if type(document) is not dict or not document.get("id"):
        raise BridgeError("Choose a current canonical Part document first.")
    output = document.get("active_feature")
    feature = next((f for f in document.get("features", []) if f.get("id") == output), None)
    if not feature or feature.get("kind") not in {
        "extrude",
        "extrude_through",
        "extrude_to_face",
        "extrude_symmetric",
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
    }:
        raise BridgeError("Display a solid feature before using this Part in an assembly.")
    return {
        "source_document_id": document["id"],
        "source_digest": canonical_digest(document),
        "document": copy.deepcopy(document),
    }, output


def _definition(source, output, name):
    return {
        "id": identity("part"),
        "name": name or source["document"]["name"],
        "source_document_id": source["source_document_id"],
        "source_digest": source["source_digest"],
        "output_feature_id": output,
        "mate_frames": [{"id": "origin", "name": "Part origin", "placement": origin_frame()}],
    }


def new_from_part(document, *, name="Assembly", part_name="", instance_name=""):
    """Explicitly ground the first captured part at the assembly origin."""
    source, output = _part_source(document)
    definition = _definition(source, output, part_name)
    instance = {
        "id": identity("instance"),
        "part_id": definition["id"],
        "name": instance_name or definition["name"],
    }
    return {
        "kind": "assembly",
        "assembly_schema_version": 1,
        "id": identity("assembly"),
        "name": name or "Assembly",
        "length_unit": "mm",
        "angle_unit": "rad",
        "part_sources": [source],
        "parts": [definition],
        "instances": [instance],
        "joints": [],
        "grounded_instance": instance["id"],
        "ground": origin_frame(),
        "verification_presets": [],
        "active_verification_preset": None,
    }


def capture_definition(assembly, document, *, name=""):
    """Prepare a definition; caller MUST insert its instance in the same Apply.

    An already accepted identical source/output reuses its definition. Working
    edits to an accepted source require an explicit source-wide update instead.
    """
    candidate = copy.deepcopy(assembly)
    source, output = _part_source(document)
    accepted = next(
        (s for s in candidate["part_sources"] if s["source_document_id"] == document["id"]), None
    )
    if accepted and accepted["source_digest"] != source["source_digest"]:
        raise BridgeError(
            "This Part has an update available. Explicitly update all its assembly instances, "
            "or fork an independent Part before inserting it."
        )
    existing = next(
        (
            p
            for p in candidate["parts"]
            if p["source_document_id"] == document["id"] and p["output_feature_id"] == output
        ),
        None,
    )
    if existing:
        return candidate, existing["id"]
    if accepted is None:
        candidate["part_sources"].append(source)
    definition = _definition(source, output, name)
    candidate["parts"].append(definition)
    return candidate, definition["id"]


def insert_instance(
    assembly,
    part_id,
    *,
    parent,
    parent_frame,
    child_frame,
    kind,
    coordinate=0.0,
    limits=None,
    rotation=0.0,
    rotation_limits=None,
    extra_coordinates=None,
    name="",
    joint_name="",
):
    """Build child plus its incoming joint atomically; never save an orphan."""
    candidate = copy.deepcopy(assembly)
    part = next((p for p in candidate["parts"] if p["id"] == part_id), None)
    if part is None:
        raise BridgeError("Choose an existing reusable part definition.")
    child = {"id": identity("instance"), "part_id": part_id, "name": name or part["name"]}
    joint = {
        "id": identity("joint"),
        "name": joint_name or kind.title(),
        "kind": kind,
        "parent": parent,
        "child": child["id"],
        "parent_frame": parent_frame,
        "child_frame": child_frame,
    }
    if kind not in NO_SCALAR_COORDINATE:
        joint["coordinate"] = coordinate
        if limits is not None:
            joint["limits"] = list(limits)
    if kind == "cylindrical":
        joint["rotation"] = rotation
        joint["rotation_limits"] = list(rotation_limits) if rotation_limits is not None else None
    for field in extra_names(kind):
        value, bounds = (extra_coordinates or {}).get(
            field, (joint.get(field, 0.0), joint.get(field + "_limits"))
        )
        joint[field] = value
        joint[field + "_limits"] = list(bounds) if bounds is not None else None
    candidate["instances"].append(child)
    candidate["joints"].append(joint)
    return candidate


def edit_frame(assembly, part_id, *, frame_id="", name="", placement, support_face=None):
    """Explicit literal datum or named exact planar-face datum with local offset."""
    candidate = copy.deepcopy(assembly)
    part = next((p for p in candidate["parts"] if p["id"] == part_id), None)
    if part is None:
        raise BridgeError("Choose a part definition before editing a mate frame.")
    if frame_id:
        frame = next((f for f in part["mate_frames"] if f["id"] == frame_id), None)
        if frame is None:
            raise BridgeError("The selected mate frame no longer exists.")
        frame.update(name=name or frame["name"], placement=copy.deepcopy(placement))
    else:
        part["mate_frames"].append(
            {
                "id": identity("frame"),
                "name": name or "Mate frame",
                "placement": copy.deepcopy(placement),
            }
        )
    frame = part["mate_frames"][-1] if not frame_id else frame
    if support_face is not None:
        frame["support_face"] = support_face
    else:
        frame.pop("support_face", None)
    return candidate


def edit_joint(
    assembly,
    joint_id,
    *,
    coordinate,
    limits,
    rotation=None,
    rotation_limits=None,
    extra_coordinates=None,
):
    candidate = copy.deepcopy(assembly)
    joint = next((j for j in candidate["joints"] if j["id"] == joint_id), None)
    if joint is None or joint["kind"] == "fixed":
        raise BridgeError("Choose an existing revolute or slider joint.")
    if joint["kind"] not in NO_SCALAR_COORDINATE:
        joint["coordinate"] = coordinate
    if joint["kind"] == "cylindrical" and rotation is not None:
        joint["rotation"] = rotation
        joint["rotation_limits"] = list(rotation_limits) if rotation_limits is not None else None
    if limits is None:
        joint.pop("limits", None)
    elif joint["kind"] not in NO_SCALAR_COORDINATE:
        joint["limits"] = list(limits)
    for field in extra_names(joint["kind"]):
        if extra_coordinates is not None and field in extra_coordinates:
            value, bounds = extra_coordinates[field]
            joint[field] = value
            joint[field + "_limits"] = list(bounds) if bounds is not None else None
    return candidate


def update_source(assembly, document):
    """Preview an all-instance source update without moving literal datum frames."""
    candidate = copy.deepcopy(assembly)
    source, _ = _part_source(document)
    accepted = next(
        (
            s
            for s in candidate["part_sources"]
            if s["source_document_id"] == source["source_document_id"]
        ),
        None,
    )
    if accepted is None:
        raise BridgeError("This working Part is not an accepted assembly source.")
    accepted.update(source)
    parts = []
    for part in candidate["parts"]:
        if part["source_document_id"] == document["id"]:
            part["source_digest"] = source["source_digest"]
            parts.append(part["id"])
    affected = [i["id"] for i in candidate["instances"] if i["part_id"] in parts]
    return candidate, affected


def working_copy(assembly, part_id):
    """Return embedded source without overwriting any current working Part."""
    part = next((p for p in assembly["parts"] if p["id"] == part_id), None)
    if part is None:
        raise BridgeError("Choose an existing part definition.")
    source = next(
        s for s in assembly["part_sources"] if s["source_document_id"] == part["source_document_id"]
    )
    return copy.deepcopy(source["document"])


def edit_verification_preset(
    assembly,
    *,
    preset_id="",
    name,
    kind,
    policy,
    pair=None,
    minimum_mm=None,
    requirement_name="",
    contact_policy=None,
):
    """Explicitly create/update a named policy; pair updates keep stable row IDs.

    Editing one pair never drops the other authored engineering requirements.
    Choosing interference-only explicitly removes the selected preset's clearance
    requirements; the confirmation dialog must explain that intent change.
    """
    if contact_policy is not None and (
        contact_policy != "accept_tolerance_band" or minimum_mm != 0 or kind != "clearance"
    ):
        raise BridgeError("Intended-contact acceptance requires a named pair with zero minimum.")
    candidate = copy.deepcopy(assembly)
    presets = candidate.setdefault("verification_presets", [])
    preset = next((p for p in presets if p["id"] == preset_id), None) if preset_id else None
    if preset_id and preset is None:
        raise BridgeError("The selected verification preset no longer exists.")
    if preset is None:
        preset = {"id": identity("preset"), "requirements": []}
        presets.append(preset)
    preset.update(name=name, kind=kind, policy=copy.deepcopy(policy))
    if kind == "interference_only":
        preset["requirements"] = []
    elif kind == "clearance":
        if pair is None or len(pair) != 2 or pair[0] == pair[1]:
            raise BridgeError("Choose two distinct instances for the clearance requirement.")
        pair = sorted(pair)
        requirement = next(
            (r for r in preset["requirements"] if sorted(r["instances"]) == pair), None
        )
        if requirement is None:
            requirement = {"id": identity("requirement")}
            preset["requirements"].append(requirement)
        requirement.update(
            name=requirement_name or "Minimum clearance", instances=pair, minimum_mm=minimum_mm
        )
        if contact_policy is None:
            requirement.pop("contact_policy", None)
        else:
            requirement["contact_policy"] = contact_policy
    else:
        raise BridgeError("Choose clearance or interference-only verification.")
    candidate["active_verification_preset"] = preset["id"]
    return candidate


def standard_verification_preset(assembly):
    """Explicit first-use setup only; never replace or select existing intent."""
    if assembly["verification_presets"] or assembly["active_verification_preset"]:
        raise BridgeError("Saved check settings already exist. Choose or edit them explicitly.")
    return edit_verification_preset(
        assembly,
        name="Standard strict interference",
        kind="interference_only",
        policy={
            "linear_tolerance_mm": 1e-6,
            "volume_tolerance_mm3": 1e-9,
            "linear_deflection_mm": 0.1,
        },
    )


def select_verification_preset(assembly, preset_id):
    candidate = copy.deepcopy(assembly)
    if preset_id is not None and not any(
        p["id"] == preset_id for p in candidate["verification_presets"]
    ):
        raise BridgeError("Choose an existing verification preset, or clear the selection.")
    candidate["active_verification_preset"] = preset_id
    return candidate


def remove_component(assembly, instance_id):
    """Detach a branch and its dependent policy references, preserving reusable Parts.

    Empty clearance presets are removed rather than weakened to interference-only.
    The caller presents the returned impact before committing this detached candidate.
    """
    instances = {row["id"]: row for row in assembly["instances"]}
    if instance_id not in instances:
        raise BridgeError("Choose an existing component to remove.")
    if instance_id == assembly["grounded_instance"]:
        raise BridgeError("The grounded root cannot be removed. Start a new assembly instead.")
    removed = {instance_id}
    for _ in assembly["instances"]:
        children = {j["child"] for j in assembly["joints"] if j["parent"] in removed}
        if children <= removed:
            break
        removed.update(children)
    candidate = copy.deepcopy(assembly)
    removed_instances = [row for row in assembly["instances"] if row["id"] in removed]
    removed_joints = [
        row for row in assembly["joints"] if row["parent"] in removed or row["child"] in removed
    ]
    removed_joint_ids = {row["id"] for row in removed_joints}
    related = [
        row["name"]
        for row in assembly.get("gear_relations", [])
        if {row["driver_joint"], row["driven_joint"]} & removed_joint_ids
    ]
    if related:
        raise BridgeError(
            "Remove these gear relations before removing the component: " + ", ".join(related)
        )
    candidate["instances"] = [row for row in candidate["instances"] if row["id"] not in removed]
    candidate["joints"] = [
        row
        for row in candidate["joints"]
        if row["parent"] not in removed and row["child"] not in removed
    ]
    requirements, deleted_presets, retained = [], [], []
    for preset in candidate.get("verification_presets", []):
        affected = [r for r in preset["requirements"] if set(r["instances"]) & removed]
        for requirement in affected:
            requirements.append(
                {
                    "preset": preset["name"],
                    "name": requirement["name"],
                    "instances": [instances[key]["name"] for key in requirement["instances"]],
                }
            )
        preset["requirements"] = [
            r for r in preset["requirements"] if not set(r["instances"]) & removed
        ]
        if preset["kind"] == "clearance" and not preset["requirements"]:
            deleted_presets.append({"id": preset["id"], "name": preset["name"]})
        else:
            retained.append(preset)
    candidate["verification_presets"] = retained
    active_cleared = candidate.get("active_verification_preset") in {
        p["id"] for p in deleted_presets
    }
    if active_cleared:
        candidate["active_verification_preset"] = None
    impact = {
        "instances": [{"id": row["id"], "name": row["name"]} for row in removed_instances],
        "joints": [{"id": row["id"], "name": row["name"]} for row in removed_joints],
        "requirements": requirements,
        "deleted_presets": deleted_presets,
        "active_preset_cleared": active_cleared,
    }
    return candidate, impact


def edit_gear_relation(
    assembly,
    *,
    relation_id="",
    name="Gear relation",
    driver_joint,
    driven_joint,
    ratio,
    offset_rad,
    keep_alignment=False,
):
    """Detached explicit relation edit. Canonical acceptance still needs sidecar replay."""
    from .assembly_gears import ordered_relations, saved_coordinates

    current = saved_coordinates(assembly)
    if current is None:
        raise BridgeError("The saved gear pose is invalid. Repair the relation first.")
    candidate = copy.deepcopy(assembly)
    rows = candidate.setdefault("gear_relations", [])
    old = next((row for row in rows if row["id"] == relation_id), None)
    if relation_id and old is None:
        raise BridgeError("This gear relation no longer exists.")
    joints = {joint["id"]: joint for joint in candidate["joints"]}
    if any(
        key not in joints or joints[key]["kind"] != "revolute"
        for key in (driver_joint, driven_joint)
    ):
        raise BridgeError("Choose two existing revolute joints.")
    position = rows.index(old) if old else len(rows)
    if old:
        joints[old["driven_joint"]]["coordinate"] = current[old["driven_joint"]]
        rows.remove(old)
    # Compute alignment only when explicitly requested. Editing other fields never
    # silently changes an authored offset.
    if keep_alignment:
        offset_rad = current[driven_joint] - ratio * current[driver_joint]
    rows.insert(
        position,
        {
            "id": relation_id or identity("gear"),
            "name": name,
            "driver_joint": driver_joint,
            "driven_joint": driven_joint,
            "ratio": ratio,
            "offset_rad": offset_rad,
        },
    )
    joints[driven_joint]["coordinate"] = None
    ordered_relations(candidate)
    if saved_coordinates(candidate) is None:
        raise BridgeError("The gear-driven coordinate exceeds its range or authored limits.")
    return candidate


def remove_gear_relation(assembly, relation_id):
    """Release the driven axis at its exact current value, preserving chained poses."""
    from .assembly_gears import saved_coordinates

    values = saved_coordinates(assembly)
    candidate = copy.deepcopy(assembly)
    rows = candidate.get("gear_relations", [])
    row = next((row for row in rows if row["id"] == relation_id), None)
    if row is None or values is None:
        raise BridgeError("Choose an existing valid gear relation.")
    joint = next(j for j in candidate["joints"] if j["id"] == row["driven_joint"])
    joint["coordinate"] = values[joint["id"]]
    rows.remove(row)
    if not rows:
        candidate.pop("gear_relations", None)
    return candidate
