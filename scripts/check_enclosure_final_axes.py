"""Inspect actual final cylindrical bore axes; no persistent identity inference."""

import json
import sys
from pathlib import Path

from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Cylinder
from OCP.TopAbs import TopAbs_FACE
from OCP.TopoDS import TopoDS

from mechanical_cad.engine import regenerate
from mechanical_cad.kernel_ocp import OCPKernel, _subshapes
from mechanical_cad.model import Document

P = Path(sys.argv[1])
results = {}


def solid(d):
    k = OCPKernel()
    r = regenerate(Document.from_dict(d), k, result_version=3)
    assert r.ok
    return k, r.shapes[d["active_feature"]]


def axes(s, radii):
    out = set()
    for f in _subshapes(s, TopAbs_FACE):
        a = BRepAdaptor_Surface(TopoDS.Face(f))
        if a.GetType() != GeomAbs_Cylinder:
            continue
        c = a.Cylinder()
        if (
            any(abs(c.Radius() - r) < 1e-7 for r in radii)
            and abs(c.Axis().Direction().Z()) > 1 - 1e-8
        ):
            p = c.Axis().Location()
            out.add((round(p.X(), 10), round(p.Y(), 10)))
    return sorted(out, key=lambda p: (p[1], p[0]))


for label, file, diam in [
    ("grouped_nominal", "removable_duct_cover.mcad.json", [1.6]),
    ("grouped_diameter", "hole_edited.mcad.json", [1.6, 1.8]),
    ("datum_nominal", "removable_duct_cover_datum.mcad.json", [1.6]),
]:
    d = json.loads((P / file).read_text())
    k, s = solid(d)
    v = axes(s, diam)
    assert len(v) == 4
    results[label] = {"actual_final_bore_axes_xy_mm": v, "solid_count": k.inspect(s)["solids"]}
d = json.loads((P / "removable_duct_cover_datum.mcad.json").read_text())
d["features"] = [f for f in d["features"] if not f["id"].startswith("mount_4")]
d["active_feature"] = "mount_3"
k, s = solid(d)
v = axes(s, [1.6])
assert len(v) == 3
results["datum_three_mounts"] = {
    "actual_final_bore_axes_xy_mm": v,
    "check": k.manufacturing_check(s),
    "note": "Three bores; fourth base post intentionally unused. No strength claim.",
}
(P / "datum_three_mounts_edit.mcad.json").write_text(json.dumps(d, indent=2) + "\n")
# Inspect final BRep cylinders on BOTH Parts, after upstream/diameter edits.
for label, parameters in [
    ("datum_diameter_final", {"mount_diameter": 3.6, "counterbore_diameter": 6.8}),
    (
        "datum_size_final",
        {
            "width": 110,
            "depth": 76,
            "height": 40,
            "mount_edge": 8,
            "mount_diameter": 3.6,
            "counterbore_diameter": 6.8,
        },
    ),
]:
    pair = {}
    for part, filename, radii in [
        ("posts", "ventilated_body_datum.mcad.json", [4.5]),
        ("bores", "removable_duct_cover_datum.mcad.json", [1.8]),
    ]:
        changed = json.loads((P / filename).read_text())
        changed["parameters"].update(parameters)
        kernel, shape = solid(changed)
        pair[part] = axes(shape, radii)
        assert len(pair[part]) == 4
        assert kernel.inspect(shape)["solids"] == 1
    assert pair["posts"] == pair["bores"], pair
    results[label] = pair
(P / "final_hole_axes_report.json").write_text(json.dumps(results, indent=2) + "\n")
print(results)
