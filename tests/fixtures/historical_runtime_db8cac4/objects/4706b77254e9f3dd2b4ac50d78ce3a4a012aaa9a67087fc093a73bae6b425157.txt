"""Intentional relation removal clears its selection in the same accepted draft."""

import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
os.environ["MCAD_ROOT"] = str(ROOT)
os.environ.setdefault("MCAD_PYTHON", str(ROOT / ".venv/bin/python"))
sys.path.insert(0, str(ROOT / "blender_addon"))
from mechanical_cad_blender import (  # noqa: E402
    constraint_ui,
    document_state,
    general_session,
    register,
    unregister,
)
from mechanical_cad_blender.general_sketch_commands import (  # noqa: E402
    AddLine,
    AddRelation,
    DeleteBatch,
    DraftError,
    PointSeed,
)

checks = []


def check(value, message):
    assert value, message
    checks.append(message)


def wait(owner, context):
    deadline = time.monotonic() + 20
    while owner.pending is not None and time.monotonic() < deadline:
        owner.tick(context)
        time.sleep(0.01)
    check(owner.pending is None and not owner.error, "Actual native Check completes")


register()
window = bpy.context.window
area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
region = next(r for r in area.regions if r.type == "WINDOW")
with bpy.context.temp_override(window=window, area=area, region=region):
    context = bpy.context
    document_state._populate_document(
        context.scene,
        {
            "schema_version": 1,
            "id": "release_selection",
            "name": "Release selection",
            "units": "mm",
            "parameters": {},
            "features": [],
            "active_feature": None,
        },
    )
    owner = general_session.GeneralSession(context)
    owner.start()
    p, q, line = owner.execute(context, AddLine(PointSeed(2, 3), PointSeed(12, 3))).entity_ids
    wait(owner, context)
    horizontal = owner.execute(context, AddRelation("horizontal", (line,))).constraint_id
    wait(owner, context)
    distance = owner.execute(context, AddRelation("distance", (p, q), value=10)).constraint_id
    wait(owner, context)
    owner.draft.place_annotation(distance, (12, 34))
    constraint_ui.select_bindings(
        owner, (("constraint", horizontal), ("point", p)), context=context
    )
    owner.checkpoint()
    old = owner.draft
    saved = owner.stored_snapshot
    evidence = owner.evidence_response
    annotations = owner.draft.annotations
    preview = owner.commands.preview_delete((("constraint", horizontal),))
    with patch.object(owner, "checkpoint", side_effect=DraftError("checkpoint refused")):
        try:
            owner.execute(context, DeleteBatch(preview))
        except DraftError:
            pass
        else:
            raise AssertionError("Failed checkpoint unexpectedly accepted")
    check(
        owner.draft is old and owner.evidence_response is evidence,
        "Failed removal restores exact wrapper and solve evidence",
    )
    check(
        owner.stored_snapshot == saved == context.scene.mechanical_cad.sketch_draft_json,
        "Failed removal keeps selection and command checkpoint exact",
    )
    owner.execute(context, DeleteBatch(preview))
    check(
        owner.draft.selection == [{"kind": "point", "id": p}],
        "Accepted removal clears only the intentionally removed relation",
    )
    check(owner.draft.annotations == annotations, "Accepted removal preserves all annotations")
    wait(owner, context)
    owner.local_history(context)
    wait(owner, context)
    check(
        any(item["id"] == horizontal for item in owner.commands.sketch["constraints"]),
        "Undo restores original stable relation identity",
    )
    check(
        owner.draft.selection == [{"kind": "point", "id": p}],
        "Undo does not invent a replacement selection",
    )
    constraint_ui.select_bindings(
        owner, (("constraint", horizontal), ("point", p)), context=context
    )
    owner.local_history(context, redo=True)
    wait(owner, context)
    check(
        owner.draft.selection == [{"kind": "point", "id": p}],
        "Redo removal clears its reselected relation and keeps the point",
    )
    check(owner.draft.annotations == annotations, "History preserves annotation metadata")
    owner.local_history(context)
    wait(owner, context)
    constraint_ui.select_bindings(owner, (("constraint", horizontal),), context=context)
    # Undoing the distance addition leaves H selected; undoing H then clears it.
    owner.local_history(context)
    wait(owner, context)
    check(
        owner.draft.selection == [{"kind": "constraint", "id": horizontal}],
        "Unrelated history removal preserves the still-existing selection",
    )
    owner.local_history(context)
    wait(owner, context)
    check(owner.draft.selection == [], "Undo of a selected relation addition clears that ID")
    owner.cleanup()
unregister()
print("CONSTRAINT_SELECTION_RELEASE_SMOKE_OK", len(checks))
