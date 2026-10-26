"""Native 5.2.2 offscreen API/state smoke, NOT an installed or interactive GUI gate.

Run with --background --factory-startup --python-exit-code 1 --python this_file.
No registration, operators, owner session, timers, sidecar or canonical edits.
Synthetic solve responses below qualify display validation only, never solving.
"""

import copy
import importlib
import math
import os
import sys
import types
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

import bpy
import gpu
from mathutils import Matrix

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
PACKAGE = "mcad_general_overlay_smoke"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[PACKAGE] = package
overlay = importlib.import_module(PACKAGE + ".general_sketch_overlay")
geometry = importlib.import_module(PACKAGE + ".general_view_geometry")
bridge = importlib.import_module(PACKAGE + ".sketch_action_bridge")
checks = []


def check(condition, description):
    assert condition, description
    checks.append(description)


def rejects(callback, error=ValueError):
    try:
        callback()
    except error:
        return
    raise AssertionError(f"Expected {error.__name__}")


def fixture():
    sketch = {
        "schema_version": 2,
        "id": "sketch",
        "units": "mm",
        "plane": {"id": "plane", "origin": [0, 0, 0], "quaternion": [1, 0, 0, 0]},
        "points": [{"id": "a", "u": 0, "v": 0}, {"id": "b", "u": 30, "v": 40}],
        "lines": [{"id": "line", "start": "a", "end": "b"}],
        "circles": [{"id": "circle", "center": "a", "radius": 5.1234567890123}],
        "constraints": [
            {"id": "length", "kind": "distance", "refs": ["a", "b"], "value": 50.0},
            {"id": "radius", "kind": "radius", "refs": ["circle"], "value": "size / 2"},
        ],
    }
    annotations = {
        "length": {
            "kind": "distance",
            "refs": ["a", "b"],
            "display": "distance",
            "offset": [-12, 6],
        },
        "radius": {"kind": "radius", "refs": ["circle"], "display": "radius", "offset": [15, 6]},
    }
    document = {
        "schema_version": 2,
        "id": "part",
        "name": "Part",
        "units": "mm",
        "parameters": {"size": 12},
        "features": [
            {
                "id": "profile",
                "kind": "sketch_constrained",
                "label": "Draft",
                "params": {},
                "inputs": {},
                "sketch": sketch,
            }
        ],
        "active_feature": "profile",
    }
    request = {
        "protocol_version": 1,
        "action": "solve_sketch",
        "result_version": 2,
        "document": document,
        "feature_id": "profile",
    }
    canonical = bridge.snapshots._expected_document(document)
    solved = geometry._normalized_sketch(sketch)
    solved["circles"][0]["radius"] = 6
    solved["constraints"][1]["value"] = 6
    response = {
        "protocol_version": 1,
        "action": "solve_sketch",
        "result_version": 2,
        "input_fingerprint": bridge.snapshots.input_fingerprint(request),
        "ok": True,
        "error": None,
        "result": {
            "document_id": "part",
            "feature_id": "profile",
            "document_hash": bridge.snapshots.document_hash(canonical),
            "sketch": {
                "solver": "libslvs",
                "solver_version": "3.2",
                "status": "okay",
                "remaining_dof": 5,
                "failed_constraints": [],
                "redundant_constraints": [],
                "max_residual_mm": 0,
                "solved": solved,
                "dimensions": {"length": 50, "radius": 6},
            },
            "profile_check": {
                "ready": False,
                "error": {"code": "mixed_profile_regions", "message": "Open display fixture"},
            },
        },
    }
    return sketch, annotations, request, response


def project(world):
    return world[0] * 4 + 220, world[1] * 4 + 220


def gpu_state():
    return (
        gpu.state.blend_get(),
        gpu.state.depth_test_get(),
        gpu.state.depth_mask_get(),
        gpu.state.line_width_get(),
    )


def native_state():
    return (
        tuple(item.name for item in bpy.data.objects),
        tuple(item.name for item in bpy.data.meshes),
        tuple(item.name for item in bpy.data.scenes),
        bpy.context.scene.unit_settings.scale_length,
    )


check(bpy.app.version[:3] == (5, 2, 2), "Qualified native test runtime is Blender 5.2.2")
before_native = native_state()
sketch, annotations, request, response = fixture()
before_source = copy.deepcopy((sketch, annotations, request, response))
authored = geometry.build_geometry(sketch, source="authored")
# Inspector selection may name a non-dimensional relation. The renderer gets
# bounded authored identities explicitly; those are never solver evidence.
relation_frame = overlay.build_frame(
    authored,
    lambda world: world[:2],
    selection=({"kind": "constraint", "id": "fixed_anchor"},),
    relation_ids=("fixed_anchor",),
)
check(not relation_frame.unavailable, "Authored non-dimensional relation can be selected")
check(not relation_frame.labels, "Non-dimensional selection creates no fictitious dimension")
missing_relation = overlay.build_frame(
    authored,
    lambda world: world[:2],
    selection=({"kind": "constraint", "id": "removed_anchor"},),
    relation_ids=("fixed_anchor",),
)
check(
    any(issue.reason == "selection_unavailable" for issue in missing_relation.unavailable),
    "Missing relation identity remains explicitly unavailable",
)
for bad in ("fixed", ("fixed", "fixed"), (False,), tuple("r" + str(i) for i in range(513))):
    rejects(
        lambda bad=bad: overlay.build_frame(authored, lambda world: world[:2], relation_ids=bad)
    )
    check(True, "Malformed or oversized authored relation IDs reject")
solved = geometry.build_geometry(
    sketch, source="solved", solve_request=request, solve_response=response
)
fingerprint = response["input_fingerprint"]
retained = geometry.retained_outline(solved)
retained_frame = overlay.build_frame(retained, project, annotations=annotations)
check(retained_frame.source == "retained", "Retained outline is an explicit display variant")
check(retained_frame.request_fingerprint is None, "Retained frame cannot authorize a current solve")
check(
    all("~" in item.text for item in retained_frame.labels),
    "Retained dimensions are visibly unverified",
)
check(
    overlay._display_raw(15.652173913043478) == "15.6522", "Numeric annotation detail is readable"
)
check(
    overlay._display_raw("radius * 2") == "radius * 2",
    "Formula annotation detail preserves exact input",
)

selection = [
    {"kind": "line", "id": "line"},
    {"kind": "point", "id": "b"},
    {"kind": "constraint", "id": "radius"},
]
proposal = {"kind": "line", "anchor": {"kind": "existing", "point_id": "b"}, "endpoint": [55, 25]}
frame = overlay.build_frame(
    authored, project, selection=selection, annotations=annotations, proposal=proposal
)
check(
    frame.source == "authored" and not frame.unavailable, "Authored frame is explicit and complete"
)
check(
    any(item.kind == "line" and item.selected for item in frame.strokes),
    "Stable-ID line selection is preserved",
)
check(
    any(item.selected and item.identifier == "b" for item in frame.markers),
    "Point selection is independent of line selection",
)
check(
    any(item.proposal for item in frame.strokes) and any(item.proposal for item in frame.markers),
    "Unaccepted proposal has separate presentation flags",
)
radius_label = next(item for item in frame.labels if item.kind == "radius")
check(
    radius_label.text == "R ~5.12346 mm" and radius_label.measured_mm == 5.1234567890123,
    "Readable authored radius is approximate while raw measured precision is retained",
)
check(
    radius_label.raw_value == "size / 2" and radius_label.detail == "value: size / 2",
    "Formula remains exact and is separate from the measured label",
)
check(
    next(item for item in frame.labels if item.kind == "distance").raw_value == 50.0,
    "Literal source value survives readable formatting",
)
rejects(lambda: setattr(frame, "source", "solved"), FrozenInstanceError)
check(True, "Detached frame dataclass is immutable")
rejects(lambda: overlay.build_frame(solved, project))
rejects(lambda: overlay.build_frame(solved, project, current_request_fingerprint="stale"))
current = overlay.build_frame(
    solved, project, annotations=annotations, current_request_fingerprint=fingerprint
)
check(
    next(item for item in current.labels if item.kind == "radius").text == "R 6 mm",
    "Only exact current solved geometry receives solved dimension formatting",
)
check(
    overlay.AUTHORED != overlay.SOLVED != overlay.PROPOSAL != overlay.SELECTED,
    "Authored, solved, proposal and selection styles are distinct",
)
with patch.object(overlay.gpu.shader, "from_builtin", side_effect=AssertionError("GPU touched")):
    rejects(lambda: overlay.draw_frame(current))
    rejects(lambda: overlay.draw_frame(current, current_request_fingerprint="stale"))
check(True, "Stale or missing currency is rejected before any draw GPU work")

invisible = overlay.build_frame(authored, lambda world: None, annotations=annotations)
check(
    not invisible.strokes
    and not invisible.markers
    and not invisible.labels
    and invisible.unavailable,
    "Invisible projection is omitted with explicit issues",
)
limited = overlay.build_frame(authored, project, max_project_calls=1)
check(
    limited.projection_calls <= 1 and limited.unavailable,
    "Projection budget is bounded and visible",
)
limited = overlay.build_frame(authored, project, max_segments=1)
check(
    sum(len(item.segments) for item in limited.strokes) <= 1 and limited.unavailable,
    "Total line-segment output has a hard bound",
)
limited = overlay.build_frame(authored, project, max_circle_segments=8, circle_error_px=1e-6)
check(
    any(item.reason == "refinement_budget" for item in limited.unavailable),
    "Circle refinement exhaustion cannot look complete",
)
bad_annotations = copy.deepcopy(annotations)
bad_annotations["radius"]["refs"] = ["missing"]
missing = overlay.build_frame(
    authored,
    project,
    annotations=bad_annotations,
    selection=[{"kind": "point", "id": "missing"}],
    proposal={
        "kind": "circle",
        "anchor": {"kind": "existing", "point_id": "missing"},
        "radius": 10,
    },
)
check(
    {item.reason for item in missing.unavailable}
    >= {"annotation_binding_unavailable", "selection_unavailable", "anchor_unavailable"},
    "Unavailable relation, selection and proposal bindings remain explicit",
)
circle_preview = overlay.build_frame(
    authored,
    project,
    proposal={"kind": "circle", "anchor": {"kind": "new", "position": [60, 15]}, "radius": 10},
)
check(
    any(item.kind == "circle" and item.proposal for item in circle_preview.strokes),
    "Analytic circle proposals project through the shared bounded sampler",
)
zero_preview = overlay.build_frame(
    authored,
    project,
    proposal={"kind": "circle", "anchor": {"kind": "new", "position": [60, 15]}, "radius": 0},
)
check(
    any(item.proposal for item in zero_preview.markers)
    and not any(item.proposal for item in zero_preview.strokes),
    "Zero-radius pointer preview draws its observed center only",
)
for kwargs in (
    {"max_segments": 0},
    {"max_project_calls": 0},
    {"max_circle_segments": 10000},
    {"circle_error_px": float("nan")},
    {"max_segments": True},
):
    rejects(lambda kwargs=kwargs: overlay.build_frame(authored, project, **kwargs))
check(True, "Malformed resource budgets fail before projection")

arc_source = {
    "schema_version": 3,
    "id": "arc_sketch",
    "units": "mm",
    "plane": {"id": "arc_plane", "origin": [0, 0, 0], "quaternion": [1, 0, 0, 0]},
    "points": [
        {"id": "center", "u": 0, "v": 0},
        {"id": "start", "u": 50, "v": 0},
        {"id": "end", "u": 0, "v": 70},
    ],
    "lines": [],
    "circles": [],
    "arcs": [{"id": "arc", "center": "center", "start": "start", "end": "end", "direction": "ccw"}],
    "constraints": [{"id": "arc_radius", "kind": "radius", "refs": ["arc"], "value": "size / 2"}],
}
arc_proposal = {
    "kind": "arc",
    "phase": "end",
    "direction": "cw",
    "center": {"kind": "new", "position": [60, 40]},
    "start": {"kind": "new", "position": [90, 40]},
    "observation": {"kind": "new", "position": [60, 80]},
}
before_arc = copy.deepcopy((arc_source, arc_proposal))
arc_frame = overlay.build_frame(
    geometry.build_geometry(arc_source, source="authored"),
    project,
    selection=[{"kind": "arc", "id": "arc"}],
    proposal=arc_proposal,
    annotations={
        "arc_radius": {"kind": "radius", "refs": ["arc"], "display": "radius", "offset": [0, 60]}
    },
)
check(not arc_frame.unavailable, "Finite arc and raw-end proposal frames are complete")
check(
    any(item.kind == "arc" and item.selected for item in arc_frame.strokes)
    and any(item.kind == "arc" and item.proposal for item in arc_frame.strokes),
    "Selected and proposed finite arcs have separate exact display identities",
)
check(
    len([item for item in arc_frame.strokes if item.kind == "arc_discrepancy"]) == 2,
    "Authored and proposed unequal raw ends each retain their visible discrepancy connector",
)
check(
    any(
        item.role == "Observed end" and item.position == project((60, 80, 0))
        for item in arc_frame.markers
    ),
    "Arc proposal marker stays at its raw observed end rather than the support circle",
)
check(
    [item.text for item in arc_frame.arc_labels]
    == [
        "CCW (local UV) +90° · minor",
        "CW (local UV) -270° · major",
    ]
    and all("Provisional until Check" in item.detail for item in arc_frame.arc_labels),
    "Direction, signed sweep and meaning remain explicitly provisional before genuine Check",
)
check(
    arc_frame.labels[0].text == "R ~50 mm" and arc_frame.labels[0].raw_value == "size / 2",
    "Arc radius label uses measured start radius while retaining the exact raw driver",
)

# gpu.init is native Blender's documented background GPU initialization API.
# Offscreen output proves drawing calls execute; it does not qualify actual UI.
gpu.init()
offscreen = gpu.types.GPUOffScreen(720, 560)
try:
    with offscreen.bind(), gpu.matrix.push_pop(), gpu.matrix.push_pop_projection():
        gpu.matrix.load_matrix(Matrix.Identity(4))
        gpu.matrix.load_projection_matrix(
            Matrix(((2 / 720, 0, 0, -1), (0, 2 / 560, 0, -1), (0, 0, -1, 0), (0, 0, 0, 1)))
        )
        framebuffer = gpu.state.active_framebuffer_get()
        framebuffer.clear(color=(0, 0, 0, 0), depth=1)
        gpu.state.blend_set("ADDITIVE")
        gpu.state.depth_test_set("LESS_EQUAL")
        gpu.state.depth_mask_set(True)
        gpu.state.line_width_set(2.0)
        saved = gpu_state()
        hit_boxes = overlay.draw_frame(frame, usable_rect=(20, 20, 690, 540))
        check(
            len(hit_boxes) == len(frame.labels)
            and all(
                20 <= box[0] <= box[2] <= 690 and 20 <= box[1] <= box[3] <= 540
                for _, box in hit_boxes
            ),
            "Rendered dimension hit boxes use the actual clamped pixel layout",
        )
        check(gpu_state() == saved, "Native authored draw restores prior GPU state")
        with patch.object(overlay.blf, "draw", wraps=overlay.blf.draw) as arc_draw:
            arc_boxes = overlay.draw_frame(arc_frame, usable_rect=(20, 20, 690, 540))
        arc_text = [call.args[1] for call in arc_draw.call_args_list]
        check(
            all(label.text in arc_text for label in arc_frame.arc_labels)
            and "Observed end" in arc_text
            and "Raw end" in arc_text,
            "Native arc drawing shows signed sweep meaning and actual end-marker roles",
        )
        check(
            len(arc_boxes) == len(arc_frame.labels)
            and all(identifier == "arc_radius" for identifier, _ in arc_boxes),
            "Arc explanatory text creates no fictitious editable dimension hit targets",
        )
        check(gpu_state() == saved, "Native finite arc draw restores prior GPU state")
        with patch.object(overlay.blf, "draw", wraps=overlay.blf.draw) as retained_draw:
            overlay.draw_frame(retained_frame, usable_rect=(20, 20, 690, 540))
        check(
            "Unverified edit · retained outline"
            in [call.args[1] for call in retained_draw.call_args_list],
            "Native retained rendering explicitly labels its lack of solver currency",
        )
        check(gpu_state() == saved, "Native retained draw restores prior GPU state")
        with patch.object(overlay.blf, "draw", wraps=overlay.blf.draw) as drawn:
            overlay.draw_frame(frame, scale=1.2, usable_rect=(20, 20, 690, 540))
        displayed = [call.args[1] for call in drawn.call_args_list]
        check(
            all(label.text in displayed for label in frame.labels),
            "Fractional UI scale does not hide labels through floating-point height rounding",
        )
        with patch.object(overlay.blf, "draw", wraps=overlay.blf.draw) as drawn:
            overlay.draw_frame(limited, usable_rect=(20, 20, 300, 540))
        check(
            any(call.args[1].startswith("Incomplete display") for call in drawn.call_args_list),
            "A narrow status field keeps the incomplete-display warning first",
        )
        overlay.draw_frame(
            current,
            current_request_fingerprint=fingerprint,
            origin=(24, 50),
            usable_rect=(20, 20, 690, 540),
        )
        check(gpu_state() == saved, "Native solved draw restores prior GPU state")
        raw = "  size\t+\n2  "
        layout = overlay.draw_editor(
            raw,
            10,
            3,
            error="Unknown parameter: size",
            origin=(800, 800),
            usable_rect=(20, 20, 690, 540),
        )
        check(gpu_state() == saved, "Native text/selection/caret draw restores GPU state")
        check(
            layout.selection is not None
            and r"\t" in layout.display_text
            and r"\n" in layout.display_text
            and "\t" not in layout.display_text,
            "Escaped Unicode-scalar projection aligns the raw selection",
        )
        check(
            layout.bounds[0] >= 20
            and layout.bounds[1] >= 20
            and layout.bounds[2] <= 690
            and layout.bounds[3] <= 540,
            "Compact field clamps to the owner-supplied usable rectangle",
        )
        check(
            layout.bounds[0] <= layout.caret[0] <= layout.bounds[2],
            "Caret stays within the compact field",
        )
        long_raw = "x" * 65530
        layout = overlay.draw_editor(long_raw, len(long_raw), 0, origin=(20, 110), width=250)
        check(
            layout.visible_range[1] - layout.visible_range[0] <= overlay.MAX_VISIBLE_SCALARS
            and layout.visible_range[1] == len(long_raw),
            "Long raw fields measure only bounded visible scalar context",
        )
        check(layout.selection is not None, "Offscreen selection is clipped to visible raw context")
        tiny = overlay.draw_editor("size", 4, 0, usable_rect=(0, 0, 50, 20))
        check(
            tiny.display_text == "" and tiny.bounds == (0, 0, 50, 20),
            "Too-small safe area does not spill text outside it",
        )
        overlay.draw_editor("", 0, 0, caret_visible=False, origin=(400, 50))
        check(gpu_state() == saved, "Empty field and externally hidden caret restore GPU state")

        pixels = framebuffer.read_color(0, 0, 720, 560, 4, 0, "FLOAT")
        pixels.dimensions = (720 * 560 * 4,)
        check(all(math.isfinite(value) for value in pixels), "Native framebuffer pixels are finite")
        check(
            sum(value > 0.1 for value in pixels) > 1000,
            "Native GPU and BLF calls produced actual offscreen pixels",
        )
        for callback in (
            lambda: overlay.draw_frame(frame),
            lambda: overlay.draw_editor("size / 2", 8, 3),
        ):
            with patch.object(
                overlay, "batch_for_shader", side_effect=RuntimeError("injected batch")
            ):
                rejects(callback, RuntimeError)
            check(
                gpu_state() == saved,
                "Injected native batch failure restores every changed GPU state",
            )
            with patch.object(overlay.blf, "draw", side_effect=RuntimeError("injected text")):
                rejects(callback, RuntimeError)
            check(gpu_state() == saved, "Injected BLF failure restores every changed GPU state")
        real_mask_set = gpu.state.depth_mask_set

        def fail_setup(value):
            if not value:
                raise RuntimeError("injected setup")
            real_mask_set(value)

        with patch.object(overlay.gpu.state, "depth_mask_set", side_effect=fail_setup):
            rejects(lambda: overlay.draw_frame(frame), RuntimeError)
        check(
            gpu_state() == saved, "Partial GPU setup failure still restores preceding state changes"
        )
        for callback in (
            lambda: overlay.draw_editor("bad", 9, 0),
            lambda: overlay.draw_editor("bad", 0, 0, width=float("inf")),
            lambda: overlay.draw_editor("bad", 0, 0, usable_rect=(4, 0, 1, 1)),
            lambda: overlay.draw_frame(frame, scale=float("nan")),
            lambda: overlay.draw_frame(frame, origin=(float("inf"), 0)),
            lambda: overlay.draw_editor("bad", 0, 0, origin=(0,)),
        ):
            rejects(callback)
        check(gpu_state() == saved, "Invalid presentation arguments cannot alter GPU state")
finally:
    offscreen.free()

check(
    (sketch, annotations, request, response) == before_source,
    "Projection and drawing never change source, placement, request or response",
)
check(native_state() == before_native, "No scene, object, mesh or user unit state was changed")
check(
    (arc_source, arc_proposal) == before_arc, "Arc draw never repairs or changes raw endpoint seeds"
)
check(
    not any(name == "OCP" or name.startswith("OCP.") or name == "slvs" for name in sys.modules),
    "Native CAD modules are never imported into Blender",
)
print(
    "GENERAL_OVERLAY_SMOKE_OK", len(checks), "checks; real offscreen GPU/BLF; not GUI qualification"
)
for description in checks:
    print("PASS", description)
