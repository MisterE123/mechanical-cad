"""Native Shell UI, atomic failure, expressions and two-process persistence.

Run separately with MCAD_SHELL_PHASE=create/reopen and MCAD_SHELL_BLEND outside
source. Headless operator checks do not claim interactive mouse qualification.
"""

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

ROOT = Path(os.environ["MCAD_ROOT"])
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402  # noqa: E402
    document_state,
    register,
    solid_operators,
    unregister,
    workspace_ui,
)

register()
state = bpy.context.scene.mechanical_cad
path = os.environ["MCAD_SHELL_BLEND"]


def run(operator, **kwargs):
    result = operator(**kwargs)
    assert result == {"FINISHED"}, (result, state.last_action_error)
    assert state.status == "READY", (state.status, state.last_action_error)
    return state.active_feature


if os.environ.get("MCAD_SHELL_PHASE") == "reopen":
    bpy.ops.wm.open_mainfile(filepath=path)
    state = bpy.context.scene.mechanical_cad
    run(bpy.ops.mcad.regenerate)
    doc = json.loads(state.document_json)
    assert doc["features"][-1]["opening_faces"][0].endswith("/face/cap.end")
    assert abs(state.volume - (3000 - 16 * 11 * 8)) < 1e-5, state.volume
    print("MCAD_OPEN_SHELL_REOPEN_OK")
else:
    run(bpy.ops.mcad.new_document, name="Picked open enclosure")
    profile = run(bpy.ops.mcad.add_rectangle, width=20, height=15)
    base = run(bpy.ops.mcad.add_extrude, profile=profile, length=10)
    run(
        bpy.ops.mcad.named_parameter,
        parameter_name="wall",
        expression="1",
        original_json=state.document_json,
    )
    opening = base + "/face/cap.end"

    # The actual add invoke consumes the direct pick's stable handoff.
    class Context:
        window_manager = SimpleNamespace(invoke_props_dialog=lambda *a, **k: {"RUNNING_MODAL"})

        def __getattr__(self, name):
            return getattr(bpy.context, name)

    context = Context()
    chosen = SimpleNamespace(
        kind="shell",
        picked_base=base,
        picked_opening_face=opening,
        picked_document_json=state.document_json,
        properties=SimpleNamespace(is_property_set=lambda key: False),
    )
    assert solid_operators.MCAD_OT_add_solid_feature.invoke(chosen, context, None) == {
        "RUNNING_MODAL"
    }
    assert chosen.shell_mode == "OPEN" and chosen.opening_face == opening and chosen.base == base
    assert workspace_ui._ACTIONS["SHELL"][1] == "mcad.pick_shell_face"
    shell = run(
        bpy.ops.mcad.add_solid_feature,
        kind="shell",
        base=base,
        shell_mode="OPEN",
        opening_face=opening,
        thickness="wall",
        original_json=state.document_json,
    )
    assert abs(state.volume - 894) < 1e-5, state.volume
    before = state.document_json
    try:
        result = bpy.ops.mcad.edit_solid_feature(
            kind="shell",
            feature_id=shell,
            base=base,
            shell_mode="OPEN",
            opening_face=opening,
            thickness="100",
            original_json=before,
        )
    except RuntimeError:
        result = {"CANCELLED"}
    assert result == {"CANCELLED"} and state.document_json == before
    # A valid edit changes this feature expression, not the named project parameter.
    run(
        bpy.ops.mcad.edit_solid_feature,
        kind="shell",
        feature_id=shell,
        base=base,
        shell_mode="OPEN",
        opening_face=opening,
        thickness="wall + 1",
        original_json=state.document_json,
    )
    doc = json.loads(state.document_json)
    assert doc["parameters"]["wall"] == "1"
    assert doc["features"][-1]["params"]["thickness"] == "wall + 1"
    assert abs(state.volume - (3000 - 16 * 11 * 8)) < 1e-5, state.volume
    # Existing closed shells still have no newly serialized opening field.
    run(
        bpy.ops.mcad.add_solid_feature,
        kind="shell",
        base=base,
        shell_mode="CLOSED",
        thickness="1",
        original_json=state.document_json,
    )
    assert "opening_faces" not in json.loads(state.document_json)["features"][-1]
    assert abs(state.volume - (3000 - 18 * 13 * 8)) < 1e-5
    # Return to the valid authored open feature before storing this regression.
    assert document_state._commit_candidate(bpy.context, doc)
    bpy.ops.wm.save_as_mainfile(filepath=path)
    print("MCAD_OPEN_SHELL_CREATE_OK")
unregister()
