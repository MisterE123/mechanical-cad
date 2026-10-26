"""Registered Assembly STEP operator, truthful outcomes and fresh reopen.

Use source-loaded Blender with MCAD_ROOT, MCAD_PYTHON, a fresh
MCAD_ASSEMBLY_STEP_DIRECTORY and MCAD_ASSEMBLY_STEP_PHASE=save/reopen.
The outer collector launches the two lifetimes serially. No manual GUI claim.
"""

import hashlib
import json
import os
import signal
import sys
from pathlib import Path
from unittest.mock import patch

sys.dont_write_bytecode = True
import bpy  # noqa: E402

ROOT = Path(os.environ["MCAD_ROOT"]).resolve()
DIRECTORY = Path(os.environ["MCAD_ASSEMBLY_STEP_DIRECTORY"]).resolve()
PHASE = os.environ.get("MCAD_ASSEMBLY_STEP_PHASE", "save")
sys.path.insert(0, str(ROOT / "blender_addon"))
sys.path.insert(0, str(ROOT / "tests"))
import mechanical_cad_blender as addon  # noqa: E402
from blender_async_helpers import replay_assembly  # noqa: E402
from mechanical_cad_blender import (  # noqa: E402
    assembly_export_owner,
    assembly_state,
    backend_runtime,
    execution_lease,
    guarded_transport,
    sidecar_job,
)

checks, jobs = [], []


def check(value, label):
    assert value, label
    checks.append(label)
    print("ASSEMBLY_STEP_CHECK", label, flush=True)


def persist(name, value):
    with (DIRECTORY / name).open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def state():
    return bpy.context.scene.mechanical_cad_assembly


def call(operation, **kwargs):
    check(operation(**kwargs) == {"FINISHED"}, operation.idname() + " completes")
    check(not execution_lease.is_busy(), "Native lease collected")


def current_check():
    call(bpy.ops.mcad.assembly_check)
    check(assembly_state.report_is_current(bpy.context), "Current guarded pose report")
    check(json.loads(state().report_json)["report"]["passed"], "Configured pose passes")


def save():
    DIRECTORY.mkdir()
    bpy.data.objects["Cube"]["keep"] = "unrelated user object"
    call(
        bpy.ops.mcad.assembly_load,
        filepath=str(ROOT / "examples/box_sector/assembly.mcad-assembly.json"),
    )
    check(not bpy.ops.mcad.assembly_export_step.poll(), "Replay alone cannot authorize export")
    current_check()
    canonical = state().document_json
    part = bpy.context.scene.mechanical_cad.document_json
    check(bpy.ops.mcad.assembly_export_step.poll(), "Checked Assembly exposes export operator")
    call(bpy.ops.mcad.assembly_export_step, filepath=str(DIRECTORY / "assembly.step"))
    receipt = json.loads(state().export_receipt_json)
    check(receipt["outcome"] == "WRITTEN", "Actual operator retains historical write")
    check(
        receipt["export"]["definition_count"] == 2 and receipt["export"]["instance_count"] == 3,
        "Two definitions and three instances",
    )
    check(
        state().document_json == canonical
        and bpy.context.scene.mechanical_cad.document_json == part,
        "Export preserves both canonical models",
    )
    before = len(jobs)
    intent = assembly_export_owner.capture(bpy.context)
    assembly_state.invalidate(bpy.context.scene, "Controlled stale file-selector intent")
    try:
        assembly_export_owner.run_export(
            bpy.context, str(DIRECTORY / "must-not-exist.step"), snapshot=intent
        )
    except (RuntimeError, ValueError):
        pass
    else:
        raise AssertionError("Stale dialog intent was accepted")
    check(
        len(jobs) == before and not (DIRECTORY / "must-not-exist.step").exists(),
        "Stale file selector rejects before launch",
    )
    current_check()
    original = guarded_transport.execute

    def lose_current(*args, **kwargs):
        evidence = original(*args, **kwargs)
        backend_runtime.revoke("Controlled post-write backend revocation")
        return evidence

    with patch.object(guarded_transport, "execute", lose_current):
        try:
            result = bpy.ops.mcad.assembly_export_step(
                filepath=str(DIRECTORY / "written-before-revocation.step")
            )
            check(result == {"CANCELLED"}, "Rejected current handoff cannot report FINISHED")
        except RuntimeError as exc:
            check("written" in str(exc), "Operator tells the truth after post-write revocation")
    receipt = json.loads(state().export_receipt_json)
    check(
        receipt["outcome"] == "WRITTEN"
        and (DIRECTORY / "written-before-revocation.step").is_file(),
        "Written file survives lost current authority",
    )
    check(
        not assembly_state.report_is_current(bpy.context),
        "Export does not revive old pose authority",
    )
    check(state().document_json == canonical, "Post-write rejection preserves canonical Assembly")
    call(replay_assembly)
    current_check()
    retained = state().export_receipt_json
    files = {
        name: digest(DIRECTORY / name)
        for name in ("assembly.step", "written-before-revocation.step")
    }
    persist(
        "expected.json",
        {
            "assembly": json.loads(canonical),
            "canonical": canonical,
            "part": part,
            "receipt": retained,
            "files": files,
        },
    )
    call(bpy.ops.wm.save_as_mainfile, filepath=str(DIRECTORY / "project.blend"))


def reopen():
    expected = json.loads((DIRECTORY / "expected.json").read_text())
    call(bpy.ops.wm.open_mainfile, filepath=str(DIRECTORY / "project.blend"))
    check(state().document_json == expected["canonical"], "Canonical Assembly bytes survive reopen")
    check(
        bpy.context.scene.mechanical_cad.document_json == expected["part"],
        "Working Part bytes survive reopen",
    )
    check(
        state().export_receipt_json == expected["receipt"],
        "File receipt remains historical after reopen",
    )
    check(not bpy.ops.mcad.assembly_export_step.poll(), "Saved PASS cannot reauthorize export")
    call(replay_assembly)
    check(not bpy.ops.mcad.assembly_export_step.poll(), "Reopen replay still requires Check Pose")
    current_check()
    call(bpy.ops.mcad.assembly_export_step, filepath=str(DIRECTORY / "assembly-reopened.step"))
    check(
        bpy.data.objects["Cube"]["keep"] == "unrelated user object",
        "Unrelated object survives both lifetimes",
    )
    for name, expected_hash in expected["files"].items():
        check(digest(DIRECTORY / name) == expected_hash, "Recovery does not rewrite " + name)
    persist(
        "reopened-export.json",
        {
            "file": "assembly-reopened.step",
            "sha256": digest(DIRECTORY / "assembly-reopened.step"),
            "receipt": json.loads(state().export_receipt_json),
        },
    )
    call(bpy.ops.wm.save_as_mainfile, filepath=str(DIRECTORY / "project-recovered.blend"))


def main():
    addon.register()
    original = sidecar_job.SidecarJob.start

    def observe(job):
        jobs.append(json.loads(job._payload)["action"])
        return original(job)

    try:
        with patch.object(sidecar_job.SidecarJob, "start", observe):
            (save if PHASE == "save" else reopen)()
        check(not execution_lease.is_busy(), "No final lease")
        check(
            not any(
                name.split(".")[0] in {"OCP", "slvs", "mechanical_cad"} for name in sys.modules
            ),
            "Native CAD stays outside Blender",
        )
        persist(PHASE + "-result.json", {"checks": checks, "sidecars": jobs, "manual_gui": False})
    finally:
        addon.unregister()
    print("ASSEMBLY_STEP_EXPORT_OK", PHASE, flush=True)


if __name__ == "__main__":

    def timeout(_signum, _frame):
        raise TimeoutError("Assembly STEP owner lifetime exceeded 600 seconds")

    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(600)
    try:
        main()
    finally:
        signal.alarm(0)
