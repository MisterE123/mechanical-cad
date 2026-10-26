"""Native proposal/end-face RNA and separate-process saved-intent qualification.

Set MCAD_ROOT, MCAD_PYTHON and MCAD_REPAIR_BLEND; repeat with
MCAD_REPAIR_REOPEN=1. Run background Blender with --python-exit-code 1.
Only popup presentation is intercepted. This is not actual GUI qualification.
"""

import json
import math
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path[:0] = [str(ROOT / "blender_addon"), str(ROOT / "tests")]
from end_face_repair_cases import end_face_case, feature  # noqa: E402
from mechanical_cad_blender import (  # noqa: E402
    bridge,
    display,
    register,
    repair_intent,
    staged_edit,
    unregister,
)
from mechanical_cad_blender import document_state as doc  # noqa: E402
from mechanical_cad_blender import (  # noqa: E402
    end_face_repair_ui as ui,
)

assert bpy.app.background, "Use an isolated background Blender, never the user's GUI"
BLEND = Path(os.environ["MCAD_REPAIR_BLEND"])
EXPECTED = BLEND.with_suffix(".expected.json")
mode = "repair"
checks = []


def check(condition, message):
    assert condition, message
    checks.append(message)
    print("END_FACE_CHECK=" + message, flush=True)


def snapshot():
    scene = bpy.context.scene
    return (
        scene.mechanical_cad.document_json,
        id(doc._RUNTIME.get(doc._scene_key(scene))),
        tuple(
            (o.as_pointer(), o.data.as_pointer(), o.hide_viewport, o.hide_get())
            for o in display._owned_objects(scene)
        ),
    )


class DialogContext:
    window_manager = SimpleNamespace(invoke_props_dialog=lambda *a, **k: {"RUNNING_MODAL"})

    def __getattr__(self, key):
        return getattr(bpy.context, key)


execute = ui.MCAD_OT_replace_end_face.execute


def review(self, context):
    before = snapshot()
    proposal = staged_edit.require(context, self.staged_token)
    check(
        ui.MCAD_OT_replace_end_face.invoke(self, DialogContext(), None) == {"RUNNING_MODAL"},
        "Registered review opens on fresh proposed replay",
    )
    check(
        self._document == proposal.document and self.original_json == proposal.base_json,
        "Review binds proposed graph and accepted base separately",
    )
    check(self.target == self.end_face == "NONE", "No target or face is selected automatically")
    sources = ui._sources(self.properties, context)
    check(
        "replacement" in {row[0] for row in sources},
        "RNA offers earlier source-qualified replacement",
    )
    self.target = "replacement"
    check(self.end_face == "NONE", "Changing source requires explicit face selection")
    check(
        "block/face/cap.end" in {row[0] for row in ui._faces(self.properties, context)},
        "RNA offers stable parallel face with valid saved reach",
    )
    self.end_face = "block/face/cap.end"
    if mode == "cancel":
        self.cancel(context)
        check(
            staged_edit.current(context) is proposal and snapshot() == before,
            "Cancel retains exact proposal, accepted data and display",
        )
        check(self._review_evidence is None, "Cancel releases read-only evidence")
        return {"CANCELLED"}
    return execute(self, context)


ui.MCAD_OT_replace_end_face.execute = review
register()
bpy.context.preferences.edit.use_global_undo = True


def repair(identifier, expected):
    proposal = staged_edit.current(bpy.context)
    check(
        bpy.ops.mcad.replace_end_face(
            "EXEC_DEFAULT", feature_id=identifier, staged_token=proposal.token
        )
        == expected,
        "Actual operator returns expected partial/final result",
    )


if os.environ.get("MCAD_REPAIR_REOPEN"):
    expected = json.loads(EXPECTED.read_text())
    check(
        bpy.ops.wm.open_mainfile(filepath=str(BLEND)) == {"FINISHED"},
        "Separate process opens saved repair",
    )
    state = bpy.context.scene.mechanical_cad
    check(
        state.document_json == expected["base"] and state.repair_intent_json == expected["raw"],
        "Reopen preserves accepted bytes and dormant intent exactly",
    )
    check(
        staged_edit.current(bpy.context) is None and not doc.part_is_current(bpy.context),
        "Reopen restores no live proposal or native authority",
    )
    before = snapshot()
    check(
        bpy.ops.mcad.resume_saved_repair() == {"FINISHED"},
        "Resume freshly validates accepted base and every proposal state",
    )
    proposal = staged_edit.current(bpy.context)
    check(
        len(proposal.repairs) == 1
        and proposal.token not in expected["tokens"]
        and snapshot() == before,
        "Resume restores only proposal history with fresh ownership",
    )
    mode = "cancel"
    repair("tool2", {"CANCELLED"})
    check(
        bpy.ops.mcad.undo_proposal_repair(staged_token=proposal.token) == {"FINISHED"},
        "Proposal Undo works after fresh Resume",
    )
    undone = staged_edit.current(bpy.context)
    check(
        undone.candidate_json == json.loads(expected["raw"])["states"][0] and not undone.repairs,
        "Undo restores exact preceding unapplied state",
    )
    mode = "repair"
    repair("tool", {"CANCELLED"})
    repair("tool2", {"FINISHED"})
    current = json.loads(state.document_json)
    check(
        feature(current, "slot_tool")["params"]["length"] == 6,
        "Final commit retains attempted upstream edit",
    )
    check(
        all(
            feature(current, name)["inputs"]["target"] == "replacement"
            for name in ("tool", "tool2")
        ),
        "Full successful replay accepts both explicit target choices",
    )
    check(
        feature(current, "tool")["params"] == {"direction": -1, "offset": "gap"}
        and feature(current, "tool2")["params"] == {"direction": 1, "offset": "gap + allowance"},
        "Saved direction and offset expressions remain unchanged",
    )
    check(
        abs(
            doc.current_part_result(bpy.context)["features"][-1]["stats"]["volume"]
            - 12.75 * math.pi
        )
        < 1e-7
        and doc.part_is_current(bpy.context),
        "Accepted result has exact rebuilt volume",
    )
    check(
        staged_edit.current(bpy.context) is None and not state.repair_intent_json,
        "Final commit consumes only its owned proposal and checkpoint",
    )
    check(
        not any(
            name == "OCP"
            or name.startswith("OCP.")
            or name == "mechanical_cad"
            or name.startswith("mechanical_cad.")
            for name in sys.modules
        ),
        "Native kernel/core never imported in Blender",
    )
    marker = "MCAD_END_FACE_REPAIR_REOPEN_OK"
else:
    base, proposed = end_face_case()
    check(doc._commit_candidate(bpy.context, base), "Accepted native fixture builds")
    before = snapshot()
    try:
        doc._commit_candidate(bpy.context, proposed, stage_feature_id="slot_tool")
    except bridge.BridgeError:
        pass
    proposal = staged_edit.current(bpy.context)
    check(
        proposal is not None and proposal.document == proposed and snapshot() == before,
        "Upstream Cut split retains attempt without accepted mutation",
    )
    check(
        {row["id"] for row in proposal.failures} == {"tool", "tool2"},
        "Both broken end references remain explicit failures",
    )
    mode = "cancel"
    repair("tool", {"CANCELLED"})
    mode = "repair"
    repair("tool", {"CANCELLED"})
    partial = staged_edit.current(bpy.context)
    check(
        len(partial.repairs) == 1 and snapshot() == before,
        "Valid partial extrusion repair stays unapplied",
    )
    check(
        bpy.ops.wm.save_as_mainfile(filepath=str(BLEND)) == {"FINISHED"},
        "Actual Blender Save checkpoints bounded repair intent",
    )
    state = bpy.context.scene.mechanical_cad
    raw = state.repair_intent_json
    saved = repair_intent.decode(raw)
    check(
        staged_edit.current(bpy.context) is None and len(saved["states"]) == 2,
        "Successful Save suspends proposal and retains both intent states",
    )
    check(
        proposal.token not in raw
        and partial.token not in raw
        and "snapshot:" not in raw
        and "cut_ancestry" not in raw,
        "Saved intent has no native tokens, snapshot IDs or geometry authority",
    )
    check(snapshot() == before, "Save preserves accepted JSON, runtime and display")
    EXPECTED.write_text(
        json.dumps(
            {"base": state.document_json, "raw": raw, "tokens": [proposal.token, partial.token]}
        )
    )
    marker = "MCAD_END_FACE_REPAIR_CREATE_OK"

unregister()
print(marker + "=" + json.dumps(checks), flush=True)
