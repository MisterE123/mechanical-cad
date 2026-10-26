"""Native Blender background check of real Part operators and isolated backend.

MCAD_ROOT and MCAD_PYTHON select source and pinned sidecar. This proves RNA,
canonical publication and geometry, not mouse/keyboard usability.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

import bpy

if not bpy.app.background:
    raise RuntimeError("Run only in isolated native Blender background mode")
root = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(root / "blender_addon"))
import mechanical_cad_blender as addon  # noqa: E402

addon.register()
base = dict(
    schema_version=1,
    id="native",
    name="Native operator check",
    units="mm",
    parameters={},
    active_feature="block",
    features=[
        dict(
            id="profile",
            label="Rectangle",
            kind="sketch_rectangle",
            params=dict(width=10, height=10),
            inputs={},
        ),
        dict(
            id="block",
            label="Block",
            kind="extrude",
            params=dict(length=10),
            inputs=dict(profile="profile"),
        ),
    ],
)
state = bpy.context.scene.mechanical_cad
results = []
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / "base.mcad.json"
    path.write_text(json.dumps(base))
    cases = [
        dict(kind="fillet", base="block", radius="1"),
        dict(kind="chamfer", base="block", distance="1"),
        dict(kind="transform", base="block", x="5", rz="90"),
        dict(kind="linear_pattern", base="block", count="3", dx="5"),
        dict(kind="circular_pattern", base="block", count="4", angle="360", axis_y="0", axis_z="1"),
        dict(kind="shell", base="block", thickness="1"),
        dict(
            kind="fillet",
            base="block",
            radius="1",
            edge_mode="PAIR",
            face_a="block/face/cap.end",
            face_b="block/face/side.x_min",
        ),
    ]
    for case in cases:
        assert bpy.ops.mcad.load_document(filepath=str(path)) == {"FINISHED"}
        assert state.status == "READY", state.error
        assert bpy.ops.mcad.add_solid_feature(**case) == {"FINISHED"}
        assert state.status == "READY", (case, state.error)
        assert state.volume > 0
        results.append(
            dict(kind=case["kind"], volume=state.volume, selected=case.get("edge_mode") == "PAIR")
        )
    current = json.loads(state.document_json)
    feature = current["features"][-1]
    assert bpy.ops.mcad.edit_solid_feature(
        feature_id=feature["id"],
        kind="fillet",
        feature_label="Edited selected edge",
        original_json=state.document_json,
        base="block",
        radius="0.5",
        edge_mode="PAIR",
        face_a="block/face/cap.end",
        face_b="block/face/side.x_min",
    ) == {"FINISHED"}
    assert state.status == "READY", state.error
    changed = json.loads(state.document_json)["features"][-1]
    assert changed["id"] == feature["id"] and changed["edge_faces"] == feature["edge_faces"]
    assert changed["params"]["radius"] == "0.5"
    loft_document = dict(
        schema_version=1,
        id="loft",
        name="Native loft",
        units="mm",
        parameters={},
        active_feature="top",
        features=[
            dict(
                id="bottom", label="Bottom", kind="sketch_circle", params=dict(radius=2), inputs={}
            ),
            dict(
                id="top", label="Top", kind="sketch_circle", params=dict(radius=4, z=10), inputs={}
            ),
        ],
    )
    path.write_text(json.dumps(loft_document))
    assert bpy.ops.mcad.load_document(filepath=str(path)) == {"FINISHED"}
    assert bpy.ops.mcad.add_solid_feature(kind="loft", start="bottom", end="top", ruled="0") == {
        "FINISHED"
    }
    assert state.status == "READY", state.error
    results.append(dict(kind="loft", volume=state.volume))
    sweep_document = dict(
        schema_version=2,
        id="sweep",
        name="Native sweep",
        units="mm",
        parameters={},
        active_feature="path",
        features=[
            dict(
                id="section",
                label="Section",
                kind="sketch_circle",
                params=dict(radius=2),
                inputs={},
            ),
            dict(
                id="path",
                label="Path",
                kind="sketch_constrained",
                params={},
                inputs={},
                sketch=dict(
                    id="path",
                    schema_version=2,
                    units="mm",
                    plane=dict(
                        id="plane", origin=[0, 0, 0], quaternion=[2**-0.5, 0, -(2**-0.5), 0]
                    ),
                    points=[dict(id="a", u=0, v=0), dict(id="b", u=20, v=0)],
                    lines=[dict(id="rail", start="a", end="b")],
                    circles=[],
                    constraints=[
                        dict(id="anchor", kind="fixed", refs=["a"], target=[0, 0]),
                        dict(id="end", kind="fixed", refs=["b"], target=[20, 0]),
                    ],
                ),
            ),
        ],
    )
    path.write_text(json.dumps(sweep_document))
    assert bpy.ops.mcad.load_document(filepath=str(path)) == {"FINISHED"}
    assert state.status == "READY", state.error
    assert bpy.ops.mcad.add_solid_feature(kind="sweep", profile="section", path="path") == {
        "FINISHED"
    }
    assert state.status == "READY", state.error
    results.append(dict(kind="sweep", volume=state.volume))

    path.write_text(json.dumps(base))
    assert bpy.ops.mcad.load_document(filepath=str(path)) == {"FINISHED"}
    assert bpy.ops.mcad.add_solid_feature(
        kind="sketch_face_circle", support="block", support_face="block/face/cap.end", radius="2"
    ) == {"FINISHED"}
    assert state.status == "READY", state.error
    face_id = json.loads(state.document_json)["active_feature"]
    assert bpy.ops.mcad.add_extrude(profile=face_id, length=-3) == {"FINISHED"}
    assert state.status == "READY", state.error
    tool_id = json.loads(state.document_json)["active_feature"]
    assert bpy.ops.mcad.add_solid_feature(kind="cut", base="block", tool=tool_id) == {"FINISHED"}
    assert state.status == "READY", state.error
    assert abs(state.volume - (1000 - 3 * 4 * 3.141592653589793)) < 0.01
    assert bpy.ops.mcad.edit_solid_feature(
        feature_id="block",
        kind="extrude",
        feature_label="Taller block",
        original_json=state.document_json,
        profile="profile",
        length="20",
    ) == {"FINISHED"}
    assert state.status == "READY", state.error
    assert abs(state.volume - (2000 - 3 * 4 * 3.141592653589793)) < 0.01
    results.append(dict(kind="associative_face_hole_after_upstream_edit", volume=state.volume))

assert not any(name == "OCP" or name.startswith("OCP.") for name in sys.modules)
print(
    "MCAD_CONNECTED_PARTS_RESULT="
    + json.dumps(dict(ok=True, blender=bpy.app.version_string, cases=results))
)
addon.unregister()
