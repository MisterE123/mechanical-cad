# ruff: noqa: E402, F401, F403, F405
# Research-only direct native API probes; not imported by production.
"""Assert the bounded experimental observations, not a production arc feature."""

import json
import math
import os
from pathlib import Path

ROOT = Path(os.environ.get("MCAD_ARC_EVIDENCE", "/tmp/mcad-arc-kernel-evidence"))
main = json.loads((ROOT / "probe_contract_results.json").read_text())
boundaries = json.loads((ROOT / "probe_boundaries_results.json").read_text())
lineage = json.loads((ROOT / "probe_lineage_results.json").read_text())
checks = 0


def require(condition):
    global checks
    assert condition
    checks += 1


expected = {
    "quarter_ccw": 5 * math.pi,
    "quarter_cw": 5 * math.pi,
    "major_ccw": 15 * math.pi,
    "major_cw": 15 * math.pi,
    "semicircle_ccw": 10 * math.pi,
    "semicircle_cw": 10 * math.pi,
    "seam_ccw": 10 * math.pi / 9,
}
for name, length in expected.items():
    row = main["directed_arcs"][name]
    require(row["valid"] and not row["vertices_same"])
    require(math.isclose(row["length"], length, rel_tol=1e-12))
for _name, row in main["profiles"].items():
    require(row["valid"])
    require(
        math.isclose(row["stats"]["volume"], row["analytic_volume"], rel_tol=1e-9, abs_tol=1e-8)
    )
    require(all(n == 1 for n in row["generated_counts"].values()))
    require(all(face["provenance"]["semantic_status"] == "stable" for face in row["topology"]))
    require(
        all(
            face["signature"]["surface"] == "cylinder"
            for face in row["topology"]
            if face["role"].startswith("side.arc.")
        )
    )
    require(row["mesh"]["check"]["watertight"] and row["mesh"]["check"]["consistently_oriented"])
    require(set(row["mesh"]["face_ids"]) == {face["id"] for face in row["topology"]})
require(main["raw_parameter_boundaries"]["0.0"]["vertices_same"])
require(math.isclose(main["raw_parameter_boundaries"]["0.0"]["length"], 20 * math.pi))
require(main["raw_parameter_boundaries"]["1e-10"]["length"] > 60)
require(main["raw_parameter_boundaries"]["1e-08"]["vertices_same"])
require(boundaries["parametric_confusion"] == 1e-9)
require(
    any(
        row["radius"] == 1e6
        and row["sweep"] == 1e-10
        and row["chord"] > 1e-6
        and row["length"] > 6e6
        for row in boundaries["radius_parameter_grid"]
    )
)
require(boundaries["raw_wire_history"]["generated_raw_line"] == 0)
require(boundaries["raw_wire_history"]["generated_inserted_line"] == 1)
require(
    boundaries["open_wire"]
    == {"done": True, "valid": True, "closed": False, "vertices": 3, "edges": 2}
)
order = lineage["graph_and_order"]
require(order["distinct_canonical_traversals"] == 1)
require(order["all_semantic_role_status_surface_maps_equal"])
require(order["min_volume"] == order["max_volume"])
require(order["cases"]["equal_coords_distinct_ids"]["error"] == "ValueError")
require(order["cases"]["explicit_coincidence"][0] == "open")
require(order["cases"]["branch"]["error"] == "ValueError")
require(order["cases"]["two_arc_disk"][0] == "closed")
cut = lineage["cuts"]["full_height_notch"]
require(len(cut["arc_images"]) == 2)
require(all(face["provenance"]["semantic_status"] == "split" for face in cut["arc_images"]))
require(cut["resolution"]["status"] == "ambiguous")
require(lineage["cuts"]["partial_height_window"]["resolution"]["status"] == "resolved")
print(f"{checks} bounded evidence assertions passed.")
