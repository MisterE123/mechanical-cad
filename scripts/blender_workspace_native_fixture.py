"""Native event-loop workspace regression; no kernel or real sketch editing.

Run in a disposable graphical Blender session. Example arguments after `--`:
--output /workspace/shared/workspace-fixture.blend [--verify-reopen] [--quit]
The second process loads the saved file before running this script with
--verify-reopen. Real drawing/Undo/solver acceptance is a separate GUI gate.
"""

import argparse
import json
import sys
import time
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "blender_addon"))
import mechanical_cad_blender as addon  # noqa: E402
from mechanical_cad_blender import workspace, workspace_ui  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--output", required=True)
parser.add_argument("--verify-reopen", action="store_true")
parser.add_argument("--quit", action="store_true")
args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else [])
output = Path(args.output)
report = output.with_suffix(".reopen.json" if args.verify_reopen else ".create.json")
addon.register()
workspace.register()
workspace_ui.register()
START = time.monotonic()
RESULT = {"version": bpy.app.version_string, "checks": [], "passed": False}
SOURCE = None
SCENE = None
DOCUMENT = None
COUNT = None
CUSTOM = None
EXISTING = None


def check(condition, name):
    if not condition:
        raise AssertionError(name)
    RESULT["checks"].append(name)


def snapshot():
    return {
        w.as_pointer(): (
            w.name,
            [
                (a.type, a.spaces.active.show_region_toolbar, a.spaces.active.show_region_ui)
                for s in w.screens
                for a in s.areas
                if a.type == "VIEW_3D"
            ],
        )
        for w in bpy.data.workspaces
        if w.get(workspace.OWNER_KEY) != workspace.OWNER
    }


def finish(context):
    check(context.scene == SCENE, "shared scene identity after all role switches")
    check(context.scene.mechanical_cad.document_json == DOCUMENT, "canonical JSON unchanged")
    check(len(bpy.data.workspaces) == COUNT, "repeated setup creates no duplicate workspaces")
    check(snapshot() == EXISTING, "pre-existing workspace names/layout flags preserved")
    check(
        CUSTOM.spaces.active.show_region_ui is False, "customized CAD layout preserved on reentry"
    )
    check(not workspace.active_draft(context), "cancel hook clears injected draft before handoff")
    RESULT["roles"] = {role: workspace.find_workspace(role).name for role in workspace.ROLES}
    if not args.verify_reopen:
        bpy.ops.wm.save_as_mainfile(filepath=str(output))
        check(output.is_file(), "native fixture saved")
    RESULT["passed"] = True
    report.write_text(json.dumps(RESULT, indent=2))
    print("MCAD_WORKSPACE_NATIVE_OK", RESULT)
    if args.quit:
        bpy.app.timers.register(lambda: bpy.ops.wm.quit_blender() and None, first_interval=0.3)


def after_assembly(context):
    check(workspace.get_role(context) == "ASSEMBLY", "Assembly actual tab activation")
    workspace.request_workspace(context, "PART", on_ready=finish)


def repeated(context):
    check(workspace.get_role(context) == "SKETCH", "Sketch repeated tab activation")
    check(CUSTOM.spaces.active.show_region_ui is False, "reentry does not reset sidebar")
    workspace.request_workspace(context, "ASSEMBLY", on_ready=after_assembly)


def after_create(context):
    global COUNT, CUSTOM
    check(workspace.get_role(context) == "SKETCH", "Sketch actual tab activation")
    check(
        all(workspace.find_workspace(role) is not None for role in workspace.ROLES),
        "three role-tagged workspaces exist",
    )
    if args.verify_reopen:
        check(
            len([w for w in bpy.data.workspaces if w.get(workspace.OWNER_KEY) == workspace.OWNER])
            == 3,
            "saved role tags reopened without duplicate creation",
        )
    COUNT = len(bpy.data.workspaces)
    CUSTOM = context.area
    CUSTOM.spaces.active.show_region_ui = False
    draft = {"active": True}

    def cancel(reason, context=None):
        draft["active"] = False

    workspace.set_draft_handlers(lambda context: draft if draft["active"] else None, cancel)
    workspace.request_workspace(context, "SKETCH", on_ready=repeated)


def start():
    global SOURCE, SCENE, DOCUMENT, EXISTING
    SOURCE = bpy.context.workspace
    SCENE = bpy.context.scene
    if not args.verify_reopen:
        SOURCE.name = "Sketch"  # deliberate collision must remain untouched
        state = SCENE.mechanical_cad
        state.document_json = json.dumps(
            {
                "schema_version": 1,
                "id": "workspace_fixture",
                "name": "Workspace fixture",
                "units": "mm",
                "parameters": {},
                "features": [],
                "active_feature": None,
            }
        )
        state.document_name = "Workspace fixture"
    DOCUMENT = SCENE.mechanical_cad.document_json
    EXISTING = snapshot()
    workspace.request_workspace(bpy.context, "SKETCH", on_ready=after_create)
    return None


def watchdog():
    if RESULT["passed"]:
        return None
    if time.monotonic() - START > 30 or workspace._LAST_ERROR:
        RESULT["error"] = workspace._LAST_ERROR or "native fixture timed out"
        report.write_text(json.dumps(RESULT, indent=2))
        print("MCAD_WORKSPACE_NATIVE_FAILED", RESULT)
        if args.quit:
            bpy.ops.wm.quit_blender()
        return None
    return 0.3


bpy.app.timers.register(start, first_interval=0.5)
bpy.app.timers.register(watchdog, first_interval=0.8)
