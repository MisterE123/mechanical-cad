"""Registered arc reference ownership and two-process raw-intent restore; no GUI claims."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
OUT = Path(os.environ["MCAD_ARC_OUTPUT"])
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    document_state,
    draft_dispatch,
    general_session,
    register,
    solid_projection_picker,  # noqa: E402
    solid_review,
    unregister,
    workspace,
)

captured = []
original = solid_projection_picker.MCAD_OT_use_solid_edge.execute


def capture(self, context):
    result = original(self, context)
    if result == {"RUNNING_MODAL"}:
        captured.append(self)
    return result


solid_projection_picker.MCAD_OT_use_solid_edge.execute = capture


def wait(owner, context):
    deadline = time.monotonic() + 60
    while owner.pending is not None:
        assert time.monotonic() < deadline
        owner.tick(context)
        time.sleep(0.01)
    assert not owner.error, owner.error


register()
if os.environ.get("MCAD_ARC_REOPEN"):
    bpy.ops.wm.open_mainfile(filepath=str(OUT / "arc-draft.blend"))
window = bpy.context.window
area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
region = next(r for r in area.regions if r.type == "WINDOW")
with bpy.context.temp_override(window=window, area=area, region=region):
    context = bpy.context
    state = context.scene.mechanical_cad
    if os.environ.get("MCAD_ARC_REOPEN"):
        expected = json.loads((OUT / "expected.json").read_text())
        assert state.document_json == expected["document"]
        assert state.sketch_draft_json == expected["draft"]
        assert not solid_review._REVIEWS
        document_state.regenerate(context)
        restored = draft_dispatch.restore(state.sketch_draft_json, state.document_json)
        owner = general_session.GeneralSession(context, restored=restored)
        owner.start()
        assert not owner.commands.has_current_solution
        owner.check(context)
        wait(owner, context)
        assert owner.commands.candidate() == expected["candidate"]
        assert len(owner.commands.sketch["arcs"]) == 1
        with patch.object(workspace, "request_workspace"):
            owner.request_finish(context)
            wait(owner, context)
        assert owner.finished
        edited = json.loads(state.document_json)
        next(r for r in edited["features"][0]["sketch"]["constraints"] if r["kind"] == "radius")[
            "value"
        ] = 3
        document_state._commit_candidate(context, edited)
        assert state.status == "READY", state.error
        owner = general_session.GeneralSession(context, expected["feature_id"])
        owner.start()
        arc = next(iter(owner.geometry().arcs.values()))
        assert abs(arc.radius_mm - 3) < 1e-7
        owner.discard("Arc source-edit replay verified")
        print("MCAD_ARC_PROJECTION_REOPEN_OK", flush=True)
    else:
        source = json.loads((ROOT / "tests/fixtures/solid_arc_projection/source.json").read_text())
        document_state._populate_document(context.scene, source)
        document_state.regenerate(context)
        assert state.status == "READY", state.error
        accepted = state.document_json
        owner = general_session.GeneralSession(context)
        owner.start()
        assert bpy.ops.mcad.use_solid_edge(source_solid="pad") == {"RUNNING_MODAL"}
        picker = captured[-1]._picker
        deadline = time.monotonic() + 60
        while picker.pending is not None:
            assert time.monotonic() < deadline
            picker.poll_catalog(context)
            time.sleep(0.01)
        entry = max(
            (e for e in picker.catalog["pad"] if "arc" in e), key=lambda e: e["arc"]["center"][2]
        )
        picker.close()
        owner.project_solid_edge(
            context,
            "pad",
            entry["faces"],
            entry["arc"]["endpoint_faces"],
            picker.catalog_evidence,
            picker.catalog_token,
            picker.catalog_version,
        )
        wait(owner, context)
        assert state.document_json == accepted
        assert not solid_review._REVIEWS
        feature = next(
            f
            for f in owner.commands.candidate()["features"]
            if f["id"] == owner.commands.feature_id
        )
        assert feature["projections"][0]["kind"] == "arc"
        assert feature["sketch"]["arcs"][0]["construction"]
        assert "fillet_intent" not in feature["sketch"]["arcs"][0]
        assert abs(next(iter(owner.geometry().arcs.values())).radius_mm - 2) < 1e-7
        owner.local_history(context)
        wait(owner, context)
        assert not owner.commands.sketch.get("arcs")
        owner.local_history(context, redo=True)
        wait(owner, context)
        candidate = owner.commands.candidate()
        feature_id = owner.commands.feature_id
        owner.suspend("Arc persistence verification")
        expected = {
            "document": state.document_json,
            "draft": state.sketch_draft_json,
            "candidate": candidate,
            "feature_id": feature_id,
        }
        (OUT / "expected.json").write_text(json.dumps(expected))
        bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "arc-draft.blend"))
        assert state.document_json == accepted
        print("MCAD_ARC_PROJECTION_OWNER_OK", flush=True)
assert "OCP" not in sys.modules and "slvs" not in sys.modules
unregister()
if not os.environ.get("MCAD_ARC_REOPEN"):
    result = subprocess.run(
        [
            bpy.app.binary_path,
            "--background",
            "--factory-startup",
            "--threads",
            "1",
            "--python-exit-code",
            "1",
            "--python",
            str(Path(__file__).resolve()),
        ],
        env={**os.environ, "MCAD_ARC_REOPEN": "1"},
        capture_output=True,
        text=True,
        timeout=120,
    )
    print(result.stdout, flush=True)
    print(result.stderr, flush=True)
    assert result.returncode == 0 and "MCAD_ARC_PROJECTION_REOPEN_OK" in result.stdout
    print("MCAD_ARC_PROJECTION_SMOKE_OK", flush=True)
