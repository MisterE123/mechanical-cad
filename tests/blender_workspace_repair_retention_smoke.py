"""Native workspace-only repair retention and separate-process Resume.

Run isolated background Blender with --factory-startup --python-exit-code 1,
MCAD_ROOT, MCAD_PYTHON and an absolute temporary MCAD_REPAIR_BLEND path. Repeat
in a new process with MCAD_REPAIR_REOPEN=1. The first run deliberately starts
without a saved checkpoint. A real workspace context override creates the old
binding; no deferred headless Window.workspace assignment or fake context is
used to simulate the workspace change. Only popup presentation is intercepted.
"""

import copy
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
sys.path[:0] = [str(ROOT / "blender_addon"), str(ROOT / "tests")]
from mechanical_cad_blender import (  # noqa: E402
    bridge,
    display,
    projection_repair_ui,
    register,
    repair_intent,
    staged_edit,
    staged_edit_store,
    unregister,
)
from mechanical_cad_blender import document_state as doc  # noqa: E402
from staged_edit_cases import multiple_projection_case  # noqa: E402

BLEND = Path(os.environ["MCAD_REPAIR_BLEND"])
EXPECTED = BLEND.with_suffix(".expected.json")
checks = []


def check(condition, message):
    assert condition, message
    checks.append(message)
    print("WORKSPACE_REPAIR_CHECK=" + message, flush=True)


def accepted_snapshot():
    scene = bpy.context.scene
    return (
        scene.mechanical_cad.document_json,
        id(doc._RUNTIME.get(doc._scene_key(scene))),
        tuple(
            (obj.as_pointer(), obj.data.as_pointer(), obj.hide_viewport, obj.hide_get())
            for obj in display._owned_objects(scene)
        ),
        scene.mechanical_cad.sketch_annotation_json,
    )


def reject_expired(token):
    try:
        staged_edit.require(bpy.context, token)
    except bridge.BridgeError:
        return
    raise AssertionError("Old proposal token unexpectedly retained authority")


class DialogContext:
    window_manager = SimpleNamespace(invoke_props_dialog=lambda *a, **k: {"RUNNING_MODAL"})

    def __getattr__(self, key):
        return getattr(bpy.context, key)


execute_repair = projection_repair_ui.MCAD_OT_replace_projection_reference.execute


def repair_operator(self, context):
    assert projection_repair_ui.MCAD_OT_replace_projection_reference.invoke(
        self, DialogContext(), None
    ) == {"RUNNING_MODAL"}
    self.target = "reference"
    self.replacement = str(
        next(
            i for i, row in enumerate(self._entries) if row["row"] == {"source": "replacement_ring"}
        )
    )
    return execute_repair(self, context)


projection_repair_ui.MCAD_OT_replace_projection_reference.execute = repair_operator
assert bpy.app.background, "Use isolated background Blender, never the user's GUI"
assert BLEND.is_absolute(), "MCAD_REPAIR_BLEND must be an absolute temporary path"
register()

if os.environ.get("MCAD_REPAIR_REOPEN"):
    expected = json.loads(EXPECTED.read_text())
    check(os.getpid() != expected["pid"], "Reopen runs in a distinct native Blender process")
    with patch.object(
        doc, "_run_sidecar", side_effect=AssertionError("Load must not replay repair intent")
    ):
        assert bpy.ops.wm.open_mainfile(filepath=str(BLEND)) == {"FINISHED"}
    state = bpy.context.scene.mechanical_cad
    check(
        state.document_json == expected["accepted"] and state.repair_intent_json == expected["raw"],
        "Separate-process reopen preserves exact accepted bytes and dormant v1 intent",
    )
    check(
        not state.last_action_error,
        "Successful workspace-recovery Save reopens without a stale in-memory-only or save-to-disk notice",
    )
    scene_key = doc._scene_key(bpy.context.scene)
    check(
        staged_edit.current(bpy.context) is None
        and scene_key not in doc._RUNTIME
        and scene_key not in doc._GEOMETRY_RUNTIME
        and not doc.part_is_current(bpy.context),
        "Load restores no live proposal, native receipt or current geometry authority",
    )
    before = accepted_snapshot()
    saved = repair_intent.decode(state.repair_intent_json)
    calls = []
    claims = []
    run = doc._run_sidecar

    def record(*args, **kwargs):
        calls.append(copy.deepcopy(args[1]))
        evidence = run(*args, **kwargs)
        claims.append(evidence.publication)
        return evidence

    with patch.object(doc, "_run_sidecar", side_effect=record):
        assert bpy.ops.mcad.resume_saved_repair("EXEC_DEFAULT") == {"FINISHED"}
    proposal = staged_edit.current(bpy.context)
    check(
        calls == [json.loads(saved["base_json"])] + [json.loads(raw) for raw in saved["states"]],
        "Explicit Resume freshly replays the accepted base and every retained state in order",
    )
    check(
        len(calls) == 3 and all(claim._state == "cancelled" for claim in claims),
        "Resume cancels each read-only native publication claim instead of publishing geometry",
    )
    check(
        proposal is not None
        and proposal.token not in expected["tokens"]
        and proposal.binding["workspace"] == bpy.context.workspace
        and len(proposal.repairs) == 1
        and proposal.candidate_json == saved["states"][-1]
        and proposal.repairs[0][0] == saved["states"][0],
        "Fresh current-workspace ownership restores the exact partial repair and Undo history",
    )
    for token in expected["tokens"]:
        reject_expired(token)
    check(
        accepted_snapshot() == before
        and not state.repair_intent_json
        and not doc.part_is_current(bpy.context),
        "Resume consumes intent only after validation without accepted JSON or display changes",
    )
    assert bpy.ops.mcad.undo_proposal_repair(staged_token=proposal.token) == {"FINISHED"}
    undone = staged_edit.current(bpy.context)
    check(
        undone.candidate_json == saved["states"][0]
        and not undone.repairs
        and undone.token != proposal.token
        and undone.token not in expected["tokens"],
        "Proposal Undo after reopen restores the exact original unapplied edit with fresh ownership",
    )
    check(
        accepted_snapshot() == before and not doc.part_is_current(bpy.context),
        "Resumed proposal Undo leaves accepted JSON and loaded display unchanged",
    )
    marker = "MCAD_WORKSPACE_REPAIR_REOPEN_OK"
else:
    original_workspace = bpy.context.workspace
    other_workspace = next(ws for ws in bpy.data.workspaces if ws != original_workspace)
    scene, window, view_layer = bpy.context.scene, bpy.context.window, bpy.context.view_layer
    base, proposed = multiple_projection_case()

    with bpy.context.temp_override(workspace=other_workspace):
        check(
            bpy.context.workspace == other_workspace
            and bpy.context.window == window
            and bpy.context.scene == scene
            and bpy.context.view_layer == view_layer,
            "A real native workspace override changes only the workspace binding",
        )
        check(doc._commit_candidate(bpy.context, base), "Accepted native Part fixture builds")
        before = accepted_snapshot()
        try:
            doc._commit_candidate(bpy.context, proposed, stage_feature_id="source")
        except bridge.BridgeError:
            pass
        original = staged_edit.current(bpy.context)
        check(
            original is not None
            and original.document == proposed
            and {row["id"] for row in original.failures} == {"target", "target_two"}
            and accepted_snapshot() == before,
            "Failed upstream edit retains two repairable references without changing accepted geometry",
        )
        assert bpy.ops.mcad.replace_projection_reference(
            "EXEC_DEFAULT", feature_id="target", staged_token=original.token
        ) == {"CANCELLED"}
        partial = staged_edit.current(bpy.context)
        check(
            len(partial.repairs) == 1
            and {row["id"] for row in partial.failures} == {"target_two"}
            and accepted_snapshot() == before,
            "One actual partial repair retains unapplied progress and proposal-local Undo",
        )
        expected_raw = repair_intent.encode(partial)

    state = scene.mechanical_cad
    check(
        bpy.context.workspace == original_workspace
        and partial.binding["workspace"] == other_workspace
        and bpy.context.workspace != partial.binding["workspace"]
        and bpy.context.scene == partial.binding["scene"] == scene
        and bpy.context.window == partial.binding["window"] == window
        and bpy.context.view_layer == partial.binding["view_layer"] == view_layer,
        "Leaving the native override creates a workspace-only stale proposal binding",
    )
    check(
        not state.repair_intent_json
        and not staged_edit_store._CHECKPOINTS
        and not staged_edit_store._SAVE_PENDING
        and staged_edit.current(bpy.context) is partial,
        "Initial stale-workspace Save starts with live progress and no previously saved checkpoint",
    )
    with patch.object(
        doc, "_run_sidecar", side_effect=AssertionError("Save must preserve intent without replay")
    ):
        assert bpy.ops.wm.save_as_mainfile(filepath=str(BLEND)) == {"FINISHED"}
    raw = state.repair_intent_json
    check(raw == expected_raw, "Actual Save retains the latest exact strict v1 repair-intent bytes")
    saved = repair_intent.decode(raw)
    check(
        set(saved)
        == {
            "schema_version",
            "kind",
            "base_json",
            "base_hash",
            "owner_id",
            "scale",
            "feature_id",
            "states",
            "annotation_before",
            "annotation_after",
        }
        and saved["schema_version"] == 1
        and saved["kind"] == "unapplied_repair_intent"
        and saved["states"] == [original.candidate_json, partial.candidate_json]
        and saved["base_json"] == before[0],
        "Strict v1 envelope contains only accepted base and both exact unapplied intent states",
    )
    check(
        staged_edit.current(bpy.context) is None
        and not staged_edit_store._CHECKPOINTS
        and not staged_edit_store._SAVE_PENDING,
        "Successful workspace-stale Save retires live ownership and checkpoint bookkeeping",
    )
    for token in (original.token, partial.token):
        reject_expired(token)
    check(
        original.token not in raw
        and partial.token not in raw
        and "snapshot:" not in raw
        and "cut_ancestry" not in raw,
        "Saved intent contains no old proposal token, native snapshot or geometry authority",
    )
    check(
        accepted_snapshot() == before,
        "Workspace-stale Save never changes accepted JSON, runtime or display",
    )
    EXPECTED.write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "accepted": state.document_json,
                "raw": raw,
                "tokens": [original.token, partial.token],
            }
        )
    )
    marker = "MCAD_WORKSPACE_REPAIR_CREATE_OK"

unregister()
print(marker + "=" + json.dumps(checks), flush=True)
