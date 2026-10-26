"""Exercise downstream edits and bounded invalid cases on the authored example."""

import copy
import importlib
import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
p = types.ModuleType("example_addon")
p.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[p.__name__] = p
edit = importlib.import_module("example_addon.assembly_edit")
hole = importlib.import_module("example_addon.hole_recipe")
from mechanical_cad.engine import regenerate  # noqa: E402
from mechanical_cad.kernel_ocp import OCPKernel, _shape_bounds  # noqa: E402
from mechanical_cad.model import Document  # noqa: E402
from mechanical_cad.sidecar import process_request  # noqa: E402

OUT = Path(sys.argv[1])
report = {}
body = json.loads((OUT / "ventilated_body.mcad.json").read_text())
cover = json.loads((OUT / "removable_duct_cover.mcad.json").read_text())


def check(name, d, ok=True):
    k = OCPKernel()
    r = regenerate(Document.from_dict(d), k, result_version=3)
    report[name] = {
        "ok": r.ok,
        "errors": [{f["id"]: f.get("error")} for f in r.result["features"] if f["status"] != "ok"],
    }
    assert r.ok == ok, (name, report[name])
    if r.ok:
        s = r.shapes[d["active_feature"]]
        report[name].update(check=k.manufacturing_check(s), bounds_mm=_shape_bounds(s))
        assert report[name]["check"]["mesh"]["watertight"]
    print(name, r.ok, flush=True)
    return r


check("body_baseline", body)
check("cover_baseline", cover)
for name, changes in [
    ("body_wider_deeper", dict(width=110, depth=76, height=40)),
    ("body_wall", dict(wall=2.8)),
    ("vent_count", dict(vent_count=6)),
    ("duct_middle", dict(duct_middle=22)),
    ("duct_wall", dict(duct_wall=2.5)),
]:
    d = copy.deepcopy(cover if name.startswith("duct") else body)
    d["parameters"].update(changes)
    check(name, d)
    (OUT / (name + "_edited.mcad.json")).write_text(json.dumps(d, indent=2) + "\n")
root = "hole_" + f"{1:032x}"
values = hole.inspect_hole(cover, root)
assert values
values["diameter"] = 3.6
values["counter_diameter"] = 6.8
changed = hole.hole_candidate(cover, root, editing=True, **values)
check("grouped_hole_diameter", changed)
count_changed = copy.deepcopy(cover)
last_hole = "hole_" + f"{4:032x}"
count_changed["features"] = [
    f for f in count_changed["features"] if not f["id"].startswith(last_hole)
]
count_changed["active_feature"] = "hole_" + f"{3:032x}"
check("hole_count_three", count_changed)
(OUT / "hole_count_3_edited.mcad.json").write_text(json.dumps(count_changed, indent=2) + "\n")
# Nominal Hole centers remain centroid-relative; not edge-constrained under edits.
(OUT / "hole_edited.mcad.json").write_text(json.dumps(changed, indent=2) + "\n")
bad = copy.deepcopy(body)
bad["parameters"]["wall"] = 40
check("invalid_wall_refused", bad, False)
bad = copy.deepcopy(cover)
bad["parameters"]["duct_middle"] = 1
check("invalid_inner_radius_refused", bad, False)
bad = copy.deepcopy(body)
bad["features"][2]["edge_pairs"][0][0] = "blank/face/missing"
check("missing_blend_identity_refused", bad, False)
assembly = edit.new_from_part(
    body, name="Ventilated enclosure • current source", instance_name="Ventilated base"
)
part = assembly["parts"][0]["id"]
root_instance = assembly["instances"][0]["id"]
assembly = edit.edit_frame(
    assembly,
    part,
    name="Cover seat with 0.2 mm illustrative gap",
    placement={"xyz_mm": [0, 0, 35.2], "wxyz": [1, 0, 0, 0]},
)
assembly, cover_id = edit.capture_definition(assembly, cover, name="Removable duct cover")
assembly = edit.insert_instance(
    assembly,
    cover_id,
    parent=root_instance,
    parent_frame=assembly["parts"][0]["mate_frames"][-1]["id"],
    child_frame="origin",
    kind="fixed",
    name="Removable duct cover",
    joint_name="Cover at nominal 0.2 mm gap",
)
assembly = edit.edit_verification_preset(
    assembly,
    name="Interference check at 0.00001 mm resolution",
    kind="interference_only",
    policy={"linear_tolerance_mm": 1e-5, "volume_tolerance_mm3": 1e-7, "linear_deflection_mm": 0.1},
)
(OUT / "ventilated_enclosure.mcad-assembly.json").write_text(json.dumps(assembly, indent=2) + "\n")
for action in ["assembly_replay", "assembly_export_step"]:
    request = dict(
        protocol_version=1,
        kind="assembly",
        assembly_protocol_version=1,
        result_version=3,
        action=action,
        assembly=assembly,
    )
    if action.endswith("step"):
        request["path"] = str((OUT / "ventilated_enclosure.step").resolve())
    if action == "assembly_replay":
        request["policy"] = {
            "linear_tolerance_mm": 1e-5,
            "volume_tolerance_mm3": 1e-7,
            "linear_deflection_mm": 0.1,
        }
    response = process_request(request)
    report[action] = {
        "ok": response.get("ok"),
        "report": response.get("report"),
        "export": response.get("export"),
        "error": response.get("error"),
    }
    if not response.get("ok"):
        print(action, response.get("error"), response.get("report"))
    assert response.get("ok")
(OUT / "validation_report.json").write_text(json.dumps(report, indent=2) + "\n")
print("ENCLOSURE_VALIDATION_OK", list(report), flush=True)
