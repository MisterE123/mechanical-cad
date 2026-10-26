"""Shared native-free numeric and draft-dialog helpers for assembly operators."""

import json
import math

import bpy

from . import (
    assembly_display,
    backend_runtime,
    bridge,
    display,
    document_state,
    execution_lease,
    guarded_operations,
    operation_contracts,
    workspace,
)
from . import assembly_state as state_api
from .assembly_coordinates import NO_SCALAR_COORDINATE, extra_names
from .guarded_evidence import GuardedEvidence
from .unit_input import normalize_unit_input

_ENUM_CACHE = {}
JOINT_KINDS = [
    ("fixed", "Fixed", "Rigid relation; no motion coordinate"),
    ("revolute", "Revolute", "Right-hand rotation about mate local +Z"),
    ("slider", "Slider", "Translation along mate local +Z"),
    ("cylindrical", "Cylindrical", "Independent translation and rotation along mate local +Z"),
    ("planar", "Planar", "Two translations in mate XY and rotation about mate Z"),
    ("spherical", "Spherical / Ball", "Fixed center with independent XYZ Euler rotations"),
]


def state(context):
    return context.scene.mechanical_cad_assembly


def assembly(context):
    return state_api.read_assembly(state(context))


def working_part(context):
    return document_state._read_document(context.scene.mechanical_cad)


def canonical_working_part(context):
    """Capture authoritative bytes only during an explicit operation, never draw.

    Canonical defaults/order do not mutate the editor's raw JSON. Bind both
    documents and the original native scene/window across the extra boundary.
    """
    # Capture/update must reject unsupported sources before acquiring native work.
    document = working_part(context)
    operation_contracts.result_version_for(document, action="canonical_snapshot")
    token = execution_lease.try_acquire()
    if token is None:
        raise bridge.BridgeError(execution_lease.BUSY_MESSAGE)
    try:
        scene = context.scene
        scene_id = scene.as_pointer()
        window_id = context.window.as_pointer() if context.window else 0
        raw = scene.mechanical_cad.document_json
        document = bridge.parse_document_json(raw)
        owner_id = scene.mechanical_cad.owner_id
        view_layer = context.view_layer
        assembly_raw = scene.mechanical_cad_assembly.document_json
        selection = backend_runtime.capture(context)
        owner_token = object()
        with execution_lease.synchronous(token):
            evidence = guarded_operations.canonical_snapshot_guarded(
                document,
                selection=selection,
                owner_token=owner_token,
                current_selection=lambda: backend_runtime.capture(context),
            )

        def assert_capture():
            if (
                context.scene.as_pointer() != scene_id
                or (context.window.as_pointer() if context.window else 0) != window_id
                or context.view_layer != view_layer
                or scene.mechanical_cad.owner_id != owner_id
                or scene.mechanical_cad.document_json != raw
                or scene.mechanical_cad_assembly.document_json != assembly_raw
            ):
                raise bridge.BridgeError(
                    "The scene, window, working Part or assembly changed during snapshot capture. Retry."
                )

        assert_capture()
        if type(evidence) is not GuardedEvidence:
            raise bridge.BridgeError("Canonical capture requires guarded snapshot evidence.")
        if json.dumps(evidence.operation_request().get("document"), sort_keys=True) != json.dumps(
            document,
            sort_keys=True,
        ):
            raise bridge.BridgeError("Canonical capture belongs to a different working Part.")
        current = backend_runtime.assert_current(selection, context)
        receipt = evidence.publication.consume(
            current,
            owner_token=owner_token,
            expected_action="canonical_snapshot",
            expected_result_version=None,
            require_success=True,
        )
        backend_runtime.assert_current(selection, context)
        assert_capture()
        return receipt["canonical_document"]
    finally:
        execution_lease.release(token)


def choices(rows):
    values = tuple((r["id"], r.get("name", r["id"]), r["id"]) for r in rows)
    return _ENUM_CACHE.setdefault(values, list(values))


def rows(context, key):
    try:
        return assembly(context)[key] if context else []
    except (AttributeError, bridge.BridgeError):
        return []


def part_choices(self, context):
    return choices(rows(context, "parts"))


def support_face_choices(self, context):
    """Offer only stable planar faces from current accepted exact-source evidence."""
    try:
        response = state_api.current_display_response(context)
        part = next(p for p in response["result"]["parts"] if p["id"] == self.part_id)
        faces = [
            {"id": face["id"], "name": face["id"]}
            for face in part["topology"]
            if face.get("provenance", {}).get("semantic_status") == "stable"
            and face.get("signature", {}).get("surface") == "plane"
        ]
        return choices(faces) or [("", "No stable planar faces", "Replay a supported Part")]
    except (AttributeError, KeyError, StopIteration, bridge.BridgeError):
        return [("", "Replay Assembly first", "Current exact-source evidence is required")]


def instance_choices(self, context):
    return choices(rows(context, "instances"))


def joint_choices(self, context):
    return choices([r for r in rows(context, "joints") if r["kind"] != "fixed"])


def sample_coordinate_choices(self, context):
    result = []
    for joint in rows(context, "joints"):
        if joint["kind"] not in NO_SCALAR_COORDINATE and joint.get("coordinate") is not None:
            result.append(
                {
                    "id": joint["id"],
                    "name": joint["name"]
                    + (" · translation Z" if joint["kind"] == "cylindrical" else ""),
                }
            )
        for field in extra_names(joint["kind"]):
            result.append(
                {
                    "id": joint["id"] + ":" + field,
                    "name": joint["name"]
                    + " · "
                    + field.replace("_", " ")
                    + (" Z" if field == "rotation" else ""),
                }
            )
    return choices(result)


def frame_choices(context, part_id):
    part = next((p for p in rows(context, "parts") if p["id"] == part_id), {})
    return choices(part.get("mate_frames", []))


def parent_frames(self, context):
    parent = next((i for i in rows(context, "instances") if i["id"] == self.parent), {})
    return frame_choices(context, parent.get("part_id"))


def child_frames(self, context):
    if self.use_working_part:
        try:
            source = working_part(context)
            existing = next(
                (
                    p
                    for p in rows(context, "parts")
                    if p["source_document_id"] == source["id"]
                    and p["output_feature_id"] == source["active_feature"]
                ),
                None,
            )
            if existing:
                return choices(existing["mate_frames"])
        except (AttributeError, bridge.BridgeError):
            pass
        return [("origin", "Part origin", "Literal origin of the captured working Part")]
    return frame_choices(context, self.part_id)


def editable_frames(self, context):
    return frame_choices(context, self.part_id)


def number(text, dimension="scalar"):
    result = float(normalize_unit_input(text, dimension))
    if not math.isfinite(result):
        raise bridge.BridgeError("Enter a finite number; arithmetic expressions are not supported.")
    return result


def vector(text, size, dimension="scalar"):
    values = [number(v.strip(), dimension) for v in text.split(",")]
    if len(values) != size:
        raise bridge.BridgeError(f"Enter exactly {size} comma-separated numbers.")
    return values


def unit_value(text, kind):
    dimension = (
        "angle"
        if kind == "revolute"
        else "length"
        if kind in {"slider", "cylindrical"}
        else "scalar"
    )
    value = number(text, dimension)
    return math.radians(value) if kind == "revolute" else value


def unit_text(value, kind):
    return repr(math.degrees(value) if kind == "revolute" else value)


def quaternion_from_degrees(text):
    x, y, z = [math.radians(v) / 2 for v in vector(text, 3, "angle")]
    cx, cy, cz, sx, sy, sz = (
        math.cos(x),
        math.cos(y),
        math.cos(z),
        math.sin(x),
        math.sin(y),
        math.sin(z),
    )
    return [
        cx * cy * cz + sx * sy * sz,
        sx * cy * cz - cx * sy * sz,
        cx * sy * cz + sx * cy * sz,
        cx * cy * sz - sx * sy * cz,
    ]


def degrees_from_quaternion(value):
    w, x, y, z = value
    angles = [
        math.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y)),
        math.asin(max(-1.0, min(1.0, 2 * (w * y - z * x)))),
        math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z)),
    ]
    return ", ".join(repr(math.degrees(v)) for v in angles)


def focus_assembly(context, *, whole_scene=False):
    if bpy.app.background:
        return False
    return display._focus_objects(
        context,
        assembly_display.owned_objects(context.scene, state(context).owner_id),
        whole_scene=whole_scene,
    )


def activate_assembly_workspace(context):
    if bpy.app.background:
        return
    try:
        if workspace.get_role(context) == "ASSEMBLY":
            focus_assembly(context)
        else:
            workspace.request_workspace(context, "ASSEMBLY", on_ready=focus_assembly)
    except (RuntimeError, AttributeError) as exc:
        state(context).last_action_error = "Assembly accepted; use Focus Assembly: " + str(exc)


def reject(operator, context, exc):
    state(context).last_action_error = str(exc)
    operator.report({"ERROR"}, str(exc)[:1000])
    return {"CANCELLED"}


def help_lines(layout, operator, lines):
    layout.prop(operator, "show_help", text="Explain this operation", icon="QUESTION")
    if operator.show_help:
        box = layout.box()
        for line in lines:
            box.label(text=line)


def joint_help_lines(kind):
    lines = [
        "A rooted tree: each child has one parent. No closed-loop solver.",
        "Axes belong to the parent mate frame, not the screen or world.",
        "Translations accept mm/cm/m/in/ft; angles accept deg/rad (saved radians).",
        "Each axis has independent limits; lower must be below upper.",
        "Out-of-limit values reject the edit; nothing is silently clamped.",
    ]
    lines += {
        "fixed": ["Fixed locks the two named mate frames together."],
        "revolute": ["Revolute rotates right-handed about mate-local +Z."],
        "slider": ["Slider translates along mate-local +Z."],
        "cylindrical": ["Cylindrical slides along +Z and rotates about +Z independently."],
        "planar": [
            "Planar moves along mate X and Y, and rotates about +Z.",
            "Relative Z stays zero: the mate planes remain coincident.",
        ],
        "spherical": [
            "Ball fixes the mate centers and rotates X, then Y, then Z.",
            "Limits bound Euler angle components, not a cone angle.",
            "Euler angles have singularities; this is forward positioning.",
        ],
    }.get(kind, [])
    lines += [
        "Sample checks one chosen axis while other saved axes stay fixed.",
        "Only listed poses are checked, not continuous collision safety.",
        "Apply replays the assembly; Cancel preserves your saved model.",
    ]
    return lines


def joint_fields(layout, operator, kind):
    if kind == "fixed":
        layout.label(text="Fixed: no coordinate or limits.")
        return
    if kind not in NO_SCALAR_COORDINATE:
        unit = "degrees" if kind == "revolute" else "mm"
        layout.prop(operator, "coordinate", text=f"Coordinate ({unit})")
        layout.prop(operator, "use_limits")
        if operator.use_limits:
            layout.prop(operator, "lower", text=f"Lower ({unit})")
            layout.prop(operator, "upper", text=f"Upper ({unit})")
    for field in extra_names(kind):
        unit = "mm" if field.startswith("translation") else "degrees"
        label = field.replace("_", " ").title() + (" Z" if field == "rotation" else "")
        layout.prop(operator, field, text=f"{label} ({unit})")
        layout.prop(operator, "use_" + field + "_limits", text=f"{label} limits")
        if getattr(operator, "use_" + field + "_limits"):
            layout.prop(operator, field + "_lower", text=f"Lower ({unit})")
            layout.prop(operator, field + "_upper", text=f"Upper ({unit})")
    if kind == "planar":
        layout.label(text="Translate in mate XY; rotate about mate +Z.")
    if kind == "spherical":
        layout.label(text="Ball joint: fixed center; Euler X then Y then Z.")
        layout.label(text="Angular component limits, not a cone-angle limit.")


def extra_joint_arguments(operator, kind):
    result = {}
    for field in extra_names(kind):
        unit_kind = "slider" if field.startswith("translation") else "revolute"
        value = unit_value(getattr(operator, field), unit_kind)
        bounds = (
            [
                unit_value(getattr(operator, field + "_lower"), unit_kind),
                unit_value(getattr(operator, field + "_upper"), unit_kind),
            ]
            if getattr(operator, "use_" + field + "_limits")
            else None
        )
        # Reopening and accepting unchanged text must not perturb saved radians.
        original = getattr(operator, "_original_axes", {}).get(field)
        if original:
            texts, saved, saved_limits = original
            if getattr(operator, field) == texts[0]:
                value = saved
            if bounds is not None and saved_limits is not None:
                for index, suffix in enumerate(("_lower", "_upper")):
                    if getattr(operator, field + suffix) == texts[index + 1]:
                        bounds[index] = saved_limits[index]
        result[field] = (value, bounds)
    return result


def load_extra_joint_fields(operator, joint):
    operator._original_axes = {}
    for field in extra_names(joint["kind"]):
        unit_kind = "slider" if field.startswith("translation") else "revolute"
        setattr(operator, field, unit_text(joint[field], unit_kind))
        limits = joint[field + "_limits"]
        setattr(operator, "use_" + field + "_limits", limits is not None)
        if limits is not None:
            setattr(operator, field + "_lower", unit_text(limits[0], unit_kind))
            setattr(operator, field + "_upper", unit_text(limits[1], unit_kind))
        operator._original_axes[field] = (
            [getattr(operator, field + suffix) for suffix in ("", "_lower", "_upper")],
            joint[field],
            limits,
        )


class AssemblyEdit:
    _expected = None
    _working_expected = None
    _scene_pointer = None
    _window_pointer = None

    def capture_dialog(self, context):
        state_api.begin_interaction()
        self._expected = state(context).document_json
        self._working_expected = context.scene.mechanical_cad.document_json
        self._scene_pointer = context.scene.as_pointer()
        self._window_pointer = context.window.as_pointer() if context.window else 0

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and bool(state(context).document_json)

    def invoke(self, context, event):
        self.capture_dialog(context)
        return context.window_manager.invoke_props_dialog(self, width=520, confirm_text="Apply")

    def cancel(self, context):
        pass  # Dialog fields are local; Cancel has no canonical or display side effects.

    def apply(self, context, candidate):
        self.require_same_working_part(context)
        state_api.commit_candidate(context, candidate, expected_json=self._expected)
        try:
            focus_assembly(context)
        except (RuntimeError, AttributeError) as exc:
            state(context).last_action_error = "Assembly accepted; use Focus Assembly: " + str(exc)
        return {"FINISHED"}

    def require_same_working_part(self, context):
        window = context.window.as_pointer() if context.window else 0
        if self._scene_pointer is not None and (
            context.scene.as_pointer() != self._scene_pointer or window != self._window_pointer
        ):
            raise bridge.BridgeError(
                "The scene or window changed while the dialog was open. Reopen it."
            )
        if (
            self._working_expected is not None
            and self._working_expected != context.scene.mechanical_cad.document_json
        ):
            raise bridge.BridgeError("The working Part changed. Reopen this dialog.")
