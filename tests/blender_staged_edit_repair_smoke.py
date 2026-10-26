"""Real native replay, registered repair RNA and proposal lifecycle regression.

MCAD_ROOT=<repo> MCAD_PYTHON=<sidecar-python> blender --background \
  --factory-startup --python-exit-code 1 --python tests/blender_staged_edit_repair_smoke.py

Only final popup presentation is intercepted. Actual OperatorProperties enum
callbacks, guarded native replay, publication, save/load and session Undo run.
This does not qualify mouse interaction, dialog drawing or installed packages.
"""

import copy
import json
import math
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
sys.path[:0] = [str(ROOT / "blender_addon"), str(ROOT / "tests")]
from mechanical_cad_blender import (  # noqa: E402
    backend_runtime,
    bridge,
    display,
    geometry_operations,
    register,
    solid_operators,
    staged_edit,
    unregister,
)
from mechanical_cad_blender import (  # noqa: E402
    document_state as doc,
)
from mechanical_cad_blender import (  # noqa: E402
    projection_repair_ui as projection_ui,
)
from mechanical_cad_blender import (  # noqa: E402
    support_intent_ui as support_ui,
)
from staged_edit_cases import feature, projection_case, support_case  # noqa: E402

if not bpy.app.background:
    raise RuntimeError("Run only in an isolated background Blender")

checks = []
mode = "cancel"


def check(value, label):
    assert value, label
    checks.append(label)
    print("STAGED_CHECK=" + label, flush=True)


def reject(callback, text=None):
    try:
        callback()
    except bridge.BridgeError as exc:
        if text:
            assert text.lower() in str(exc).lower(), str(exc)
        return str(exc)
    raise AssertionError("Expected guarded rejection")


def snapshot():
    context = bpy.context
    state = doc._snapshot_fields(context.scene.mechanical_cad)
    # A rejection may explain itself without modifying accepted-model state.
    state.pop("last_action_error", None)
    objects = tuple(
        (
            obj.as_pointer(),
            obj.data.as_pointer() if obj.data else None,
            obj.hide_viewport,
            obj.hide_render,
            obj.hide_get(),
            tuple(tuple(v.co) for v in obj.data.vertices) if obj.type == "MESH" else (),
        )
        for obj in display._owned_objects(context.scene)
    )
    return (
        state,
        objects,
        id(doc._RUNTIME.get(doc._scene_key(context.scene))),
        json.dumps(doc.current_part_result(context), sort_keys=True),
    )


def reset(base):
    staged_edit.cancel_all()
    assert doc._commit_candidate(bpy.context, copy.deepcopy(base))
    assert doc.part_is_current(bpy.context)


def stage(proposed, upstream):
    before = snapshot()
    message = reject(
        lambda: doc._commit_candidate(
            bpy.context, copy.deepcopy(proposed), stage_feature_id=upstream
        )
    )
    proposal = staged_edit.current(bpy.context)
    check(proposal is not None, "Native downstream reference failure retains proposed edit")
    check(proposal.document == proposed, "Retained document is the exact failed candidate")
    check(snapshot() == before, "Failed edit leaves accepted JSON, runtime and display unchanged")
    check("repair" in message.lower(), "Failure reports explicit repair directions")
    return proposal


class DialogContext:
    window_manager = SimpleNamespace(invoke_props_dialog=lambda *a, **k: {"RUNNING_MODAL"})

    def __getattr__(self, key):
        return getattr(bpy.context, key)


support_execute = support_ui.MCAD_OT_edit_sketch_support.execute
projection_execute = projection_ui.MCAD_OT_replace_projection_reference.execute
solid_execute = solid_operators.MCAD_OT_edit_solid_feature.execute


def solid_trampoline(self, context):
    before = snapshot()
    assert isinstance(self, bpy.types.Operator)
    assert isinstance(self.properties, bpy.types.OperatorProperties)
    assert solid_operators.MCAD_OT_edit_solid_feature.invoke(self, DialogContext(), None) == {
        "RUNNING_MODAL"
    }
    check(
        self.kind == "extrude" and self.length == "1",
        "Actual Edit Feature loads upstream extrusion",
    )
    self.length = "5"
    result = solid_execute(self, context)
    check(result == {"CANCELLED"}, "Actual Edit Feature rejects failed full candidate")
    proposal = staged_edit.current(context)
    check(proposal is not None, "Actual Edit Feature opts into retained downstream repair")
    check(proposal.feature_id == "slot_tool", "Actual editor records the edited upstream feature")
    check(
        feature(proposal.document, "slot_tool")["params"]["length"] == "5",
        "Actual editor retains the exact proposed dimension text",
    )
    check(
        snapshot() == before,
        "Actual failed editor leaves accepted JSON, runtime and mesh unchanged",
    )
    check(
        "repair" in context.scene.mechanical_cad.last_action_error.lower(),
        "Actual editor reports a discoverable repair direction",
    )
    return result


def support_trampoline(self, context):
    before = snapshot()
    proposal = staged_edit.require(context, self.staged_token)
    assert isinstance(self, bpy.types.Operator)
    assert isinstance(self.properties, bpy.types.OperatorProperties)
    assert support_ui.MCAD_OT_edit_sketch_support.invoke(self, DialogContext(), None) == {
        "RUNNING_MODAL"
    }
    check(self._document == proposal.document, "Support dialog reviews proposed, not accepted data")
    check(self.original_json == proposal.base_json, "Support dialog binds accepted base separately")
    check(not hasattr(self.properties, "_document"), "Support RNA wrapper has no Python owner data")
    assert self.support_source == "slotted"
    assert "block" in {item[0] for item in support_ui._sources(self.properties, context)}
    self.support_source = "block"
    assert self.support_face in {item[0] for item in support_ui._faces(self.properties, context)}
    self.support_face = "block/face/cap.end"
    self.support_source = "slotted"
    self.support_face = "block/face/cap.end"
    self.policy = "PRESERVE_PLANE"
    self.orientation = "WORLD_AXES"
    if mode == "cancel":
        self.cancel(context)
        check(staged_edit.current(context) is proposal, "Support Cancel retains the exact proposal")
        check(snapshot() == before, "Support Cancel leaves accepted runtime/display unchanged")
        return {"CANCELLED"}
    result = support_execute(self, context)
    assert result == {"FINISHED"}, context.scene.mechanical_cad.last_action_error
    check(self._review_evidence is None, "Support Apply releases read-only review evidence")
    return result


def projection_trampoline(self, context):
    before = snapshot()
    proposal = staged_edit.require(context, self.staged_token)
    assert isinstance(self, bpy.types.Operator)
    assert isinstance(self.properties, bpy.types.OperatorProperties)
    assert projection_ui.MCAD_OT_replace_projection_reference.invoke(
        self, DialogContext(), None
    ) == {"RUNNING_MODAL"}
    check(self._document == proposal.document, "Projection dialog reviews proposed source geometry")
    check(
        not hasattr(self.properties, "_feature"), "Projection RNA wrapper has no Python owner data"
    )
    assert self.target == "reference" and self.replacement == "0"
    self.target = "reference"
    assert self.replacement == "0" and not self.reverse
    assert projection_ui._sources(self.properties, context)[0][0] == "0"
    assert self._entries[0]["row"] == {"source": "replacement_ring"}
    if mode == "cancel":
        self.cancel(context)
        check(
            staged_edit.current(context) is proposal, "Projection Cancel retains the exact proposal"
        )
        check(snapshot() == before, "Projection Cancel leaves accepted runtime/display unchanged")
        return {"CANCELLED"}
    if mode == "failed_repair":
        # A support-plane mutation is unrelated to replacing one projection.
        # Reject it before native work, preserving the exact prior proposal.
        candidate = self._candidate()
        feature(candidate, "target")["sketch"]["plane"]["quaternion"] = [
            math.sqrt(0.5),
            math.sqrt(0.5),
            0,
            0,
        ]
        with patch.object(doc, "_run_sidecar", wraps=doc._run_sidecar) as native_replay:
            reject(lambda: staged_edit.accept(context, proposal.token, candidate), "plane")
        check(
            native_replay.call_count == 0, "Unrelated plane edit is rejected before native replay"
        )
        self._release()
        check(
            staged_edit.current(context) is proposal, "Failed full repair retains original proposal"
        )
        check(
            proposal.document == self._document, "Failed repair does not accumulate partial changes"
        )
        check(
            snapshot() == before, "Failed repair leaves accepted JSON, runtime and mesh unchanged"
        )
        return {"CANCELLED"}
    result = projection_execute(self, context)
    assert result == {"FINISHED"}, context.scene.mechanical_cad.last_action_error
    check(self._catalog_evidence is None, "Projection Apply releases catalog evidence")
    return result


support_ui.MCAD_OT_edit_sketch_support.execute = support_trampoline
projection_ui.MCAD_OT_replace_projection_reference.execute = projection_trampoline
solid_operators.MCAD_OT_edit_solid_feature.execute = solid_trampoline
register()

support_base, support_proposed = support_case()
projection_base, projection_proposed = projection_case()

# Exercise the genuine user-facing entry point, not only the publication seam.
reset(support_base)
try:
    assert bpy.ops.mcad.edit_solid_feature("EXEC_DEFAULT", feature_id="slot_tool") == {"CANCELLED"}
except RuntimeError as exc:
    # Background bpy.ops surfaces the real operator's ERROR report as an
    # exception. The trampoline above already checks its real execute result.
    assert "repair" in str(exc).lower(), str(exc)
proposal = staged_edit.current(bpy.context)
assert proposal is not None
staged_edit.discard(bpy.context, proposal.token)

# Actual RNA callbacks cannot silently invalidate the retained proposal.
for parameter_value in (3, "3"):
    base = copy.deepcopy(projection_base)
    proposed = copy.deepcopy(projection_proposed)
    base["parameters"]["r"] = proposed["parameters"]["r"] = parameter_value
    reset(base)
    proposal = stage(proposed, "source")
    parameter = bpy.context.scene.mechanical_cad.parameters[0]
    before = snapshot()
    check(doc.has_staged_edit(bpy.context), "Pending proposal disables parameter editing")
    if isinstance(parameter_value, str):
        parameter.expression = "r + 100"
        check(parameter.expression == "3", "Formula RNA edit restores accepted expression")
    else:
        parameter.value = 99
        check(parameter.value == 3, "Numeric RNA edit restores accepted value")
    check(snapshot() == before, "Parameter RNA edit preserves accepted model and display")
    check(
        staged_edit.current(bpy.context) is proposal, "Parameter RNA edit preserves exact proposal"
    )
    parameter.is_expression = not isinstance(parameter_value, str)
    check(
        parameter.is_expression == isinstance(parameter_value, str),
        "Mode RNA edit restores accepted mode",
    )
    check(snapshot() == before, "Mode RNA edit preserves accepted model and display")
    check(staged_edit.current(bpy.context) is proposal, "Mode RNA edit preserves exact proposal")
    check(
        "discard the proposed edit" in bpy.context.scene.mechanical_cad.last_action_error,
        "Blocked parameter edit explains repair or discard requirement",
    )
    staged_edit.discard(bpy.context, proposal.token)

# No explicit staging request means the historical atomic rejection remains.
reset(support_base)
before = snapshot()
reject(lambda: doc._commit_candidate(bpy.context, support_proposed))
check(staged_edit.current(bpy.context) is None, "Ordinary failed commit does not retain a proposal")
check(snapshot() == before, "Non-opt-in rejection remains atomic")

proposal = stage(support_proposed, "slot_tool")
with patch.object(doc, "_run_sidecar", side_effect=AssertionError("Blocked edit launched replay")):
    reject(lambda: doc._commit_candidate(bpy.context, support_base), "retained")
    reject(
        lambda: doc._commit_candidate(bpy.context, support_proposed, stage_feature_id="slot_tool"),
        "retained",
    )
with doc.replay_guard(bpy.context):
    reject(
        lambda: doc._publish_candidate_locked(
            bpy.context, support_base, None, {}, json.dumps(support_base)
        ),
        "retained",
    )
check(
    staged_edit.current(bpy.context) is proposal,
    "Direct completed publication cannot bypass pending-proposal gate",
)
check(
    staged_edit.current(bpy.context) is proposal, "Second proposal cannot overwrite retained work"
)
before = snapshot()
staged_edit.discard(bpy.context, proposal.token)
check(snapshot() == before, "Explicit discard preserves accepted display and authority")

# Genuine registered support RNA callbacks and atomic explicit repair.
for mode in ("cancel", "accept"):
    reset(support_base)
    proposal = stage(support_proposed, "slot_tool")
    result = bpy.ops.mcad.edit_sketch_support(
        "EXEC_DEFAULT", feature_id="attached", staged_token=proposal.token
    )
    assert result == ({"CANCELLED"} if mode == "cancel" else {"FINISHED"})
    if mode == "accept":
        saved = json.loads(bpy.context.scene.mechanical_cad.document_json)
        check(
            feature(saved, "slot_tool")["params"]["length"] == 5,
            "Support repair accepts upstream depth",
        )
        check(
            "support_intent" in feature(saved, "attached"),
            "Support repair records visible logical intent",
        )
        check(
            staged_edit.current(bpy.context) is None, "Successful support repair retires proposal"
        )
        check(
            doc.part_is_current(bpy.context),
            "Full repaired support Part has fresh runtime authority",
        )
        volume = doc.current_part_result(bpy.context)["features"][-1]["stats"]["volume"]
        check(
            abs(volume - 8 * math.pi) < 1e-7, "Support repair rebuilds dependent exact boss volume"
        )

# Genuine registered projection RNA callbacks, failed full replay and retry.
for mode in ("cancel", "failed_repair", "accept"):
    if mode != "accept":
        reset(projection_base)
        proposal = stage(projection_proposed, "source")
    else:
        proposal = staged_edit.current(bpy.context)
        assert proposal is not None  # Retry the exact proposal from failed_repair.
    result = bpy.ops.mcad.replace_projection_reference(
        "EXEC_DEFAULT", feature_id="target", staged_token=proposal.token
    )
    assert result == ({"FINISHED"} if mode == "accept" else {"CANCELLED"})
    if mode == "accept":
        saved = json.loads(bpy.context.scene.mechanical_cad.document_json)
        check(
            feature(saved, "source") == feature(projection_proposed, "source"),
            "Projection repair keeps upstream edit",
        )
        target = feature(saved, "target")
        check(
            target["projections"][0]["source"] == "replacement_ring",
            "Replacement uses explicit authored source identity",
        )
        check(
            any(c["id"] == "match" for c in target["sketch"]["constraints"]),
            "Projection repair retains equal relation",
        )
        check(
            staged_edit.current(bpy.context) is None,
            "Successful projection repair retires proposal",
        )
        result = doc.current_part_result(bpy.context)
        check(
            all(row["status"] == "ok" for row in result["features"]),
            "Every repaired feature replays successfully",
        )
        check(
            abs(result["features"][-1]["stats"]["volume"] - 80 * math.pi) < 1e-7,
            "Repaired projection drives exact dependent extrusion",
        )

# An upstream failure is not a downstream-reference repair transaction.
reset(projection_base)
invalid = copy.deepcopy(projection_proposed)
feature(invalid, "source")["sketch"]["constraints"][1]["value"] = -1
before = snapshot()
reject(lambda: doc._commit_candidate(bpy.context, invalid, stage_feature_id="source"))
check(
    staged_edit.current(bpy.context) is None,
    "Failed upstream geometry is not staged as reference repair",
)
check(snapshot() == before, "Upstream failure preserves accepted authority")

# Exact accepted base, unit scale and backend generation invalidate old tokens.
for change in ("base", "units", "backend", "deflection"):
    reset(projection_base)
    proposal = stage(projection_proposed, "source")
    scene = bpy.context.scene
    if change == "base":
        scene.mechanical_cad.document_json += " "
    elif change == "units":
        scene.unit_settings.scale_length *= 2
    elif change == "backend":
        backend_runtime.revoke("Test backend changed")
    else:
        selection, deflection = backend_runtime.configuration(bpy.context)
        with patch.object(
            backend_runtime, "configuration", return_value=(selection, deflection * 2)
        ):
            reject(lambda token=proposal.token: staged_edit.require(bpy.context, token), "expired")
            check(
                staged_edit.current(bpy.context) is None,
                "Changed tessellation settings retire proposal",
            )
    reject(lambda token=proposal.token: staged_edit.require(bpy.context, token), "expired")
    check(
        staged_edit.current(bpy.context) is None, "Changed " + change + " invalidates old proposal"
    )
    if change == "units":
        scene.unit_settings.scale_length /= 2

# Native save writes accepted JSON only, and native load retires another proposal.
with tempfile.TemporaryDirectory(prefix="mcad-staged-") as directory:
    reset(projection_base)
    accepted = bpy.context.scene.mechanical_cad.document_json
    proposal = stage(projection_proposed, "source")
    document_path = str(Path(directory) / "accepted_only.mcad.json")
    assert bpy.ops.mcad.save_document(filepath=document_path) == {"FINISHED"}
    check(
        json.loads(Path(document_path).read_text()) == json.loads(accepted),
        "JSON Save writes accepted model, never retained candidate",
    )
    check(staged_edit.current(bpy.context) is proposal, "JSON Save keeps the proposal available")
    step_path = str(Path(directory) / "accepted_only.step")
    assert geometry_operations.run_geometry_action(
        bpy.context, "export_step", destination=step_path
    )
    state = bpy.context.scene.mechanical_cad
    check(
        state.document_json == accepted and state.geometry_document_json == accepted,
        "STEP export replay/report binds accepted canonical model only",
    )
    report = json.loads(state.geometry_report_json)
    check(
        abs(report["geometry_check"]["brep"]["volume"] - 45 * math.pi) < 1e-7,
        "STEP export checks accepted radius 3, not proposed radius 4",
    )
    check(
        Path(step_path).is_file() and Path(step_path).stat().st_size > 0,
        "Real native STEP export writes accepted geometry",
    )
    check(
        staged_edit.current(bpy.context) is proposal and proposal.document == projection_proposed,
        "STEP export neither accepts nor changes retained proposal",
    )
    blend = str(Path(directory) / "accepted_only.blend")
    assert bpy.ops.wm.save_as_mainfile(filepath=blend) == {"FINISHED"}
    check(
        staged_edit.current(bpy.context) is None,
        "Successful native save suspends the checkpointed proposal",
    )
    check(
        bpy.context.scene.mechanical_cad.document_json == accepted,
        "Native save preserves accepted canonical bytes",
    )
    check(
        bool(bpy.context.scene.mechanical_cad.repair_intent_json),
        "Save retains separate repair intent",
    )
    assert bpy.ops.mcad.discard_saved_repair() == {"FINISHED"}
    stage(projection_proposed, "source")
    assert bpy.ops.wm.open_mainfile(filepath=blend) == {"FINISHED"}
    check(
        staged_edit.current(bpy.context) is None,
        "Native load retires the previous session proposal",
    )
    check(
        bpy.context.scene.mechanical_cad.document_json == accepted,
        "Reopened blend contains only accepted model",
    )
    assert doc.regenerate(bpy.context)
    assert bpy.ops.mcad.discard_saved_repair() == {"FINISHED"}

# Actual session Undo/Redo uses canonical snapshots, never proposal persistence.
reset(projection_base)
bpy.context.preferences.edit.use_global_undo = True
accepted = bpy.context.scene.mechanical_cad.document_json
bpy.ops.ed.undo_push(message="Accepted projected part")
bpy.context.scene["staged_repair_audit"] = 1
bpy.ops.ed.undo_push(message="Unrelated native change")
stage(projection_proposed, "source")
check(bpy.ops.ed.undo() == {"FINISHED"}, "Native Undo runs")
check(staged_edit.current(bpy.context) is None, "Native Undo retires a staged proposal")
check(
    bpy.context.scene.mechanical_cad.document_json == accepted,
    "Native Undo does not accept transient proposal",
)

reset(projection_base)
accepted = bpy.context.scene.mechanical_cad.document_json
bpy.ops.ed.undo_push(message="Before accepted repair")
proposal = stage(projection_proposed, "source")
mode = "accept"
assert bpy.ops.mcad.replace_projection_reference(
    "EXEC_DEFAULT", feature_id="target", staged_token=proposal.token
) == {"FINISHED"}
repaired_json = bpy.context.scene.mechanical_cad.document_json
bpy.ops.ed.undo_push(message="Accepted complete repair")
check(bpy.ops.ed.undo() == {"FINISHED"}, "Native Undo restores a repair as one canonical change")
check(
    bpy.context.scene.mechanical_cad.document_json == accepted,
    "Undo restores both old source and old reference",
)
check(staged_edit.current(bpy.context) is None, "Undo never resurrects proposal storage")
check(bpy.ops.ed.redo() == {"FINISHED"}, "Native Redo restores accepted repair")
check(
    bpy.context.scene.mechanical_cad.document_json == repaired_json,
    "Redo restores upstream edit and reference together",
)
check(staged_edit.current(bpy.context) is None, "Redo has no pending proposal")
assert doc.regenerate(bpy.context)

unregister()
print("MCAD_STAGED_EDIT_REPAIR_RESULT=" + json.dumps({"ok": True, "checks": checks}), flush=True)
