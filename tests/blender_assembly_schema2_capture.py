"""Authentic viewport schema-2 capture, native reopen, edit and all-instance update.

The fixture is the exact user-authored GUI regression, including omitted optional
constraint fields, formulas, numeric normalization and nonlexical entity order.
"""

import copy
import json
import math
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
os.environ["MCAD_ROOT"] = str(ROOT)
os.environ.setdefault("MCAD_PYTHON", str(ROOT / ".venv/bin/python"))
sys.path.insert(0, str(ROOT / "blender_addon"))
sys.path.insert(0, str(ROOT / "tests"))
from blender_async_helpers import replay_assembly  # noqa: E402
from mechanical_cad_blender import (  # noqa: E402
    assembly_display,
    assembly_pending,
    assembly_state,
    bridge,
    guarded_operations,
    part_snapshot_bridge,
    register,
    unregister,
)
from mechanical_cad_blender.assembly_operator_helpers import canonical_working_part  # noqa: E402

checks = []


def check(value, label):
    assert value, label
    checks.append(label)


def part_state():
    return bpy.context.scene.mechanical_cad


def assembly_storage():
    return bpy.context.scene.mechanical_cad_assembly


def data():
    return assembly_state.read_assembly(assembly_storage())


def identity(document):
    result = {key: copy.deepcopy(document[key]) for key in ("parts", "instances", "joints")}
    for part in result["parts"]:
        part.pop("source_digest")
    return result


def verify_dimensions(width):
    objects = assembly_display.owned_objects(bpy.context.scene, assembly_storage().owner_id)
    instances = [obj for obj in objects if obj.get(assembly_display.ROLE_KEY) == "instance"]
    check(len(instances) == 2, "both source instances exist")
    for obj in instances:
        for actual, expected in zip(obj.dimensions, (width / 1000, 0.008, 0.004), strict=True):
            check(math.isclose(actual, expected, rel_tol=1e-5), "instance mesh has updated size")
    check(instances[0].data == instances[1].data, "both instances share the accepted mesh")


register()
phase = os.environ.get("MCAD_CAPTURE_PHASE", "save")
if phase == "reopen":
    path = Path(os.environ["MCAD_CAPTURE_BLEND"])
    saved = json.loads(path.with_suffix(".json").read_text())
    bpy.ops.wm.open_mainfile(filepath=str(path))
    check(part_state().document_json == saved["working"], "native reopen preserves exact raw Part")
    check(assembly_storage().document_json == saved["assembly"], "native reopen preserves snapshot")
    check(not assembly_state.source_updates(bpy.context), "canonical defaults are not an update")
    check(replay_assembly() == {"FINISHED"}, "reopened assembly freshly replays")
    old = data()
    check(bpy.ops.mcad.assembly_check() == {"FINISHED"}, "schema-2 report freshly generated")
    old_report = json.loads(assembly_storage().report_json)
    check(
        old["part_sources"][0]["source_digest"] in json.dumps(old_report),
        "report binds source hash",
    )
    parameter = next(row for row in part_state().parameters if row.key == "sketch_1_width")
    parameter.expression = "12 + 4"
    check(bpy.ops.mcad.regenerate() == {"FINISHED"}, "normal Part edit replays original features")
    edited_raw = part_state().document_json
    edited = json.loads(edited_raw)
    original = json.loads(saved["working"])
    check(
        edited["features"] == original["features"], "stable feature/entity IDs, seeds and formulas"
    )
    check(
        len(assembly_state.source_updates(bpy.context)[0]["instance_ids"]) == 2,
        "update names both instances",
    )
    check(assembly_storage().document_json == saved["assembly"], "edit does not publish assembly")
    check(bpy.ops.mcad.assembly_update_source() == {"FINISHED"}, "explicit source update succeeds")
    updated = data()
    check(identity(updated) == identity(old), "definition/frame/instance/joint identity retained")
    check(part_state().document_json == edited_raw, "update preserves raw working Part bytes")
    check(not assembly_state.source_updates(bpy.context), "accepted canonical revision is current")
    receipt = part_snapshot_bridge.canonical_snapshot(edited)
    check(
        updated["part_sources"][0]["source_digest"] == receipt["content_hash"],
        "authoritative hash used uniformly",
    )
    check(
        updated["part_sources"][0]["document"] == receipt["canonical_document"],
        "exact canonical source embedded",
    )
    verify_dimensions(16)
    check(not assembly_state.report_is_current(bpy.context), "source publication revokes old check")
    check(bpy.ops.mcad.assembly_check() == {"FINISHED"}, "updated source check succeeds")
    new_report = json.loads(assembly_storage().report_json)
    check(
        new_report["report_fingerprint"] != old_report["report_fingerprint"],
        "source update changes evidence identity",
    )
    check(receipt["content_hash"] in json.dumps(new_report), "new report binds new source hash")

    # A late raw Part edit must block a pending response even when native geometry
    # has already completed. No ready response becomes current after this edit.
    pending = assembly_pending.prepare(bpy.context, "assembly_check")
    part_state().document_json = edited_raw.replace("12 + 4", "12 + 5")
    failed = False
    deadline = time.monotonic() + 70
    while time.monotonic() < deadline:
        try:
            result = assembly_pending.poll(bpy.context, pending)
        except bridge.BridgeError:
            failed = True
            break
        check(result is None, "late-input response is never published")
        time.sleep(0.01)
    check(failed and pending.done, "pending schema-2 edit rejects and cleans up")
    check(
        not assembly_state.report_is_current(bpy.context),
        "late edit cannot retain current evidence",
    )
    part_state().document_json = edited_raw

    # The added capture exchange itself is bound to exact raw state.
    accepted = assembly_storage().document_json
    real_snapshot = guarded_operations.canonical_snapshot_guarded

    def change_during_snapshot(document, **options):
        result = real_snapshot(document, **options)
        part_state().document_json = edited_raw.replace("12 + 4", "12 + 6")
        return result

    with patch.object(guarded_operations, "canonical_snapshot_guarded", change_during_snapshot):
        try:
            canonical_working_part(bpy.context)
        except bridge.BridgeError:
            checks.append("snapshot rejects newer working edit")
        else:
            raise AssertionError("late snapshot accepted")
    check(assembly_storage().document_json == accepted, "snapshot failure keeps accepted assembly")
else:
    fixture = ROOT / "examples/regressions/viewport_schema2_capture.mcad.json"
    check(
        bpy.ops.mcad.load_document(filepath=str(fixture)) == {"FINISHED"}, "exact GUI fixture loads"
    )
    working = part_state().document_json
    check(math.isclose(part_state().volume, 384, rel_tol=1e-6), "authentic 12x8x4 Part")
    check(
        bpy.ops.mcad.assembly_new(name="Viewport source regression", grounded=True) == {"FINISHED"},
        "viewport schema-2 captured",
    )
    check(part_state().document_json == working, "capture never normalizes editor bytes")
    check(not assembly_state.source_updates(bpy.context), "capture has no spurious source notice")
    part, root = data()["parts"][0]["id"], data()["grounded_instance"]
    check(
        bpy.ops.mcad.assembly_insert(
            part_id=part,
            parent=root,
            parent_frame="origin",
            child_frame="origin",
            kind="slider",
            coordinate="20",
            name="Reused block",
        )
        == {"FINISHED"},
        "second instance reuses captured definition",
    )
    verify_dimensions(12)
    with tempfile.TemporaryDirectory(prefix="mcad-schema2-capture-") as directory:
        path = Path(directory) / "captured.blend"
        path.with_suffix(".json").write_text(
            json.dumps({"working": working, "assembly": assembly_storage().document_json})
        )
        check(
            bpy.ops.wm.save_as_mainfile(filepath=str(path)) == {"FINISHED"}, "native snapshot saved"
        )
        environment = dict(os.environ, MCAD_CAPTURE_PHASE="reopen", MCAD_CAPTURE_BLEND=str(path))
        command = (
            [
                bpy.app.binary_path,
                "--background",
                "--factory-startup",
                "--python-exit-code",
                "1",
                "--python-expr",
                "import sys; sys.dont_write_bytecode = True",
                "--python",
                str(Path(__file__).resolve()),
            ]
            if bpy.app.binary_path
            else [sys.executable, str(Path(__file__).resolve())]
        )
        child = subprocess.run(
            command, env=environment, text=True, capture_output=True, timeout=180
        )
        check(child.returncode == 0, f"fresh-process regression: {child.stdout}\n{child.stderr}")
        check('"phase": "reopen"' in child.stdout, "actual reopen phase completed")
        print(child.stdout)
check(
    not any(name == "OCP" or name.startswith("OCP.") or name == "slvs" for name in sys.modules),
    "native CAD remains isolated",
)
unregister()
print(
    "ASSEMBLY_SCHEMA2_CAPTURE_RESULT="
    + json.dumps({"ok": True, "phase": phase, "checks": len(checks)})
)
