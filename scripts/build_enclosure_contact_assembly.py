"""Author explicit intended-seat policy and verify exact two-solid STEP readback."""

import copy
import importlib
import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
p = types.ModuleType("contact_example")
p.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[p.__name__] = p
edit = importlib.import_module("contact_example.assembly_edit")
from mechanical_cad.kernel_ocp import OCPKernel, _exact_volume, _shape_bounds  # noqa: E402
from mechanical_cad.sidecar import process_request  # noqa: E402

OUT = Path(sys.argv[1])
base = json.loads((OUT / "ventilated_body_datum.mcad.json").read_text())
lid = json.loads((OUT / "removable_duct_cover_datum.mcad.json").read_text())
a = edit.new_from_part(
    base, name="Datum-stable ventilated enclosure", instance_name="Ventilated base"
)
a = edit.edit_frame(
    a,
    a["parts"][0]["id"],
    name="Intended lid seat at base height",
    placement={"xyz_mm": [0, 0, 35], "wxyz": [1, 0, 0, 0]},
)
a, lid_id = edit.capture_definition(a, lid, name="Datum-stable duct cover")
a = edit.insert_instance(
    a,
    lid_id,
    parent=a["instances"][0]["id"],
    parent_frame=a["parts"][0]["mate_frames"][-1]["id"],
    child_frame="origin",
    kind="fixed",
    name="Removable duct cover",
    joint_name="Cover seated on enclosure rim",
)
a["replay_tolerance_mm"] = 1e-5
pair = [i["id"] for i in a["instances"]]
a = edit.edit_verification_preset(
    a,
    name="Named lid/base intended seat",
    kind="clearance",
    pair=pair,
    minimum_mm=0,
    requirement_name="Lid against enclosure rim",
    contact_policy="accept_tolerance_band",
    policy={"linear_tolerance_mm": 1e-5, "volume_tolerance_mm3": 1e-7, "linear_deflection_mm": 0.1},
)
(OUT / "ventilated_enclosure_datum.mcad-assembly.json").write_text(json.dumps(a, indent=2) + "\n")
reports = {}
for action in ["assembly_replay", "assembly_check", "assembly_export_step"]:
    request = dict(
        protocol_version=1,
        kind="assembly",
        assembly_protocol_version=1,
        result_version=3,
        action=action,
        assembly=a,
    )
    if action == "assembly_export_step":
        request["path"] = str((OUT / "ventilated_enclosure_datum.step").resolve())
    r = process_request(request)
    report = r.get("report") or r.get("result", {}).get("report")
    assert r["ok"], (action, r.get("error"), report)
    reports[action] = {"ok": r["ok"], "report": report, "export": r.get("export")}
    if action != "assembly_replay":
        assert report["policy_accepted"] and not report["passed"] and report["complete"]
        for pose in report["poses"]:
            for row in pose["pairs"]:
                assert (
                    row["common_volume_mm3"] == 0
                    and row["minimum_distance_mm"] == 0
                    and row["clearance_verdict"] == "at_threshold"
                )
    print(action, "OK", flush=True)
k = OCPKernel()
s = k.import_step(str(OUT / "ventilated_enclosure_datum.step"))
reports["step_readback"] = {
    "stats": k.inspect(s),
    "bounds_mm": _shape_bounds(s),
    "exact_volume_mm3": _exact_volume(s),
}
assert reports["step_readback"]["stats"]["solids"] == 2
assert (
    abs(reports["step_readback"]["exact_volume_mm3"] - (51157.52455738847 + 29149.00349893428))
    < 1e-4
)
# Width/depth/edge offsets are changed in both independent Part definitions.
# The assembly seat is deliberately a literal datum, so height needs an explicit
# matching frame edit. This is recorded, not silently advertised as automatic.
edited = copy.deepcopy(a)
for source in (base, lid):
    changed = copy.deepcopy(source)
    changed["parameters"].update(width=110, depth=76, height=40, mount_edge=8)
    if source["id"] == lid["id"]:
        changed["parameters"].update(mount_diameter=3.6, counterbore_diameter=6.8)
    edited, _ = edit.update_source(edited, changed)
frame = edited["parts"][0]["mate_frames"][-1]
edited = edit.edit_frame(
    edited,
    edited["parts"][0]["id"],
    frame_id=frame["id"],
    name=frame["name"],
    placement={"xyz_mm": [0, 0, 40], "wxyz": [1, 0, 0, 0]},
)
request = dict(
    protocol_version=1,
    kind="assembly",
    assembly_protocol_version=1,
    result_version=3,
    action="assembly_check",
    assembly=edited,
)
response = process_request(request)
assert response["ok"] and response["report"]["policy_accepted"]
reports["size_edit_after_explicit_height_frame_update"] = response["report"]
(OUT / "datum_size_edit_assembly.mcad-assembly.json").write_text(
    json.dumps(edited, indent=2) + "\n"
)
(OUT / "datum_assembly_report.json").write_text(json.dumps(reports, indent=2) + "\n")
print("ENCLOSURE_INTENDED_CONTACT_EXPORT_OK", flush=True)
