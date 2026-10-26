"""Event-loop Focus/Restore proof, not mouse/keyboard usability acceptance.

Run in a disposable graphical Blender using --python-exit-code 1. MCAD_PYTHON
must identify the existing sidecar. --output receives a JSON receipt; --quit
closes this disposable process. Otherwise leave the live draft for GUI
review. No Blender jobs should overlap a separately reserved native slot.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import bpy

ROOT = Path(__file__).resolve().parents[1]
os.environ["MCAD_ROOT"] = str(ROOT)
sys.path.insert(0, str(ROOT / "blender_addon"))
import mechanical_cad_blender as addon  # noqa: E402
from mechanical_cad_blender import (  # noqa: E402
    constraint_ui,
    general_viewport,
    sketch_session,
    workspace,
    workspace_view,
)
from mechanical_cad_blender.general_sketch_commands import AddLine, PointSeed  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--output", required=True)
parser.add_argument("--quit", action="store_true")
args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
receipt = {"passed": False, "checks": [], "blender": bpy.app.version_string}
phase = "start"
owner = None
before = None
source = None
layout_before = None
area = None
canonical = None
started = time.monotonic()
toggles = 0
selected_line = None


def check(value, message):
    if not value:
        raise AssertionError(message)
    receipt["checks"].append(message)


def layout_snapshot(screen):
    return sorted((a.type, a.x, a.y, a.width, a.height) for a in screen.areas)


def snapshot(session):
    return (
        json.dumps(session.commands.checkpoint_payload(), sort_keys=True),
        json.dumps(session.draft.ui_payload(), sort_keys=True),
        session.evidence_request,
        session.evidence_response,
        session.commands._solution,
    )


def ready(context):
    global phase, area, layout_before, canonical
    area = context.area
    layout_before = layout_snapshot(context.window.screen)
    canonical = context.scene.mechanical_cad.document_json
    check(bpy.ops.mcad.general_sketch("INVOKE_DEFAULT") == {"RUNNING_MODAL"},
          "Real general sketch modal starts")
    phase = "draw"


def run():
    global phase, owner, before, source, toggles, selected_line, area
    if time.monotonic() - started > 90:
        raise RuntimeError("Focus fixture timeout")
    if phase == "start":
        if not hasattr(bpy.types.Scene, "mechanical_cad"):
            addon.register()
        # Use a separate test scene and an ordinary workspace as the source;
        # never replace the existing scene's CAD document or custom CAD layouts.
        bpy.context.window.scene = bpy.data.scenes.new("Focus CAD verification")
        ordinary = bpy.context.workspace
        if ordinary.get(workspace.OWNER_KEY) == workspace.OWNER:
            ordinary = next(w for w in bpy.data.workspaces if w.get(workspace.OWNER_KEY) != workspace.OWNER)
        bpy.context.window.workspace = ordinary
        phase = "prepare"
        return 0.25
    if phase == "prepare":
        bpy.ops.mcad.new_document(name="Focus CAD verification")
        source = (bpy.context.workspace, layout_snapshot(bpy.context.window.screen))
        workspace.request_workspace(bpy.context, "SKETCH", on_ready=ready)
        phase = "setup"
        return 0.1
    if phase == "setup":
        return 0.1
    area = max((a for a in bpy.context.window.screen.areas if a.type == "VIEW_3D"),
               key=lambda a: a.width * a.height)
    region = next(r for r in area.regions if r.type == "WINDOW")
    with bpy.context.temp_override(area=area, region=region):
        context = bpy.context
        if phase == "draw":
            owner = sketch_session.active_session(context)
            check(owner is not None, "Live owner acquired")
            _, _, selected_line = owner.execute(
                context, AddLine(PointSeed(0, 0), PointSeed(20, 10))
            ).entity_ids
            phase = "solve"
        elif phase == "solve":
            if owner.pending:
                owner.tick(context)
                return 0.1
            check(owner.commands.has_current_solution, "Unsaved line has real solver evidence")
            constraint_ui.select_bindings(owner, (("line", selected_line),), context=context)
            before = snapshot(owner)
            phase = "toggle"
        elif phase == "toggle":
            check(bpy.ops.mcad.focus_workspace() == {"FINISHED"}, "Focus/Restore native action runs")
            phase = "verify"
        elif phase == "verify":
            check(not owner.alive, "Original owner explicitly suspended before area transition")
            check(sketch_session.suspended_draft(context)["compatible"], "Saved sketch remains compatible")
            check("choose Resume" in context.scene.mechanical_cad.sketch_notice,
                  "Visible notice explains how to continue editing")
            check(context.scene.mechanical_cad.document_json == canonical, "Canonical model unchanged")
            check(area.spaces.active.show_region_ui, "CAD history/constraint sidebar remains enabled")
            focused = workspace_view.is_focused(context)
            check(focused == (toggles % 2 == 0), "Focus and Restore alternate")
            if not focused:
                check(layout_snapshot(context.window.screen) == layout_before,
                      "Exact custom area types, bounds and editor layout restored")
            check(layout_snapshot(source[0].screens[0]) == source[1], "Original Blender layout unchanged")
            toggles += 1
            phase = "resume_toggle"
        elif phase == "resume_toggle":
            bpy.ops.mcad.general_sketch("INVOKE_DEFAULT", resume_saved=True)
            owner = sketch_session.active_session(context)
            check(snapshot(owner)[:2] == before[:2], "Resume preserves exact unsaved geometry and selection")
            check(owner.evidence_response is not before[3], "Resume never reuses old viewport solve authority")
            check(not owner.commands.has_current_solution, "Resume honestly starts unverified")
            owner.check(context)
            phase = "recheck"
        elif phase == "recheck":
            if owner.pending:
                owner.tick(context)
                return 0.1
            check(owner.commands.has_current_solution, "Resumed draft is freshly verified")
            phase = "toggle" if toggles < 4 else "escape"

        elif phase == "escape":
            event = SimpleNamespace(type="ESC", value="PRESS", mouse_x=area.x + area.width // 2,
                                    mouse_y=area.y + area.height // 2, shift=False, ctrl=False,
                                    alt=False, oskey=False)
            result = general_viewport.MCAD_OT_general_sketch.modal(
                SimpleNamespace(owner=owner), context, event
            )
            check(result == {"CANCELLED"}, "Esc modal route safely suspends after Focus/Restore")
            check(not owner.alive and sketch_session.suspended_draft(context)["compatible"],
                  "Esc retains a compatible saved draft")
            check(context.scene.mechanical_cad.document_json == canonical, "Esc never commits the draft")
            phase = "resume"
        elif phase == "resume":
            check(bpy.ops.mcad.general_sketch("INVOKE_DEFAULT", resume_saved=True) == {"RUNNING_MODAL"},
                  "Suspended draft resumes after viewport changes")
            owner = sketch_session.active_session(context)
            check(snapshot(owner)[:2] == before[:2], "Resume preserves unsaved geometry and selection")
            owner.check(context)
            receipt["passed"] = True
            Path(args.output).write_text(json.dumps(receipt, indent=2))
            print("MCAD_WORKSPACE_FOCUS_OK", json.dumps(receipt), flush=True)
            if args.quit:
                bpy.app.timers.register(lambda: bpy.ops.wm.quit_blender() and None, first_interval=0.5)
            return None
    return 0.25


def tick():
    try:
        return run()
    except Exception as exc:
        receipt["error"] = repr(exc)
        Path(args.output).write_text(json.dumps(receipt, indent=2))
        print("MCAD_WORKSPACE_FOCUS_FAILED", repr(exc), flush=True)
        raise


bpy.app.timers.register(tick, first_interval=0.5)
