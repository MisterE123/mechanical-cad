"""Build and verify an unlinked adapter over a freshly imported oblique STEP base.

Run in the isolated CAD Python runtime, never in Blender. Output goes to an
explicit new directory; generated STEP bytes are embedded in the canonical model.
"""

from __future__ import annotations

import argparse
import copy
import importlib
import json
import math
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
p = types.ModuleType("adapter_example_addon")
p.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[p.__name__] = p
frames = importlib.import_module(p.__name__ + ".assembly_frame_evidence")
offsets = importlib.import_module(p.__name__ + ".fixed_plane_edit")

from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Cut  # noqa: E402
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform  # noqa: E402
from OCP.BRepExtrema import BRepExtrema_DistShapeShape  # noqa: E402
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox  # noqa: E402
from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec  # noqa: E402

from mechanical_cad.actions import run_geometry_action  # noqa: E402
from mechanical_cad.engine import regenerate  # noqa: E402
from mechanical_cad.kernel_ocp import OCPKernel, _shape_bounds  # noqa: E402
from mechanical_cad.model import Document  # noqa: E402
from mechanical_cad.step_asset import encode_step  # noqa: E402


def feature(identifier, kind, params=None, inputs=None, **extra):
    return dict(id=identifier, kind=kind, label=identifier.replace("_", " ").title(),
                params=params or {}, inputs=inputs or {}, **extra)


def replay(data):
    kernel = OCPKernel()
    result = regenerate(Document.from_dict(data), kernel, result_version=3)
    assert result.ok, [(f["id"], f.get("error")) for f in result.result["features"]
                       if f["status"] != "ok"]
    return kernel, result


def outline(plane):
    points = [(-30, -20), (30, -20), (30, 20), (-30, 20)]
    return feature("adapter_outline", "sketch_constrained", sketch={
        "schema_version": 1, "id": "adapter_outline_geometry", "units": "mm",
        "plane": copy.deepcopy(plane),
        "points": [dict(id=f"p{i}", u=x, v=y) for i, (x, y) in enumerate(points)],
        "lines": [dict(id=f"l{i}", start=f"p{i}", end=f"p{(i+1)%4}") for i in range(4)],
        "constraints": [
            dict(id="anchor", kind="fixed", refs=["p0"], target=[-30, -20]),
            *[dict(id=f"axis{i}", kind="horizontal" if i % 2 == 0 else "vertical",
                   refs=[f"l{i}"]) for i in range(4)],
            dict(id="width", kind="distance", refs=["p0", "p1"], value="width"),
            dict(id="height", kind="distance", refs=["p1", "p2"], value="height"),
        ],
    })


def circle(identifier, plane, x, y, radius):
    return feature(identifier, "sketch_constrained", sketch={
        "schema_version": 2, "id": identifier + "_geometry", "units": "mm",
        "plane": copy.deepcopy(plane), "points": [dict(id="center", u=x, v=y)],
        "lines": [], "circles": [dict(id="rim", center="center", radius=3)],
        "constraints": [dict(id="center_lock", kind="fixed", refs=["center"], target=[x, y]),
                        dict(id="radius", kind="radius", refs=["rim"], value=radius)],
    })


def close(actual, expected):
    assert math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-6), (actual, expected)


def build(output):
    output.mkdir(parents=True, exist_ok=False)
    kernel = OCPKernel()
    stock = BRepPrimAPI_MakeBox(gp_Pnt(-40, -30, -12), 80, 60, 12).Shape()
    slot = BRepPrimAPI_MakeBox(gp_Pnt(-10, -5, -13), 20, 10, 14).Shape()
    cut = BRepAlgoAPI_Cut(stock, slot)
    assert cut.IsDone()
    rotation = gp_Trsf()
    rotation.SetRotation(gp_Ax1(gp_Pnt(), gp_Dir(1, 1, 0)), 0.6)
    body = BRepBuilderAPI_Transform(cut.Shape(), rotation, True).Shape()
    source_path = output / "imported_slotted_base.step"
    kernel.export_step(body, source_path)
    data = dict(schema_version=2, id="imported_mounting_adapter",
                name="Unlinked adapter over an oblique imported slotted base", units="mm",
                parameters=dict(width=60, height=40, thickness=6, bolt_radius=3,
                                clearance_radius=7),
                features=[feature("imported_base", "import_step",
                                  step_data=encode_step(source_path.read_bytes()))],
                active_feature="imported_base")
    kernel, initial = replay(data)
    topology = initial.result["features"][0]["topology"]
    assert all(f["provenance"]["semantic_status"] == "unknown" for f in topology)
    direction = gp_Dir(0, 0, 1).Transformed(rotation).Coord()
    # Explicit one-shot geometric selection for this generated fixture only.
    # Neither this selector nor the snapshot face ID enters the model graph.
    faces = [f for f in topology if f["signature"]["surface"] == "plane"
             and sum(a*b for a, b in zip(f["signature"]["normal"], direction, strict=True))
             > 1 - 1e-10]
    assert len(faces) == 1
    frame = frames.face_frame(faces[0]["signature"])
    plane = dict(id="copied_plane", origin=frame["xyz_mm"], quaternion=frame["wxyz"])
    data["features"].append(outline(plane))
    data = offsets.offset_candidate(data, "adapter_outline", "2 mm")
    saved_plane = copy.deepcopy(data["features"][-1]["sketch"]["plane"])
    data["features"].append(feature("adapter_pad", "extrude", {"length": "thickness"},
                                    {"profile": "adapter_outline"}))
    base = "adapter_pad"
    for index, (x, y, radius) in enumerate([
        (-22, -12, "bolt_radius"), (22, -12, "bolt_radius"),
        (22, 12, "bolt_radius"), (-22, 12, "bolt_radius"), (0, 0, "clearance_radius"),
    ], 1):
        identifier = f"bore_{index}"
        data["features"].extend([
            circle(identifier + "_profile", saved_plane, x, y, radius),
            feature(identifier + "_tool", "extrude", {"length": "thickness"},
                    {"profile": identifier + "_profile"}),
            feature(identifier, "cut", inputs={"base": base, "tool": identifier + "_tool"}),
        ])
        base = identifier
    data["active_feature"] = base
    doc = Document.from_dict(data)
    canonical = doc.to_json()
    model_path = output / "imported_mounting_adapter.mcad.json"
    model_path.write_text(canonical + "\n")
    restored = Document.from_json(model_path.read_text())
    assert restored.to_json() == canonical
    data = restored.to_dict()
    kernel, result = replay(data)
    source = result.shapes["imported_base"]
    adapter = result.shapes[base]
    expected_volume = (60*40 - math.pi*(4*3**2 + 7**2))*6
    close(kernel.inspect(source)["volume"], (80*60 - 20*10)*12)
    close(kernel.inspect(adapter)["volume"], expected_volume)
    plane_frame = offsets.Workplane.from_saved(saved_plane)
    cylinder_signatures = [f["signature"] for f in result.result["features"][-1]["topology"]
                           if f["signature"]["surface"] == "cylinder"]
    assert len(cylinder_signatures) == 5
    remaining_centers = [(-22, -12, 3), (22, -12, 3), (22, 12, 3), (-22, 12, 3), (0, 0, 7)]
    max_axis_error = 0
    for signature in cylinder_signatures:
        local = plane_frame.world_to_local(signature["axis_origin"])
        matches = [c for c in remaining_centers
                   if math.dist(local[:2], c[:2]) < 1e-6
                   and abs(signature["radius"] - c[2]) < 1e-6]
        assert len(matches) == 1
        remaining_centers.remove(matches[0])
        max_axis_error = max(max_axis_error, math.dist(local[:2], matches[0][:2]))
        close(abs(sum(a*b for a, b in zip(signature["axis"], plane_frame.normal, strict=True))), 1)
    distance = BRepExtrema_DistShapeShape(source, adapter)
    assert distance.IsDone()
    close(distance.Value(), 2)
    overlap = BRepAlgoAPI_Common(source, adapter)
    assert overlap.IsDone()
    close(kernel.inspect(overlap.Shape())["volume"], 0)
    report = dict(runtime=kernel.runtime_versions(), source=kernel.inspect(source),
                  adapter=kernel.inspect(adapter), expected_adapter_volume_mm3=expected_volume,
                  separation_mm=distance.Value(), overlap_mm3=0,
                  imported_face_identity="unknown", fixed_plane=saved_plane,
                  bore_axis_center_error_mm=max_axis_error, cylindrical_bores=5)
    presentation_meshes = {}
    for name, active in (("base", "imported_base"), ("adapter", base)):
        branch = copy.deepcopy(data)
        branch["active_feature"] = active
        target = output / (name + ".step")
        response = run_geometry_action(Document.from_dict(branch), "export_step",
                                       destination=target, result_version=3)
        assert response["ok"], response.get("error")
        readback = kernel.import_step(target)
        before, after = kernel.inspect(result.shapes[active]), kernel.inspect(readback)
        assert after["valid"] and after["solids"] == 1
        close(after["volume"], before["volume"])
        report[name + "_export_readback"] = after
        stl = run_geometry_action(Document.from_dict(branch), "export_stl",
                                  destination=output / (name + ".stl"), result_version=3)
        assert stl["ok"], stl.get("error")
        presentation_meshes[name] = next(f["mesh"] for f in result.result["features"]
                                         if f["id"] == active)
    (output / "presentation_meshes.json").write_text(json.dumps(presentation_meshes) + "\n")
    # Replace only embedded source bytes. Adapter plane and all authored features
    # intentionally stay fixed; no automatic source tracking is promised.
    move = gp_Trsf()
    move.SetTranslation(gp_Vec(100, 100, 100))
    replacement_path = output / "replacement_base.step"
    kernel.export_step(BRepBuilderAPI_Transform(body, move, True).Shape(), replacement_path)
    changed = copy.deepcopy(data)
    changed["features"][0]["step_data"] = encode_step(replacement_path.read_bytes())
    k2, replaced = replay(changed)
    assert changed["features"][1:] == data["features"][1:]
    assert changed["features"][1]["sketch"]["plane"] == saved_plane
    close(k2.inspect(replaced.shapes[base])["volume"], expected_volume)
    original_adapter = kernel.inspect(adapter)
    assert k2.inspect(replaced.shapes[base]) == original_adapter
    assert _shape_bounds(replaced.shapes[base]) == _shape_bounds(adapter)
    moved_distance = BRepExtrema_DistShapeShape(replaced.shapes["imported_base"],
                                              replaced.shapes[base])
    assert moved_distance.IsDone() and moved_distance.Value() > 100
    report["source_replaced_adapter_unchanged"] = True
    report["replacement_separation_mm"] = moved_distance.Value()
    (output / "source_replaced.mcad.json").write_text(Document.from_dict(changed).to_json() + "\n")
    # Independent parameter edit and invalid replay establish editable intent and
    # visible failure rather than accepting last-good geometry.
    edited = copy.deepcopy(data)
    edited["parameters"].update(thickness=8, bolt_radius=3.5)
    k3, edit_result = replay(edited)
    close(k3.inspect(edit_result.shapes[base])["volume"],
          (60*40 - math.pi*(4*3.5**2 + 7**2))*8)
    (output / "diameter_thickness_edit.mcad.json").write_text(
        Document.from_dict(edited).to_json() + "\n")
    invalid = copy.deepcopy(data)
    invalid["parameters"]["thickness"] = 0
    failure = regenerate(Document.from_dict(invalid), OCPKernel(), result_version=3)
    assert not failure.ok
    bad_export = output / "must_not_exist.step"
    rejection = run_geometry_action(Document.from_dict(invalid), "export_step",
                                    destination=bad_export, result_version=3)
    assert not rejection["ok"] and not bad_export.exists()
    report["invalid_zero_thickness_rejected"] = True
    report["invalid_export_wrote_no_file"] = True
    report["parameter_edit_volume_mm3"] = k3.inspect(edit_result.shapes[base])["volume"]
    (output / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print("IMPORTED_ADAPTER_VERIFIED", json.dumps(report), flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="New output directory, never overwritten")
    build(parser.parse_args().output)
