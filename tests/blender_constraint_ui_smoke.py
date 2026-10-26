"""Native-headless constraint operators and exact confirmation/selection seams.

Popup routing is observed through a test window-manager adapter; no GUI visual,
focus, mouse, or user-scale acceptance is claimed. Commands run the real pinned
native sidecar. Run Blender 5.2.2 with --background --python-exit-code 1.
"""

import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
os.environ["MCAD_ROOT"] = str(ROOT)
os.environ.setdefault("MCAD_PYTHON", str(ROOT / ".venv/bin/python"))
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    constraint_actions,
    constraint_ui,
    document_state,
    execution_lease,
    general_session,
    register,
    sketch_session,
    unregister,
)
from mechanical_cad_blender.general_authoring import GeneralSketchAuthoringState  # noqa: E402
from mechanical_cad_blender.general_sketch_commands import (  # noqa: E402
    AddArc,
    AddCircle,
    AddLine,
    AddRelation,
    PointRef,
    PointSeed,
)
from mechanical_cad_blender.general_sketch_draft import GeneralSketchDraft  # noqa: E402

checks = []


def check(value, message):
    assert value, message
    checks.append(message)


def wait(owner, context):
    deadline = time.monotonic() + 30
    while owner.pending is not None and time.monotonic() < deadline:
        owner.tick(context)
        time.sleep(0.01)
    check(owner.pending is None, "Native check completes")
    check(not execution_lease.is_busy(), "Native check releases the existing execution lease")


def snapshot(owner):
    return {
        "draft": owner.draft,
        "commands": owner.commands,
        "checkpoint": json.dumps(owner.commands.checkpoint_payload(), sort_keys=True),
        "saved": owner.stored_snapshot,
        "request": owner.evidence_request,
        "response": owner.evidence_response,
        "solution": owner.commands._solution,
        "diagnostics": owner.current_diagnostics,
        "ui": owner.draft.ui_payload(),
    }


def unchanged(owner, before, *, ui=False):
    check(owner.commands is before["commands"], "UI retains the exact live command object")
    check(
        json.dumps(owner.commands.checkpoint_payload(), sort_keys=True) == before["checkpoint"],
        "UI preserves exact command revisions, seeds, ID ledger and local history",
    )
    check(
        owner.evidence_request is before["request"]
        and owner.evidence_response is before["response"]
        and owner.commands._solution is before["solution"],
        "UI preserves exact accepted solve evidence and authority",
    )
    check(
        owner.current_diagnostics is before["diagnostics"],
        "UI preserves exact diagnostics separately from solve evidence",
    )
    if ui:
        check(
            owner.draft is before["draft"] and owner.draft.ui_payload() == before["ui"],
            "Failure/cancel restores the original UI wrapper and selection",
        )
        check(
            owner.stored_snapshot == before["saved"]
            and owner.scene.mechanical_cad.sketch_draft_json == before["saved"],
            "Failure/cancel preserves saved checkpoint ownership and bytes",
        )


def operator(action):
    result = SimpleNamespace(action=action, reports=[])
    result.report = lambda level, text: result.reports.append((level, text))
    result.execute = lambda context: constraint_ui.MCAD_OT_constraint_action.execute(
        result, context
    )
    return result


def popup_context(context):
    calls = []
    manager = SimpleNamespace(
        invoke_props_dialog=lambda instance, **kwargs: (
            calls.append((instance, kwargs)) or {"RUNNING_MODAL"}
        )
    )
    return SimpleNamespace(
        window=context.window,
        scene=context.scene,
        area=context.area,
        workspace=context.workspace,
        view_layer=context.view_layer,
        window_manager=manager,
    ), calls


def invoke(action, context):
    instance = operator(action)
    proxy, calls = popup_context(context)
    check(
        constraint_ui.MCAD_OT_constraint_action.invoke(instance, proxy, None) == {"RUNNING_MODAL"},
        "Native invoke path requests an explicit confirmation popup",
    )
    check(
        len(calls) == 1 and calls[0][0] is instance and calls[0][1]["confirm_text"] == "Apply",
        "Popup is attached to the same prepared operator instance",
    )
    return instance


class Layout:
    """Record UI labels/operators without substituting any command behavior."""

    def __init__(self, items=None):
        self.items = [] if items is None else items
        self.enabled = True
        self.operator_context = "INVOKE_DEFAULT"

    def row(self, **kwargs):
        return Layout(self.items)

    column = row
    box = row

    def label(self, **kwargs):
        self.items.append(("label", kwargs.get("text", "")))

    def operator(self, name, **kwargs):
        result = SimpleNamespace(name=name, **kwargs)
        self.items.append(("operator", result))
        return result


register()
check(
    all(cls.is_registered for cls in constraint_ui.CLASSES),
    "Normal add-on registration includes the inspector operators",
)
window = bpy.context.window
area = next(area for area in window.screen.areas if area.type == "VIEW_3D")
region = next(region for region in area.regions if region.type == "WINDOW")
with bpy.context.temp_override(window=window, area=area, region=region):
    context = bpy.context
    document_state._populate_document(
        context.scene,
        {
            "schema_version": 1,
            "id": "constraint_ui_native",
            "name": "Constraint inspector test",
            "units": "mm",
            "parameters": {},
            "features": [],
            "active_feature": None,
        },
    )
    canonical = context.scene.mechanical_cad.document_json
    owner = general_session.GeneralSession(context)
    owner.start()
    first, second, line = owner.execute(
        context, AddLine(PointSeed(3, 4), PointSeed(13, 6))
    ).entity_ids
    wait(owner, context)
    check(owner.commands.has_current_solution, "Line has real successful native evidence")
    constraint_ui.select_bindings(owner, (("line", line),), context=context)
    check(
        constraint_ui.action_available(context, "horizontal"),
        "Horizontal is available for one exact line",
    )
    check(
        not constraint_ui.action_available(context, "coincident"),
        "Production Coincident remains unavailable",
    )
    check(
        bpy.ops.mcad.constraint_action("EXEC_DEFAULT", action="horizontal") == {"FINISHED"},
        "Normal native operator applies Horizontal directly",
    )
    wait(owner, context)
    horizontal = next(
        item["id"] for item in owner.commands.sketch["constraints"] if item["kind"] == "horizontal"
    )
    before = snapshot(owner)
    check(
        bpy.ops.mcad.constraint_action("EXEC_DEFAULT", action="horizontal") == {"FINISHED"},
        "Repeated Horizontal inspects its existing exact ID",
    )
    unchanged(owner, before)
    check(
        owner.draft.selection == [{"kind": "constraint", "id": horizontal}],
        "Existing relation becomes the exact inspector selection",
    )
    constraint_ui.select_bindings(owner, (("line", line),), context=context)
    before = snapshot(owner)
    check(
        bpy.ops.mcad.constraint_select(
            "EXEC_DEFAULT",
            kind="point",
            identifier=first,
            source_kind="line",
            source_id=line,
            source_role="START",
        )
        == {"FINISHED"},
        "Explicit Start point resolves endpoint/line picking ambiguity",
    )
    unchanged(owner, before)
    check(
        owner.commands.has_current_solution and owner.can_finish,
        "Point selection retains current solution and Finish qualification",
    )
    invalid = SimpleNamespace(
        kind="point",
        identifier=second,
        source_kind="line",
        source_id=line,
        source_role="START",
        report=lambda *_: None,
    )
    check(
        constraint_ui.MCAD_OT_constraint_select.execute(invalid, context) == {"CANCELLED"},
        "Stale curve-point button cannot silently retarget selection",
    )
    before = snapshot(owner)
    with patch.object(owner, "checkpoint", side_effect=RuntimeError("Injected checkpoint failure")):
        try:
            constraint_ui.select_bindings(owner, (("point", second),), context=context)
        except RuntimeError:
            pass
        else:
            raise AssertionError("Expected failed UI checkpoint")
    unchanged(owner, before, ui=True)
    # The real CAS guard rejects unrelated saved-slot edits before UI mutation.
    external = before["saved"] + " "
    owner.scene.mechanical_cad.sketch_draft_json = external
    try:
        constraint_ui.select_bindings(owner, (("point", second),), context=context)
    except ValueError:
        pass
    else:
        raise AssertionError("Expected external slot conflict")
    check(
        owner.draft is before["draft"] and owner.scene.mechanical_cad.sketch_draft_json == external,
        "External saved-slot conflict is preserved without changing selection",
    )
    owner.scene.mechanical_cad.sketch_draft_json = before["saved"]
    unchanged(owner, before, ui=True)
    wrong_area, _ = popup_context(context)
    wrong_area.area = None
    try:
        constraint_ui.select_bindings(owner, (("point", second),), context=wrong_area)
    except ValueError:
        pass
    else:
        raise AssertionError("Expected original viewport guard")
    unchanged(owner, before, ui=True)
    direct = operator("fix_origin")
    check(
        direct.execute(context) == {"CANCELLED"}, "Direct execute cannot bypass origin confirmation"
    )
    unchanged(owner, before, ui=True)
    cancelled = invoke("fix_origin", context)
    check(
        cancelled._prepared_intent.target == (0, 0)
        and "move" in cancelled._prepared_intent.disclosure,
        "Origin popup discloses exact point, target and possible movement",
    )
    layout = Layout()
    cancelled.layout = layout
    constraint_ui.MCAD_OT_constraint_action.draw(cancelled, context)
    check(
        any("Sketch-plane target" in text for kind, text in layout.items if kind == "label"),
        "Popup renders its prepared target",
    )
    constraint_ui.MCAD_OT_constraint_action.cancel(cancelled, context)
    unchanged(owner, before, ui=True)
    check(
        cancelled.execute(context) == {"CANCELLED"},
        "Cancelled popup grants no later confirmation authority",
    )
    stale = invoke("fix_origin", context)
    original_intent = stale._prepared_intent
    constraint_ui.select_bindings(owner, (("point", second),), context=context)
    changed_selection = snapshot(owner)
    with patch.object(constraint_actions, "apply", wraps=constraint_actions.apply) as applying:
        check(
            stale.execute(context) == {"CANCELLED"},
            "Confirmation rejects a changed target selection",
        )
        check(
            applying.call_args.args[2] is original_intent,
            "Confirmation passes the original frozen intent, never a newly prepared replacement",
        )
    unchanged(owner, changed_selection, ui=True)
    constraint_ui.select_bindings(owner, (("point", first),), context=context)
    confirmed = invoke("fix_origin", context)
    original_intent = confirmed._prepared_intent
    with patch.object(constraint_actions, "apply", wraps=constraint_actions.apply) as applying:
        check(
            confirmed.execute(context) == {"FINISHED"},
            "Confirmed origin action applies through the shared owner",
        )
        check(
            applying.call_args.args[2] is original_intent
            and applying.call_args.kwargs["confirmed"] is True,
            "Confirmed origin retains exact disclosed intent",
        )
    wait(owner, context)
    fixed = next(item for item in owner.commands.sketch["constraints"] if item["kind"] == "fixed")
    check(
        fixed["refs"] == [first] and fixed["target"] == [0, 0],
        "Origin action anchors only the explicitly named point",
    )
    before = snapshot(owner)
    check(
        bpy.ops.mcad.constraint_action("EXEC_DEFAULT", action="fix_here") == {"FINISHED"},
        "Fix on an already fixed point inspects its existing relation",
    )
    unchanged(owner, before)
    check(
        owner.draft.selection == [{"kind": "constraint", "id": fixed["id"]}],
        "Existing fixed target is selected, never overwritten",
    )
    check(
        bpy.ops.mcad.constraint_action("EXEC_DEFAULT", action="remove_relation") == {"FINISHED"},
        "Ordinary release uses native owner command path",
    )
    wait(owner, context)
    layout = Layout()
    constraint_ui.draw_inspector(layout, context, owner)
    check(
        owner.draft.selection == []
        and not any(
            kind == "label" and "Selection binding unavailable" in text
            for kind, text in layout.items
        ),
        "Intentional release clears only its removed selection in the accepted transaction",
    )
    constraint_ui.select_bindings(owner, (("point", first),), context=context)
    check(
        bpy.ops.mcad.constraint_action("EXEC_DEFAULT", action="fix_here") == {"FINISHED"},
        "Fix here uses current validated coordinates without a popup",
    )
    wait(owner, context)
    check(
        bpy.ops.mcad.constraint_history("EXEC_DEFAULT", direction="UNDO") == {"FINISHED"},
        "Visible Undo routes to local sketch history",
    )
    wait(owner, context)
    check(
        not any(item["kind"] == "fixed" for item in owner.commands.sketch["constraints"]),
        "Local Undo removes only its last anchor action",
    )
    check(
        bpy.ops.mcad.constraint_history("EXEC_DEFAULT", direction="REDO") == {"FINISHED"},
        "Visible Redo routes to the same local journal",
    )
    wait(owner, context)
    # Native failure candidates are inspectable but do not grant ordinary release.
    center, circle = owner.execute(context, AddCircle(PointSeed(20, 20), 5)).entity_ids
    wait(owner, context)
    owner.execute(context, AddRelation("radius", (circle,), value=5))
    wait(owner, context)
    conflicting = owner.execute(context, AddRelation("radius", (circle,), value=7)).constraint_id
    pending = snapshot(owner)
    check(
        constraint_ui.MCAD_OT_constraint_select.execute(
            SimpleNamespace(
                kind="constraint",
                identifier=horizontal,
                source_kind="NONE",
                source_id="",
                source_role="NONE",
                report=lambda *_: None,
            ),
            context,
        )
        == {"CANCELLED"},
        "Selection is guarded while a native check is pending",
    )
    check(owner.draft is pending["draft"], "Pending guard leaves UI wrapper unchanged")
    wait(owner, context)
    check(
        owner.current_diagnostics is not None and not owner.commands.has_current_solution,
        "Real inconsistent native report has candidates and no solve authority",
    )
    before = snapshot(owner)
    check(
        bpy.ops.mcad.constraint_select("EXEC_DEFAULT", kind="constraint", identifier=conflicting)
        == {"FINISHED"},
        "Failed-state relation inspection uses exact authored ID",
    )
    unchanged(owner, before)
    check(
        not constraint_ui.action_available(context, "remove_relation"),
        "Failure candidates never authorize ordinary release",
    )
    before = snapshot(owner)
    check(
        operator("remove_relation").execute(context) == {"CANCELLED"},
        "Ordinary removal rejects diagnostics as solve authority",
    )
    check(
        operator("recover_remove_relation").execute(context) == {"CANCELLED"},
        "Recovery cannot bypass its authored-position disclosure",
    )
    unchanged(owner, before, ui=True)
    layout = Layout()
    constraint_ui.draw_inspector(layout, context, owner)
    check(
        any(
            kind == "operator" and item.name == "mcad.help" and item.topic == "sketch.constraints"
            for kind, item in layout.items
        ),
        "Inspector exposes its constraint help beside the title",
    )
    check(
        ("label", "Conflict candidates") in layout.items,
        "Inspector clearly labels native IDs as Conflict candidates",
    )
    check(
        not any(
            kind == "operator"
            and item.name == "mcad.constraint_action"
            and getattr(item, "action", "") == "coincident"
            for kind, item in layout.items
        ),
        "Inspector exposes no production Coincident",
    )
    recovery = invoke("recover_remove_relation", context)
    check(
        conflicting in recovery._prepared_intent.disclosure
        and "authored" in recovery._prepared_intent.disclosure
        and "unverified" in recovery._prepared_intent.disclosure,
        "Recovery popup identifies the relation, exact seed policy and unverified result",
    )
    constraint_ui.MCAD_OT_constraint_action.cancel(recovery, context)
    unchanged(owner, before, ui=True)
    recovery = invoke("recover_remove_relation", context)
    authored_before = owner.commands.sketch
    surviving = [item for item in authored_before["constraints"] if item["id"] != conflicting]
    original_intent = recovery._prepared_intent
    with patch.object(constraint_actions, "apply", wraps=constraint_actions.apply) as applying:
        check(
            recovery.execute(context) == {"FINISHED"},
            "Confirmed recovery removes the exact disclosed relation",
        )
        check(
            applying.call_args.args[2] is original_intent,
            "Recovery confirmation retains its original frozen intent",
        )
    check(
        owner.commands.sketch["constraints"] == surviving,
        "Recovery retains every surviving relation and exact expression",
    )
    check(owner.draft.selection == [], "Intentional recovery clears the removed selected relation")

    check(
        all(
            owner.commands.sketch[key] == authored_before[key]
            for key in ("points", "lines", "circles")
        ),
        "Recovery preserves authored positions and circle radius seeds exactly",
    )
    check(
        not owner.commands.has_current_solution,
        "Recovery result has no solve authority before its new Check",
    )
    wait(owner, context)
    check(owner.commands.has_current_solution, "Fresh native Check independently verifies recovery")
    # Explicit center button is the circle endpoint-ambiguity fallback.
    constraint_ui.select_bindings(owner, (("circle", circle),), context=context)
    check(
        bpy.ops.mcad.constraint_select(
            "EXEC_DEFAULT",
            kind="point",
            identifier=center,
            source_kind="circle",
            source_id=circle,
            source_role="CENTER",
        )
        == {"FINISHED"},
        "Circle center is explicitly selectable without pointer tie-breaking",
    )
    before = snapshot(owner)
    try:
        constraint_ui.select_bindings(owner, (("constraint", "missing_relation"),), context=context)
    except ValueError:
        pass
    else:
        raise AssertionError("Expected missing stable ID rejection")
    unchanged(owner, before, ui=True)
    owner.draft.begin_line(PointSeed(30, 30), (35, 35))
    check(
        not constraint_ui.action_available(context, "fix_here"),
        "Unfinished proposal guards constraint actions",
    )
    owner.draft.cancel_proposal()
    owner.checkpoint()
    radius = next(
        item["id"] for item in owner.commands.sketch["constraints"] if item["kind"] == "radius"
    )
    owner.begin_dimension(radius)
    check(
        not constraint_ui.action_available(context, "fix_here"),
        "Retained dimension input guards constraint actions",
    )
    check(
        constraint_ui.MCAD_OT_constraint_select.execute(
            SimpleNamespace(
                kind="point",
                identifier=first,
                source_kind="NONE",
                source_id="",
                source_role="NONE",
                report=lambda *_: None,
            ),
            context,
        )
        == {"CANCELLED"},
        "Retained dimension input guards UI selection",
    )
    owner.cancel_dimension()
    check(
        context.scene.mechanical_cad.document_json == canonical,
        "All local UI actions leave the canonical Part untouched",
    )
    owner.cleanup()
    check(
        sketch_session.active_session() is None
        and not constraint_ui.action_available(context, "horizontal"),
        "Retired owner disables inspector actions",
    )
    check(
        operator("fix_origin").execute(context) == {"CANCELLED"},
        "Invalid owner fails closed without constructing a replacement",
    )
    # Separate authored-only fixture tests bounded rows, transient pagination,
    # and both endpoint choices without introducing fabricated solve evidence.
    context.scene.mechanical_cad.sketch_draft_json = ""
    commands = GeneralSketchDraft(canonical)
    hub, _ = commands.execute(AddCircle(PointSeed(0, 0), 2)).entity_ids
    for index in range(8):
        endpoint, branch = commands.execute(
            AddLine(PointRef(hub), PointSeed(index + 2, index + 3))
        ).entity_ids
        commands.execute(AddRelation("horizontal", (branch,)))
    restored_owner = general_session.GeneralSession(context, restored=commands)
    restored_owner.start()
    constraint_ui.select_bindings(restored_owner, (("point", hub),), context=context)
    before = snapshot(restored_owner)
    layout = Layout()
    constraint_ui.draw_inspector(layout, context, restored_owner)
    buttons = [
        item
        for kind, item in layout.items
        if kind == "operator" and item.name == "mcad.constraint_select"
    ]
    check(
        len(buttons) == constraint_ui.PAGE_SIZE,
        "Inspector renders at most six incident relation rows",
    )
    first_ids = {item.identifier for item in buttons}
    check(
        bpy.ops.mcad.constraint_page("EXEC_DEFAULT", scope="relations", delta=1) == {"FINISHED"},
        "Relation pagination is an explicit UI-only operator",
    )
    unchanged(restored_owner, before, ui=True)
    layout = Layout()
    constraint_ui.draw_inspector(layout, context, restored_owner)
    buttons = [
        item
        for kind, item in layout.items
        if kind == "operator" and item.name == "mcad.constraint_select"
    ]
    check(
        len(buttons) == 2 and first_ids.isdisjoint(item.identifier for item in buttons),
        "Second bounded page exposes the remaining exact IDs",
    )
    check("page" not in restored_owner.stored_snapshot, "Pagination adds no persisted codec fields")
    constraint_ui.select_bindings(restored_owner, (("line", branch),), context=context)
    check(
        bpy.ops.mcad.constraint_select(
            "EXEC_DEFAULT",
            kind="point",
            identifier=endpoint,
            source_kind="line",
            source_id=branch,
            source_role="END",
        )
        == {"FINISHED"},
        "Explicit End point preserves the exact endpoint identity",
    )
    constraint_ui.select_bindings(restored_owner, (("line", branch),), context=context)
    check(
        bpy.ops.mcad.constraint_action("EXEC_DEFAULT", action="vertical") == {"FINISHED"},
        "Normal Vertical operator reaches the existing command/async path",
    )
    check(
        any(
            item["kind"] == "vertical" and item["refs"] == [branch]
            for item in restored_owner.commands.sketch["constraints"]
        ),
        "Vertical names only the selected authored line",
    )
    wait(restored_owner, context)
    restored_owner.cleanup()
    # Authored-only arc fixture checks native RNA identity controls without
    # pretending to be the mandatory manually drawn positive GUI workflow.
    context.scene.mechanical_cad.sketch_draft_json = ""
    commands = GeneralSketchDraft(canonical, journal_version=3)
    commands.execute(AddArc(PointSeed(0, 0), PointSeed(5, 0), PointSeed(0, 5), "ccw"))
    arc_owner = general_session.GeneralSession(
        context, restored=GeneralSketchAuthoringState(commands, ui_version=2)
    )
    arc_owner.start()
    arc = arc_owner.commands.sketch["arcs"][0]
    for role in ("center", "start", "end"):
        constraint_ui.select_bindings(arc_owner, (("arc", arc["id"]),), context=context)
        before = snapshot(arc_owner)
        check(
            bpy.ops.mcad.constraint_select(
                "EXEC_DEFAULT",
                kind="point",
                identifier=arc[role],
                source_kind="arc",
                source_id=arc["id"],
                source_role=role.upper(),
            )
            == {"FINISHED"},
            "Arc inspector selects exact " + role + " point",
        )
        unchanged(arc_owner, before)
        check(arc_owner.draft.proposal is None, "Inspector selection never accepts a point input")
        check(
            json.loads(arc_owner.stored_snapshot)["schema_version"] == 3,
            "Arc inspector checkpoints through the explicit envelope-3 dispatcher",
        )
    constraint_ui.select_bindings(arc_owner, (("arc", arc["id"]),), context=context)
    before = snapshot(arc_owner)
    bad_source = SimpleNamespace(
        kind="point",
        identifier=arc["center"],
        source_kind="circle",
        source_id=arc["id"],
        source_role="CENTER",
        report=lambda *_: None,
    )
    check(
        constraint_ui.MCAD_OT_constraint_select.execute(bad_source, context) == {"CANCELLED"},
        "Arc Center never infers or accepts circle source kind",
    )
    unchanged(arc_owner, before, ui=True)
    arc_owner.cleanup()
unregister()
print("CONSTRAINT_UI_SMOKE_OK", len(checks))
