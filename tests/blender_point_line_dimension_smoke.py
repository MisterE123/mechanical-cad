"""Native owner gesture seams: mocked hit coordinates, real drafts/solver/Undo."""

import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    document_state,
    general_session,
    general_viewport,
    register,
    unregister,
)
from mechanical_cad_blender.general_sketch_commands import (  # noqa: E402
    AddCircle,
    AddProjectionGeometry,
    PointSeed,
)


def wait(owner):
    end = time.monotonic() + 40
    while owner.pending is not None and time.monotonic() < end:
        owner.tick(bpy.context)
        time.sleep(0.01)
    assert owner.pending is None and not owner.error, owner.error


def click(owner, hit=None):
    event = SimpleNamespace(mouse_x=100, mouse_y=100)

    def pick(_owner, _event, kinds):
        return SimpleNamespace(kind=hit[0], identifier=hit[1]) if hit and hit[0] in kinds else None

    with (
        patch.object(general_viewport, "_pick", side_effect=pick),
        patch.object(general_viewport, "_pointer", return_value=(12, 12)),
    ):
        general_viewport._dimension(owner, bpy.context, event)


register()
window = bpy.context.window
area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
region = next(r for r in area.regions if r.type == "WINDOW")
with bpy.context.temp_override(window=window, area=area, region=region):
    document_state._populate_document(
        bpy.context.scene,
        {
            "schema_version": 1,
            "id": "offset",
            "name": "Offset",
            "units": "mm",
            "parameters": {},
            "features": [],
            "active_feature": None,
        },
    )
    owner = general_session.GeneralSession(bpy.context)
    owner.start()
    lines = []
    for a, b in [((0, 0), (20, 0)), ((0, -10), (0, 20))]:
        result = owner.execute(
            bpy.context, AddProjectionGeometry("line", (PointSeed(*a), PointSeed(*b)))
        )
        lines.append(result.entity_ids[-1])
        wait(owner)
    result = owner.execute(bpy.context, AddCircle(PointSeed(7, 5), 2))
    center, circle = result.entity_ids
    wait(owner)
    base = owner.commands.sketch
    assert bpy.ops.mcad.general_tool(tool="Dimension") == {"FINISHED"}
    click(owner, ("point", center))
    assert owner.draft.selection == [{"kind": "point", "id": center}]
    click(owner, ("line", lines[0]))
    preview = general_viewport._dimension_proposal(owner)
    assert preview["endpoint"] == (7, 0)
    assert owner.commands.sketch == base  # Preview has no accepted geometry.
    click(owner)
    relation = owner.commands.pending_edit.constraint_id
    assert owner.input_controller is not None
    assert relation in owner.draft.annotations
    assert len(owner.commands.sketch["points"]) == len(base["points"]) + 1
    annotation = owner.draft.annotations[relation]
    owner.cancel_dimension()
    owner.local_history(bpy.context)
    wait(owner)
    assert owner.commands.sketch == base
    assert relation not in owner.draft.annotations
    assert not owner.draft.status.conflicts
    owner.local_history(bpy.context, redo=True)
    wait(owner)
    assert owner.draft.annotations[relation] == annotation
    assert not owner.draft.status.conflicts
    # Repeated gesture still reuses its relation and opens the field.
    click(owner, ("point", center))
    click(owner, ("line", lines[0]))
    click(owner)
    assert owner.commands.pending_edit.constraint_id == relation
    owner.update_raw("8")
    owner.request_driver_accept(bpy.context)
    wait(owner)
    assert abs(owner.geometry().points[center][1] - 8) < 1e-6
    # Direct point-point distance is the same ordinary three-click gesture.
    endpoint = owner.geometry().lines[lines[0]].start_id
    click(owner, ("point", center))
    click(owner, ("point", endpoint))
    assert general_viewport._point_dimension(owner)[3] == "Point distance"
    click(owner)
    owner.update_raw("10")
    owner.request_driver_accept(bpy.context)
    wait(owner)
    assert abs(owner.geometry().points[center][0] - 6) < 1e-6
    owner.local_history(bpy.context)  # Numeric edit.
    wait(owner)
    owner.local_history(bpy.context)  # Point-point relation.
    wait(owner)
    click(owner, ("point", center))
    click(owner, ("line", lines[1]))
    click(owner)
    owner.update_raw("6")
    owner.request_driver_accept(bpy.context)
    wait(owner)
    assert abs(owner.geometry().points[center][0] - 6) < 1e-6
    assert abs(owner.geometry().points[center][1] - 8) < 1e-6
    assert owner.can_finish
    # Undo the last numeric edit and dimension, then author a divergent branch.
    last_relation = next(reversed(owner.draft.annotations))
    owner.local_history(bpy.context)
    wait(owner)
    owner.local_history(bpy.context)
    wait(owner)
    assert last_relation not in owner.draft.annotations
    assert owner._history_annotations
    from mechanical_cad_blender.general_sketch_commands import AddRelation

    owner.execute(bpy.context, AddRelation("radius", (circle,), value=2))
    wait(owner)
    assert not owner.commands.can_redo
    assert not owner._history_annotations  # Abandoned label cannot revive later.
    owner.local_history(bpy.context)
    wait(owner)
    owner.local_history(bpy.context, redo=True)
    wait(owner)
    assert last_relation not in owner.draft.annotations
    assert not owner.draft.status.conflicts
    owner.request_finish(bpy.context)
    wait(owner)
    assert owner.finished
# Existing missing imported bindings are not swept away by cleanup.
missing = {"kind": "distance", "refs": ["old_a", "old_b"], "offset": [1, 2]}
removed = {"kind": "distance", "refs": ["a", "b"], "offset": [1, 2]}
candidate = SimpleNamespace(
    command_draft=SimpleNamespace(sketch={"constraints": []}),
    annotations={"imported_missing": missing, "removed": removed},
    selection=[],
)
candidate.remove_annotation = lambda key: candidate.annotations.pop(key)
candidate.discard_selection = lambda targets: None
old_owner = SimpleNamespace(commands=SimpleNamespace(sketch={"constraints": [{"id": "removed"}]}))
general_session.GeneralSession._clear_removed_relation_selection(old_owner, candidate)
assert candidate.annotations == {"imported_missing": missing}
unregister()
print("POINT_LINE_DIMENSION_SMOKE_OK")
