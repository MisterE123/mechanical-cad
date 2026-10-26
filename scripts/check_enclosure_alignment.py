"""Measure centroid-relative Hole drift; author and test datum-driven alternative."""

import copy
import json
import sys
from pathlib import Path

from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps

from mechanical_cad.engine import regenerate
from mechanical_cad.kernel_ocp import OCPKernel
from mechanical_cad.model import Document

OUT = Path(sys.argv[1])
body = json.loads((OUT / "ventilated_body.mcad.json").read_text())
cover = json.loads((OUT / "removable_duct_cover.mcad.json").read_text())


def replay(d):
    k = OCPKernel()
    r = regenerate(Document.from_dict(d), k, result_version=3)
    assert r.ok, [(f["id"], f.get("error")) for f in r.result["features"] if f["status"] != "ok"]
    return k, r


def center(shape):
    g = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape, g)
    return list(g.CentreOfMass().Coord())[:2]


def compare(label, b, c, prefix="hole_"):
    _, br = replay(b)
    _, cr = replay(c)
    posts = [center(br.shapes[f"post_profile_{i}"]) for i in range(4)]
    ids = [
        f"hole_{i + 1:032x}_profile" if prefix == "hole_" else f"mount_{i + 1}_profile"
        for i in range(4)
    ]
    bores = [center(cr.shapes[i]) for i in ids]
    delta = [[v[j] - p[j] for j in range(2)] for p, v in zip(posts, bores, strict=True)]
    result = {
        "post_centers_mm": posts,
        "hole_centers_mm": bores,
        "delta_xy_mm": delta,
        "max_center_misalignment_mm": max((x * x + y * y) ** 0.5 for x, y in delta),
    }
    print(label, result["max_center_misalignment_mm"], flush=True)
    return result


report = {"grouped_nominal": compare("grouped_nominal", body, cover)}
changed = json.loads((OUT / "hole_edited.mcad.json").read_text())
report["grouped_diameter_edit"] = compare("grouped_diameter_edit", body, changed)
b = copy.deepcopy(body)
c = copy.deepcopy(cover)
for d in (b, c):
    d["parameters"].update(width=110, depth=76, height=40)
report["grouped_size_edit"] = compare("grouped_size_edit", b, c)
# Keep the original grouped-Hole workflow as a repro; do not hide its local-frame rule.
base = copy.deepcopy(body)
base["id"] = "ventilated_body_datum"
base["name"] = "Datum-stable ventilated base"
base["parameters"].update(mount_edge=7, pilot_diameter=2.6)
positions = [
    ("mount_edge", "mount_edge"),
    ("width-mount_edge", "mount_edge"),
    ("mount_edge", "depth-mount_edge"),
    ("width-mount_edge", "depth-mount_edge"),
]
for i, (x, y) in enumerate(positions):
    for f in base["features"]:
        if f["id"] in (f"post_profile_{i}", f"pilot_profile_{i}"):
            f["params"].update(x=x, y=y)
            if f["id"].startswith("pilot_"):
                f["params"]["radius"] = "pilot_diameter/2"
lid = copy.deepcopy(cover)
lid["id"] = "removable_duct_cover_datum"
lid["name"] = "Datum-stable removable duct cover"
lid["parameters"].update(
    mount_edge=7,
    mount_diameter=3.2,
    mount_depth="cover+1",
    counterbore_diameter=6.4,
    counterbore_depth=1.6,
)
lid["features"] = lid["features"][:15]
assert lid["features"][-1]["id"] == "open_airway"
last = "open_airway"
for i, (x, y) in enumerate(positions):
    root = f"mount_{i + 1}"

    def add(suffix, kind, params, inputs, label, root=root):
        id = root + suffix
        lid["features"].append(dict(id=id, kind=kind, params=params, inputs=inputs, label=label))
        return id

    profile = add(
        "_profile",
        "sketch_circle",
        dict(radius="mount_diameter/2", x=x, y=y, z="cover"),
        {},
        f"Mount {i + 1} datum circle",
    )
    tool = add(
        "_tool",
        "extrude",
        dict(length="-mount_depth"),
        dict(profile=profile),
        f"Mount {i + 1} bore depth",
    )
    bore = add("_bore", "cut", {}, dict(base=last, tool=tool), f"Mount {i + 1} through bore")
    profile = add(
        "_counter_profile",
        "sketch_circle",
        dict(radius="counterbore_diameter/2", x=x, y=y, z="cover"),
        {},
        f"Mount {i + 1} counterbore datum",
    )
    tool = add(
        "_counter_tool",
        "extrude",
        dict(length="-counterbore_depth"),
        dict(profile=profile),
        f"Mount {i + 1} counterbore depth",
    )
    last = add("", "cut", {}, dict(base=bore, tool=tool), f"Mount {i + 1} counterbore")
lid["active_feature"] = last
for d in (base, lid):
    d = Document.from_dict(d).to_dict()
    k, r = replay(d)
    shape = r.shapes[d["active_feature"]]
    (OUT / (d["id"] + ".mcad.json")).write_text(json.dumps(d, indent=2) + "\n")
    k.export_step(shape, str(OUT / (d["id"] + ".step")))
    k.export_stl(shape, str(OUT / (d["id"] + ".stl")))
    report[d["id"] + "_check"] = k.manufacturing_check(shape)
report["datum_nominal"] = compare("datum_nominal", base, lid, "mount_")
b = copy.deepcopy(base)
c = copy.deepcopy(lid)
c["parameters"].update(mount_diameter=3.6, counterbore_diameter=6.8)
report["datum_diameter_edit"] = compare("datum_diameter_edit", b, c, "mount_")
for d in (b, c):
    d["parameters"].update(width=110, depth=76, height=40, mount_edge=8)
report["datum_size_and_edge_edit"] = compare("datum_size_and_edge_edit", b, c, "mount_")
for key in ["datum_nominal", "datum_diameter_edit", "datum_size_and_edge_edit"]:
    assert report[key]["max_center_misalignment_mm"] < 1e-8
(OUT / "alignment_report.json").write_text(json.dumps(report, indent=2) + "\n")
print("ENCLOSURE_DATUM_ALIGNMENT_OK", flush=True)
