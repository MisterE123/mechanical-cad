"""Real sidecar-backed geometry/export operator integration, with failure injection.

Use MCAD_ROOT/MCAD_PYTHON and Blender --background --factory-startup
--python-exit-code 1 --python tests/blender_geometry_actions_smoke.py, or standalone
bpy Python. All exports live in a temporary directory; no user files are touched.
"""

import json
import math
import os
import struct
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
os.environ["MCAD_ROOT"] = str(ROOT)
os.environ.setdefault("MCAD_PYTHON", str(ROOT / ".venv" / "bin" / "python"))
sys.path.insert(0, str(ROOT / "blender_addon"))
import mechanical_cad_blender as addon  # noqa: E402
from mechanical_cad_blender import (  # noqa: E402
    backend_runtime,
    bridge,
    document_state,
    geometry_operations,  # noqa: E402
    guarded_transport,
    sidecar_job,
)
from mechanical_cad_blender.geometry_operations import run_geometry_action  # noqa: E402

checks = []


def check(condition, message):
    assert condition, message
    checks.append(message)


def state():
    return bpy.context.scene.mechanical_cad


def width():
    return next(row for row in state().parameters if row.key == "width")


def report():
    return json.loads(state().geometry_report_json)


def call(operator, **kwargs):
    check(operator(**kwargs) == {"FINISHED"}, f"{operator.idname()} completes its explicit action")


def check_volume(value):
    expected = (value * 30 - math.pi * 4**2) * 10
    actual = report()["geometry_check"]["brep"]["volume"]
    check(
        math.isclose(actual, expected, rel_tol=1e-12),
        "Report retains full backend volume precision",
    )
    check(
        repr(actual) in state().geometry_message,
        "Readable report uses backend double, not RNA float",
    )


addon.register()
call(bpy.ops.mcad.new_demo)
for operator in (bpy.ops.mcad.export_step, bpy.ops.mcad.export_stl):
    check(
        operator.get_rna_type().properties["check_existing"].default,
        "File selector enables overwrite confirmation",
    )
with tempfile.TemporaryDirectory(prefix="mcad-actions-") as folder:
    directory = Path(folder)
    call(bpy.ops.mcad.check_geometry)
    check(
        state().geometry_status == "PASSED" and state().status == "READY",
        "Check verifies current CAD output",
    )
    check(not list(directory.iterdir()), "Read-only check creates no export")
    check(report()["export"] is None, "Read-only check reports no export")
    check_volume(40)
    width().value = 60
    check(state().geometry_status == "OUTDATED", "Editing invalidates earlier check report")
    # Corrupt display; export must regenerate from JSON and never consume this mesh.
    obj = addon._owned_objects(bpy.context.scene)[0]
    obj.data.vertices[0].co.x += 8
    obj.scale = (20, 20, 20)
    step = directory / "Fresh part Å.step"
    call(bpy.ops.mcad.export_step, filepath=str(step), check_existing=False)
    check(
        step.is_file() and "ISO-10303-21" in step.read_text()[:100],
        "STEP is a real newly written file",
    )
    check(
        state().status == "READY" and state().geometry_status == "PASSED",
        "Dirty draft exports after fresh replay",
    )
    check_volume(60)
    check(
        report()["export"]["destination"] == str(step),
        "Export reports exact caller-selected destination",
    )
    check(
        report()["export"]["document_hash"] == report()["document_hash"],
        "Export identifies its canonical replay",
    )
    bpy.context.view_layer.update()
    check(
        math.isclose(obj.dimensions.x, 0.06, rel_tol=1e-6),
        "Export replay restores canonical display size",
    )
    stl = directory / "Fresh triangles.stl"
    call(bpy.ops.mcad.export_stl, filepath=str(stl), check_existing=False)
    content = stl.read_bytes()
    count = struct.unpack_from("<I", content, 80)[0]
    check(len(content) == 84 + 50 * count, "STL has a consistent checked binary triangle payload")
    coordinates = []
    for index in range(count):
        coordinates.extend(struct.unpack_from("<9f", content, 84 + 50 * index + 12)[::3])
    check(
        math.isclose(max(coordinates) - min(coordinates), 60, rel_tol=1e-6),
        "Encoded STL uses current dimensions in mm",
    )
    check(
        report()["geometry_check"]["encoded_mesh"]["watertight"],
        "Report includes actual encoded STL mesh check",
    )
    check("millimetres" in state().geometry_message, "STL report explains unitless file import")
    sentinel = b"prior export must survive"
    step.write_bytes(sentinel)
    before_json = state().document_json
    width().value = -5
    call(bpy.ops.mcad.export_step, filepath=str(step), check_existing=False)
    check(step.read_bytes() == sentinel, "Invalid draft cannot replace an existing export")
    check(
        state().status == "FAILED" and state().geometry_status == "FAILED",
        "Failed replay is an explicit action failure",
    )
    check(
        addon._owned_objects(bpy.context.scene)[0].get("mechanical_cad_stale"),
        "Failed action restores marked last-good cache",
    )
    check(report()["export"] is None, "Failed action never claims file success")
    check(state().document_json != before_json, "Failed draft remains available for correction")
    width().value = 60
    call(bpy.ops.mcad.check_geometry)
    check(state().status == "READY", "Corrected draft recovers")
    missing = directory / "missing parent" / "part.step"
    call(bpy.ops.mcad.export_step, filepath=str(missing), check_existing=False)
    check(not missing.exists(), "Export does not silently create missing destination directories")
    check(
        state().status == "READY" and state().geometry_status == "FAILED",
        "I/O failure is distinct from successful CAD regeneration",
    )
    check(report()["error"]["code"] == "export_io_error", "I/O diagnostic is preserved")
    check_volume(60)
    with patch.dict(os.environ, {"MCAD_PYTHON": str(directory / "missing-python")}):
        call(bpy.ops.mcad.export_step, filepath=str(step), check_existing=False)
    check(
        state().status == "FAILED" and state().geometry_status == "FAILED",
        "Missing backend fails without claiming an ambiguous write",
    )
    check(step.read_bytes() == sentinel, "Backend startup failure preserves destination")
    call(bpy.ops.mcad.check_geometry)
    with patch.object(
        sidecar_job.SidecarJob,
        "result",
        side_effect=bridge._transport_error({"action": "export_step"}, "sidecar timed out"),
    ):
        call(bpy.ops.mcad.export_step, filepath=str(step), check_existing=False)
    check(state().geometry_status == "UNKNOWN", "Export timeout reports unconfirmed file outcome")
    check(
        "may already have been replaced" in state().geometry_message,
        "Timeout does not falsely promise prior-file preservation",
    )
    check(state().status == "FAILED", "Unconfirmed action cannot leave a ready display")
    call(bpy.ops.mcad.check_geometry)
    with patch.dict(os.environ, {"MCAD_PYTHON": str(directory / "missing-python")}):
        call(bpy.ops.mcad.regenerate)
    check(
        state().geometry_status == "OUTDATED",
        "Ordinary replay failure invalidates prior verification",
    )
    call(bpy.ops.mcad.check_geometry)
    actual_result = sidecar_job.SidecarJob.result

    def lose_reply_after_write(job):
        actual_result(job)
        return {"lost": "reply"}

    with patch.object(sidecar_job.SidecarJob, "result", lose_reply_after_write):
        call(bpy.ops.mcad.export_step, filepath=str(step), check_existing=False)
    check(
        step.read_bytes() != sentinel,
        "Lost-reply test actually commits its output before losing confirmation",
    )
    check(
        state().geometry_status == "UNKNOWN",
        "A committed file with lost reply is still unconfirmed to the UI",
    )
    check(
        report()["requested_destination"] == str(step),
        "Unconfirmed report identifies the file to inspect",
    )
    call(bpy.ops.mcad.check_geometry)
    original = guarded_transport.execute

    def superseded(*args, **kwargs):
        response = original(*args, **kwargs)
        width().value = 70
        return response

    with patch.object(guarded_transport, "execute", superseded):
        call(bpy.ops.mcad.check_geometry)
    check(
        state().geometry_status == "OUTDATED" and state().status == "DIRTY",
        "Superseded snapshot cannot verify the changed draft",
    )
    check(
        addon._owned_objects(bpy.context.scene)[0].hide_viewport,
        "Superseded response does not replace current display",
    )
    call(bpy.ops.mcad.check_geometry)
    check_volume(70)
    # Post-launch malformed capability receipts never become a definite no-write
    # claim. Each fixture really completes the selected file replacement once.
    for corruption in ("missing", "nonce", "identity"):
        step.write_bytes(sentinel)

        def corrupt_receipt(job, corruption=corruption):
            response = actual_result(job)
            if corruption == "missing":
                response.pop("backend_receipt")
            elif corruption == "nonce":
                response["backend_receipt"]["request_id"] = "0" * 32
            else:
                response["backend_receipt"]["backend"]["core_origin"] = "/different/core"
            return response

        with (
            patch.object(sidecar_job.SidecarJob, "result", corrupt_receipt),
            patch.object(guarded_transport, "execute", wraps=guarded_transport.execute) as once,
        ):
            check(
                not run_geometry_action(bpy.context, "export_step", destination=str(step)),
                "Malformed " + corruption + " receipt rejects current export authority",
            )
            check(once.call_count == 1, "Malformed export receipt never automatically retries")
        check(
            step.read_bytes() != sentinel,
            "Malformed-receipt fixture replaces the destination before rejection",
        )
        check(
            state().geometry_status == "UNKNOWN",
            "Malformed " + corruption + " receipt retains unknown file outcome",
        )
        check(report()["export"] is None, "Malformed receipt never invents a confirmed write")

    # Owner-side rejection after a successful transport also has unknown file
    # outcome unless the exact intended write receipt has already been validated.
    retained = []

    def capture_export(*args, **kwargs):
        evidence = original(*args, **kwargs)
        retained.append(evidence)
        return evidence

    with patch.object(guarded_transport, "execute", capture_export):
        check(
            run_geometry_action(bpy.context, "export_step", destination=str(step)),
            "Capture one real historical export completion",
        )
    for substitution in ("earlier_nonce", "plain_projection", "revalidation_failure"):
        step.write_bytes(sentinel)

        def substitute_export(*args, substitution=substitution, **kwargs):
            evidence = original(*args, **kwargs)
            if substitution == "earlier_nonce":
                return retained[0]
            if substitution == "plain_projection":
                return evidence.response_snapshot()
            return evidence

        projection = geometry_operations._historical_projection
        with (
            patch.object(guarded_transport, "execute", side_effect=substitute_export) as once,
            patch.object(
                geometry_operations,
                "_historical_projection",
                side_effect=ValueError("Injected owner revalidation rejection")
                if substitution == "revalidation_failure"
                else None,
                wraps=projection,
            ),
        ):
            check(
                not run_geometry_action(bpy.context, "export_step", destination=str(step)),
                "Postlaunch " + substitution + " rejects current authority",
            )
            check(once.call_count == 1, "Postlaunch owner rejection never automatically retries")
        check(step.read_bytes() != sentinel, "Owner-rejection fixture actually replaced the file")
        check(
            state().geometry_status == "UNKNOWN" and report()["export"] is None,
            "Owner-side rejected receipt cannot imply no-write or historical confirmation",
        )
        check(
            "may already have been replaced" in state().geometry_message,
            "Owner-side uncertainty is explicit",
        )

    # A validated write followed by stale settings is historical evidence,
    # including the transport's explicit historical-export exception path.
    original_result = guarded_transport.GuardedJob.result

    def stale_at_handoff(job, current_selection, *, owner_token):
        backend_runtime.revoke("Export settings A to B")
        backend_runtime.revoke("Export settings B to A")
        return original_result(job, backend_runtime.capture(bpy.context), owner_token=owner_token)

    with patch.object(guarded_transport.GuardedJob, "result", stale_at_handoff):
        check(
            not run_geometry_action(bpy.context, "export_step", destination=str(step)),
            "Stale validated export does not verify current scene",
        )
    check(
        state().geometry_status == "OUTDATED",
        "Validated stale export is historical rather than unknown",
    )
    check(
        report()["export"]["destination"] == str(step),
        "Historical export preserves the exact validated write receipt",
    )
    check(
        "written" in state().geometry_message and "earlier request" in state().geometry_message,
        "Historical export explains file outcome and stale current CAD",
    )
    check(
        not document_state.part_is_current(bpy.context)
        and not document_state.geometry_report_is_current(bpy.context),
        "Historical export grants no current Part or geometry authority",
    )
    call(bpy.ops.mcad.check_geometry)
    check(
        document_state.geometry_report_is_current(bpy.context),
        "Fresh check restores current geometry authority",
    )

    document_state._REPLAY_RUNNING = True
    try:
        for operator in (
            bpy.ops.mcad.activate_feature,
            bpy.ops.mcad.check_geometry,
            bpy.ops.mcad.export_step,
            bpy.ops.mcad.export_stl,
        ):
            check(not operator.poll(), "Geometry action honors shared replay lock")
        try:
            run_geometry_action(bpy.context, "check_geometry")
        except bridge.BridgeError:
            check(True, "Direct geometry action honors shared replay lock")
        else:
            raise AssertionError("Geometry action ignored replay lock")
        try:
            document_state._commit_candidate(bpy.context, addon.demo_document())
        except bridge.BridgeError:
            check(True, "Candidate transactions honor shared replay lock")
        else:
            raise AssertionError("Candidate commit ignored replay lock")
    finally:
        document_state._REPLAY_RUNNING = False
    state().feature_index = 0
    call(bpy.ops.mcad.activate_feature)
    call(bpy.ops.mcad.check_geometry)
    check(
        state().status == "READY" and state().geometry_status == "FAILED",
        "Valid sketch is not falsely certified as a solid",
    )
    check(report()["error"]["code"] == "not_a_solid", "Active-profile diagnostic is readable")
    check(
        len(addon._owned_objects(bpy.context.scene)) == 1,
        "Repeated actions retain one owned display",
    )
    call(bpy.ops.mcad.new_document, name="Empty action test")
    call(bpy.ops.mcad.check_geometry)
    check(
        report()["error"]["code"] == "missing_active_feature",
        "Empty document requests an active solid",
    )
check(
    not any(name == "OCP" or name.startswith("OCP.") for name in sys.modules),
    "Native CAD stays outside Blender",
)
addon.unregister()
print(
    "MCAD_GEOMETRY_OPERATORS_RESULT="
    + json.dumps(
        {
            "ok": True,
            "blender": bpy.app.version_string,
            "check_count": len(checks),
        }
    )
)
