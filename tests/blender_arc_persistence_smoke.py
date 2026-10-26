"""Two actual Blender lifetimes retain arc intent, raw text and layout without authority.

The committed sector is an explicitly declared fixture. Manual drawing is a
separate installed-GUI gate; the editor smoke builds from blank through adapters.
"""

import copy
import json
import math
import os
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import bpy

ROOT = Path(os.environ.get("MCAD_ROOT", Path(__file__).resolve().parents[1])).resolve()
os.environ["MCAD_ROOT"] = str(ROOT)
sys.path.insert(0, str(ROOT / "blender_addon"))
import mechanical_cad_blender as addon  # noqa: E402
from mechanical_cad_blender import (  # noqa: E402
    document_state as doc,
)
from mechanical_cad_blender import (  # noqa: E402
    draft_dispatch,
    execution_lease,
    general_session,
    guarded_transport,
    sketch_session,
    workspace,
)
from mechanical_cad_blender.general_sketch_commands import PointSeed  # noqa: E402

checks = []
PHASE = os.environ.get("MCAD_ARC_PERSISTENCE_PHASE", "save")


def check(value, label):
    assert value, label
    checks.append(label)
    print("ARC_PERSISTENCE_CHECK", PHASE, len(checks), label, flush=True)


def current_volume(context):
    result = doc.current_part_result(context)
    assert result is not None, "Volume requires current guarded native evidence"
    volume = result["features"][1]["stats"]["volume"]
    display_volume = context.scene.mechanical_cad.volume
    print(
        "ARC_PERSISTENCE_VOLUME", json.dumps({"native": volume, "rna": display_volume}), flush=True
    )
    check(
        display_volume == struct.unpack("f", struct.pack("f", volume))[0],
        "RNA volume is the exact float32 presentation of current native volume",
    )
    return volume


def wait(owner, context):
    deadline = time.monotonic() + 60
    while owner.pending is not None and time.monotonic() < deadline:
        owner.tick(context)
        time.sleep(0.01)
    check(
        owner.pending is None and not execution_lease.is_busy(), "All native owner work collected"
    )
    check(not owner.error, "Real owner operation succeeds: " + owner.error)


def enter(context, role, on_ready=None):
    check(role == "SKETCH", "Resume uses existing Sketch workspace routing")
    if on_ready:
        on_ready(context)
    return True


def resume(context):
    with patch.object(workspace, "request_workspace", side_effect=enter):
        check(bpy.ops.mcad.resume_sketch() == {"FINISHED"}, "Registered Resume accepts envelope3")
    owner = sketch_session.active_session(context)
    check(type(owner) is general_session.GeneralSession, "Resume selects the shared General owner")
    check(
        owner.pending is None and not owner.proposal_capture,
        "Resume restores neither jobs nor capture",
    )
    check(
        owner.current_solution_response() is None and not owner.can_finish,
        "Resume grants no solve or Finish authority",
    )
    return owner


def shape(document):
    source = document["features"][0]["sketch"]
    return copy.deepcopy({key: source[key] for key in ("points", "lines", "circles", "arcs")})


def context_parts():
    window = bpy.context.window
    area = next(item for item in window.screen.areas if item.type == "VIEW_3D")
    region = next(item for item in area.regions if item.type == "WINDOW")
    window.workspace[workspace.OWNER_KEY] = workspace.OWNER
    window.workspace[workspace.ROLE_KEY] = "SKETCH"
    return window, area, region


addon.register()
if PHASE == "reopen":
    directory = Path(os.environ["MCAD_ARC_PERSISTENCE_DIRECTORY"])
    bpy.ops.wm.open_mainfile(filepath=str(directory / "arc-intent.blend"))
    expected = json.loads((directory / "expected.json").read_text())
    window, area, region = context_parts()
    for name, saved in expected.items():
        window.scene = bpy.data.scenes[name]
        with bpy.context.temp_override(window=window, area=area, region=region):
            context = bpy.context
            state = context.scene.mechanical_cad
            check(state.document_json == saved["document"], name + " canonical JSON is byte-exact")
            check(state.sketch_draft_json == saved["draft"], name + " envelope3 is byte-exact")
            check(state.sketch_annotation_json == saved["layout"], name + " layout1 is byte-exact")
            check(
                doc.current_part_result(context) is None,
                name + " saved Part flags grant no authority",
            )
            info = sketch_session.suspended_draft(context)
            check(
                info["compatible"] and info["editor_available"] and info["schema_version"] == 3,
                name + " exact saved intent has its supported editor",
            )
            with patch.object(
                guarded_transport,
                "GuardedJob",
                side_effect=AssertionError("Resume started native work"),
            ):
                owner = resume(context)
            if name == "Arc unfinished proposal":
                check(
                    owner.draft.proposal == saved["proposal"],
                    "Unfinished center/start/raw end observation survives exact",
                )
                check(owner.commands.sketch["points"] == [], "Unaccepted gesture still owns no IDs")
                check(owner.draft.point_input_phase == ("arc", "end"), "Exact input phase survives")
                owner.suspend("Persistence probe retains unfinished intent")
                check(
                    state.sketch_draft_json == saved["draft"],
                    "Resume/Suspend preserves exact pure proposal bytes",
                )
            else:
                before = shape(owner.commands.candidate())
                check(
                    owner.commands.pending_edit.raw_text == " 7 + 0 ",
                    "Pending radius keeps exact whitespace and formula",
                )
                check(
                    owner.draft.annotations == saved["annotations"],
                    "Radius label offset survives in UI intent",
                )
                retained = (state.sketch_draft_json, owner.commands.pending_edit.raw_text)
                try:
                    owner.request_driver_accept(context)
                except ValueError as error:
                    check("Reopen" in str(error), "Retained input cannot be accepted before Reopen")
                else:
                    raise AssertionError("Retained input bypassed explicit Reopen")
                check(
                    (state.sketch_draft_json, owner.commands.pending_edit.raw_text) == retained
                    and owner.pending is None
                    and not owner.input_token
                    and owner.current_solution_response() is None
                    and not owner.can_finish,
                    "Rejected retained acceptance preserves slot/raw text and grants no authority",
                )
                check(
                    owner.begin_dimension(owner.commands.pending_edit.constraint_id) == " 7 + 0 ",
                    "Explicit Reopen preserves exact retained raw text",
                )
                owner.request_driver_accept(context)
                wait(owner, context)
                check(
                    owner.commands.pending_edit is None and owner.can_finish,
                    "Explicit acceptance obtains fresh complete solve/replay chain",
                )
                check(
                    shape(owner.commands.candidate()) == before,
                    "Fresh radius edit preserves all authored geometry IDs and seeds",
                )
                owner.local_history(context)
                wait(owner, context)
                check(
                    next(
                        row
                        for row in owner.commands.sketch["constraints"]
                        if row["id"] == "sector_radius"
                    )
                    == next(
                        row
                        for row in json.loads(saved["document"])["features"][0]["sketch"][
                            "constraints"
                        ]
                        if row["id"] == "sector_radius"
                    ),
                    "Local Undo restores the exact pre-edit radius formula record",
                )
                owner.local_history(context, redo=True)
                wait(owner, context)
                owner.request_finish(context)
                wait(owner, context)
                check(
                    math.isclose(current_volume(context), 384.84510006474966, abs_tol=1e-10),
                    "Fresh-process same-feature radius7 rebuild succeeds",
                )
                check(
                    shape(doc._read_document(state)) == before,
                    "Committed reopened sector preserves identities",
                )
                check(
                    doc.part_is_current(context) and not doc.geometry_report_is_current(context),
                    "Fresh Part replay is current without a manufactured Geometry Check",
                )
                check(
                    not state.sketch_draft_json,
                    "Successful Finish clears only the accepted saved draft",
                )
else:
    source = json.loads(
        (
            ROOT / "tests/fixtures/arc_authoring_evidence/radius_edit_5_0_replay.operation.json"
        ).read_text()
    )["document"]
    window, area, region = context_parts()
    expected = {}
    radius_scene = window.scene
    radius_scene.name = "Arc pending radius"
    with bpy.context.temp_override(window=window, area=area, region=region):
        context = bpy.context
        check(doc._commit_candidate(context, source), "Declared sector fixture freshly publishes")
        owner = general_session.GeneralSession(context, "profile")
        owner.start()
        owner.check(context)
        wait(owner, context)
        owner.draft.place_annotation("sector_radius", (9, 11))
        owner.checkpoint()
        owner.request_finish(context)
        wait(owner, context)
        owner = general_session.GeneralSession(context, "profile")
        owner.start()
        owner.check(context)
        wait(owner, context)
        owner.begin_dimension("sector_radius")
        owner.update_raw(" 7 + 0 ")
        annotations = copy.deepcopy(owner.draft.annotations)
        owner.suspend("Save exact pending arc radius")
        state = context.scene.mechanical_cad
        check(
            draft_dispatch.inspect(state.sketch_draft_json).schema_version == 3,
            "Pending arc uses explicit envelope3",
        )
        expected[radius_scene.name] = {
            "document": state.document_json,
            "draft": state.sketch_draft_json,
            "layout": state.sketch_annotation_json,
            "annotations": annotations,
        }
    proposal_scene = bpy.data.scenes.new("Arc unfinished proposal")
    window.scene = proposal_scene
    with bpy.context.temp_override(window=window, area=area, region=region):
        context = bpy.context
        doc._populate_document(
            proposal_scene,
            {
                "schema_version": 1,
                "id": "saved_arc_proposal",
                "name": "Saved arc proposal",
                "units": "mm",
                "parameters": {},
                "features": [],
                "active_feature": None,
            },
        )
        owner = general_session.GeneralSession(context)
        owner.start()
        owner.enable_arc(owner.prepare_gesture("arc"))
        owner.accept_point_input(context, PointSeed(0, 0), expected_phase=("arc", "center"))
        owner.accept_point_input(context, PointSeed(5, 0), expected_phase=("arc", "start"))
        owner.draft.observe_arc(PointSeed(0, 6))
        proposal = copy.deepcopy(owner.draft.proposal)
        owner.suspend("Save raw unfinished arc proposal")
        state = context.scene.mechanical_cad
        expected[proposal_scene.name] = {
            "document": state.document_json,
            "draft": state.sketch_draft_json,
            "layout": state.sketch_annotation_json,
            "proposal": proposal,
        }
    window.scene = radius_scene
    check(
        not execution_lease.is_busy() and sketch_session.active_session() is None,
        "All work and owners are closed before saving",
    )
    temporary = None
    if os.environ.get("MCAD_ARC_PERSISTENCE_DIRECTORY"):
        directory = Path(os.environ["MCAD_ARC_PERSISTENCE_DIRECTORY"])
        directory.mkdir(parents=True, exist_ok=False)
    else:
        temporary = tempfile.TemporaryDirectory(prefix="mcad-arc-persistence-")
        directory = Path(temporary.name)
    (directory / "expected.json").write_text(json.dumps(expected, indent=2) + "\n")
    check(
        bpy.ops.wm.save_as_mainfile(filepath=str(directory / "arc-intent.blend")) == {"FINISHED"},
        "Actual .blend saves both arc scenes",
    )
    environment = dict(
        os.environ,
        MCAD_ARC_PERSISTENCE_PHASE="reopen",
        MCAD_ARC_PERSISTENCE_DIRECTORY=str(directory),
    )
    command = [
        bpy.app.binary_path,
        "--background",
        "--factory-startup",
        "--python-exit-code",
        "1",
        "--python-expr",
        "import sys; sys.dont_write_bytecode = True",
        "--python",
        str(Path(__file__).resolve()),
    ]
    child = subprocess.run(command, env=environment, text=True, capture_output=True, timeout=240)
    (directory / "reopen.stdout.log").write_text(child.stdout)
    (directory / "reopen.stderr.log").write_text(child.stderr)
    (directory / "reopen.process.json").write_text(
        json.dumps(
            {"command": command, "returncode": child.returncode, "phase": "reopen"}, indent=2
        )
        + "\n"
    )
    check(child.returncode == 0, "Fresh Blender process passed: " + child.stdout + child.stderr)
    check(
        '"phase": "reopen"' in child.stdout and "ARC_PERSISTENCE_RESULT=" in child.stdout,
        "Child emitted its actual reopen terminal receipt",
    )
    print(child.stdout)
    if temporary is not None:
        temporary.cleanup()
check(not execution_lease.is_busy(), "No native work remains at process completion")
check(
    not any(name == "OCP" or name.startswith("OCP.") or name == "slvs" for name in sys.modules),
    "Native CAD stays outside Blender",
)
addon.unregister()
print("ARC_PERSISTENCE_RESULT=" + json.dumps({"ok": True, "phase": PHASE, "checks": len(checks)}))
