"""Native guarded Part, Rectangle and snapshot non-bypass/revocation checks."""

import copy
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
os.environ["MCAD_ROOT"] = str(ROOT)
os.environ.setdefault("MCAD_PYTHON", str(ROOT / ".venv/bin/python"))
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    backend_runtime,
    draft_dispatch,
    guarded_operations,
    guarded_transport,
    part_publication,
    register,
    unregister,
    viewport_sketch,
)
from mechanical_cad_blender import document_state as doc  # noqa: E402

checks = []


def check(value, message):
    assert value, message
    checks.append(message)


def rejects(call, message):
    try:
        call()
    except (ValueError, RuntimeError):
        checks.append(message)
    else:
        raise AssertionError(message)


def execute(intent):
    with doc.replay_guard(bpy.context):
        return guarded_transport.execute(
            intent.prepared,
            intent.selection,
            owner_token=intent.owner_token,
            current_selection=lambda: backend_runtime.capture(bpy.context),
        )


register()
context, scene = bpy.context, bpy.context.scene
state = scene.mechanical_cad
rectangle = json.loads((ROOT / "examples/viewport_rectangle.mcad.json").read_text())
check(doc._commit_candidate(context, rectangle), "Fresh guarded rectangle Part publishes")
current = doc.current_part_result(context)
check(current and doc.part_is_current(context), "Current Part reads immutable runtime projection")
feature = next(item for item in current["features"] if item["id"] == "sketch_1")
state.features[0].sketch_report_json = '{"remaining_dof": 900}'
check(
    doc.current_part_result(context)["features"][0]["sketch"] == feature["sketch"],
    "Saved report mutation cannot change current guarded Part content",
)

binding = doc._capture_binding(context)
for untrusted in (current, {"ok": True, "result": current}):
    before = state.document_json
    rejects(
        lambda value=untrusted: doc._apply_result(context, rectangle, value, binding),
        "Part sink rejects legacy result and response dictionaries",
    )
    check(state.document_json == before, "Dictionary rejection leaves authored bytes unchanged")
with doc.replay_guard(context):
    snapshot = guarded_operations.canonical_snapshot_guarded(
        rectangle,
        selection=binding["selection"],
        owner_token=binding["owner_token"],
        current_selection=lambda: backend_runtime.capture(context),
    )
rejects(
    lambda: doc._apply_result(context, rectangle, snapshot, binding),
    "Pure snapshot evidence cannot authorize Part display",
)
intent = part_publication.prepare(context, rectangle)
rejects(lambda: intent.publish(context, snapshot), "Pure snapshot evidence cannot authorize Finish")
with patch.object(guarded_transport, "execute", return_value=snapshot):
    rejects(
        lambda: guarded_operations.canonical_snapshot_guarded(
            rectangle,
            selection=binding["selection"],
            owner_token=binding["owner_token"],
            current_selection=lambda: backend_runtime.capture(context),
        ),
        "Pure snapshot adapter rejects an earlier identical-source nonce",
    )

# Identical operation data and owner do not authorize reuse of an earlier nonce.
owner_token = object()
first_binding = doc._capture_binding(context, owner_token=owner_token)
with doc.replay_guard(context):
    previous_completion = doc._run_sidecar(context, rectangle, binding=first_binding)
second_binding = doc._capture_binding(context, owner_token=owner_token)
with (
    doc.replay_guard(context),
    patch.object(guarded_transport, "execute", return_value=previous_completion),
):
    rejects(
        lambda: doc._run_sidecar(context, rectangle, binding=second_binding),
        "Identical same-owner earlier completion cannot replace a fresh Part nonce",
    )
check(
    first_binding["request_fingerprint"] != second_binding["request_fingerprint"],
    "Every explicit Part operation captures a fresh guarded request",
)

# Saved READY/CURRENT bytes cannot launch work or restore Rectangle DoF.
doc._populate_document(scene, rectangle)
state.status = "READY"
state.features[0].sketch_report_status = "CURRENT"
state.features[0].sketch_report_json = json.dumps(feature["sketch"])
state.features[0].sketch_document_json = state.document_json
window = context.window
area = next(area for area in window.screen.areas if area.type == "VIEW_3D")
region = next(region for region in area.regions if region.type == "WINDOW")
with context.temp_override(window=window, area=area, region=region):
    session = viewport_sketch.RectangleSession(context, "sketch_1")
    with patch.object(guarded_transport, "execute", side_effect=AssertionError("Passive launch")):
        check(
            not session.initialize_preview(context),
            "Saved CURRENT opens an unverified authored preview",
        )
        check(session.current_solver_report() is None, "Saved CURRENT grants no live DoF")
    session.cleanup()
    check(doc.regenerate(context), "Explicit replay restores Part authority")
    session = viewport_sketch.RectangleSession(context, "sketch_1")
    session.start()
    check(
        session.initialize_preview(context), "Exact live Part evidence can seed Rectangle preview"
    )
    check(
        not any(key.startswith("_guarded") for key in asdict(session.draft)),
        "Draft codec contains no runtime authority",
    )
    encoded = draft_dispatch.dumps(session.draft)
    session.draft.pending_dimensions = {
        "width": "bad raw text",
        "height": "30",
        "fix_corner": False,
    }
    session.draft.solver_report = None
    session.draft.validated_json = ""
    expected_points = copy.deepcopy(feature["sketch"]["solved"]["points"])
    check(
        session.draft.guarded_seed_points(backend_runtime.capture(context)) == expected_points,
        "Pending raw text permits only the previous applied guarded seed",
    )
    check(not session.has_current_solution, "Pending raw text never becomes a current solution")
    popup = SimpleNamespace(
        session=session,
        width=session.draft.width_text,
        height=session.draft.height_text,
        fix_position=False,
        _close_later=lambda: None,
    )
    check(
        viewport_sketch.MCAD_OT_sketch_dimensions.execute(popup, context) == {"FINISHED"},
        "Native dimension Apply can release position while pending input exists",
    )
    check(
        session.current_solver_report()["remaining_dof"] == 2,
        "Released rectangle retains real translational DoF",
    )
    before_seed = copy.deepcopy(session.draft.seed_override)
    backend_runtime.revoke("A to B")
    backend_runtime.revoke("B to A")
    rejects(
        lambda: session.draft.guarded_seed_points(backend_runtime.capture(context)),
        "Settings ABA revokes the old solved seed",
    )
    check(
        session.draft.seed_override == before_seed, "Seed rejection preserves authored seed bytes"
    )
    check(session.current_solver_report() is None, "Settings ABA revokes Rectangle DoF")
    check(
        encoded and state.document_json == json.dumps(rectangle, allow_nan=False),
        "Runtime revocation leaves canonical bytes intact",
    )
    session.cleanup()

# Formula-to-number uses immutable resolved evidence; saved float/string caches
# cannot supply the number, and A→B→A cannot restore conversion authority.
formula = doc.demo_document()
formula["parameters"]["width"] = "20*2"
check(doc._commit_candidate(context, formula), "Formula Part obtains guarded resolved evidence")
row = next(row for row in state.parameters if row.key == "width")
row.resolved_text = "999"
row.resolved_expression = "20*2"
row.is_expression = False
check(
    json.loads(state.document_json)["parameters"]["width"] == 40,
    "Formula conversion ignores forged saved numeric cache",
)
check(doc._commit_candidate(context, formula), "Formula reset is freshly guarded")
backend_runtime.revoke("A to B")
backend_runtime.revoke("B to A")
row = next(row for row in state.parameters if row.key == "width")
row.resolved_text = "40"
row.resolved_expression = "20*2"
state.status = "READY"
row.is_expression = False
check(row.is_expression, "Settings ABA blocks formula conversion despite forged READY")
check(
    json.loads(state.document_json)["parameters"]["width"] == "20*2",
    "Rejected formula conversion preserves exact expression",
)

# A callback after display writes must be checked before runtime authority exists.
check(doc.regenerate(context), "Fresh replay recovers after ABA")
for field in ("document", "owner", "scale"):
    before = state.document_json
    owner, scale = state.owner_id, scene.unit_settings.scale_length
    original_display = doc._display_feature

    def change_during_display(*args, field=field, original_display=original_display, **kwargs):
        original_display(*args, **kwargs)
        if field == "document":
            state.document_json += " "
        elif field == "owner":
            state.owner_id += "changed"
        else:
            scene.unit_settings.scale_length = 0.25

    with patch.object(doc, "_display_feature", change_during_display):
        check(
            not doc.regenerate(context), "Post-write " + field + " change rejects Part publication"
        )
    check(
        not doc.part_is_current(context), "Rejected post-write callback cannot leave current Part"
    )
    state.document_json, state.owner_id, scene.unit_settings.scale_length = before, owner, scale
    check(doc.regenerate(context), "Explicit replay recovers from callback rejection")

# Rollback restores authored state and exact display resources, never an expired
# generation. Exercise both display and annotation callbacks inside the seam.
for seam in ("display", "layout"):
    candidate = copy.deepcopy(formula)
    candidate["name"] = "Rejected new candidate"
    intent = part_publication.prepare(context, candidate)
    evidence = execute(intent)
    before = state.document_json
    original = doc._apply_result

    def revoke_after_write(*args, original=original):
        original(*args)
        backend_runtime.revoke("Injected publication ABA A to B")
        backend_runtime.revoke("Injected publication ABA B to A")
        raise RuntimeError("Injected publication callback failure")

    def revoke_layout(*args):
        backend_runtime.revoke("Injected layout ABA A to B")
        backend_runtime.revoke("Injected layout ABA B to A")
        raise RuntimeError("Injected layout callback failure")

    target, name, replacement = (
        (doc, "_apply_result", revoke_after_write)
        if seam == "display"
        else (intent, "_publish_layout", revoke_layout)
    )
    with patch.object(target, name, replacement):
        rejects(
            lambda intent=intent, evidence=evidence: intent.publish(context, evidence),
            "Generation-changing " + seam + " callback rejects publication",
        )
    check(state.document_json == before, "Rollback preserves canonical authored bytes")
    check(
        not doc.part_is_current(context) and state.status != "READY",
        "Rollback cannot revive expired Part authority",
    )
    check(doc.regenerate(context), "Fresh replay recovers after generation-aware rollback")

check(
    not any(name == "OCP" or name.startswith("OCP.") or name == "slvs" for name in sys.modules),
    "Native CAD remains outside Blender",
)
unregister()
print("PART_CAPABILITY_SMOKE_OK", len(checks))
