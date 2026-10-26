"""Exactly two native Blender lifetimes; fixture intent/history never authority.

Parent save phase: six registered operations/six serial sidecars. One bounded
reopen child: nine registered operations/nine serial sidecars. Zero separate
readers, replay-oracle calls, automatic retries, GUI claims or third lifetimes.
All exports stay in the exclusive MCAD_GEOMETRY3_PERSISTENCE_DIRECTORY.
Controller must authorize this whole process tree before running either phase.
"""

import copy
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blender_geometry3_owner_smoke as gate_tools  # noqa: E402
from mechanical_cad_blender import (  # noqa: E402
    backend_runtime,
    draft_dispatch,
    execution_lease,
    general_session,
    guarded_transport,
    sketch_annotation_store,
    sketch_session,
    workspace,
)

addon, doc = gate_tools.addon, gate_tools.doc
require, persist = gate_tools.require, gate_tools.persist
state, report = gate_tools.state, gate_tools.report
SAVE_ROWS = ("save_check", "save_step", "save_stl", "save_unknown", "save_outdated", "save_v2")
REOPEN_ROWS = (
    "fresh_check_geometry",
    "fresh_export_step",
    "fresh_export_stl",
    "after_history",
    "after_aba",
    "after_reenable",
    "ordinary_check_geometry",
    "ordinary_export_step",
    "ordinary_export_stl",
)
PHASE = os.environ.get("MCAD_GEOMETRY3_PERSISTENCE_PHASE", "save")
DIRECTORY = Path(os.environ["MCAD_GEOMETRY3_PERSISTENCE_DIRECTORY"]).resolve()
BLEND = DIRECTORY / "geometry3-history.blend"


def saved_fields():
    return {
        "document": state().document_json,
        "draft": state().sketch_draft_json,
        "layout": state().sketch_annotation_json,
        "report": state().geometry_report_json,
        "report_document": state().geometry_document_json,
        "status": state().geometry_status,
        "features": [
            [row.feature_id, row.label, row.kind, row.sketch_report_json, row.sketch_document_json]
            for row in state().features
        ],
    }


def no_work(*args, **kwargs):
    raise AssertionError("Saved reports/intent must not launch or acquire a native lease")


def file_facts():
    return {
        path.name: {"sha256": gate_tools.digest(path), "bytes": path.stat().st_size}
        for path in sorted(DIRECTORY.iterdir())
        if path.suffix in (".step", ".stl")
    }


def assert_files(expected):
    for name, facts in expected.items():
        path = DIRECTORY / name
        require(
            path.stat().st_size == facts["bytes"] and gate_tools.digest(path) == facts["sha256"],
            name + " is unaffected by history/lifetime changes",
        )


def save():
    DIRECTORY.mkdir(parents=True, exist_ok=False)
    gate = gate_tools.NativeGate(DIRECTORY / "save", SAVE_ROWS)
    window, area, region = gate_tools.context_parts()
    expected = {}
    with bpy.context.temp_override(window=window, area=area, region=region):
        success = window.scene
        success.name = "Geometry3 saved success and intent"
        document = gate_tools.sector()
        doc._populate_document(success, document)
        for label, action, name in (
            ("save_check", "check_geometry", None),
            ("save_step", "export_step", "saved_success.step"),
            ("save_stl", "export_stl", "saved_success.stl"),
        ):
            gate.call(label, action, destination=None if name is None else DIRECTORY / name)
            gate_tools.current(action)
        success_report = state().geometry_report_json
        # Author raw pending UI intent with the existing owner, without solve/replay.
        with (
            patch.object(execution_lease, "try_acquire", no_work),
            patch.object(guarded_transport, "GuardedJob", no_work),
        ):
            window.workspace[workspace.ROLE_KEY] = "SKETCH"
            owner = general_session.GeneralSession(bpy.context, "profile")
            owner.start()
            owner.draft.place_annotation("sector_radius", (9, 11))
            annotations = copy.deepcopy(owner.draft.annotations)
            state().sketch_annotation_json = sketch_annotation_store.replace_annotations(
                state().sketch_annotation_json, document["id"], "profile", annotations
            )
            owner.begin_dimension("sector_radius")
            owner.update_raw(" 7 + 0 ")
            owner.checkpoint()
            owner.suspend("Save exact Geometry3 raw radius and label intent")
        require(
            state().geometry_report_json == success_report, "Draft retains exact export history"
        )
        expected[success.name] = saved_fields()
        expected[success.name]["raw_radius"] = " 7 + 0 "
        expected[success.name]["annotations"] = annotations
        window.workspace[workspace.ROLE_KEY] = "PART"

        unknown = bpy.data.scenes.new("Geometry3 saved UNKNOWN")
        window.scene = unknown
        doc._populate_document(unknown, gate_tools.sector())
        gate.call(
            "save_unknown",
            "export_step",
            destination=DIRECTORY / "saved_unknown.step",
            returned=lambda response: {"lost": "after actual file replacement"},
        )
        require(
            state().geometry_status == "UNKNOWN" and report()["export"] is None,
            "Save actual post-write UNKNOWN history",
        )
        gate_tools.unverified()
        expected[unknown.name] = saved_fields()

        outdated = bpy.data.scenes.new("Geometry3 saved OUTDATED")
        window.scene = outdated
        doc._populate_document(outdated, gate_tools.sector())

        def owner_changed(evidence):
            state().owner_id += "_later_owner"
            return evidence

        gate.call(
            "save_outdated",
            "export_step",
            destination=DIRECTORY / "saved_outdated.step",
            execute=owner_changed,
        )
        require(
            state().geometry_status == "OUTDATED" and report()["export"] is not None,
            "Save confirmed same-request historical write",
        )
        gate_tools.unverified()
        expected[outdated.name] = saved_fields()

        ordinary = bpy.data.scenes.new("Geometry2 saved ordinary")
        window.scene = ordinary
        doc._populate_document(ordinary, addon.demo_document())
        gate.call("save_v2", "check_geometry")
        gate_tools.current("check_geometry", 2)
        expected[ordinary.name] = saved_fields()
        window.scene = success
        require(
            sketch_session.active_session() is None and not execution_lease.is_busy(),
            "Save has no active sketch owner or native work",
        )
        persist(
            DIRECTORY / "expected.json",
            {
                "scenes": expected,
                "files": file_facts(),
                "blender_lifetimes": 2,
                "sidecar_ceiling": 15,
            },
        )
        require(
            bpy.ops.wm.save_as_mainfile(filepath=str(BLEND)) == {"FINISHED"},
            "Actual .blend stores all four history/intent scenes",
        )
        gate.finish()
    # Exactly one child; output and cleanup are retained even on a timeout/failure.
    command = [
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
    environment = dict(os.environ, MCAD_GEOMETRY3_PERSISTENCE_PHASE="reopen")
    process = subprocess.Popen(
        command, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=600)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.terminate()
        try:
            stdout, stderr = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate(timeout=10)
    (DIRECTORY / "reopen.stdout.raw").write_bytes(stdout)
    (DIRECTORY / "reopen.stderr.raw").write_bytes(stderr)
    persist(
        DIRECTORY / "reopen.process.json",
        {
            "command": command,
            "pid": process.pid,
            "returncode": process.returncode,
            "timeout_seconds": 600,
            "timed_out": timed_out,
            "collected": process.poll() is not None,
        },
    )
    require(not timed_out and process.returncode == 0, "Reopen child completed and was reaped")
    lines = stdout.decode("utf-8", errors="replace").splitlines()
    results = [
        json.loads(line.split("=", 1)[1])
        for line in lines
        if line.startswith("GEOMETRY3_PERSISTENCE_RESULT=")
    ]
    require(
        len(results) == 1 and results[0] == {"ok": True, "phase": "reopen", "sidecars": 9},
        "Child returned its exact terminal marker",
    )
    print(stdout.decode("utf-8", errors="replace"), flush=True)
    assert_files(json.loads((DIRECTORY / "expected.json").read_text())["files"])


def reopen():
    gate = gate_tools.NativeGate(DIRECTORY / "reopen", REOPEN_ROWS)
    with (
        patch.object(execution_lease, "try_acquire", no_work),
        patch.object(gate_tools.sidecar_job.SidecarJob, "start", no_work),
    ):
        require(
            bpy.ops.wm.open_mainfile(filepath=str(BLEND)) == {"FINISHED"},
            "Open actual saved .blend",
        )
        expected = json.loads((DIRECTORY / "expected.json").read_text())
        window, area, region = gate_tools.context_parts()
        for name, saved in expected["scenes"].items():
            window.scene = bpy.data.scenes[name]
            with bpy.context.temp_override(window=window, area=area, region=region):
                actual = saved_fields()
                for key in ("document", "draft", "layout", "report", "report_document", "features"):
                    require(actual[key] == saved[key], name + " retains byte-exact " + key)
                require(
                    state().geometry_status != "PASSED", "Saved status never restores authority"
                )
                gate_tools.unverified()
                require(
                    doc.current_part_evidence(bpy.context) is None,
                    "No saved request/token reconstructed",
                )
                if "raw_radius" in saved:
                    draft = draft_dispatch.restore(state().sketch_draft_json, state().document_json)
                    require(
                        draft.command_draft.pending_edit.raw_text == saved["raw_radius"],
                        "Exact pending whitespace/formula survives",
                    )
                    require(
                        draft.annotations == saved["annotations"],
                        "Exact separate annotation intent survives",
                    )
                    require(
                        sketch_session.suspended_draft(bpy.context)["compatible"],
                        "Saved draft is compatible editable intent",
                    )
                if saved["status"] == "UNKNOWN":
                    require(
                        report()["export"] is None and report()["ok"] is False,
                        "Saved UNKNOWN never acquires a confirmed write",
                    )
                if saved["status"] == "OUTDATED":
                    require(
                        report()["export"] == json.loads(saved["report"])["export"],
                        "Saved OUTDATED keeps only exact historical file facts",
                    )
        assert_files(expected["files"])

    window.scene = bpy.data.scenes["Geometry3 saved success and intent"]
    with bpy.context.temp_override(window=window, area=area, region=region):
        require(
            bpy.ops.mcad.discard_suspended_sketch() == {"FINISHED"},
            "Explicitly discard inspected pending input before fresh output",
        )
        for action in gate_tools.ACTIONS:
            suffix = ".step" if action == "export_step" else ".stl"
            path = None if action == "check_geometry" else DIRECTORY / ("reopened" + suffix)
            before = state().document_json
            gate.call("fresh_" + action, action, destination=path)
            gate_tools.current(action)
            require(
                state().document_json == before, "Fresh output preserves saved seeds/IDs/formulas"
            )
        files = file_facts()
        original = state().document_json
        require(
            bpy.ops.ed.undo_push(message="Geometry3 before exact canonical edit") == {"FINISHED"},
            "Native Undo baseline recorded",
        )
        next(row for row in state().parameters if row.key == "radius").value = 7
        changed = state().document_json
        require(changed != original, "Same-ID edit changes only canonical parameter intent")
        require(
            bpy.ops.ed.undo_push(message="Geometry3 after exact canonical edit") == {"FINISHED"},
            "Native Redo checkpoint recorded",
        )
        require(bpy.ops.ed.undo() == {"FINISHED"}, "Actual native Undo executes")
        require(state().document_json == original, "Undo restores exact canonical JSON")
        gate_tools.unverified()
        assert_files(files)
        require(bpy.ops.ed.redo() == {"FINISHED"}, "Actual native Redo executes")
        require(state().document_json == changed, "Redo restores exact edited JSON")
        gate_tools.unverified()
        assert_files(files)
        gate.call("after_history", "check_geometry")
        gate_tools.current("check_geometry")
        retained = state().document_json
        backend_runtime.revoke("Persistence backend A to B")
        backend_runtime.revoke("Persistence backend B to A")
        gate_tools.unverified()
        require(state().document_json == retained, "ABA preserves exact canonical intent")
        assert_files(files)
        gate.call("after_aba", "check_geometry")
        gate_tools.current("check_geometry")
        saved_report = state().geometry_report_json
        addon.unregister()
        addon.register()
        gate_tools.unverified()
        require(
            state().document_json == retained and state().geometry_report_json == saved_report,
            "Disable/re-enable retains intent and report bytes, no authority",
        )
        assert_files(files)
        gate.call("after_reenable", "check_geometry")
        gate_tools.current("check_geometry")

        window.scene = bpy.data.scenes["Geometry2 saved ordinary"]
        saved = expected["scenes"][window.scene.name]
        require(
            state().document_json == saved["document"], "Ordinary v2 persisted intent remains exact"
        )
        gate_tools.unverified()
        for action in gate_tools.ACTIONS:
            suffix = ".step" if action == "export_step" else ".stl"
            path = (
                None if action == "check_geometry" else DIRECTORY / ("ordinary_reopened" + suffix)
            )
            gate.call("ordinary_" + action, action, destination=path)
            gate_tools.current(action, 2)
        gate.finish()


addon.register()
if PHASE == "save":
    save()
elif PHASE == "reopen":
    reopen()
else:
    raise AssertionError("Unknown persistence phase")
require(not execution_lease.is_busy(), "No native process or lease remains at lifetime end")
addon.unregister()
print(
    "GEOMETRY3_PERSISTENCE_RESULT="
    + json.dumps({"ok": True, "phase": PHASE, "sidecars": 6 if PHASE == "save" else 9})
)
