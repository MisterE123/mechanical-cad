"""Gear configurator RNA and recording-layout contracts; not GUI qualification."""

import copy
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import assembly_job_ui, gear_pair, register  # noqa: E402
from mechanical_cad_blender.gear_pair_ui import (  # noqa: E402
    MCAD_OT_gear_pair,
    draw_gear_parts,
)


class Layout:
    def __init__(self):
        self.fields = []
        self.rows = []
        self.labels = []
        self.buttons = []
        self.button_properties = []
        self.enabled = True

    def prop(self, owner, field, **kwargs):
        self.fields.append(field)

    def row(self, **kwargs):
        child = Layout()
        self.rows.append(child)
        return child

    def box(self):
        return self

    def label(self, *, text, **kwargs):
        self.labels.append(text)

    def operator(self, identifier, *, text, **kwargs):
        self.buttons.append((identifier, text))
        properties = SimpleNamespace()
        self.button_properties.append(properties)
        return properties


register()
properties = bpy.ops.mcad.gear_pair.get_rna_type().properties
expected = {
    "name": "Printable spur gear pair",
    "module": "2",
    "teeth_a": 20,
    "teeth_b": 40,
    "pressure_angle": "20",
    "thickness": "8",
    "bore_a": "5",
    "bore_b": "5",
    "pair_backlash": "0.2",
    "clearance": "0.25",
    "profile_tolerance": "0.01",
    "replace_existing": False,
    "show_advanced": False,
    "show_details": False,
}
for field, default in expected.items():
    assert properties[field].default == default, field
for field, label, meaning in (
    ("module", "Module (mm)", "millimetres"),
    ("pressure_angle", "Pressure (deg)", "Pressure angle in degrees"),
    ("bore_a", "A bore (mm)", "Driver A bore diameter in millimetres"),
    ("bore_b", "B bore (mm)", "Driven B bore diameter in millimetres"),
    ("pair_backlash", "Backlash (mm)", "Total pair circular backlash in millimetres"),
    ("clearance", "Root (× module)", "dimensionless multiple of module"),
):
    assert properties[field].name == label
    assert meaning in properties[field].description
assert "half is removed" in properties["pair_backlash"].description
assert "not millimetres" in properties["clearance"].description

for accepted in ("", "accepted assembly sentinel"):
    for editing in (False, True):
        layout = Layout()
        owner = SimpleNamespace(**expected, layout=layout, edit_existing=editing)
        owner.parameters = lambda owner=owner: MCAD_OT_gear_pair.parameters(owner)
        context = SimpleNamespace(
            scene=SimpleNamespace(mechanical_cad_assembly=SimpleNamespace(document_json=accepted))
        )
        before = owner.parameters()
        for advanced, details in (
            (False, False),
            (True, False),
            (True, True),
            (False, True),
            (False, False),
        ):
            owner.show_advanced, owner.show_details = advanced, details
            owner.layout = layout = Layout()
            MCAD_OT_gear_pair.draw(owner, context)
            rows = [
                ["teeth_a", "teeth_b"],
                ["module"],
                ["thickness"],
                ["bore_a"],
                ["bore_b"],
                ["pair_backlash"],
            ]
            if advanced:
                rows += [["pressure_angle"], ["clearance"], ["profile_tolerance"]]
            assert [row.fields for row in layout.rows] == rows
            assert layout.fields == ["name", "show_advanced", "show_details"] + (
                ["replace_existing"] if accepted and not editing else []
            )
            assert "Shaft spacing: 60 mm · B/A ratio: -0.5" in layout.labels
            assert any("Reference base is NOT FOR PRINT" in line for line in layout.labels)
            assert any("Interference NOT checked" in line for line in layout.labels)
            assert any(
                "no contact, strength or print-fit guarantee" in line for line in layout.labels
            )
            assert any("no print-fit allowance" in line for line in layout.labels)
            assert any("Automatic +Z" in line for line in layout.labels) == details
            assert any("Pressure 20°" in line for line in layout.labels) == (not advanced)
            assert context.scene.mechanical_cad_assembly.document_json == accepted
            assert owner.parameters() == before
        # Closing disclosures retains typed custom values, including invalid drafts.
        owner.pressure_angle = "25"
        owner.clearance = "0.3"
        owner.profile_tolerance = "0.025"
        owner.layout = layout = Layout()
        MCAD_OT_gear_pair.draw(owner, context)
        assert any(
            "Pressure 25° · Root 0.3 × module · Tolerance 0.025 mm" == line
            for line in layout.labels
        )
        owner.pressure_angle = "invalid draft"
        owner.layout = layout = Layout()
        MCAD_OT_gear_pair.draw(owner, context)
        assert owner.pressure_angle == "invalid draft"
        assert any("invalid draft" in line for line in layout.labels)
        assert owner.show_advanced is False and owner.show_details is False

for width in (220, 300):
    for message in ("", assembly_job_ui.execution_lease.QUARANTINE_MESSAGE):
        layout = Layout()
        context = SimpleNamespace(
            scene=object(),
            region=SimpleNamespace(width=width),
            preferences=SimpleNamespace(system=SimpleNamespace(ui_scale=1)),
        )
        details = {"candidate": True, "state": "running", "elapsed_seconds": 1, "message": message}
        with patch.object(assembly_job_ui.assembly_pending, "status", return_value=details):
            assert assembly_job_ui.draw_pending(layout, context)
        guidance = " ".join(layout.labels[2:])
        assert "Accepted assembly unchanged." in guidance
        assert "Interference NOT checked by this update." in guidance
        for line in layout.labels[2:]:
            assert len(line) <= int((width - 42) / 7.5)
        assert layout.rows[0].buttons == [("mcad.assembly_cancel_check", "Cancel Creation")]
        assert layout.rows[0].enabled == (not message)

print(
    "GEAR_PAIR_DRAW_SMOKE_OK: unchanged defaults, disclosure round trips, draft retention, visible safeguards, progress"
)

# Recording-only export guidance: the exact accepted candidate remains untouched.
data = gear_pair.build_pair()
before = copy.deepcopy(data)
layout = Layout()
draw_gear_parts(layout, data)
assert data == before
assert [identifier for identifier, text in layout.buttons] == [
    "mcad.gear_pair",
    "mcad.assembly_open_part",
    "mcad.assembly_open_part",
]
assert [button.part_id for button in layout.button_properties[1:]] == ["part_1", "part_2"]
assert layout.button_properties[0].edit_existing is True
assert all(len(line) <= 30 for line in layout.labels)
assert " ".join(layout.labels[1:]) == (
    "Open a gear Part for STL/STEP. Assembly STEP includes the reference base, if present."
)
empty = Layout()
draw_gear_parts(empty, {"part_sources": [], "parts": []})
assert not empty.labels and not empty.buttons
print("GEAR_EXPORT_GUIDANCE_DRAW_OK: short complete guidance, unchanged buttons and candidate")
