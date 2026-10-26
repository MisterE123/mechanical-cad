"""Pure Gate-C owner and viewport ports; no Blender or native process is run."""

import copy
import gc
import importlib
import json
import sys
import types
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "mcad_arc_gesture_owner_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[PACKAGE] = package
BASE = json.dumps(
    dict(
        schema_version=1,
        id="Part",
        name="Part",
        units="mm",
        parameters={},
        features=[],
        active_feature=None,
    )
)


def load(name):
    return importlib.import_module(PACKAGE + "." + name)


d = load("general_sketch_draft")
a = load("general_authoring")
dispatch = load("draft_dispatch")
selections = load("backend_selection")


class Host(types.SimpleNamespace):
    def as_pointer(self):
        return id(self)

    def __eq__(self, other):
        return self is other

    def __ne__(self, other):
        return self is not other


def inert(*args, **kwargs):
    return None


@pytest.fixture
def host(monkeypatch):
    selected = selections.BackendSelection.capture(
        str(ROOT), sys.executable, generation=1, lifetime_id="pure-gesture-port", environment={}
    )
    current = [selected]
    stubs = {
        "assembly_job_ui": {"ensure_supervisor": inert},
        "backend_runtime": {"capture": lambda context: current[0]},
        "document_state": {"_REPLAY_RUNNING": False},
        "part_publication": {},
        "sketch_view_presentation": {},
        "workspace": {},
        "common": {"_state": lambda context: context.scene.mechanical_cad, "MM_TO_METERS": 0.001},
        "display": {"_focus_display": inert},
        "workspace_ui": {},
        "sketch_overlay": {},
        "general_sketch_overlay": {},
        "help_ui": {
            "_draw_feature_help": inert,
            "_feature_help_next": inert,
            "_feature_help_previous": inert,
        },
    }
    for name, fields in stubs.items():
        stub = types.ModuleType(PACKAGE + "." + name)
        stub.__dict__.update(fields)
        monkeypatch.setitem(sys.modules, stub.__name__, stub)
        monkeypatch.setattr(package, name, stub, raising=False)
    bpy = types.ModuleType("bpy")
    bpy.data = Host(scenes=[])
    props = types.ModuleType("bpy.props")
    for key in ("BoolProperty", "FloatProperty", "IntProperty", "StringProperty", "EnumProperty"):
        setattr(props, key, lambda **kwargs: kwargs)
    operators = types.ModuleType("bpy.types")
    operators.Operator = type("Operator", (), {"report": inert})
    for name, stub in {
        "bpy": bpy,
        "bpy.props": props,
        "bpy.types": operators,
        "blf": types.ModuleType("blf"),
        "bpy_extras": Host(view3d_utils=Host()),
        "mathutils": Host(Vector=tuple, Quaternion=tuple),
    }.items():
        monkeypatch.setitem(sys.modules, name, stub)
    for name in ("sketch_session", "general_session", "viewport_sketch", "general_viewport"):
        sys.modules.pop(PACKAGE + "." + name, None)
    session = load("general_session")
    lifecycle = load("sketch_session")
    viewport = load("general_viewport")
    state = Host(
        document_json=BASE,
        sketch_draft_json="",
        sketch_draft_scene_id="scene-id",
        sketch_annotation_json="",
    )
    scene = Host(
        session_uid=1, name="Test", mechanical_cad=state, unit_settings=Host(scale_length=1)
    )
    region = Host(type="WINDOW", x=0, y=0)
    area = Host(
        type="VIEW_3D",
        regions=[region],
        spaces=Host(active=Host(region_3d=Host())),
        tag_redraw=inert,
    )
    workspace = Host()
    window = Host(
        scene=scene,
        workspace=workspace,
        screen=Host(areas=[area]),
        view_layer=Host(objects=Host(active=None)),
    )
    context = Host(
        scene=scene,
        area=area,
        window=window,
        workspace=workspace,
        view_layer=window.view_layer,
        window_manager=Host(),
    )
    owner = session.GeneralSession(context)
    checks = []
    owner.check = lambda context: checks.append(owner.commands.revision)
    lifecycle._ACTIVE = owner
    yield Host(
        owner=owner,
        context=context,
        session=session,
        lifecycle=lifecycle,
        viewport=viewport,
        current=current,
        checks=checks,
        state=state,
    )
    lifecycle._ACTIVE = None
    lifecycle._RECOVERY_RESERVATIONS.clear()


def promote(host):
    binding = host.owner.prepare_gesture("arc")
    host.owner.enable_arc(binding)


def store(host):
    host.owner.checkpoint()
    return host.state.sketch_draft_json


def add_points(host):
    ids = [
        host.owner.commands.execute(d.AddPoint(d.PointSeed(*xy))).entity_ids[0]
        for xy in ((0, 0), (5, 0), (0, 7), (0, 0))
    ]
    store(host)
    return ids


def picker(host, point, **kwargs):
    binding = host.owner.prepare_gesture("point")
    return host.owner.accept_point_input(
        host.context, d.PointRef(point), expected_phase=binding.phase, picker=binding, **kwargs
    )


def pointer(host, xy):
    return host.owner.accept_point_input(
        host.context, d.PointSeed(*xy), expected_phase=host.owner.draft.point_input_phase
    )


def test_promotion_cancel_is_exact_and_confirm_is_one_atomic_checkpoint(host):
    before = store(host)
    original = host.owner.commands.checkpoint_payload()
    binding = host.owner.prepare_gesture("arc")
    host.owner.cancel_gesture(binding)
    assert host.state.sketch_draft_json == before
    assert host.owner.commands.journal_version == 2 and host.owner.draft.ui_version == 1
    with pytest.raises(d.DraftError, match="no longer active"):
        host.owner.enable_arc(binding)
    promote(host)
    assert host.owner.commands.journal_version == 3 and host.owner.draft.ui_version == 2
    assert dispatch.inspect(host.state.sketch_draft_json).schema_version == 3
    assert host.owner.commands.sketch == original["accepted_sketch"]
    assert host.owner.commands.revision == original["revision"]
    assert host.owner.draft.tool == "Arc" and host.checks == []


@pytest.mark.parametrize("mode", ["failure", "external", "backend"])
def test_promotion_checkpoint_failure_rolls_back_only_owned_slot(host, monkeypatch, mode):
    before = store(host)
    original = host.owner.draft
    checkpoint = host.owner.checkpoint

    def fail():
        checkpoint()
        if mode == "external":
            host.state.sketch_draft_json = "external recovery slot"
        if mode == "backend":
            host.current[0] = replace(host.current[0], generation=2)
        else:
            raise RuntimeError("injected checkpoint")

    binding = host.owner.prepare_gesture("arc")
    monkeypatch.setattr(host.owner, "checkpoint", fail)
    with pytest.raises((RuntimeError, d.DraftError)):
        host.owner.enable_arc(binding)
    assert host.owner.draft is original
    assert host.state.sketch_draft_json == (
        "external recovery slot" if mode == "external" else before
    )
    assert host.owner.stored_snapshot == before


def test_all_five_exact_id_phases_preserve_coincident_distinct_identity(host):
    promote(host)
    center, start, end, coincident = add_points(host)
    original = host.owner.commands.checkpoint_payload()
    assert picker(host, coincident) == ()
    assert host.owner.draft.proposal["center"]["point_id"] == coincident
    assert not host.owner.proposal_capture
    assert picker(host, start) == ()
    assert host.owner.commands.checkpoint_payload() == original
    arc_id = picker(host, end)[0]
    arc = host.owner.commands.sketch["arcs"][0]
    assert arc == dict(id=arc_id, center=coincident, start=start, end=end, direction="ccw")
    assert host.checks == [original["revision"] + 1]
    host.owner.draft.select_tool("Line")
    before = host.owner.commands.checkpoint_payload()
    assert picker(host, coincident, source_kind="arc", source_id=arc_id, role="center") == ()
    assert host.owner.commands.checkpoint_payload() == before
    picker(host, start, source_kind="arc", source_id=arc_id, role="start")
    line = host.owner.commands.sketch["lines"][0]
    assert (line["start"], line["end"]) == (coincident, start)
    assert center != coincident and len(host.checks) == 2


@pytest.mark.parametrize(
    "change",
    [
        "slot",
        "ui",
        "revision",
        "commands",
        "phase",
        "units",
        "window",
        "workspace",
        "owner",
        "session",
        "backend",
        "capture",
    ],
)
def test_exact_picker_stale_bindings_reject_once_without_repick(host, change):
    promote(host)
    ids = add_points(host)
    binding = host.owner.prepare_gesture("point")
    before = host.owner.commands.sketch
    if change == "slot":
        host.state.sketch_draft_json += " "
    elif change == "ui":
        host.owner.draft.select((("point", ids[0]),))
    elif change == "revision":
        host.owner.commands.execute(d.AddPoint(d.PointSeed(9, 9)))
    elif change == "commands":
        host.owner.draft = dispatch.clone(host.owner.draft)
    elif change == "phase":
        host.owner.draft.begin_arc(d.PointRef(ids[0]))
    elif change == "units":
        host.owner.scene.unit_settings.scale_length = 2
    elif change == "window":
        host.owner.window.view_layer = Host(objects=Host(active=None))
    elif change == "workspace":
        host.owner.window.workspace = Host()
    elif change == "owner":
        host.owner.owner_token = object()
    elif change == "session":
        host.owner.session_id = "new-session"
    elif change == "backend":
        host.current[0] = replace(host.current[0], generation=2)
    elif change == "capture":
        host.owner.proposal_capture = True
    with pytest.raises(d.DraftError):
        host.owner.accept_point_input(
            host.context, d.PointRef(ids[0]), expected_phase=binding.phase, picker=binding
        )
    assert host.owner.commands.sketch.get("arcs") == before.get("arcs")
    assert not host.checks
    assert host.owner.gesture_intent is None
    assert host.owner.proposal_capture is False
    with pytest.raises(d.DraftError):
        host.owner.accept_point_input(
            host.context, d.PointRef(ids[0]), expected_phase=binding.phase, picker=binding
        )


@pytest.mark.parametrize("observed", ["slot", "document", "context"])
def test_observed_owner_aba_retires_picker(host, observed):
    promote(host)
    ids = add_points(host)
    binding = host.owner.prepare_gesture("point")
    if observed == "slot":
        old = host.state.sketch_draft_json
        host.state.sketch_draft_json = "external"
        with pytest.raises(d.DraftError):
            host.owner._require_current()
        host.state.sketch_draft_json = old
    elif observed == "document":
        old = host.state.document_json
        host.state.document_json += " "
        assert not host.owner.valid_context()
        host.state.document_json = old
    else:
        old = host.owner.window.workspace
        host.owner.window.workspace = Host()
        assert not host.owner.valid_context()
        host.owner.window.workspace = old
    with pytest.raises(d.DraftError, match="no longer active"):
        host.owner.accept_point_input(
            host.context, d.PointRef(ids[0]), expected_phase=binding.phase, picker=binding
        )


def test_picker_wrong_role_repeated_role_and_double_confirmation(host):
    promote(host)
    ids = add_points(host)
    line = host.owner.commands.execute(
        d.AddLine(d.PointRef(ids[0]), d.PointRef(ids[1]))
    ).entity_ids[0]
    store(host)
    before = dispatch.dumps(host.owner.draft)
    with pytest.raises(d.DraftError, match="wrong source role"):
        picker(host, ids[0], source_kind="line", source_id=line, role="end")
    assert dispatch.dumps(host.owner.draft) == before
    picker(host, ids[0])
    before = dispatch.dumps(host.owner.draft)
    with pytest.raises(d.DraftError, match="distinct"):
        picker(host, ids[0])
    assert dispatch.dumps(host.owner.draft) == before
    binding = host.owner.prepare_gesture("point")
    host.owner.accept_point_input(
        host.context, d.PointRef(ids[1]), expected_phase=binding.phase, picker=binding
    )
    with pytest.raises(d.DraftError, match="no longer active"):
        host.owner.accept_point_input(
            host.context, d.PointRef(ids[1]), expected_phase=binding.phase, picker=binding
        )


def test_raw_pointer_arc_third_click_keeps_unequal_radius_and_one_command(host):
    promote(host)
    revision = host.owner.commands.revision
    assert pointer(host, (-0.0, 0)) == ()
    assert pointer(host, (5, 0)) == ()
    assert host.owner.commands.revision == revision and not host.owner.commands.sketch["points"]
    pointer(host, (0, 7.125))
    sketch = host.owner.commands.sketch
    arc = sketch["arcs"][0]
    points = {point["id"]: point for point in sketch["points"]}
    assert points[arc["end"]]["v"] == 7.125
    assert sketch["constraints"] == [] and host.checks == [revision + 1]
    assert not host.owner.proposal_capture


def test_suspend_resume_picker_cancel_never_revives_capture(host):
    promote(host)
    ids = add_points(host)
    pointer(host, (1, 1))
    raw = store(host)
    resumed = dispatch.restore(raw, BASE)
    host.lifecycle._ACTIVE = None
    host.owner = host.session.GeneralSession(host.context, restored=resumed)
    assert host.owner.proposal_capture is False
    before = host.state.sketch_draft_json
    binding = host.owner.prepare_gesture("point")
    host.owner.cancel_gesture(binding)
    assert host.state.sketch_draft_json == before and not host.owner.proposal_capture
    with pytest.raises(d.DraftError, match="not capturing"):
        pointer(host, (5, 0))
    assert picker(host, ids[1]) == () and not host.owner.proposal_capture


def test_reverse_proposal_and_command_are_distinct_and_preserve_ids(host):
    promote(host)
    pointer(host, (0, 0))
    before = host.owner.commands.checkpoint_payload()
    host.owner.reverse_arc(host.context, host.owner.prepare_gesture("reverse"))
    assert host.owner.draft.proposal["direction"] == "cw"
    assert host.owner.commands.checkpoint_payload() == before and host.checks == []
    host.owner.proposal_capture = True
    pointer(host, (5, 0))
    pointer(host, (0, 5))
    sketch = host.owner.commands.sketch
    identifier = sketch["arcs"][0]["id"]
    host.owner.draft.select((("arc", identifier),))
    host.owner.reverse_arc(host.context, host.owner.prepare_gesture("reverse"))
    expected = copy.deepcopy(sketch)
    expected["arcs"][0]["direction"] = "ccw"
    assert host.owner.commands.sketch == expected and len(host.checks) == 2
    host.owner.commands.undo()
    assert host.owner.commands.sketch == sketch


def test_general_profile_tools_remain_available_after_arc_and_line_creation(host):
    assert host.owner.can_use_tool("Circle") and host.owner.can_use_tool("Arc")
    promote(host)
    pointer(host, (0, 0))
    pointer(host, (5, 0))
    pointer(host, (0, 5))
    assert host.owner.can_use_tool("Arc") and host.owner.can_use_tool("Circle")
    assert host.owner.can_use_tool("Line")
    arc = host.owner.commands.sketch["arcs"][0]
    host.owner.commands.execute(d.AddLine(d.PointRef(arc["center"]), d.PointRef(arc["start"])))
    host.owner.commands.execute(d.AddLine(d.PointRef(arc["end"]), d.PointRef(arc["center"])))
    assert host.owner.can_use_tool("Line")
    host.owner.commands.undo()
    host.owner.commands.undo()
    host.owner.commands.undo()
    assert host.owner.can_use_tool("Circle") and host.owner.can_use_tool("Arc")


def test_picker_operator_uses_exact_declared_source_no_pointer_lookup(host, monkeypatch):
    promote(host)
    ids = add_points(host)
    line = host.owner.commands.execute(
        d.AddLine(d.PointRef(ids[0]), d.PointRef(ids[1]))
    ).entity_ids[0]
    store(host)
    host.context.window_manager.invoke_props_dialog = lambda *args, **kwargs: {"RUNNING_MODAL"}
    op = host.viewport.MCAD_OT_use_existing_point()
    assert op.invoke(host.context, None) == {"RUNNING_MODAL"}
    op.point_id = ids[1]
    op.source = "line:" + line + ":end"
    monkeypatch.setattr(host.viewport, "_anchor", lambda *args: pytest.fail("must not repick"))
    monkeypatch.setattr(host.viewport, "_pointer", lambda *args: pytest.fail("must not project"))
    assert op.execute(host.context) == {"FINISHED"}
    assert host.owner.draft.proposal["center"]["point_id"] == ids[1]
    assert op.execute(host.context) == {"CANCELLED"}


def test_schema3_edit_routes_general_before_rectangle_even_arc_empty(host):
    route = load("viewport_sketch")._selected_editor
    doc = json.loads((ROOT / "examples/viewport_rectangle.mcad.json").read_text())
    feature = next(item for item in doc["features"] if item["kind"] == "sketch_constrained")
    state = Host(
        document_json=json.dumps(doc),
        feature_index=0,
        features=[Host(kind="sketch_constrained", feature_id=feature["id"])],
    )
    assert route(state) == "mcad.rectangle_sketch"
    feature["sketch"]["schema_version"] = 3
    feature["sketch"]["arcs"] = []
    feature["sketch"].setdefault("circles", [])
    state.document_json = json.dumps(doc)
    assert route(state) == "mcad.general_sketch"


@pytest.mark.parametrize(
    "kind,version",
    [(dispatch.GENERAL, 1), (dispatch.GENERAL, 2), (dispatch.GENERAL, 3), (dispatch.RECTANGLE, 1)],
)
def test_resume_route_exact_supported_kind_versions(host, kind, version):
    assert host.lifecycle.editor_operator(kind, version) == (
        "mcad.rectangle_sketch" if kind == dispatch.RECTANGLE else "mcad.general_sketch"
    )


@pytest.mark.parametrize(
    "kind,version",
    [
        (dispatch.GENERAL, True),
        (dispatch.GENERAL, 3.0),
        (dispatch.GENERAL, "3"),
        (dispatch.GENERAL, 0),
        (dispatch.GENERAL, 4),
        (dispatch.RECTANGLE, 2),
        (dispatch.RECTANGLE, 3),
        ("unknown", 3),
        (None, 3),
    ],
)
def test_resume_route_rejects_malformed_unknown_and_cross_kind_versions(host, kind, version):
    assert host.lifecycle.editor_operator(kind, version) is None


def test_picker_requires_explicit_choice_and_cancel_keeps_exact_slot(host):
    promote(host)
    add_points(host)
    before = store(host)
    host.context.window_manager.invoke_props_dialog = lambda *args, **kwargs: {"RUNNING_MODAL"}
    op = host.viewport.MCAD_OT_use_existing_point()
    assert op.invoke(host.context, None) == {"RUNNING_MODAL"}
    assert op.point_id == ":choose_point:"
    assert op.execute(host.context) == {"CANCELLED"}
    assert host.state.sketch_draft_json == before and host.owner.draft.proposal is None
    assert not host.owner.proposal_capture


@pytest.mark.parametrize("action", ["invoke", "confirm", "pointer"])
def test_actual_caller_wrong_viewport_rejects_and_retires_dialog(host, action):
    promote(host)
    ids = add_points(host)
    wrong = Host(**vars(host.context))
    wrong.area = Host(type="VIEW_3D")
    before = store(host)
    if action == "invoke":
        op = host.viewport.MCAD_OT_use_existing_point()
        assert op.invoke(wrong, None) == {"CANCELLED"}
    elif action == "confirm":
        binding = host.owner.prepare_gesture("point")
        with pytest.raises(d.DraftError, match="original sketch viewport"):
            host.owner.accept_point_input(
                wrong, d.PointRef(ids[0]), expected_phase=binding.phase, picker=binding
            )
    else:
        with pytest.raises(d.DraftError, match="original sketch viewport"):
            host.owner.accept_point_input(
                wrong, d.PointSeed(0, 0), expected_phase=("arc", "center")
            )
    assert host.state.sketch_draft_json == before
    assert host.owner.gesture_intent is None


def test_arc_dimension_targets_real_arc_radius_and_annotation_center(host, monkeypatch):
    promote(host)
    pointer(host, (1, 2))
    pointer(host, (6, 2))
    pointer(host, (1, 9))
    arc = host.owner.commands.sketch["arcs"][0]
    host.owner.draft.select((("arc", arc["id"]),))
    monkeypatch.setattr(host.viewport, "_pointer", lambda *args: (8, 9))
    checks_before = list(host.checks)
    event = Host(mouse_x=80, mouse_y=90)
    host.viewport._dimension(host.owner, host.context, event)
    relation = host.owner.commands.sketch["constraints"][0]
    assert relation["kind"] == "radius" and relation["refs"] == [arc["id"]]
    assert relation["value"] == 5
    assert host.owner.draft.annotations[relation["id"]]["offset"] == [7, 7]
    assert host.owner.commands.pending_edit.constraint_id == relation["id"]
    assert host.owner.input_controller.raw == "5.0"
    assert {host.owner.input_controller.anchor, host.owner.input_controller.caret} == {0, 3}
    assert host.owner.field_position == (80, 90)
    assert host.checks == checks_before  # Placement opens typing before a guarded native trial.
    revision = host.owner.commands.revision
    host.owner.cancel_dimension()
    host.viewport._dimension(host.owner, host.context, event)
    assert host.owner.commands.revision == revision
    assert len(host.owner.commands.sketch["constraints"]) == 1
    assert host.owner.commands.pending_edit.constraint_id == relation["id"]
    assert host.owner.draft.annotations[relation["id"]]["offset"] == [7, 7]


def test_pointer_rejected_existing_arc_endpoint_remains_exact_observation(host):
    promote(host)
    ids = add_points(host)
    picker(host, ids[0])
    picker(host, ids[1])
    host.owner.proposal_capture = True
    before = host.owner.commands.checkpoint_payload()
    with pytest.raises(d.DraftError):
        host.owner.accept_point_input(
            host.context, d.PointRef(ids[1]), expected_phase=("arc", "end")
        )
    assert host.owner.commands.checkpoint_payload() == before
    assert host.owner.draft.proposal["observation"] == {"kind": "existing", "point_id": ids[1]}
    assert host.owner.draft.proposal["phase"] == "end"
    assert not host.checks


def test_new_general_entry_accepts_arc_graph_but_rectangle_keeps_legacy_boundary(host):
    route = load("viewport_sketch")
    doc = json.loads((ROOT / "examples/sector_profile_data_only.mcad.json").read_text())
    state = Host(document_json=json.dumps(doc))
    before = state.document_json
    assert route._require_new_sketch(state) is None
    assert state.document_json == before
    with pytest.raises(ValueError, match="Rectangle"):
        route._require_new_sketch(state, rectangle=True)
    assert route._require_new_sketch(Host(document_json=BASE)) is None
    assert route._require_new_sketch(Host(document_json=BASE), rectangle=True) is None


def _recorded_evidence(host, request, inner):
    """Synthetic receipt around unchanged recorded native inner, no launch."""
    contracts = load("backend_contracts")
    prepared = contracts.prepare_request(request)
    required = prepared.guarded_request()["backend_contract"]["required_capabilities"]
    selected = host.current[0]
    response = contracts.project_response(inner)
    response["backend_receipt"] = {
        "version": 1,
        "request_id": prepared.request_id,
        "request_fingerprint": prepared.fingerprint,
        "required_capabilities": required,
        "confirmed_capabilities": required[:],
        "missing_capabilities": [],
        "phase": "dispatched",
        "backend": {
            "core_version": "synthetic-gesture-port",
            "project_root": selected.project_root,
            "core_origin": selected.core_origin,
            "solver_origin": str(Path(selected.core_origin) / "sketch_solver.py"),
            "python_executable": selected.python_executable,
            "python_executable_target": selected.python_executable_target,
            "python_prefix": "/synthetic/prefix",
            "python_base_prefix": "/synthetic/base",
            "python_version": [3, 12, 14],
        },
    }
    evidence = load("guarded_evidence").accept_response(
        prepared, response, selected, owner_token=host.owner.owner_token
    )
    evidence.publication.consume(
        selected,
        owner_token=host.owner.owner_token,
        expected_action=request["action"],
        expected_result_version=request["result_version"],
    )
    return prepared, evidence


@pytest.mark.parametrize("version", [2, 3])
def test_ui_clone_preserves_full_guarded_driver_chain_and_native_status(host, version):
    fixtures = ROOT / "tests/fixtures/arc_authoring_evidence"
    if version == 3:
        request = json.loads((fixtures / "radius_edit_5_0_solve_sketch.operation.json").read_text())
        inner = json.loads((fixtures / "radius_edit_5_0_solve_sketch.response").read_text())
        replay = json.loads((fixtures / "radius_edit_5_0_replay.operation.json").read_text())
        downstream = json.loads((fixtures / "radius_edit_5_0_replay.response").read_text())
    else:
        legacy = ROOT / "tests/fixtures/result_v3/legacy_30383a1"
        request = json.loads((legacy / "solve_viewport_rectangle.request.txt").read_text())
        inner = json.loads((legacy / "solve_viewport_rectangle.stdout.txt").read_text())
        replay = json.loads((fixtures / "rectangle_replay2.request.raw").read_text())
        replay.pop("backend_contract")
        downstream = json.loads((fixtures / "rectangle_replay2.response.raw").read_text())
    host.state.document_json = json.dumps(request["document"])
    host.lifecycle._ACTIVE = None
    host.owner = host.session.GeneralSession(host.context, request["feature_id"])
    host.lifecycle._ACTIVE = host.owner
    commands = host.owner.commands
    relation = next(
        item for item in commands.sketch["constraints"] if item["kind"] in {"radius", "distance"}
    )
    commands.begin_edit(relation["id"])
    commands.update_edit(" " + commands.pending_edit.raw_text + " ")
    assert commands.solve_request(trial=True) == request
    expected, evidence = _recorded_evidence(host, request, inner)
    commands.record_guarded_solution(
        evidence,
        commands.revision,
        expected_prepared=expected,
        expected_input_revision=commands.pending_edit.input_revision,
    )
    expected2, evidence2 = _recorded_evidence(host, replay, downstream)
    commands.accept_driver(replay_evidence=evidence2, replay_prepared=expected2)
    host.owner.guarded_evidence, host.owner.expected_prepared = evidence, expected
    host.owner.evidence_request, host.owner.evidence_response = (
        request,
        load("backend_contracts").project_response(inner),
    )
    assert host.owner.current_native_build_status == "succeeded"
    before_chain = commands._solution_evidence
    before_prepared = commands._solution_prepared
    candidate = dispatch.clone(host.owner.draft)
    candidate.select_tool("Line")
    host.owner._replace_ui_intent(candidate)
    assert host.owner.commands._solution_evidence is before_chain
    assert host.owner.commands._solution_prepared is before_prepared
    assert host.owner.current_native_build_status == "succeeded"
    if version == 2:
        first = host.owner.commands.sketch["points"][0]["id"]
        assert picker(host, first) == ()
        assert host.owner.commands._solution_evidence is before_chain
        assert host.owner.commands._solution_prepared is before_prepared
    old = host.current[0]
    host.current[0] = replace(old, generation=old.generation + 1)
    assert host.owner.current_native_build_status == "not_checked"
    host.current[0] = old
    assert host.owner.current_native_build_status == "not_checked"


def test_picker_sentinel_cannot_collide_with_imported_real_point_id(host):
    host.owner.commands.execute(d.AddPoint(d.PointSeed(0, 0)))
    document = host.owner.commands.candidate()
    feature = document["features"][0]
    feature["sketch"]["points"][0]["id"] = "__choose_point__"
    host.state.document_json = json.dumps(document)
    host.lifecycle._ACTIVE = None
    host.owner = host.session.GeneralSession(host.context, feature["id"])
    host.lifecycle._ACTIVE = host.owner
    promote(host)
    before = store(host)
    host.context.window_manager.invoke_props_dialog = lambda *args, **kwargs: {"RUNNING_MODAL"}
    op = host.viewport.MCAD_OT_use_existing_point()
    assert op.invoke(host.context, None) == {"RUNNING_MODAL"}
    assert len({item[0] for item in op.point_items}) == len(op.point_items) == 2
    assert op.execute(host.context) == {"CANCELLED"}
    assert host.state.sketch_draft_json == before
    op = host.viewport.MCAD_OT_use_existing_point()
    assert op.invoke(host.context, None) == {"RUNNING_MODAL"}
    op.point_id = "__choose_point__"
    op.source = "point"
    assert op.execute(host.context) == {"FINISHED"}
    assert host.owner.draft.proposal["center"]["point_id"] == "__choose_point__"


@pytest.fixture
def rna_picker(host, monkeypatch):
    """Model separate OperatorProperties and RNA enum validation, not bpy itself.

    Existing direct-instance tests intentionally do not emulate property RNA.
    Here Python-only operator attributes are inaccessible to every callback.
    The separate registered-RNA smoke must verify this model in real Blender.
    """
    cls = host.viewport.MCAD_OT_use_existing_point
    fields = cls.__annotations__
    callbacks = []

    class Properties:
        __slots__ = ("_operator",)

        def __init__(self, operator):
            object.__setattr__(self, "_operator", operator)

        def __getattr__(self, name):
            if name not in fields:
                raise AttributeError(name)
            return getattr(self._operator, name)

        def __setattr__(self, name, value):
            if name not in fields:
                raise AttributeError(name)
            setattr(self._operator, name, value)

    def properties(operator):
        if "_rna_properties" not in vars(operator):
            operator._rna_properties = Properties(operator)
            operator._rna_values = {}
        return operator._rna_properties

    class Property:
        def __init__(self, name, options):
            self.name, self.options = name, options

        def items(self, operator):
            proxy = properties(operator)
            callbacks.append(proxy)
            return self.options["items"](proxy, host.context)

        def __get__(self, operator, cls=None):
            if operator is None:
                return self
            properties(operator)
            if "items" not in self.options:
                return operator._rna_values.get(self.name, "")
            index = operator._rna_values.get(self.name, 0)
            items = self.items(operator)
            return items[index][0] if 0 <= index < len(items) else ""

        def __set__(self, operator, value):
            properties(operator)
            if "items" not in self.options:
                assert type(value) is str
                operator._rna_values[self.name] = value
                return
            items = self.items(operator)
            identifiers = tuple(item[0] for item in items)
            if value not in identifiers:
                raise TypeError(f"enum {value!r} not found in {identifiers!r}")
            operator._rna_values[self.name] = identifiers.index(value)
            if "update" in self.options:
                self.options["update"](properties(operator), host.context)

    for name, options in fields.items():
        monkeypatch.setattr(cls, name, Property(name, options), raising=False)
    monkeypatch.setattr(cls, "properties", property(properties), raising=False)
    monkeypatch.setattr(
        cls,
        "report",
        lambda self, levels, message: self.__dict__.setdefault("reports", []).append(message),
    )
    host.context.window_manager.invoke_props_dialog = lambda *args, **kwargs: {"RUNNING_MODAL"}
    return Host(new=cls, callbacks=callbacks, proxy_type=Properties)


def test_picker_properties_proxy_initialization_source_reset_and_accept(host, rna_picker):
    promote(host)
    ids = add_points(host)
    line = host.owner.commands.execute(
        d.AddLine(d.PointRef(ids[0]), d.PointRef(ids[1]))
    ).entity_ids[0]
    store(host)
    op = rna_picker.new()
    assert op.invoke(host.context, None) == {"RUNNING_MODAL"}
    catalog = op.binding.point_catalog
    assert op.point_id == catalog.sentinel and op.source == "point"
    assert rna_picker.callbacks and all(
        type(proxy) is rna_picker.proxy_type for proxy in rna_picker.callbacks
    )
    assert not hasattr(op.properties, "owner") and not hasattr(op.properties, "binding")
    assert not hasattr(op.properties, "point_items")
    assert host.viewport._point_items(op.properties, host.context) is catalog.point_items
    assert host.viewport._point_items(op.properties, None) is host.session.POINT_PICKER_EMPTY
    assert host.viewport._source_items(op.properties, None) is host.session.POINT_SOURCE_EMPTY
    op.point_id = ids[1]
    op.source = f"line:{line}:end"
    assert host.viewport._source_items(op.properties, host.context) is catalog.source_items[ids[1]]
    op.point_id = ids[0]
    assert op.source == "point"
    op.source = f"line:{line}:start"
    assert op.execute(host.context) == {"FINISHED"}
    assert host.owner.draft.proposal["center"]["point_id"] == ids[0]
    assert op.execute(host.context) == {"CANCELLED"}


def test_picker_properties_proxy_unprepared_forged_token_has_no_authority(host, rna_picker):
    promote(host)
    ids = add_points(host)
    opened = rna_picker.new()
    assert opened.invoke(host.context, None) == {"RUNNING_MODAL"}
    before = store(host)
    forged = rna_picker.new()
    forged.picker_token = opened.picker_token
    forged.point_id = ids[0]
    assert (
        host.viewport._point_items(forged.properties, host.context)
        is opened.binding.point_catalog.point_items
    )
    assert forged.execute(host.context) == {"CANCELLED"}
    assert host.owner.gesture_intent is opened.binding
    assert host.state.sketch_draft_json == before


@pytest.mark.parametrize("direction", ["old_to_new", "new_to_old"])
def test_picker_properties_proxy_tokens_cannot_transfer_between_dialogs(
    host, rna_picker, direction
):
    promote(host)
    ids = add_points(host)
    old = rna_picker.new()
    assert old.invoke(host.context, None) == {"RUNNING_MODAL"}
    old.point_id = ids[0]
    old_catalog = old.binding.point_catalog
    old.cancel(host.context)
    assert (
        host.viewport._point_items(old.properties, host.context) is host.session.POINT_PICKER_EMPTY
    )
    new = rna_picker.new()
    assert new.invoke(host.context, None) == {"RUNNING_MODAL"}
    new.point_id = ids[1]
    assert old_catalog.token != new.binding.point_catalog.token
    before = store(host)
    if direction == "old_to_new":
        new.picker_token = old_catalog.token
        assert (
            host.viewport._point_items(new.properties, host.context)
            is host.session.POINT_PICKER_EMPTY
        )
        assert new.execute(host.context) == {"CANCELLED"}
        assert host.owner.gesture_intent is None
    else:
        old.picker_token = new.picker_token
        host.owner.error = "Newer dialog message"
        assert old.execute(host.context) == {"CANCELLED"}
        assert host.owner.gesture_intent is new.binding
        assert host.owner.error == "Newer dialog message"
    assert host.state.sketch_draft_json == before


@pytest.mark.parametrize("field", ["window", "scene", "area", "workspace", "view_layer"])
def test_picker_properties_proxy_foreign_context_is_display_only_fallback(host, rna_picker, field):
    promote(host)
    add_points(host)
    op = rna_picker.new()
    assert op.invoke(host.context, None) == {"RUNNING_MODAL"}
    context = Host(**vars(host.context))
    setattr(context, field, Host())
    assert host.viewport._point_items(op.properties, context) is host.session.POINT_PICKER_EMPTY
    assert host.viewport._source_items(op.properties, context) is host.session.POINT_SOURCE_EMPTY
    assert host.owner.gesture_intent is op.binding


def test_picker_properties_proxy_replacement_owner_keeps_its_error(host, rna_picker):
    promote(host)
    add_points(host)
    op = rna_picker.new()
    assert op.invoke(host.context, None) == {"RUNNING_MODAL"}
    original = host.owner
    host.lifecycle._ACTIVE = None
    replacement = host.session.GeneralSession(host.context)
    replacement.error = "Replacement owner message"
    host.lifecycle._ACTIVE = replacement
    assert (
        host.viewport._point_items(op.properties, host.context) is host.session.POINT_PICKER_EMPTY
    )
    assert op.execute(host.context) == {"CANCELLED"}
    assert replacement.error == "Replacement owner message"
    assert original.gesture_intent is None and replacement.gesture_intent is None


@pytest.mark.parametrize("observed", ["slot", "document", "context"])
def test_picker_properties_proxy_observed_aba_never_revives_catalog(host, rna_picker, observed):
    promote(host)
    add_points(host)
    op = rna_picker.new()
    assert op.invoke(host.context, None) == {"RUNNING_MODAL"}
    if observed == "slot":
        old = host.state.sketch_draft_json
        host.state.sketch_draft_json = "external"
        with pytest.raises(d.DraftError):
            host.owner._require_current()
        host.state.sketch_draft_json = old
    elif observed == "document":
        old = host.state.document_json
        host.state.document_json += " "
        assert not host.owner.valid_context()
        host.state.document_json = old
    else:
        old = host.owner.window.workspace
        host.owner.window.workspace = Host()
        assert not host.owner.valid_context()
        host.owner.window.workspace = old
    assert (
        host.viewport._point_items(op.properties, host.context) is host.session.POINT_PICKER_EMPTY
    )
    assert op.execute(host.context) == {"CANCELLED"}


def test_picker_properties_proxy_keeps_frozen_strings_without_live_queries(
    host, rna_picker, monkeypatch
):
    promote(host)
    ids = add_points(host)
    op = rna_picker.new()
    assert op.invoke(host.context, None) == {"RUNNING_MODAL"}
    catalog = op.binding.point_catalog
    original_strings = tuple(item[2] for item in catalog.point_items)
    monkeypatch.setattr(
        host.owner, "_backend_current_selection", lambda: pytest.fail("No currentness in callback")
    )
    monkeypatch.setattr(
        host.owner, "_require_current", lambda: pytest.fail("No authority work in callback")
    )
    for _ in range(3):
        gc.collect()
        assert host.viewport._point_items(op.properties, host.context) is catalog.point_items
        assert all(a is b[2] for a, b in zip(original_strings, catalog.point_items, strict=True))
    with pytest.raises(TypeError):
        catalog.source_items[ids[0]] = ()
    op.cancel(host.context)
    gc.collect()
    assert op.binding.point_catalog is catalog and op.point_items is catalog.point_items
    assert (
        host.viewport._point_items(op.properties, host.context) is host.session.POINT_PICKER_EMPTY
    )


def test_picker_properties_proxy_failure_visible_and_saved_slot_exact(host, rna_picker):
    promote(host)
    add_points(host)
    before = store(host)
    op = rna_picker.new()
    assert op.invoke(host.context, None) == {"RUNNING_MODAL"}
    assert op.execute(host.context) == {"CANCELLED"}
    assert "Choose an exact point ID" in host.owner.error
    assert op.reports[-1] == host.owner.error
    assert host.owner.gesture_intent is None and host.state.sketch_draft_json == before


def test_picker_properties_proxy_missing_context_never_guesses_owner(host, rna_picker, monkeypatch):
    promote(host)
    add_points(host)
    op = rna_picker.new()
    assert op.invoke(host.context, None) == {"RUNNING_MODAL"}
    monkeypatch.setattr(host.viewport, "active", lambda *args: pytest.fail("No owner guessing"))
    assert host.viewport._point_items(op.properties, None) is host.session.POINT_PICKER_EMPTY
    assert host.viewport._source_items(op.properties, None) is host.session.POINT_SOURCE_EMPTY


@pytest.mark.parametrize("token", ["", "unknown-catalog-token"])
def test_picker_properties_proxy_unbound_token_uses_static_choices(host, rna_picker, token):
    promote(host)
    ids = add_points(host)
    op = rna_picker.new()
    op.picker_token = token
    assert (
        host.viewport._point_items(op.properties, host.context) is host.session.POINT_PICKER_EMPTY
    )
    op.point_id = host.session.POINT_PICKER_EMPTY[0][0]
    assert op.source == "point"
    with pytest.raises(TypeError, match="not found"):
        op.point_id = ids[0]
    assert op.execute(host.context) == {"CANCELLED"}
    assert host.owner.gesture_intent is None


def test_picker_properties_proxy_error_does_not_write_foreign_area(host, rna_picker):
    promote(host)
    add_points(host)
    op = rna_picker.new()
    assert op.invoke(host.context, None) == {"RUNNING_MODAL"}
    host.owner.error = "Original viewport message"
    foreign = Host(**vars(host.context))
    foreign.area = Host()
    assert op._failed(foreign, RuntimeError("Original failure")) == {"CANCELLED"}
    assert op.reports[-1] == "Original failure"
    assert host.owner.error == "Original viewport message"


def test_picker_properties_proxy_failure_survives_removed_redraw_rna(host, rna_picker, monkeypatch):
    promote(host)
    add_points(host)
    op = rna_picker.new()
    assert op.invoke(host.context, None) == {"RUNNING_MODAL"}

    def removed():
        raise ReferenceError("Area RNA was removed")

    monkeypatch.setattr(host.owner.area, "tag_redraw", removed)
    assert op.execute(host.context) == {"CANCELLED"}
    assert "Choose an exact point ID" in host.owner.error
    assert op.reports[-1] == host.owner.error


def test_picker_catalog_preserves_each_arc_source_role(host):
    ids = ("center", "start", "end")
    sketch = {"arcs": [dict(id="a1", center=ids[0], start=ids[1], end=ids[2])]}
    catalog = host.session._point_picker_catalog(sketch, ids)
    for identifier, role in zip(ids, ("center", "start", "end"), strict=True):
        assert tuple(item[0] for item in catalog.source_items[identifier]) == (
            "point",
            "arc:a1:" + role,
        )
        assert catalog.source_bindings["arc:a1:" + role] == ("arc", "a1", role)


def test_picker_catalog_sentinel_collision_and_bound_point_limit(host):
    identifiers = (":choose_point:", ":choose_point::", "__choose_point__")
    catalog = host.session._point_picker_catalog({}, identifiers)
    assert catalog.sentinel not in identifiers
    assert tuple(item[0] for item in catalog.point_items[1:]) == identifiers
    assert len({item[0] for item in catalog.point_items}) == 4
    maximum = host.session._point_picker_catalog({}, tuple(f"p{i}" for i in range(256)))
    assert len(maximum.point_items) == 257
    for count in (0, 257):
        with pytest.raises(d.DraftError, match="1 and 256"):
            host.session._point_picker_catalog({}, tuple(f"p{i}" for i in range(count)))
