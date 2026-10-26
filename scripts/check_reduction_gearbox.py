"""Bounded exact-geometry/export/edit evidence for the gearbox example."""

import argparse
import json
import math
from pathlib import Path

from generate_reduction_gearbox import build, housing

from mechanical_cad.actions import run_geometry_action
from mechanical_cad.assembly_kinematics import evaluate
from mechanical_cad.assembly_model import AssemblyDocument
from mechanical_cad.engine import regenerate
from mechanical_cad.kernel_ocp import OCPKernel, _shape_bounds
from mechanical_cad.model import Document

p = argparse.ArgumentParser()
p.add_argument("--out", type=Path, required=True)
args = p.parse_args()
out = args.out
k = OCPKernel()
a, docs = build()
assembly = AssemblyDocument.from_dict(a)
shapes = {}
report = {"parts": {}, "poses": [], "variants": []}
for d in docs:
    model = Document.from_dict(d)
    r = regenerate(model, k, result_version=3)
    assert r.ok, d["id"]
    shape = r.shapes[d["active_feature"]]
    shapes[d["id"]] = shape
    bounds = _shape_bounds(shape)
    check = k.manufacturing_check(shape, 0.1)
    report["parts"][d["id"]] = {
        "stats": k.inspect(shape),
        "bounds_mm": bounds,
        "dimensions_mm": [bounds[i + 3] - bounds[i] for i in range(3)],
        "check": check,
    }
    assert check["brep"]["solids"] == 1, check
    print("CHECKED", d["id"], flush=True)
    if d["id"] == "reference_shaft":
        continue
    for format in ("step", "stl"):
        response = run_geometry_action(
            model,
            "export_" + format,
            destination=out / (d["id"] + "." + format),
            kernel=k,
            result_version=3,
        )
        assert response["ok"], response["error"]
        report["parts"][d["id"]][format] = response["export"]
        print("EXPORTED", d["id"], format, flush=True)
# Sample one tooth period and a larger input rotation. Check both exact tooth
# meshes and static clearances against the housing; this is not a swept test.
for degrees in (0, 3.06, 8.82, 14.94, 90):
    pose = evaluate(assembly, {"input_rotation": math.radians(degrees)})
    assert pose.status == "evaluated", pose.to_dict()
    world = {
        i.id: k.transformed(shapes[i.part_id], pose.transforms[i.id]) for i in assembly.instances
    }
    pairs = [("input_gear", "middle_wheel"), ("middle_pinion", "output_wheel")]
    if degrees in (0, 90):
        pairs += [
            ("housing", i)
            for i in (
                "input_gear",
                "middle_wheel",
                "middle_pinion",
                "output_wheel",
                "input_shaft",
                "middle_shaft",
                "output_shaft",
            )
        ] + [("cover", "middle_pinion"), ("cover", "output_wheel")]
    rows = []
    for ia, ib in pairs:
        q = k.pair_check(world[ia], world[ib])
        rows.append(dict(instances=[ia, ib], **q))
        assert q["complete"], q
        assert not q["known_interference"], q
    report["poses"].append({"input_degrees": degrees, "pose": pose.to_dict(), "pairs": rows})
    print("POSE", degrees, flush=True)
for name, kwargs in [
    ("wall_4_5_wider_deeper", dict(wall=4.5, width=210, depth=106)),
    (
        "teeth_21_42_centers_63",
        dict(spacing=63, teeth_small=21, teeth_large=42, width=210, depth=106),
    ),
]:
    va, vds = build(**kwargs)
    vreport = {}
    for d in vds:
        r = regenerate(Document.from_dict(d), k, result_version=3)
        assert r.ok, d["id"]
        vreport[d["id"]] = k.inspect(r.shapes[d["active_feature"]])
        assert vreport[d["id"]]["solids"] == 1
        vreport[d["id"]]["geometry_check"] = k.manufacturing_check(
            r.shapes[d["active_feature"]], 0.1
        )
    path = out / "edit_examples"
    path.mkdir(exist_ok=True)
    (path / (name + ".mcad-assembly.json")).write_text(json.dumps(va, indent=2) + "\n")
    report["variants"].append({"name": name, "parameters": kwargs, "parts": vreport})
    print("VARIANT", name, flush=True)
# Preserve the initial impossible inner corner radius as a compact design
# failure, explicitly NOT an implementation defect or a topology bypass.
bad = housing()
bad["parameters"]["edge_radius"] = 2
bad["features"] = bad["features"][:4]
bad["active_feature"] = "open_shell"
r = regenerate(Document.from_dict(bad), k, result_version=3)
assert not r.ok
path = out / "repros"
path.mkdir(exist_ok=True)
(path / "shell_radius_smaller_than_wall.mcad.json").write_text(json.dumps(bad, indent=2) + "\n")
report["expected_design_refusal"] = [
    row for row in r.result["features"] if row["status"] == "failed"
]
# Avoid huge cached meshes in the compact evidence record.
for row in report["expected_design_refusal"]:
    row.pop("mesh", None)
(out / "geometry_evidence.json").write_text(json.dumps(report, indent=2) + "\n")
print("GEARBOX_CORE_EVIDENCE_OK", flush=True)
