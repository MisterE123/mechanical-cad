"""Registered New/Edit/Resume, palette capabilities and modal input dispatch.

Native-headless adapter evidence only; pointer/gizmo usability remains a GUI gate.
"""

import json
import os
import runpy
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
os.environ["MCAD_ROOT"] = str(ROOT)
os.environ.setdefault("MCAD_PYTHON", str(ROOT / ".venv/bin/python"))
sys.path.insert(0, str(ROOT / "blender_addon"))
import mechanical_cad_blender as addon  # noqa: E402
from mechanical_cad_blender import (  # noqa: E402
    document_state,
    draft_dispatch,
    execution_lease,
    general_authoring,
    general_viewport,
    registration,
    sketch_pending,
    sketch_session,
    viewport_sketch,
    workspace,
    workspace_ui,
)
from mechanical_cad_blender.general_session import GeneralSession  # noqa: E402
from mechanical_cad_blender.general_sketch_draft import (  # noqa: E402
    AddCircle,
    AddRelation,
    GeneralSketchDraft,
    PointSeed,
)
from mechanical_cad_blender.sketch_draft import RectangleDraft  # noqa: E402

checks = []


def check(value, label):
    assert value, label
    checks.append(label)


def wait(owner, context):
    deadline = time.monotonic() + 20
    while owner.pending is not None and time.monotonic() < deadline:
        owner.tick(context)
        time.sleep(0.01)
    check(owner.pending is None and not owner.error, "Real general edit check completes")


def event(kind, value="PRESS", **kwargs):
    return SimpleNamespace(
        **{
            "type": kind,
            "value": value,
            "unicode": "",
            "mouse_x": 100,
            "mouse_y": 100,
            "ctrl": False,
            "shift": False,
            "alt": False,
            "is_repeat": False,
            **kwargs,
        }
    )


def expect_cancel(callback, label):
    try:
        result = callback()
    except RuntimeError:
        result = {"CANCELLED"}  # Blender raises for an ERROR operator report.
    check(result == {"CANCELLED"}, label)


def enter(context, role, on_ready=None):
    check(role == "SKETCH", "Entry uses the existing staged Sketch workspace seam")
    if on_ready:
        on_ready(context)
    return True


check(not hasattr(bpy.types.Scene, "mechanical_cad"), "Normal import does not register scene RNA")
check(not execution_lease.is_busy(), "Normal import starts no native execution")
check("OCP" not in sys.modules and "slvs" not in sys.modules, "No native kernel/solver in Blender")
# A failure halfway through the expanded registry must unwind all prior classes.
original_register = bpy.utils.register_class


def fail_general(cls):
    if cls is general_viewport.MCAD_OT_general_tool:
        raise RuntimeError("injected general registration failure")
    return original_register(cls)


with patch.object(bpy.utils, "register_class", side_effect=fail_general):
    try:
        addon.register()
    except RuntimeError as exc:
        check("injected" in str(exc), "Atomic registration exposes original failure")
    else:
        raise AssertionError("Injected registration failure was not reached")
check(not hasattr(bpy.types.Scene, "mechanical_cad"), "Failed registration removes scene RNA")
check(
    not any(cls.is_registered for cls in registration.CLASSES),
    "Failed registration removes classes",
)
addon.register()
addon.register()
check(
    all(cls.is_registered for cls in general_viewport.CLASSES),
    "Normal registration owns general classes once",
)
check(
    len(registration.CLASSES) == len(set(registration.CLASSES)), "Class registry has no duplicates"
)
for handlers, callback in registration._HISTORY_HANDLERS:
    check(
        handlers.count(callback) == 1, "Repeated registration installs each lifecycle handler once"
    )

window = bpy.context.window
area = next(area for area in window.screen.areas if area.type == "VIEW_3D")
region = next(region for region in area.regions if region.type == "WINDOW")
window.workspace[workspace.OWNER_KEY] = workspace.OWNER
window.workspace[workspace.ROLE_KEY] = "SKETCH"
with bpy.context.temp_override(window=window, area=area, region=region):
    context = bpy.context
    scene = context.scene
    document_state._populate_document(
        scene,
        {
            "schema_version": 1,
            "id": "dispatch_test",
            "name": "Dispatch test",
            "units": "mm",
            "parameters": {"radius": 5},
            "features": [],
            "active_feature": None,
        },
    )
    state = scene.mechanical_cad
    base = state.document_json
    with patch.object(workspace, "request_workspace", side_effect=enter):
        check(bpy.ops.mcad.new_viewport_sketch() == {"FINISHED"}, "Registered New Sketch succeeds")
        owner = sketch_session.active_session()
        check(type(owner) is GeneralSession, "New Sketch opens the real general owner")
        check(
            workspace_ui.palette_actions(context)
            == (
                "SELECT",
                "POINTS",
                "LINE",
                "CIRCLE",
                "DIMENSION",
                "ARC",
                "REVERSE",
                "USE_POINT",
                "SKETCH_CHECK",
                "FINISH",
                "CANCEL",
            ),
            "Left palette exposes bounded general tools",
        )
        check(
            all(
                workspace_ui.available(context, action)
                for action in (
                    "SELECT",
                    "POINTS",
                    "LINE",
                    "CIRCLE",
                    "DIMENSION",
                    "ARC",
                    "SKETCH_CHECK",
                    "CANCEL",
                )
            ),
            "Idle general capabilities are available",
        )
        check(
            not workspace_ui.available(context, "DIMENSIONS"),
            "Rectangle dimensions never reach general owner",
        )
        check(
            not workspace_ui.available(context, "FINISH"), "Unverified general draft cannot Finish"
        )
        check(not bpy.ops.mcad.new_viewport_sketch.poll(), "Active owner blocks a second New")
        check(
            bpy.ops.mcad.workspace_action(action="CIRCLE") == {"FINISHED"},
            "Native left action dispatches Circle",
        )
        check(owner.draft.tool == "Circle", "Palette tool property reaches the owner")
        modal = SimpleNamespace(owner=owner)
        with patch.object(workspace_ui, "is_palette_event", return_value=True):
            with patch.object(general_viewport, "_click") as clicked:
                result = general_viewport.MCAD_OT_general_sketch.modal(
                    modal, context, event("LEFTMOUSE")
                )
                check(
                    result == {"PASS_THROUGH"} and not clicked.called,
                    "Native palette click never creates sketch geometry",
                )
        check(
            general_viewport.MCAD_OT_general_sketch.modal(modal, context, event("MIDDLEMOUSE"))
            == {"PASS_THROUGH"},
            "Native pointer navigation passes through",
        )
        check(
            general_viewport.MCAD_OT_general_sketch.modal(
                modal, context, event("MIDDLEMOUSE", "RELEASE")
            )
            == {"PASS_THROUGH"},
            "Navigation release passes through",
        )
        owner.discard()
        check(
            bpy.ops.mcad.new_rectangle_sketch() == {"FINISHED"},
            "Explicit Rectangle shortcut succeeds",
        )
        owner = sketch_session.active_session()
        check(
            type(owner) is viewport_sketch.RectangleSession,
            "Rectangle shortcut keeps the legacy owner",
        )
        check(
            workspace_ui.palette_actions(context) == ("FINISH", "CANCEL"),
            "Rectangle creation has no general tools",
        )
        owner.draft.first_point((0, 0))
        owner.draft.second_point((10, 20))
        check(
            "DIMENSIONS" in workspace_ui.palette_actions(context),
            "Rectangle dimension capability stays intact",
        )
        rectangle_document = owner.draft.candidate()
        owner.discard()

        # Supported saved kinds restore through exactly their named codec/version.
        rectangle = RectangleDraft(base)
        rectangle.first_point((0, 0))
        rectangle.second_point((4, 7))
        commands = GeneralSketchDraft(base)
        circle_id = commands.execute(AddCircle(PointSeed(0, 0), 5)).entity_ids[-1]
        relation = commands.execute(AddRelation("radius", (circle_id,), value="radius"))
        general_document = commands.candidate()
        commands.begin_edit(relation.constraint_id)
        raw = "  radius / 0 + Ω  "
        commands.update_edit(raw)
        wrapper = general_authoring.GeneralSketchAuthoringState(commands)
        wrapper.select_tool("Dimension")
        wrapper.place_annotation(relation.constraint_id, (9, 7))
        for draft, kind, version, owner_type in (
            (rectangle, draft_dispatch.RECTANGLE, 1, viewport_sketch.RectangleSession),
            (commands, draft_dispatch.GENERAL, 1, GeneralSession),
            (wrapper, draft_dispatch.GENERAL, 2, GeneralSession),
        ):
            saved = draft_dispatch.dumps(draft)
            state.sketch_draft_json = saved
            status = sketch_session.suspended_draft(context)
            check(
                status["compatible"]
                and status["editor_available"]
                and status["schema_version"] == version,
                f"{kind} v{version} has its exact available editor",
            )
            check(
                bpy.ops.mcad.resume_sketch() == {"FINISHED"},
                f"Registered Resume dispatches {kind} v{version}",
            )
            owner = sketch_session.active_session()
            check(type(owner) is owner_type, "Resume selects the matching owner type")
            check(state.sketch_draft_json == saved, "Resume does not silently rewrite saved bytes")
            if owner_type is GeneralSession:
                check(
                    owner.commands.pending_edit.raw_text == raw,
                    "Resume retains exact invalid Unicode input",
                )
                check(
                    owner.pending is None and owner.input_controller is None,
                    "Resume never starts native work or captures retained input",
                )
                check(
                    not workspace_ui.available(context, "LINE")
                    and not workspace_ui.available(context, "SKETCH_CHECK"),
                    "Unfinished input disables incompatible tools",
                )
                check(
                    bpy.ops.mcad.general_tool(tool="Reopen") == {"FINISHED"},
                    "Reopen input requires an explicit action",
                )
                general_viewport._route_field(owner, context, event("A", unicode="a"))
                expected = raw + "a"
                check(
                    owner.commands.pending_edit.raw_text == expected, "Reopened field owns typing"
                )
                with patch.object(workspace_ui, "is_palette_event", return_value=True):
                    check(
                        general_viewport.MCAD_OT_general_sketch.modal(
                            SimpleNamespace(owner=owner), context, event("LEFTMOUSE")
                        )
                        == {"RUNNING_MODAL"},
                        "Field consumes first outside palette click",
                    )
                    check(
                        owner.input_controller.closed
                        and owner.commands.pending_edit.raw_text == expected,
                        "Outside click retains exact raw input",
                    )
                    check(
                        general_viewport.MCAD_OT_general_sketch.modal(
                            SimpleNamespace(owner=owner), context, event("LEFTMOUSE", "RELEASE")
                        )
                        == {"RUNNING_MODAL"},
                        "Outside-click release cannot leak to native palette",
                    )
                check(not owner.input_token, "Outside click revokes acceptance token")
            owner.discard()

        for saved in (
            '{"kind":"future_sketch","schema_version":1,"raw":"keep me"}',
            '{"kind":"general_sketch_ui_draft","schema_version":99,"raw":"keep me"}',
            '{"kind":"rectangle_ui_draft","schema_version":99,"raw":"keep me"}',
            '{"not valid JSON',
        ):
            state.sketch_draft_json = saved
            expect_cancel(
                lambda: bpy.ops.mcad.resume_sketch(), "Unknown/corrupt Resume fails closed"
            )
            check(
                state.sketch_draft_json == saved and sketch_session.active_session() is None,
                "Unavailable draft raw bytes remain untouched",
            )
        state.sketch_draft_json = ""

        saved = draft_dispatch.dumps(wrapper)
        state.sketch_draft_json = saved
        state.document_json = base + " "
        expect_cancel(lambda: bpy.ops.mcad.resume_sketch(), "Stale saved base refuses Resume")
        check(state.sketch_draft_json == saved, "Stale Resume preserves exact slot text")
        state.document_json = base
        bpy.utils.unregister_class(general_viewport.MCAD_OT_general_sketch)
        try:
            check(
                not sketch_session.suspended_draft(context)["editor_available"],
                "Missing exact editor is visible in saved status",
            )
            expect_cancel(
                lambda: bpy.ops.mcad.resume_sketch(),
                "Missing general editor never falls back to rectangle",
            )
            check(state.sketch_draft_json == saved, "Missing-editor refusal retains raw snapshot")
        finally:
            bpy.utils.register_class(general_viewport.MCAD_OT_general_sketch)
        expect_cancel(
            lambda: bpy.ops.mcad.general_sketch(), "Direct new entry cannot replace a saved draft"
        )
        check(state.sketch_draft_json == saved, "Direct-entry refusal preserves saved input")
        state.sketch_draft_json = ""
        with patch.object(workspace, "request_workspace") as staged:
            check(
                bpy.ops.mcad.new_viewport_sketch() == {"FINISHED"},
                "New entry can wait for native workspace readiness",
            )
            callback = staged.call_args.kwargs["on_ready"]
            state.document_json = base + " "
            try:
                callback(context)
            except RuntimeError as exc:
                check(
                    "changed" in str(exc), "Staged entry rejects an intervening exact-base change"
                )
            else:
                raise AssertionError("Staged callback accepted a changed document")
            check(sketch_session.active_session() is None, "Stale staged entry starts no owner")
            state.document_json = base

        # Edit validates canonical shape before dispatch; no kind-based fallback.
        for document, owner_type in (
            (rectangle_document, viewport_sketch.RectangleSession),
            (general_document, GeneralSession),
        ):
            document_state._populate_document(scene, document)
            state.feature_index = 0
            exact = state.document_json
            check(
                bpy.ops.mcad.edit_viewport_sketch() == {"FINISHED"},
                "Registered Edit opens supported canonical sketch",
            )
            owner = sketch_session.active_session()
            check(type(owner) is owner_type, "Edit selects the supported matching editor")
            if owner_type is GeneralSession:
                check(
                    "CANCEL_CHECK" in workspace_ui.palette_actions(context),
                    "Running real check exposes Cancel Check",
                )
                check(
                    not workspace_ui.available(context, "LINE"),
                    "Running check disables structural tools",
                )
                wait(owner, context)
                check(
                    workspace_ui.available(context, "FINISH"),
                    "Real current solve enables shared Finish",
                )
                general_viewport._open_field(owner, relation.constraint_id, (100, 100))
                owner.message = "Sketch checked. Finish saves editable geometry."
                status_layout = MagicMock()
                workspace_ui._draw_general_status(status_layout, context, owner)
                status_text = " ".join(
                    call.kwargs.get("text", "") for call in status_layout.label.call_args_list
                )
                check(
                    "Current input is unverified" in status_text
                    and "Enter checks and accepts" in status_text,
                    "Pending raw input has explicit unchecked status",
                )
                check(
                    "Sketch checked" not in status_text and "DoF unverified" in status_text,
                    "Prior successful check cannot qualify pending input",
                )
                owner.error = "Division by zero; correct the pending expression."
                status_layout.reset_mock()
                workspace_ui._draw_general_status(status_layout, context, owner)
                error_text = " ".join(
                    call.kwargs.get("text", "") for call in status_layout.label.call_args_list
                )
                check(owner.error in error_text, "Specific input correction remains visible")
                owner.error = ""
                check(
                    general_viewport.MCAD_OT_general_sketch.modal(
                        SimpleNamespace(owner=owner), context, event("WHEELUPMOUSE")
                    )
                    == {"PASS_THROUGH"},
                    "Pointer navigation remains usable with text focus",
                )
                check(not owner.input_controller.closed, "Navigation preserves focused raw field")
                check(
                    general_viewport.MCAD_OT_general_sketch.modal(
                        SimpleNamespace(owner=owner), context, event("NUMPAD_1", unicode="1")
                    )
                    == {"RUNNING_MODAL"},
                    "Focused numeric keys cannot trigger native view shortcuts",
                )
            check(state.document_json == exact, "Editing leaves canonical source unchanged")
            owner.discard()

        malformed = json.loads(json.dumps(general_document))
        malformed["features"][0]["sketch"]["arcs"] = []
        state.document_json = json.dumps(malformed)
        expect_cancel(
            lambda: bpy.ops.mcad.edit_viewport_sketch(),
            "Unsupported canonical sketch fields are not silently redirected",
        )
        check(
            state.document_json == json.dumps(malformed)
            and sketch_session.active_session() is None,
            "Unsupported canonical source stays unchanged",
        )
        state.document_json = base
        token = execution_lease.try_acquire()
        try:
            for operator in (
                bpy.ops.mcad.new_viewport_sketch,
                bpy.ops.mcad.new_rectangle_sketch,
                bpy.ops.mcad.edit_viewport_sketch,
                bpy.ops.mcad.general_sketch,
            ):
                check(not operator.poll(), "Shared busy lease blocks sketch entry")
            state.sketch_draft_json = draft_dispatch.dumps(wrapper)
            check(not bpy.ops.mcad.resume_sketch.poll(), "Shared busy lease blocks Resume")
            check(sketch_session.active_session() is None, "Busy entry cannot queue a new owner")
        finally:
            execution_lease.release(token)
            state.sketch_draft_json = ""

        # Re-running the QA launcher relies only on normal idempotent registration.
        script = runpy.run_path(str(ROOT / "scripts/blender_general_viewport_dev.py"))
        for callback in (script["launch"], script["receipt"]):
            if bpy.app.timers.is_registered(callback):
                bpy.app.timers.unregister(callback)
        script["launch"]()
        check(
            type(sketch_session.active_session()) is GeneralSession,
            "QA launcher uses the registered production general viewport route",
        )
        sketch_session.active_session().discard()

check(
    not execution_lease.is_busy() and not sketch_pending.reap(),
    "Dispatch checks leave no native lease/child",
)
addon.unregister()
addon.unregister()
check(
    not any(cls.is_registered for cls in registration.CLASSES),
    "Repeated unregister removes all production classes",
)
check(not hasattr(bpy.types.Scene, "mechanical_cad"), "Unregister removes scene RNA")
print("GENERAL_DISPATCH_SMOKE_OK", len(checks))
