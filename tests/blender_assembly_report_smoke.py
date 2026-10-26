"""Native Blender fake-layout test for bounded, lossless report-dialog paging.

This tests the actual draw method without opening or manipulating any GUI.
"""

import copy
import json
import os
import sys
from itertools import combinations
from pathlib import Path
from types import SimpleNamespace

import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import assembly_verification_ui as ui  # noqa: E402

checks = []


def check(value, label):
    if not value:
        raise AssertionError(label)
    checks.append(label)


class Layout:
    def __init__(self, root=None, group=None):
        self.root = root or self
        if root is None:
            self.rows = []
        self.group = group

    def row(self, **kwargs):
        group = []
        self.root.rows.append(group)
        return Layout(self.root, group)

    def label(self, *, text, **kwargs):
        target = self.group
        if target is None:
            target = []
            self.root.rows.append(target)
        target.append(("label", text))

    def prop(self, owner, name, **kwargs):
        self.group.append(("prop", name))


instances = [
    {"id": f"i{index}", "name": f"Instance {index} " + "long name " * 24} for index in range(16)
]
joints = [
    {
        "id": f"j{index}",
        "name": f"Joint {index} " + "long name " * 24,
        "kind": "slider" if index % 2 else "revolute",
        "coordinate": index / 3,
    }
    for index in range(15)
]
pairs = [
    {
        "instances": [a["id"], b["id"]],
        "relation": "unknown",
        "clearance_verdict": "indeterminate",
        "complete": False,
        "minimum_distance_mm": 1.23456789012345,
        "minimum_required_mm": 2.5,
        "common_volume_mm3": None,
        "diagnostics": [
            {
                "code": "native_disagreement",
                "message": f"PAIR_{index}_BEGIN "
                + "Read this full correction. " * 20
                + f"PAIR_{index}_END",
            }
        ],
    }
    for index, (a, b) in enumerate(combinations(instances, 2))
]
outcome = {
    "status": "violations_found",
    "passed": False,
    "complete": False,
    "known_interference": True,
    "known_clearance_violation": True,
    "pose": {
        "requested_coordinates": {j["id"]: j["coordinate"] for j in joints},
        "effective_coordinates": {j["id"]: j["coordinate"] for j in joints},
        "diagnostics": [{"message": "Kinematics correction end marker"}],
    },
    "pairs": pairs,
    "diagnostics": [{"message": "Pose correction end marker"}],
}
response = {
    "error": {"message": "Top-level correction end marker"},
    "report": {
        **outcome,
        "poses": [outcome] * 32,
        "verification_basis": {"preset": {"name": "Named preset " * 18}},
        "diagnostics": [{"message": "Report correction end marker"}],
    },
    "result": {
        "canonical_assembly": {"instances": instances, "joints": joints},
        "source_replays": [
            {
                "source_document_id": "source_one",
                "features": [
                    {"id": "feature_one", "error": {"message": "Source correction end marker"}}
                ],
            }
        ],
    },
}
original = copy.deepcopy(response)
encoded = json.dumps(response)
old_state, old_current = ui.state, ui.state_api.report_is_current
ui.state = lambda context: SimpleNamespace(report_json=encoded)
ui.state_api.report_is_current = lambda context: False
try:
    for pose_index in (0, 31):
        for section in ("SUMMARY", "COORDINATES", "PAIRS", "DIAGNOSTICS"):
            lines = ui._report_lines(response, section, pose_index)
            check(
                all(len(line) <= ui.REPORT_LINE_WIDTH for line in lines),
                f"{section} wraps every long name/value/diagnostic",
            )
            pages = max(1, (len(lines) + ui.REPORT_PAGE_LINES - 1) // ui.REPORT_PAGE_LINES)
            seen = []
            for page in range(1, pages + 1):
                layout = Layout()
                operator = SimpleNamespace(
                    layout=layout, section=section, pose_index=pose_index, page=page
                )
                ui.MCAD_OT_assembly_report.draw(operator, SimpleNamespace())
                check(len(layout.rows) <= 13, f"{section} page {page} stays at 13 rows or fewer")
                seen.extend(row[0][1] for row in layout.rows[5:])
            check(seen == lines, f"{section} all wrapped text is accessible exactly once")
            if section == "DIAGNOSTICS":
                joined = " ".join(seen)
                check(
                    all(f"PAIR_{i}_END" in joined for i in range(120)),
                    "all 120 pair diagnostic endings remain accessible",
                )
                check(
                    all(
                        marker in joined
                        for marker in (
                            "Top-level correction",
                            "Source correction",
                            "Report correction",
                            "Pose correction",
                            "Kinematics correction",
                        )
                    ),
                    "all diagnostic scopes accessible",
                )
    check(response == original, "all report draws are read-only")
finally:
    ui.state, ui.state_api.report_is_current = old_state, old_current
check(bpy.app.version[:2] == (5, 2), "native target is Blender 5.2")
print("ASSEMBLY_REPORT_SMOKE_OK", len(checks))
