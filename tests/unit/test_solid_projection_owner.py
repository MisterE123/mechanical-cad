"""Circle picking and authoring with synthetic catalog/host ports, not native evidence."""

import copy
import importlib
import json
import sys
import types
from pathlib import Path

import pytest

PACKAGE = "mcad_solid_projection_owner_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [
    str(Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender")
]
sys.modules[PACKAGE] = package


def load(name):
    return importlib.import_module(PACKAGE + "." + name)


D = load("general_sketch_draft")
C = load("general_sketch_commands")
A = load("general_authoring")
S = load("draft_dispatch")
FACES = ["pad/face/cap.end", "pad/face/side.circle.rim"]
CIRCLE = {
    "faces": FACES,
    "points": [[6, 5, 10], [4, 7, 10], [2, 5, 10], [4, 3, 10], [6, 5, 10]],
    "circle": {"center": [4, 5, 10], "normal": [0, 0, 1], "radius": 2},
}
LINE = {
    "faces": ["pad/face/cap.end", "pad/face/side.line.a"],
    "endpoint_faces": [["pad/face/side.line.b"], ["pad/face/side.line.c"]],
    "points": [[0, 0, 10], [10, 0, 10]],
}


def document():
    return {
        "schema_version": 2,
        "id": "part",
        "name": "Projection",
        "units": "mm",
        "parameters": {},
        "active_feature": "pad",
        "features": [
            {
                "id": "source",
                "kind": "sketch_circle",
                "label": "Circle",
                "params": {"radius": 2},
                "inputs": {},
            },
            {
                "id": "pad",
                "kind": "extrude",
                "label": "Pad",
                "params": {"length": 10},
                "inputs": {"profile": "source"},
            },
        ],
    }


@pytest.mark.parametrize("version", [2, 3])
def test_circle_and_line_share_source_undo_restore_and_managed_drivers(version):
    original = json.dumps(document())
    draft = D.GeneralSketchDraft(original, journal_version=version)
    circle_command = C.AddProjectionGeometry("circle", (C.PointSeed(4, 5),), 2)
    center, circle = draft.project_solid_circle("pad", FACES, circle_command).entity_ids
    expected = {"kind": "circle", "faces": FACES, "target": circle}
    assert draft.candidate()["features"][-1]["projections"] == [expected]
    before = draft.checkpoint_payload()
    with pytest.raises(ValueError, match="matching construction"):
        draft.project_solid_edge("pad", LINE["faces"], LINE["endpoint_faces"], circle_command)
    assert draft.checkpoint_payload() == before
    line_command = C.AddProjectionGeometry("line", (C.PointSeed(0, 0), C.PointSeed(10, 0)))
    with pytest.raises(ValueError, match="matching construction"):
        draft.project_solid_circle("pad", FACES, line_command)
    assert draft.checkpoint_payload() == before
    draft.project_solid_edge("pad", LINE["faces"], LINE["endpoint_faces"], line_command)
    assert len(draft.candidate()["features"][-1]["projections"]) == 2
    draft.undo()
    assert draft.candidate()["features"][-1]["projections"] == [expected]
    wrapper = A.GeneralSketchAuthoringState(draft, ui_version=1 if version == 2 else 2)
    restored = S.restore(S.dumps(wrapper), original).command_draft
    restored.redo()
    assert len(restored.candidate()["features"][-1]["projections"]) == 2
    radius = next(c["id"] for c in restored.sketch["constraints"] if c["kind"] == "radius")
    with pytest.raises(ValueError, match="source"):
        restored.begin_edit(radius)
    with pytest.raises(ValueError, match="source"):
        restored.execute(C.MovePoint(center, (8, 9)))
    with pytest.raises(ValueError, match="construction"):
        restored.execute(C.SetConstruction((("circle", circle),), False))


@pytest.fixture
def session_module(monkeypatch):
    stubs = {
        "assembly_job_ui": {},
        "backend_runtime": {},
        "document_state": {},
        "part_publication": {},
        "sketch_view_presentation": {},
        "staged_edit_store": {},
        "workspace": {},
        "common": {"_state": lambda context: context.state},
        "display": {"_focus_display": lambda *args: None},
        "sketch_session": {
            "SketchSession": type("SketchSession", (), {}),
            "_discard_stored": lambda *args: None,
            "_tag_redraw": lambda *args: None,
        },
    }
    for name, fields in stubs.items():
        stub = types.ModuleType(PACKAGE + "." + name)
        stub.__dict__.update(fields)
        monkeypatch.setitem(sys.modules, stub.__name__, stub)
        monkeypatch.setattr(package, name, stub, raising=False)
    sys.modules.pop(PACKAGE + ".general_session", None)
    return load("general_session")


def owner_for(session, monkeypatch, *, circle=None):
    owner = object.__new__(session.GeneralSession)
    draft = D.GeneralSketchDraft(json.dumps(document()), journal_version=3)
    owner.draft = A.GeneralSketchAuthoringState(draft, ui_version=2)
    owner.display_plane = draft.sketch["plane"]
    owner._backend_context = context = object()
    owner._backend_current_selection = lambda: "selection"
    owner.require_gesture_context = owner._require_idle = lambda *args: None
    owner.replace_authoring = lambda candidate: setattr(owner, "draft", candidate)
    owner._check_authored_change = lambda context: None
    replay = {"features": []}
    monkeypatch.setattr(
        session.document_state, "current_part_result", lambda c: replay, raising=False
    )
    accepted = {"catalogs": {"pad": [copy.deepcopy(circle or CIRCLE), LINE]}, "replay": replay}
    token = object()
    calls = []

    def revalidate(selection, **kwargs):
        assert selection == "selection"
        assert kwargs == {
            "owner_token": token,
            "expected_action": "edge_catalog",
            "expected_result_version": 3,
            "require_success": True,
        }
        calls.append(True)
        return {"result": accepted}

    evidence = types.SimpleNamespace(revalidate=revalidate)
    return owner, context, evidence, token, calls, accepted


def test_owner_uses_native_circle_analytics_not_display_polyline(session_module, monkeypatch):
    owner, context, evidence, token, calls, _ = owner_for(session_module, monkeypatch)
    center, circle = owner.project_solid_edge(
        context, "pad", FACES, None, evidence, token, 3
    ).entity_ids
    authored = owner.commands.sketch
    assert authored["points"] == [{"id": center, "u": 4, "v": 5}]
    assert authored["circles"] == [
        {"id": circle, "center": center, "radius": 2, "construction": True}
    ]
    assert owner.commands.candidate()["features"][-1]["projections"] == [
        {"kind": "circle", "faces": FACES, "target": circle}
    ]
    owner.project_solid_edge(
        context, "pad", LINE["faces"], LINE["endpoint_faces"], evidence, token, 3
    )
    displayed = owner._display_authored_sketch()
    assert len(displayed["lines"]) == len(displayed["circles"]) == 1
    assert calls


def test_owner_oblique_circle_is_atomic_and_restores_catalog_binding(session_module, monkeypatch):
    circle = copy.deepcopy(CIRCLE)
    circle["circle"]["normal"] = [1, 0, 0]
    owner, context, evidence, token, _, _ = owner_for(session_module, monkeypatch, circle=circle)
    before = S.dumps(owner.draft)
    previous = owner._solid_projection_catalog = object()
    with pytest.raises(ValueError, match="parallel.*ellipse"):
        owner.project_solid_edge(context, "pad", FACES, None, evidence, token, 3)
    assert S.dumps(owner.draft) == before
    assert owner._solid_projection_catalog is previous


def test_owner_stale_replay_and_changed_line_endpoints_leave_draft_unchanged(
    session_module, monkeypatch
):
    owner, context, evidence, token, _, accepted = owner_for(session_module, monkeypatch)
    before = S.dumps(owner.draft)
    with pytest.raises(ValueError, match="stable identity"):
        owner.project_solid_edge(context, "pad", LINE["faces"], None, evidence, token, 3)
    accepted["replay"] = {"features": [], "changed": True}
    with pytest.raises(ValueError, match="source Part changed"):
        owner.project_solid_edge(context, "pad", FACES, None, evidence, token, 3)
    assert S.dumps(owner.draft) == before


@pytest.mark.parametrize("kind", ["circle", "line", "arc", "unbound_line"])
def test_picker_accepts_only_catalog_circle_or_stable_straight_edge(
    session_module, monkeypatch, kind
):
    # The real base picker's raycast and catalog checks are tested separately.
    # This fixture exercises only the projection-specific analytic eligibility.
    entry = copy.deepcopy(CIRCLE if kind in {"circle", "arc"} else LINE)
    if kind == "arc":
        entry.pop("circle")
    elif kind == "unbound_line":
        entry.pop("endpoint_faces")

    class BasePicker:
        def hover(self, context, event, *, accepting=False):
            self.hit = ("pad", *entry["faces"])
            self.points = entry["points"]
            return True

    stubs = {
        "direct_edge_pick": {"BlendEdgePicker": BasePicker},
        "general_viewport": {"active": lambda context: None},
        "face_pick": {"HoverSnapshot": type("HoverSnapshot", (), {})},
        "solid_review": {"InputBodyReview": type("InputBodyReview", (), {})},
        "viewport_sketch": {"NAVIGATION_EVENTS": {"MIDDLEMOUSE", "NUMPAD_1"}},
    }
    for name, fields in stubs.items():
        stub = types.ModuleType(PACKAGE + "." + name)
        stub.__dict__.update(fields)
        monkeypatch.setitem(sys.modules, stub.__name__, stub)
        monkeypatch.setattr(package, name, stub, raising=False)
    bpy = types.ModuleType("bpy")
    bpy.types = types.SimpleNamespace(Operator=type("Operator", (), {}))
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    props = types.ModuleType("bpy.props")
    props.EnumProperty = props.StringProperty = lambda **kwargs: None
    monkeypatch.setitem(sys.modules, "bpy.props", props)
    sys.modules.pop(PACKAGE + ".solid_projection_picker", None)
    picker = object.__new__(load("solid_projection_picker").SolidProjectionPicker)
    picker.snapshot = None
    picker.catalog = {"pad": [entry]}
    messages = []
    picker.area = types.SimpleNamespace(header_text_set=messages.append)
    assert picker.hover(None, None, accepting=True)
    if kind in {"circle", "line"}:
        assert picker.hit == ("pad", *entry["faces"])
        assert picker.hit_endpoint_faces == entry.get("endpoint_faces")
        assert "construction geometry" in picker.message
    else:
        assert picker.hit is None and picker.points == []
        assert picker.hit_endpoint_faces is None
    assert messages == [picker.message]


@pytest.mark.parametrize("version", [2, 3])
def test_multi_source_ledger_keeps_ports_through_undo_resume_redo(version):
    base = document()
    base["features"].append(
        {
            "id": "other",
            "kind": "transform",
            "label": "Other",
            "params": {},
            "inputs": {"base": "pad"},
        }
    )
    original = json.dumps(base)
    draft = D.GeneralSketchDraft(original, journal_version=version)
    command = C.AddProjectionGeometry("circle", (C.PointSeed(4, 5),), 2)
    first = draft.project_solid_circle("pad", FACES, command).entity_ids[-1]
    legacy = draft.candidate()["features"][-1]
    assert legacy["inputs"] == {"external": "pad"}
    assert draft.checkpoint_payload()["external"]["feature_id"] == "pad"
    second = draft.project_solid_circle("other", FACES, command).entity_ids[-1]
    feature = draft.candidate()["features"][-1]
    assert feature["inputs"] == {"external": "pad", "external_2": "other"}
    assert feature["projections"] == [
        {"kind": "circle", "faces": FACES, "target": first},
        {"kind": "circle", "faces": FACES, "target": second, "input": "external_2"},
    ]
    draft.undo()
    assert draft.candidate()["features"][-1] == legacy
    checkpoint = draft.checkpoint_payload()
    assert checkpoint["external"]["inputs"] == feature["inputs"]
    wrapper = A.GeneralSketchAuthoringState(draft, ui_version=1 if version == 2 else 2)
    restored = S.restore(S.dumps(wrapper), original).command_draft
    restored.redo()
    assert restored.candidate()["features"][-1] == feature
    restored.undo()
    restored.project_solid_circle("other", FACES, command)
    assert restored.candidate()["features"][-1]["inputs"] == feature["inputs"]


@pytest.mark.parametrize("version", [2, 3])
def test_saved_legacy_later_dependency_survives_but_new_later_pick_rejects(version):
    base = document()
    creator = D.GeneralSketchDraft(json.dumps(base), journal_version=version)
    command = C.AddProjectionGeometry("circle", (C.PointSeed(4, 5),), 2)
    creator.project_solid_circle("pad", FACES, command)
    saved = creator.candidate()
    target = saved["features"].pop()
    saved["features"].insert(0, target)
    draft = D.GeneralSketchDraft(json.dumps(saved), target["id"], True, journal_version=version)
    assert draft.candidate() == saved
    wrapper = A.GeneralSketchAuthoringState(draft, ui_version=1 if version == 2 else 2)
    assert S.restore(S.dumps(wrapper), json.dumps(saved)).command_draft.candidate() == saved
    before = draft.checkpoint_payload()
    with pytest.raises(ValueError, match="earlier"):
        draft.project_solid_circle("pad", FACES, command)
    assert draft.checkpoint_payload() == before


def test_owner_same_faces_from_two_solids_are_source_bound(session_module, monkeypatch):
    owner, context, evidence, token, _, accepted = owner_for(session_module, monkeypatch)
    base = document()
    base["features"].append(
        {
            "id": "other",
            "kind": "transform",
            "label": "Other",
            "params": {"x": 30},
            "inputs": {"base": "pad"},
        }
    )
    owner.draft = A.GeneralSketchAuthoringState(
        D.GeneralSketchDraft(json.dumps(base), journal_version=3), ui_version=2
    )
    other = copy.deepcopy(CIRCLE)
    other["circle"]["center"] = [34, 5, 10]
    accepted["catalogs"]["other"] = [other]
    first = owner.project_solid_edge(context, "pad", FACES, None, evidence, token, 3).entity_ids[0]
    second = owner.project_solid_edge(context, "other", FACES, None, evidence, token, 3).entity_ids[
        0
    ]
    displayed = owner._display_authored_sketch()
    points = {p["id"]: p for p in displayed["points"]}
    assert [points[first]["u"], points[first]["v"]] == [4, 5]
    assert [points[second]["u"], points[second]["v"]] == [34, 5]
    before = S.dumps(owner.draft)
    accepted["catalogs"].pop("other")
    with pytest.raises(ValueError, match="Missing or duplicate"):
        owner._display_authored_sketch()
    assert S.dumps(owner.draft) == before


def test_saved_edge_cache_cannot_cross_source_port(session_module, monkeypatch):
    owner, _, _, _, _, _ = owner_for(session_module, monkeypatch)
    owner.current_solution_response = lambda: None
    feature = {"id": "target", "inputs": {"external": "other"}}
    rows = [{"kind": "circle", "faces": FACES, "target": "guide"}]
    result = {
        "features": [
            {
                "id": "target",
                "status": "ok",
                "inputs": {"external": "pad"},
                "projection_edges": [{"kind": "circle", "faces": FACES, **CIRCLE["circle"]}],
            }
        ]
    }
    assert owner._solid_projection_edges(feature, result, "external", rows) is None


@pytest.mark.parametrize("solid_first", [False, True])
def test_actual_authoring_methods_allow_mixed_sources(session_module, monkeypatch, solid_first):
    owner, context, evidence, token, _, accepted = owner_for(session_module, monkeypatch)
    base = document()
    sketch = {
        "schema_version": 2,
        "id": "source_geometry",
        "units": "mm",
        "plane": {"id": "xy", "origin": [0, 0, 0], "quaternion": [1, 0, 0, 0]},
        "points": [{"id": "center", "u": 14, "v": 15}],
        "lines": [],
        "circles": [{"id": "circle", "center": "center", "radius": 3}],
        "constraints": [
            {"id": "fixed", "kind": "fixed", "refs": ["center"], "target": [14, 15]},
            {"id": "radius", "kind": "radius", "refs": ["circle"], "value": 3},
        ],
    }
    base["features"][0].update(kind="sketch_constrained", params={}, sketch=sketch)
    accepted["replay"]["features"] = [
        {"id": "source", "status": "ok", "sketch": {"solved": copy.deepcopy(sketch)}}
    ]
    owner.draft = A.GeneralSketchAuthoringState(
        D.GeneralSketchDraft(json.dumps(base), journal_version=3), ui_version=2
    )
    actions = {
        "sketch": lambda: owner.project_external(context, "source", "circle"),
        "solid": lambda: owner.project_solid_edge(context, "pad", FACES, None, evidence, token, 3),
    }
    points = {}
    for kind in ("solid", "sketch") if solid_first else ("sketch", "solid"):
        points[kind] = actions[kind]().entity_ids[0]
    feature = owner.commands.candidate()["features"][-1]
    assert feature["inputs"] == {
        "external": "pad" if solid_first else "source",
        "external_2": "source" if solid_first else "pad",
    }
    displayed = owner._display_authored_sketch()
    coordinates = {p["id"]: (p["u"], p["v"]) for p in displayed["points"]}
    assert coordinates[points["sketch"]] == (14, 15)
    assert coordinates[points["solid"]] == (4, 5)


@pytest.mark.parametrize(
    "mutation", ["extra_port", "missing_port", "changed_source", "duplicate_source"]
)
def test_multi_source_checkpoint_rejects_inconsistent_bindings(mutation):
    base = document()
    base["features"].append(
        {
            "id": "other",
            "kind": "transform",
            "label": "Other",
            "params": {},
            "inputs": {"base": "pad"},
        }
    )
    draft = D.GeneralSketchDraft(json.dumps(base), journal_version=3)
    command = C.AddProjectionGeometry("circle", (C.PointSeed(4, 5),), 2)
    draft.project_solid_circle("pad", FACES, command)
    draft.project_solid_circle("other", FACES, command)
    checkpoint = draft.checkpoint_payload()
    inputs = checkpoint["external"]["inputs"]
    if mutation == "extra_port":
        inputs["external_3"] = "pad"
    elif mutation == "missing_port":
        inputs.pop("external_2")
    elif mutation == "changed_source":
        inputs["external_2"] = "missing"
    else:
        inputs["external_2"] = "pad"
    with pytest.raises(ValueError):
        D.GeneralSketchDraft.from_checkpoint_payload(checkpoint, expected_journal_version=3)


@pytest.mark.parametrize("version", [2, 3])
def test_deleting_one_source_prunes_only_its_active_edge_and_retains_redo(version):
    base = document()
    base["features"].append(
        {
            "id": "other",
            "kind": "transform",
            "label": "Other",
            "params": {},
            "inputs": {"base": "pad"},
        }
    )
    original = json.dumps(base)
    draft = D.GeneralSketchDraft(original, journal_version=version)
    command = C.AddProjectionGeometry("circle", (C.PointSeed(4, 5),), 2)
    point, target = draft.project_solid_circle("pad", FACES, command).entity_ids
    draft.project_solid_circle("other", FACES, command)
    before = draft.candidate()
    # Exercise pure metadata/journal publication with synthetic release seeds;
    # this seam does not stand in for a successful native Check capability.
    prepared = C.prepare_command(
        draft.sketch,
        C.DeleteBatch(draft.preview_delete((("circle", target), ("point", point)))),
        draft.revision,
        draft._allocated_ids,
        draft._next_id,
        release_seeds={
            "points": draft.sketch["points"],
            "circles": [{"id": c["id"], "radius": c["radius"]} for c in draft.sketch["circles"]],
        },
        journal_version=version,
    )
    draft._commit(prepared.record)
    feature = draft.candidate()["features"][-1]
    assert feature["inputs"] == {"external_2": "other"}
    assert [r["input"] for r in feature["projections"]] == ["external_2"]
    wrapper = A.GeneralSketchAuthoringState(draft, ui_version=1 if version == 2 else 2)
    restored = S.restore(S.dumps(wrapper), original).command_draft
    restored.undo()
    assert restored.candidate() == before
    restored.redo()
    assert restored.candidate()["features"][-1] == feature


@pytest.fixture
def projection_picker_module(session_module, monkeypatch):
    stubs = {
        "direct_edge_pick": {"BlendEdgePicker": type("BlendEdgePicker", (), {})},
        "general_viewport": {"active": lambda context: context.owner},
        "face_pick": {"HoverSnapshot": type("HoverSnapshot", (), {})},
        "solid_review": {"InputBodyReview": type("InputBodyReview", (), {})},
        "viewport_sketch": {"NAVIGATION_EVENTS": {"MIDDLEMOUSE", "NUMPAD_1", "NDOF_MOTION"}},
    }
    for name, fields in stubs.items():
        stub = types.ModuleType(PACKAGE + "." + name)
        stub.__dict__.update(fields)
        monkeypatch.setitem(sys.modules, stub.__name__, stub)
        monkeypatch.setattr(package, name, stub, raising=False)
    bpy = types.ModuleType("bpy")
    bpy.types = types.SimpleNamespace(Operator=type("Operator", (), {}))
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    props = types.ModuleType("bpy.props")
    props.EnumProperty = props.StringProperty = lambda **kwargs: None
    monkeypatch.setitem(sys.modules, "bpy.props", props)
    sys.modules.pop(PACKAGE + ".solid_projection_picker", None)
    return load("solid_projection_picker")


def test_solid_chooser_uses_earlier_typed_outputs_and_disambiguates_labels(
    projection_picker_module,
):
    module = projection_picker_module
    features = [
        {"id": identifier, "label": "Repeated label"}
        for identifier in ("first", "sketch", "failed", "missing", "second", "target", "later")
    ]
    owner = types.SimpleNamespace(
        commands=types.SimpleNamespace(
            feature_id="target", candidate=lambda: {"features": features}
        )
    )
    result = {
        "features": [
            {
                "id": feature["id"],
                "status": "failed" if feature["id"] == "failed" else "ok",
                "output": {"kind": "sketch" if feature["id"] == "sketch" else "solid"},
            }
            for feature in features
            if feature["id"] != "missing"
        ]
    }
    items = module.earlier_solid_items(owner, result)
    assert [item[0] for item in items] == ["first", "second"]
    assert items[0][1] == "Repeated label · first"
    assert items[1][1] == "Repeated label · second"
    # A fresh draft is appended; every successful prior solid remains eligible.
    owner.commands.feature_id = "new"
    assert [item[0] for item in module.earlier_solid_items(owner, result)] == [
        "first",
        "second",
        "target",
        "later",
    ]


def test_frozen_solid_choices_cross_rna_callback_without_live_lookup(projection_picker_module):
    module = projection_picker_module
    values = (("one", "One · one", "Earlier solid"), ("two", "Two · two", "Earlier solid"))
    rna = types.SimpleNamespace(source_choices_json=json.dumps(values))
    # The callback wrapper has no _selection or Python Operator fields. None
    # context deliberately proves redraw does not recapture changed sources.
    assert module._source_items(rna, None) == values
    assert module._source_items(rna, None) is module._source_items(rna, None)


@pytest.mark.parametrize(
    "changed",
    ["revision", "saved", "saved_slot", "runtime", "area", "layer", "screen", "owner", "mode"],
)
def test_captured_projection_selection_rejects_stale_context(projection_picker_module, changed):
    module = projection_picker_module
    area = types.SimpleNamespace(type="VIEW_3D")
    window = types.SimpleNamespace(screen=object())
    owner = types.SimpleNamespace(
        alive=True,
        valid_context=lambda: True,
        commands=types.SimpleNamespace(revision=3),
        stored_snapshot="draft",
    )
    context = types.SimpleNamespace(
        owner=owner,
        window=window,
        area=area,
        view_layer=object(),
        mode="OBJECT",
        state=types.SimpleNamespace(sketch_draft_json="draft"),
    )
    selection = object.__new__(module.ProjectionSelection)
    selection.owner, selection.revision, selection.saved = owner, 3, "draft"
    selection.window, selection.screen, selection.area, selection.layer = (
        window,
        window.screen,
        area,
        context.view_layer,
    )
    selection.snapshot = types.SimpleNamespace(current=lambda context: True)
    selection.items = (("earlier", "Earlier", ""),)
    selection.require_source(context, "earlier")
    with pytest.raises(ValueError, match="eligible earlier"):
        selection.require_source(context, "later")
    if changed == "revision":
        owner.commands.revision += 1
    elif changed == "saved":
        owner.stored_snapshot += "changed"
    elif changed == "saved_slot":
        context.state.sketch_draft_json = "external replacement"
    elif changed == "runtime":
        selection.snapshot.current = lambda context: False
    elif changed == "area":
        context.area = object()
    elif changed == "layer":
        context.view_layer = object()
    elif changed == "screen":
        window.screen = object()
    elif changed == "owner":
        context.owner = object()
    else:
        context.mode = "EDIT_MESH"
    with pytest.raises(ValueError, match="changed"):
        selection.require_source(context, "earlier")


@pytest.mark.parametrize("event_type", ["MIDDLEMOUSE", "NUMPAD_1", "NDOF_MOTION"])
def test_projection_navigation_clears_hover_without_changing_draft(
    projection_picker_module, event_type
):
    module = projection_picker_module
    closed = []
    picker = types.SimpleNamespace(
        current=lambda context: True,
        edge_choice=None,
        hit=("source", "a", "b"),
        points=[1],
        area=types.SimpleNamespace(tag_redraw=lambda: None),
        close=lambda: closed.append(True),
    )
    operator = types.SimpleNamespace(_picker=picker)
    assert module.MCAD_OT_use_solid_edge.modal(
        operator, None, types.SimpleNamespace(type=event_type)
    ) == {"PASS_THROUGH"}
    assert picker.hit is None and picker.points == [] and not closed


def choice_picker(module, monkeypatch):
    picker = object.__new__(module.SolidProjectionPicker)
    picker.catalog = {"pad": [copy.deepcopy(LINE), copy.deepcopy(CIRCLE)]}
    picker.catalog_token = object()
    accepted = {"catalogs": copy.deepcopy(picker.catalog), "replay": {"id": "fresh"}}
    checks = []
    def revalidate(*args, **kwargs):
        checks.append(kwargs)
        return {"result": accepted}
    picker.catalog_evidence = types.SimpleNamespace(revalidate=revalidate)
    picker.catalog_version = 3
    picker.current = lambda context: True
    picker.choice_display_current = lambda context: True
    picker.rv3d = types.SimpleNamespace(perspective_matrix="matrix")
    picker.choice_matrix = "matrix"
    picker.region = types.SimpleNamespace(width=900, height=700, x=0, y=0)
    picker.choice_size = (900, 700)
    picker.snapshot = types.SimpleNamespace(
        result=lambda context, **kwargs: {"id": "fresh"},
        bound_feature=lambda context, obj, result: {"id": "pad"})
    monkeypatch.setattr(module.backend_runtime, "capture", lambda context: "backend", raising=False)
    picker.edge_choice = module.EdgeChoice(picker, [
        (0, "pad", entry, entry["points"], object()) for entry in picker.catalog["pad"]])
    picker.choice_panel = ([(24, 400, 680, 462), (24, 338, 680, 400)],
                           (24, 298, 180, 330), (195, 298, 350, 330), ())
    picker.area = types.SimpleNamespace(tag_redraw=lambda: None)
    return picker, accepted, checks


def test_choice_opening_release_never_selects_and_enter_never_defaults(
    projection_picker_module, monkeypatch
):
    picker, _, checks = choice_picker(projection_picker_module, monkeypatch)
    def event(kind, value="PRESS"):
        return types.SimpleNamespace(type=kind, value=value)
    assert picker.choice_event(None, event("ONE")) is None
    assert picker.edge_choice.selected is None
    picker.choice_event(None, event("LEFTMOUSE", "RELEASE"))
    assert picker.choice_event(None, event("RET")) is None
    assert not checks
    picker.choice_event(None, event("TWO"))
    assert picker.edge_choice.selected == 1 and checks
    assert picker.points == CIRCLE["points"]
    assert picker.choice_event(None, event("RET")) == "APPLY"


@pytest.mark.parametrize("changed", ["context", "matrix", "size", "catalog", "replay", "object"])
def test_choice_fresh_validation_refuses_changed_inputs(
    projection_picker_module, monkeypatch, changed
):
    picker, accepted, _ = choice_picker(projection_picker_module, monkeypatch)
    picker.validate_choice(None)
    if changed == "context":
        picker.current = lambda context: False
    elif changed == "matrix":
        picker.rv3d.perspective_matrix = "other"
    elif changed == "size":
        picker.region.width = 800
    elif changed == "catalog":
        accepted["catalogs"]["pad"][0]["points"][0][0] += 1
    elif changed == "replay":
        accepted["replay"] = {"id": "changed"}
    else:
        picker.snapshot.bound_feature = lambda *args: {"id": "other"}
    with pytest.raises(ValueError):
        picker.validate_choice(None)
    assert picker.edge_choice.selected is None


def test_choice_apply_consumes_before_owner_handoff(projection_picker_module, monkeypatch):
    picker, _, checks = choice_picker(projection_picker_module, monkeypatch)
    choice = picker.edge_choice
    choice.released = True
    choice.select(picker, 0)
    applied = []
    def close():
        assert choice.retired
        picker.edge_choice = None
    picker.close = close
    picker.owner = types.SimpleNamespace(project_solid_edge=lambda *args: applied.append(args))
    picker.apply_choice(None)
    assert checks and len(applied) == 1
    assert applied[0][1:4] == ("pad", LINE["faces"], LINE["endpoint_faces"])
    with pytest.raises(ValueError, match="expired"):
        picker.apply_choice(None)
    assert len(applied) == 1


def test_repeat_key_tail_cannot_choose_or_apply(projection_picker_module, monkeypatch):
    picker, _, checks = choice_picker(projection_picker_module, monkeypatch)
    choice = picker.edge_choice
    choice.released = True
    for key in ("ONE", "RET"):
        assert picker.choice_event(None, types.SimpleNamespace(
            type=key, value="PRESS", is_repeat=True)) is None
    assert choice.selected is None and not checks
    choice.select(picker, 0)
    assert picker.choice_event(None, types.SimpleNamespace(
        type="RET", value="PRESS", is_repeat=True)) is None
    assert not choice.retired and not checks


def test_save_retirement_also_covers_legacy_picker(projection_picker_module, monkeypatch):
    closed = []
    owner = types.SimpleNamespace(solid_projection_picker=types.SimpleNamespace(
        close=lambda: closed.append(True)))
    monkeypatch.setattr(projection_picker_module, "active", lambda: owner)
    projection_picker_module.cancel_active()
    assert closed == [True]
    owner.solid_projection_picker = None
    projection_picker_module.cancel_active()
    assert closed == [True]


@pytest.mark.parametrize("changed", ["hidden", "scene_unlink", "layer_unlink", "data"])
def test_choice_display_loss_retires_even_if_restored(projection_picker_module, changed):
    module = projection_picker_module
    picker = object.__new__(module.SolidProjectionPicker)
    picker.edge_choice = types.SimpleNamespace(retired=False)
    data = object()
    visible = [True]
    obj = types.SimpleNamespace(name="captured", data=data,
                               visible_get=lambda **kwargs: visible[0])
    picker.choice_display = ((obj, data),)
    picker.scene = types.SimpleNamespace(objects={"captured": obj})
    picker.view_layer = types.SimpleNamespace(objects={"captured": obj})
    picker.area = types.SimpleNamespace(spaces=types.SimpleNamespace(active=object()))
    assert picker.choice_display_current(None)
    if changed == "hidden":
        visible[0] = False
    elif changed == "scene_unlink":
        picker.scene.objects.clear()
    elif changed == "layer_unlink":
        picker.view_layer.objects.clear()
    else:
        obj.data = object()
    assert not picker.choice_display_current(None)
    assert picker.edge_choice.retired
    visible[0] = True
    picker.scene.objects["captured"] = picker.view_layer.objects["captured"] = obj
    obj.data = data
    assert not picker.choice_display_current(None)
