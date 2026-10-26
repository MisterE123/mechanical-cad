"""Real native Blender transaction tests; deliberately independent of registration.

blender --background --factory-startup --python-exit-code 1 \
    --python tests/blender_assembly_state_smoke.py
"""

import copy
import json
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy
from bpy.props import PointerProperty

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
os.environ["MCAD_ROOT"] = str(ROOT)
os.environ.setdefault("MCAD_PYTHON", str(ROOT / ".venv/bin/python"))
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import assembly_bridge as boundary  # noqa: E402
from mechanical_cad_blender import assembly_display as display  # noqa: E402
from mechanical_cad_blender import assembly_edit as edit  # noqa: E402
from mechanical_cad_blender import assembly_state as state_api  # noqa: E402
from mechanical_cad_blender import bridge, document_state  # noqa: E402
from mechanical_cad_blender.assembly_properties import MCAD_AssemblyState  # noqa: E402
from mechanical_cad_blender.properties import MCAD_Feature, MCAD_Parameter, MCAD_State  # noqa: E402

checks = []


def assert_that(condition, label):
    if not condition:
        raise AssertionError(label)
    checks.append(label)


def reject(operation, label):
    try:
        operation()
    except (bridge.BridgeError, RuntimeError, ValueError):
        checks.append(label)
        return
    raise AssertionError(label)


for cls in (MCAD_Parameter, MCAD_Feature, MCAD_State, MCAD_AssemblyState):
    bpy.utils.register_class(cls)
bpy.types.Scene.mechanical_cad = PointerProperty(type=MCAD_State)
bpy.types.Scene.mechanical_cad_assembly = PointerProperty(type=MCAD_AssemblyState)
context, scene = bpy.context, bpy.context.scene
state, part_state = scene.mechanical_cad_assembly, scene.mechanical_cad

if os.environ.get("MCAD_ASSEMBLY_STATE_REOPEN"):
    expected = json.loads(Path(os.environ["MCAD_ASSEMBLY_STATE_REOPEN"]).read_text())
    assert_that(
        state.document_json == expected["assembly"], "canonical assembly survives actual reload"
    )
    assert_that(part_state.document_json == expected["part"], "Part bytes survive actual reload")
    assert_that(state.report_json == expected["report"], "evidence survives actual reload")
    assert_that(state.document_path == expected["path"], "assembly path survives actual reload")
    state_api.after_file_load()
    assert_that(not state_api.report_is_current(context), "reloaded evidence is not trusted")
    assert_that(state.display_status == "STALE", "reloaded geometry marked stale")
    state_api.replay(context)
    assert_that(state_api.display_is_current(context), "fresh replay restores loaded geometry")
    assert_that(
        not state_api.report_is_current(context), "replay does not restore old verification"
    )
    response = state_api.check(context)
    assert_that(
        response["report"]["verification_basis"]["preset_id"] == "clearance",
        "saved preset survives reload",
    )
    assert_that(state_api.report_is_current(context), "fresh check restores only current evidence")
    print("ASSEMBLY_STATE_REOPEN_OK", len(checks))
    raise SystemExit(0)

# Author an ordinary schema-1 Part, rather than load the mechanism fixture.
part = {
    "schema_version": 1,
    "id": "transaction_user_part",
    "name": "User-made bracket",
    "units": "mm",
    "parameters": {"width": 17.125},
    "active_feature": "pad",
    "features": [
        {
            "id": "outline",
            "kind": "sketch_rectangle",
            "label": "My outline",
            "inputs": {},
            "params": {
                "width": "width",
                "height": 8.375,
                "x": 123.456789,
                "y": -23.456789,
                "z": 6.25,
            },
        },
        {
            "id": "pad",
            "kind": "extrude",
            "label": "My pad",
            "inputs": {"profile": "outline"},
            "params": {"length": 7.875},
        },
    ],
}
document_state._populate_document(scene, part)
document_state.regenerate(context)
part_bytes = part_state.document_json
part_objects = set(scene.objects)
original = edit.new_from_part(part, name="Reusable user assembly")
original["ground"] = {
    "xyz_mm": [12.3456789, -34.56789, 56.789],
    "wxyz": [math.cos(math.pi / 4), 0.0, 0.0, math.sin(math.pi / 4)],
}
response = state_api.commit_candidate(context, original)
assert_that(part_state.document_json == part_bytes, "capture preserves exact working Part JSON")
assert_that(
    response["result"]["canonical_assembly"]["part_sources"][0]["document"] == part,
    "embedded Part fields retain original schema-1 snapshot",
)
assert_that(state_api.display_is_current(context), "initial accepted display is current")
assert_that(not state_api.report_is_current(context), "replay never creates verification")
canonical = state_api.read_assembly(state)
part_id, root_id = canonical["parts"][0]["id"], canonical["grounded_instance"]
for coordinate in (80.0, 160.0):
    canonical = edit.insert_instance(
        canonical,
        part_id,
        parent=root_id,
        parent_frame="origin",
        child_frame="origin",
        kind="slider",
        coordinate=coordinate,
        limits=[20.0, 300.0],
        name="Repeated bracket",
    )
response = state_api.commit_candidate(context, canonical, expected_json=state.document_json)
assert_that(
    len(response["result"]["instances"]) == 3, "one user definition reused by three instances"
)
assert_that(
    part_objects <= set(scene.objects), "assembly publication preserves independent Part display"
)
assert_that(part_state.document_json == part_bytes, "assembly insertion preserves exact Part bytes")
owned = display.owned_objects(scene, state.owner_id)
instances = [o for o in owned if o.get(display.ROLE_KEY) == "instance"]
assert_that(
    len({o.data.as_pointer() for o in instances}) == 1, "instances share definition display mesh"
)
context.view_layer.update()
for obj in instances:
    pose = response["report"]["base_pose"]["transforms"][obj[display.INSTANCE_KEY]]
    for vertex, point in zip(
        obj.data.vertices, response["result"]["parts"][0]["mesh"]["vertices"], strict=True
    ):
        rotated = display._rotate(pose["wxyz"], point)
        expected = [(p + t) * 0.001 for p, t in zip(rotated, pose["xyz_mm"], strict=True)]
        assert_that(
            all(
                math.isclose(a, b, abs_tol=2e-7)
                for a, b in zip(obj.matrix_world @ vertex.co, expected, strict=True)
            ),
            "transaction publishes recentered rotated coordinates",
        )

unconfigured = state_api.check(context)
assert_that(
    unconfigured["ok"] and not unconfigured["report"]["passed"],
    "no preset yields measurements without pass",
)
assert_that(
    state_api.report_is_current(context), "unconfigured report is current evidence, not a pass"
)
canonical = state_api.read_assembly(state)
canonical["verification_presets"] = [
    {
        "id": "clearance",
        "name": "Named engineering clearance",
        "kind": "clearance",
        "requirements": [
            {
                "id": "root_gap",
                "name": "Root to first child",
                "instances": sorted([root_id, canonical["instances"][1]["id"]]),
                "minimum_mm": 10.0,
            }
        ],
        "policy": copy.deepcopy(boundary.DEFAULT_POLICY),
    }
]
canonical["active_verification_preset"] = "clearance"
state_api.commit_candidate(context, canonical)
assert_that(
    not state_api.report_is_current(context), "persisted preset edit invalidates old verification"
)
response = state_api.check(context)
assert_that(
    response["report"]["passed"] and state_api.report_is_current(context),
    "explicit preset pass remains exact-pose evidence",
)
assert_that(state.report_preset_id == "clearance", "active preset binding stored explicitly")
boundary.validate_response(json.loads(state.report_request_json), json.loads(state.report_json))
assert_that(
    state.report_document_json == state.document_json, "report binds exact accepted JSON text"
)

before_json, before_objects = state.document_json, set(scene.objects)
joints = state_api.read_assembly(state)["joints"]
sampled = state_api.sample(context, joints[0]["id"], [40.0, 60.0])
assert_that(
    state.document_json == before_json and set(scene.objects) == before_objects,
    "sampling changes evidence only, never canonical pose or display",
)
assert_that(
    all(
        p["pose"]["effective_coordinates"][joints[1]["id"]] == 160.0
        for p in sampled["report"]["poses"]
    ),
    "sampling retains every nonsampled base coordinate",
)
assert_that(state_api.report_is_current(context), "sample request and exact values remain bound")


# Every failing phase retains the accepted canonical text, Part, display identities,
# and prior exact evidence. Failure diagnostics intentionally change separately.
def preserved_failure(operation, label):
    accepted = state.document_json
    expected_part = part_state.document_json
    old_report = state.report_json
    objects = {o.as_pointer() for o in scene.objects}
    reject(operation, label)
    assert_that(state.document_json == accepted, label + ": canonical restored")
    assert_that(part_state.document_json == expected_part, label + ": Part untouched")
    assert_that(
        {o.as_pointer() for o in scene.objects} == objects, label + ": exact display restored"
    )
    assert_that(state.report_json == old_report, label + ": prior evidence retained")
    assert_that(bool(state.last_action_error), label + ": diagnostics retained")
    assert_that(state_api.display_is_current(context), label + ": accepted display remains trusted")


candidate = edit.edit_joint(
    state_api.read_assembly(state), joints[0]["id"], coordinate=90.0, limits=[20.0, 300.0]
)
with patch.object(
    state_api, "_run_sidecar", side_effect=bridge.BridgeError("Injected native failure")
):
    preserved_failure(
        lambda: state_api.commit_candidate(context, candidate), "native failure rollback"
    )
configure = display._configure
count = [0]


def broken_configure(*args):
    count[0] += 1
    configure(*args)
    if count[0] == 2:
        raise RuntimeError("Injected staging failure")


with patch.object(display, "_configure", broken_configure):
    preserved_failure(
        lambda: state_api.commit_candidate(context, candidate), "partial staging rollback"
    )
link = display._link
count[0] = 0


def broken_link(*args):
    count[0] += 1
    if count[0] == 2:
        raise RuntimeError("Injected publish failure")
    return link(*args)


with patch.object(display, "_link", broken_link):
    preserved_failure(
        lambda: state_api.commit_candidate(context, candidate), "partial publication rollback"
    )
write = state_api._write_fields


def broken_write(target, values):
    write(target, dict(list(values.items())[:5]))
    raise RuntimeError("Injected canonical write failure")


with patch.object(state_api, "_write_fields", broken_write):
    preserved_failure(
        lambda: state_api.commit_candidate(context, candidate), "partial state write rollback"
    )
with patch.object(state_api, "_write_fields", broken_write):
    preserved_failure(lambda: state_api.check(context), "partial evidence write rollback")

# Two independent failures must not strand the newly written canonical snapshot
# beside the restored old display. Recovery diagnostics must survive operator
# exception handling, so both causes also appear in the raised BridgeError.
accepted_before_cleanup = state.document_json
name_before_cleanup = state.document_name
report_before_cleanup = state.report_json
objects_before_cleanup = {o.as_pointer() for o in scene.objects}
all_objects_before_cleanup = set(bpy.data.objects)
all_meshes_before_cleanup = set(bpy.data.meshes)
compound_candidate = copy.deepcopy(candidate)
compound_candidate["name"] = "Must never survive failed acceptance"
cleanup_failure = "Injected orphan cleanup failure"
with (
    patch.object(state_api, "_write_fields", broken_write),
    patch.object(display, "_remove_orphans", side_effect=RuntimeError(cleanup_failure)),
):
    try:
        state_api.commit_candidate(context, compound_candidate)
    except bridge.BridgeError as exc:
        assert_that(
            "Injected canonical write failure" in str(exc) and cleanup_failure in str(exc),
            "compound rollback raises both primary and cleanup diagnostics",
        )
    else:
        raise AssertionError("compound rollback must reject acceptance")
assert_that(
    state.document_json == accepted_before_cleanup and state.document_name == name_before_cleanup,
    "cleanup failure cannot skip exact canonical/name restoration",
)
assert_that(
    {o.as_pointer() for o in scene.objects} == objects_before_cleanup,
    "compound failure retains exact old linked display objects",
)
assert_that(
    state.report_json == report_before_cleanup and part_state.document_json == part_bytes,
    "compound failure restores old evidence and preserves working Part",
)
assert_that(
    state.status == "FAILED" and state.display_status == "STALE",
    "unresolved cleanup is visibly FAILED, never READY",
)
assert_that(
    "Injected canonical write failure" in state.last_action_error
    and cleanup_failure in state.last_action_error,
    "compound recovery retains both diagnostics in state",
)
assert_that(
    not state_api.display_is_current(context) and not state_api.report_is_current(context),
    "incomplete rollback revokes every currentness capability",
)
assert_that(scene.as_pointer() not in state_api._BUSY, "compound failure releases transaction lock")
# The injected cleanup refusal deliberately left detached new resources. Removing
# just those test-created orphans allows subsequent tests to assert no leaks.
display._remove_orphans(
    list(set(bpy.data.objects) - all_objects_before_cleanup),
    list(set(bpy.data.meshes) - all_meshes_before_cleanup),
    state.owner_id,
)
state_api.replay(context)
state_api.check(context)

accepted = state.document_json
run = state_api._run_sidecar


def late_part(*args, **kwargs):
    result = run(*args, **kwargs)
    part_state.document_json = part_bytes + "\n"
    return result


with patch.object(state_api, "_run_sidecar", late_part):
    reject(
        lambda: state_api.commit_candidate(context, candidate),
        "late working-Part revision rejected",
    )
assert_that(
    state.document_json == accepted and part_state.document_json == part_bytes + "\n",
    "late rejection never overwrites newer Part edit",
)
part_state.document_json = part_bytes


def late_assembly(*args, **kwargs):
    result = run(*args, **kwargs)
    state.document_json = accepted + "\n"
    return result


with patch.object(state_api, "_run_sidecar", late_assembly):
    reject(
        lambda: state_api.commit_candidate(context, candidate), "late canonical revision rejected"
    )
assert_that(
    state.document_json == accepted + "\n", "late rejection never rewinds newer assembly revision"
)
state.document_json = accepted
state_api.replay(context)
# Window identity is independent of scene identity; scene-only internal helper
# contexts remain supported without manufacturing a UI window.
window_context = SimpleNamespace(scene=scene, window=context.window)
window_snapshot = state_api._capture(window_context, scene)
window_context.window = SimpleNamespace(as_pointer=lambda: context.window.as_pointer() + 1)
reject(
    lambda: state_api._assert_current(window_context, window_snapshot),
    "a different window cannot accept a request for the same scene",
)
scene_context = SimpleNamespace(scene=scene)
state_api._assert_current(scene_context, state_api._capture(scene_context, scene))
assert_that(True, "scene-only contexts remain supported without window identity")

# The real Blender context is mutable: a cloned scene can match every old byte
# while the original scene receives a newer edit. Scene identity must be pinned,
# and error recovery must still target the original scene after a window switch.
for operation_name in ("commit", "check", "save validation"):
    state_api.replay(context)
    state_api.check(context)
    switch_accepted = state.document_json
    switch_report = state.report_json
    switch_display = {o.as_pointer() for o in scene.objects}
    other_scene = scene.copy()
    other_state = other_scene.mechanical_cad_assembly
    other_fields = {name: getattr(other_state, name) for name in state_api._STATE_FIELDS}

    def late_scene_switch(*args, original_json=switch_accepted, target_scene=other_scene, **kwargs):
        result = run(*args, **kwargs)
        state.document_json = original_json + "\n"
        context.window.scene = target_scene
        return result

    operation = {
        "commit": lambda: state_api.commit_candidate(context, candidate),
        "check": lambda: state_api.check(context),
        "save validation": lambda: state_api.validate_snapshot(context),
    }[operation_name]
    try:
        with patch.object(state_api, "_run_sidecar", late_scene_switch):
            reject(operation, operation_name + ": real scene switch rejects late response")
        assert_that(
            state.document_json == switch_accepted + "\n",
            operation_name + ": newer original scene edit is never overwritten",
        )
        assert_that(
            state.report_json == switch_report
            and {o.as_pointer() for o in scene.objects} == switch_display,
            operation_name + ": original scene evidence/display remain unchanged",
        )
        assert_that(
            other_fields == {name: getattr(other_state, name) for name in state_api._STATE_FIELDS},
            operation_name + ": rejection never writes diagnostics into newly active scene",
        )
        assert_that(
            "scene changed" in state.last_action_error,
            operation_name + ": original target receives scene-switch diagnostic",
        )
    finally:
        context.window.scene = scene
        bpy.data.scenes.remove(other_scene)
    state.document_json = switch_accepted
state_api.replay(context)

part_state.sketch_draft_json = '{"saved":"draft"}'
reject(
    lambda: state_api.commit_candidate(context, candidate),
    "suspended sketch draft blocks assembly mutation",
)
part_state.sketch_draft_json = ""
with patch.object(state_api.workspace, "active_draft", return_value=object()):
    reject(
        lambda: state_api.commit_candidate(context, candidate),
        "active sketch draft blocks assembly mutation",
    )

# Explicit source update touches all repeated instances and leaves literal frames.
state_api.check(context)
updated = copy.deepcopy(part)
updated["parameters"]["width"] = 29.875
part_state.document_json = json.dumps(updated, indent=4)
updates = state_api.source_updates(context)
assert_that(
    len(updates) == 1 and len(updates[0]["instance_ids"]) == 3,
    "working update names all three affected instances",
)
assert_that(
    not state_api.report_is_current(context), "working source update invalidates verification"
)
frames = copy.deepcopy(state_api.read_assembly(state)["parts"][0]["mate_frames"])
replacement, affected = edit.update_source(state_api.read_assembly(state), updated)
updated_part_bytes = part_state.document_json
with patch.object(state_api, "_write_fields", broken_write):
    preserved_failure(
        lambda: state_api.commit_candidate(context, replacement),
        "all-instance source publication rollback",
    )
state_api.commit_candidate(context, replacement)
assert_that(
    len(affected) == 3 and not state_api.source_updates(context),
    "source-wide acceptance replaces every instance revision",
)
assert_that(
    part_state.document_json == updated_part_bytes,
    "source update preserves exact working Part bytes",
)
assert_that(
    state_api.read_assembly(state)["parts"][0]["mate_frames"] == frames,
    "source update retains literal datum coordinates",
)
assert_that(
    not state_api.report_is_current(context), "accepted source replacement clears old report trust"
)
assert_that(state_api.display_is_current(context), "all updated instances publish together")

# Currentness is fail closed and revocation survives manually undoing corruption.
state_api.check(context)
obj = next(o for o in display.owned_objects(scene, state.owner_id) if o.type == "MESH")
location = obj.location.copy()
obj.location.x += 1.0
query_fields = {name: getattr(state, name) for name in state_api._STATE_FIELDS}
query_epoch = state_api._EPOCHS.get(scene.as_pointer())
for _ in range(3):
    state_api.display_is_current(context)
    state_api.report_is_current(context)
    state_api.source_updates(context)
assert_that(
    query_fields == {name: getattr(state, name) for name in state_api._STATE_FIELDS}
    and query_epoch == state_api._EPOCHS.get(scene.as_pointer()),
    "repeated draw queries never mutate RNA or invalidation epochs",
)
state_api.depsgraph_update(scene)
assert_that(not state_api.report_is_current(context), "manual object transform invalidates report")
obj.location = location
assert_that(
    not state_api.report_is_current(context), "undoing manual corruption does not resurrect report"
)
assert_that(
    state_api.display_is_current(context),
    "geometric integrity remains distinct from evidence status",
)
state_api.check(context)
vertex = obj.data.vertices[0].co.copy()
obj.data.vertices[0].co.x += 0.001
state_api.depsgraph_update(scene)
assert_that(
    state.display_status == "STALE" and not state_api.report_is_current(context),
    "manual mesh edit invalidates display and report",
)
obj.data.vertices[0].co = vertex
state_api.replay(context)
state_api.check(context)
scene.unit_settings.scale_length = 0.01
state_api.depsgraph_update(scene)
assert_that(not state_api.report_is_current(context), "scene unit change invalidates evidence")
state_api.replay(context)
assert_that(state_api.display_is_current(context), "unit-aware replay restores scaled display")
state_api.check(context)
state_api.before_history_change()
state_api.after_history_change()
assert_that(
    not state_api.report_is_current(context), "Undo/Redo hooks revoke persisted report trust"
)
state_api.replay(context)
state_api.check(context)
state_api.rebind_existing()
assert_that(not state_api.report_is_current(context), "add-on rebind revokes report trust")
state_api.replay(context)
state_api.check(context)
state.report_request_json += " "
assert_that(
    not state_api.report_is_current(context), "persisted request byte tamper invalidates report"
)
state_api.check(context)

# Save validation never renews or replaces existing accepted evidence.
save_snapshot = {name: getattr(state, name) for name in state_api._STATE_FIELDS}
save_objects = {o.as_pointer() for o in scene.objects}
save_validation = state_api.validate_snapshot(context)
assert_that(save_validation["ok"], "save validation freshly replays canonical source")
assert_that(
    save_snapshot == {name: getattr(state, name) for name in state_api._STATE_FIELDS},
    "save validation preserves all state and evidence bytes",
)
assert_that(
    save_objects == {o.as_pointer() for o in scene.objects},
    "save validation leaves display identities untouched",
)
part_state.sketch_draft_json = '{"saved":"draft"}'
reject(lambda: state_api.validate_snapshot(context), "saved draft blocks save validation")
reject(lambda: state_api.check(context), "saved draft blocks exact check")
reject(lambda: state_api.sample(context, joints[0]["id"], [40.0]), "saved draft blocks sample")
part_state.sketch_draft_json = ""

# A schema-2 source is separately captured without changing the schema-1 assembly.
second_scene = bpy.data.scenes.new("Schema 2 source capture")
second_part = json.loads((ROOT / "examples/viewport_rectangle.mcad.json").read_text())
second_scene.mechanical_cad.document_json = json.dumps(second_part, indent=4)
second_bytes = second_scene.mechanical_cad.document_json
with context.temp_override(scene=second_scene):
    state_api.commit_candidate(context, edit.new_from_part(second_part, name="Schema 2 assembly"))
    assert_that(
        second_scene.mechanical_cad.document_json == second_bytes,
        "schema-2 capture preserves exact working JSON",
    )
    assert_that(
        state_api.read_assembly(second_scene.mechanical_cad_assembly)["part_sources"][0]["document"]
        == second_part,
        "schema-2 embedded snapshot unchanged",
    )
assert_that(state_api.display_is_current(context), "second scene leaves first scene current")

# Actual save/reopen in a separate native process; no registration handler assumptions.
state.document_path = "/tmp/user-assembly.mcad-assembly.json"
with tempfile.TemporaryDirectory(prefix="mcad-assembly-state-") as directory:
    path = Path(directory)
    manifest = path / "expected.json"
    manifest.write_text(
        json.dumps(
            {
                "assembly": state.document_json,
                "part": part_state.document_json,
                "report": state.report_json,
                "path": state.document_path,
            }
        )
    )
    state_api.before_file_save()
    bpy.ops.wm.save_as_mainfile(filepath=str(path / "assembly.blend"))
    env = dict(os.environ, MCAD_ASSEMBLY_STATE_REOPEN=str(manifest))
    completed = subprocess.run(
        [
            bpy.app.binary_path,
            "--background",
            str(path / "assembly.blend"),
            "--python-exit-code",
            "1",
            "--python-expr",
            "import sys; sys.dont_write_bytecode = True",
            "--python",
            str(Path(__file__).resolve()),
        ],
        env=env,
        text=True,
        capture_output=True,
        timeout=180,
    )
    assert_that(
        completed.returncode == 0 and "ASSEMBLY_STATE_REOPEN_OK" in completed.stdout,
        "actual second-process save/reopen: " + completed.stdout + completed.stderr,
    )
assert_that(
    not any(name.split(".")[0] in {"OCP", "mechanical_cad", "slvs"} for name in sys.modules),
    "no core or native CAD imported into Blender",
)
print("ASSEMBLY_STATE_SMOKE_OK", len(checks))
