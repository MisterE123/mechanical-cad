"""Bounded registered-owner/native fraction checks and two-process raw reopen.

Run only when the shared Blender slot is granted, with --python-exit-code 1.
MCAD_ROOT, MCAD_PYTHON, MCAD_FRACTION_BLEND and MCAD_FRACTION_PHASE=save|resume
are required. This scripted owner test does not establish real GUI interaction.
"""
import json
import math
import os
import sys
import time
from pathlib import Path

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
TARGET = Path(os.environ["MCAD_FRACTION_BLEND"])
PHASE = os.environ["MCAD_FRACTION_PHASE"]
assert PHASE in {"save", "resume"}
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    dimension_input,
    document_state,
    draft_dispatch,
    general_session,
    register,
    unregister,
)
from mechanical_cad_blender.general_sketch_commands import (  # noqa: E402
    AddCircle,
    AddRelation,
    DraftError,
    PointSeed,
)


def wait(owner):
    deadline = time.monotonic() + 45
    while owner.pending is not None and time.monotonic() < deadline:
        owner.tick(bpy.context)
        time.sleep(.01)
    assert owner.pending is None and not owner.error, owner.error


def text(owner, raw):
    # Reopening a pending field selects its retained contents, just as ordinary UI.
    owner.input_controller.handle(
        dimension_input.InputEvent("A", unicode=raw),
        approve_raw=lambda action: owner.update_raw(action.raw) is None,
    )
    assert owner.input_controller.raw == raw


def begin_circle(owner, raw, center=(10, 10)):
    owner.draft.select_tool("Circle")
    owner.draft.begin_circle(PointSeed(*center))
    owner.proposal_capture = True
    owner.open_circle_diameter(bpy.context)
    text(owner, raw)


def reject(owner, accept):
    before = draft_dispatch.dumps(owner.draft)
    try:
        accept(bpy.context)
    except DraftError as exc:
        assert "denominator" in str(exc), str(exc)
    else:
        raise AssertionError("Zero denominator was accepted")
    assert draft_dispatch.dumps(owner.draft) == before
    assert owner.pending is None


def verify(owner):
    geometry = owner.geometry()
    assert geometry.source == "solved", geometry.source
    line = next(iter(geometry.lines.values()))
    assert math.isclose(math.dist(line.start_mm, line.end_mm), 3.175, abs_tol=1e-7)
    circle = next(iter(geometry.circles.values()))
    assert math.isclose(circle.radius_mm, 1.5875, abs_tol=1e-7)
    assert math.isclose(2 * circle.radius_mm, 3.175, abs_tol=1e-7)
    drivers = owner.commands.sketch["constraints"]
    assert drivers[0]["value"] == 3.175
    assert drivers[1]["kind"] == "radius" and drivers[1]["value"] == 1.5875
    assert owner.draft.annotations[drivers[1]["id"]]["display"] == "diameter"


register()
if PHASE == "resume":
    bpy.ops.wm.open_mainfile(filepath=str(TARGET))
window = bpy.context.window
area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
region = next(r for r in area.regions if r.type == "WINDOW")
with bpy.context.temp_override(window=window, area=area, region=region):
    if PHASE == "save":
        document_state._populate_document(bpy.context.scene, {
            "schema_version": 1, "id": "fractions", "name": "Fraction input QA", "units": "mm",
            "parameters": {"width": 8}, "features": [], "active_feature": None,
        })
        canonical = bpy.context.scene.mechanical_cad.document_json
        owner = general_session.GeneralSession(bpy.context)
        owner.start()
        owner.draft.select_tool("Line")
        owner.accept_point_input(bpy.context, PointSeed(0, 0), expected_phase=("line", "start"))
        owner.open_line_length(bpy.context, PointSeed(10, 0))
        text(owner, "1/0 in")
        reject(owner, owner.request_line_length_accept)
        owner.cancel_dimension()
        owner.proposal_capture = True
        owner.open_line_length(bpy.context, PointSeed(10, 0))
        text(owner, "1/8in")
        owner.request_line_length_accept(bpy.context)
        wait(owner)
        begin_circle(owner, "1/0 in")
        reject(owner, owner.request_circle_diameter_accept)
        owner.cancel_dimension()
        owner.proposal_capture = True
        owner.open_circle_diameter(bpy.context)
        text(owner, "1/8in")
        owner.request_circle_diameter_accept(bpy.context)
        wait(owner)
        verify(owner)
        owner.execute(bpy.context, AddCircle(PointSeed(20, 20), 4))
        wait(owner)
        circle_id = owner.commands.sketch["circles"][-1]["id"]
        owner.execute(bpy.context, AddRelation("radius", (circle_id,), value="width / 2"))
        wait(owner)
        relation = owner.commands.sketch["constraints"][-1]
        before = owner.commands.sketch
        owner.begin_dimension(relation["id"])
        assert owner.commands.pending_edit.raw_text == "width / 2"
        candidate = owner.commands.trial_candidate()
        assert candidate["features"][-1]["sketch"]["constraints"][-1]["value"] == "width / 2"
        owner.cancel_dimension()
        assert owner.commands.sketch == before
        owner.check(bpy.context)
        wait(owner)
        verify(owner)
        begin_circle(owner, "1/0 in", center=(30, 30))
        reject(owner, owner.request_circle_diameter_accept)
        owner.checkpoint()
        saved = draft_dispatch.dumps(owner.draft)
        assert bpy.context.scene.mechanical_cad.document_json == canonical
        bpy.ops.wm.save_as_mainfile(filepath=str(TARGET))
        TARGET.with_suffix(".json").write_text(json.dumps({"draft": saved, "canonical": canonical}))
        owner.suspend("Fraction fixture saved")
        print("FRACTION_UNIT_SAVE_OK", flush=True)
    else:
        expected = json.loads(TARGET.with_suffix(".json").read_text())
        state = bpy.context.scene.mechanical_cad
        assert state.document_json == expected["canonical"]
        restored = draft_dispatch.restore(state.sketch_draft_json, state.document_json)
        assert draft_dispatch.dumps(restored) == expected["draft"]
        owner = general_session.GeneralSession(bpy.context, restored=restored)
        owner.start()
        assert owner.pending is None and owner.diameter_attempt is None
        assert owner.input_controller is None and not owner.input_token
        assert not owner.commands.has_current_solution and owner.guarded_evidence is None
        assert owner.draft.pending_diameter["raw_text"] == "1/0 in"
        assert owner.commands.sketch["constraints"][-1]["value"] == "width / 2"
        owner.open_circle_diameter(bpy.context)
        reject(owner, owner.request_circle_diameter_accept)
        text(owner, "1/8in")
        owner.request_circle_diameter_accept(bpy.context)
        wait(owner)
        verify(owner)
        assert owner.commands.sketch["constraints"][-2]["value"] == "width / 2"
        assert owner.commands.sketch["constraints"][-1]["value"] == 1.5875
        assert state.document_json == expected["canonical"]
        owner.discard()
        print("FRACTION_UNIT_RESUME_OK", flush=True)
unregister()
