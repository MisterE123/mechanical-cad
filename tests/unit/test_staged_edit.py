"""Host transaction gates; native replay/RNA coverage lives in the Blender smoke.

Only Blender storage and the authoritative replay/publication boundary are
controlled here. The actual proposal implementation is imported unchanged.
"""

import copy
import importlib
import json
import sys
import types
from contextlib import nullcontext
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def host(monkeypatch):
    name = "mcad_staged_host_tests"
    package = types.ModuleType(name)
    package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
    monkeypatch.setitem(sys.modules, name, package)
    bridge = types.ModuleType(name + ".bridge")
    bridge.BridgeError = type("BridgeError", (RuntimeError,), {})
    monkeypatch.setitem(sys.modules, bridge.__name__, bridge)
    doc = types.ModuleType(name + ".document_state")
    monkeypatch.setitem(sys.modules, doc.__name__, doc)
    backend = types.ModuleType(name + ".backend_runtime")
    backend.configuration = lambda context: (None, context.deflection)
    monkeypatch.setitem(sys.modules, backend.__name__, backend)
    base = {
        "id": "part",
        "name": "Part",
        "active_feature": "solid",
        "features": [
            {"id": "source", "kind": "sketch_constrained", "inputs": {}, "sketch": {"r": 3}},
            {
                "id": "target",
                "kind": "sketch_constrained",
                "inputs": {"external": "source"},
                "projections": [{"source": "old", "target": "reference"}],
                "sketch": {
                    "points": [{"id": "a"}, {"id": "b"}],
                    "lines": [{"id": "guide"}],
                    "circles": [{"id": "reference"}, {"id": "outline"}],
                    "constraints": [
                        {"id": "size", "kind": "radius", "refs": ["reference"], "value": 3},
                        {"id": "match", "kind": "equal", "refs": ["reference", "outline"]},
                    ],
                },
            },
            {"id": "solid", "kind": "extrude", "inputs": {"profile": "target"}},
        ],
    }
    state = types.SimpleNamespace(
        document_json=json.dumps(base), owner_id="owner", document_path="", last_action_error=""
    )
    scene = types.SimpleNamespace(
        mechanical_cad=state, unit_settings=types.SimpleNamespace(scale=1)
    )
    scene.as_pointer = lambda: id(scene)
    window = types.SimpleNamespace(scene=scene)
    context = types.SimpleNamespace(
        scene=scene, window=window, workspace=object(), backend_revision=1, deflection=0.1
    )
    context.window_manager = types.SimpleNamespace(windows=[window])
    registered = set()
    bpy = types.ModuleType("bpy")
    bpy.context = context
    context.temp_override = lambda **kwargs: nullcontext()
    bpy.app = types.SimpleNamespace(
        timers=types.SimpleNamespace(
            is_registered=lambda callback: callback in registered,
            register=lambda callback, **kwargs: registered.add(callback),
            unregister=lambda callback: registered.remove(callback),
        )
    )
    monkeypatch.setitem(sys.modules, "bpy", bpy)
    binding = {
        "scene": scene,
        "window": window,
        "workspace": context.workspace,
        "document_json": state.document_json,
        "owner_id": state.owner_id,
        "scale": 1,
        "backend_revision": 1,
        "deflection": 0.1,
    }

    def assert_binding(current, captured):
        if (
            current.scene is not captured["scene"]
            or current.window is not captured["window"]
            or current.workspace is not captured["workspace"]
            or state.document_json != captured["document_json"]
            or state.owner_id != captured["owner_id"]
            or scene.unit_settings.scale != captured["scale"]
            or current.backend_revision != captured["backend_revision"]
        ):
            raise bridge.BridgeError("stale native binding")

    response = {
        "ok": False,
        "result": {
            "status": "failed",
            "features": [
                {"id": "source", "status": "ok"},
                {
                    "id": "target",
                    "status": "failed",
                    "error": {"code": "invalid_sketch_projection", "message": "Missing source"},
                },
                {"id": "solid", "status": "blocked"},
            ],
        },
    }
    doc._scene_key = id
    doc._assert_binding = assert_binding
    doc._evidence_projection = lambda *args: response
    doc.current_part_result = lambda context: {"status": "ok"}
    doc.require_no_sketch_draft = lambda context: None
    doc.replay_guard = lambda context: nullcontext()
    published = []

    def commit(context, candidate, path, *, validate_result, staged_token):
        previous = copy.deepcopy(response)
        response["ok"] = True
        response["result"]["status"] = "ok"
        for row in response["result"]["features"]:
            row["status"] = "ok"
        try:
            validate_result(None, None)
        finally:
            response.clear()
            response.update(previous)
        published.append((candidate, path, staged_token))
        state.document_json = json.dumps(candidate)
        return True

    doc._commit_candidate_locked = commit
    module_name = name + ".staged_edit"
    monkeypatch.delitem(sys.modules, name + ".staged_edit_store", raising=False)
    monkeypatch.delitem(sys.modules, module_name, raising=False)
    module = importlib.import_module(module_name)
    proposed = copy.deepcopy(base)
    proposed["features"][0]["sketch"]["r"] = 4
    result = types.SimpleNamespace(
        module=module,
        doc=doc,
        context=context,
        base=base,
        proposed=proposed,
        state=state,
        binding=binding,
        response=response,
        error=bridge.BridgeError,
        published=published,
        registered=registered,
    )
    yield result
    module.cancel_all()
    sys.modules.pop(module_name, None)


def retain(host):
    assert host.module.retain(host.context, host.proposed, "source", object(), host.binding)
    return host.module.current(host.context)


def repaired(proposal):
    candidate = proposal.document
    candidate["features"][1]["projections"][0]["source"] = "replacement"
    return candidate


def test_proposal_is_detached_and_never_publishes_accepted_state(host):
    before = host.state.document_json
    proposal = retain(host)
    assert proposal.feature_id == "source" and proposal.base_json == before
    host.proposed["features"][0]["sketch"]["r"] = 99
    proposal.document["features"][0]["sketch"]["r"] = 98
    host.response["result"]["features"][1]["error"]["message"] = "Caller mutation"
    proposal.failures[0]["error"]["message"] = "Getter mutation"
    assert proposal.document["features"][0]["sketch"]["r"] == 4
    assert proposal.failures[0]["error"]["message"] == "Missing source"
    assert host.state.document_json == before and not host.published
    assert host.module._supervise in host.registered


@pytest.mark.parametrize(
    "case",
    [
        "no_authority",
        "upstream_failed",
        "only_blocked",
        "no_reference",
        "not_descendant",
        "add",
        "remove",
        "envelope",
    ],
)
def test_ineligible_candidates_do_not_create_proposals(host, case):
    if case == "no_authority":
        host.doc.current_part_result = lambda context: None
    elif case == "upstream_failed":
        host.response["result"]["features"][0]["status"] = "failed"
    elif case == "only_blocked":
        host.response["result"]["features"][1]["status"] = "blocked"
    elif case == "no_reference":
        host.proposed["features"][1].pop("projections")
    elif case == "not_descendant":
        host.proposed["features"][1]["inputs"] = {}
    elif case == "add":
        host.proposed["features"].append({"id": "extra"})
    elif case == "remove":
        host.proposed["features"].pop()
    elif case == "envelope":
        host.proposed["name"] = "Different part"
    before = host.state.document_json
    assert not host.module.retain(host.context, host.proposed, "source", object(), host.binding)
    assert host.module.current(host.context) is None
    assert host.state.document_json == before and not host.published


def test_second_proposal_and_wrong_token_cannot_replace_pending_work(host):
    proposal = retain(host)
    with pytest.raises(host.error, match="retained"):
        host.module.retain(host.context, host.proposed, "source", object(), host.binding)
    with pytest.raises(host.error, match="expired"):
        host.module.discard(host.context, "wrong-token")
    with pytest.raises(host.error, match="expired"):
        host.module.accept(host.context, "wrong-token", repaired(proposal))
    assert host.module.current(host.context) is proposal
    assert not host.published


@pytest.mark.parametrize(
    "changed", ["document", "owner", "units", "backend", "window", "workspace", "deflection"]
)
def test_changed_binding_is_passively_visible_but_action_retires_stale_proposal(host, changed):
    proposal = retain(host)
    if changed == "document":
        host.state.document_json += " "
    elif changed == "owner":
        host.state.owner_id = "new-owner"
    elif changed == "units":
        host.context.scene.unit_settings.scale = 2
    elif changed == "backend":
        host.context.backend_revision += 1
    elif changed == "window":
        host.context.window = object()
    elif changed == "workspace":
        host.context.workspace = object()
    elif changed == "deflection":
        host.context.deflection = 0.2
    changed_json = host.state.document_json
    host.state.repair_intent_json = "original saved intent, including malformed bytes"
    for _ in range(5):
        assert host.module.current(host.context) is proposal
    assert host.state.last_action_error == ""
    with pytest.raises(host.error, match="expired"):
        host.module.require(host.context, proposal.token)
    assert host.module.current(host.context) is None
    assert "context, units or backend changed" in host.state.last_action_error
    assert host.state.repair_intent_json == "original saved intent, including malformed bytes"
    assert host.state.document_json == changed_json
    assert not host.published


@pytest.mark.parametrize("action", ["accept", "undo", "advance", "discard"])
def test_stale_card_cannot_authorize_any_token_bound_mutation(host, action):
    proposal = retain(host)
    host.state.repair_intent_json = "  {unsupported raw\n"
    host.context.workspace = object()
    assert host.module.current(host.context) is proposal
    with pytest.raises(host.error, match="expired"):
        if action == "accept":
            host.module.accept(host.context, proposal.token, repaired(proposal))
        elif action == "undo":
            host.module.undo_repair(host.context, proposal.token)
        elif action == "advance":
            host.module.staged_edit_store.advance_validated(
                host.context, proposal.token, repaired(proposal), host.response["result"]
            )
        else:
            host.module.discard(host.context, proposal.token)
    assert host.module.current(host.context) is None
    assert host.state.document_json == proposal.base_json
    assert host.state.repair_intent_json == "  {unsupported raw\n"
    assert not host.published


@pytest.mark.parametrize("failure", ["exception", "false"])
def test_unsuccessful_whole_part_repair_keeps_exact_proposal(host, failure):
    proposal = retain(host)
    before = host.state.document_json

    def fail(*args, **kwargs):
        if failure == "exception":
            raise host.error("downstream replay failed")
        return False

    host.doc._commit_candidate_locked = fail
    if failure == "exception":
        with pytest.raises(host.error, match="downstream replay failed"):
            host.module.accept(host.context, proposal.token, repaired(proposal))
    else:
        assert not host.module.accept(host.context, proposal.token, repaired(proposal))
    assert host.module.current(host.context) is proposal
    assert host.state.document_json == before


def test_successful_repair_publishes_detached_candidate_once_and_discards(host):
    proposal = retain(host)
    candidate = repaired(proposal)
    assert host.module.accept(host.context, proposal.token, candidate)
    assert host.module.current(host.context) is None
    assert len(host.published) == 1
    assert host.published[0][0] == candidate and host.published[0][0] is not candidate
    assert json.loads(host.state.document_json) == candidate
    with pytest.raises(host.error, match="expired"):
        host.module.accept(host.context, proposal.token, candidate)
    assert len(host.published) == 1


@pytest.mark.parametrize(
    "change", ["envelope", "delete", "add", "label", "id", "upstream", "unchanged"]
)
def test_repair_cannot_smuggle_unrelated_part_edits(host, change):
    proposal = retain(host)
    candidate = repaired(proposal)
    if change == "envelope":
        candidate["name"] = "Changed"
    elif change == "delete":
        candidate["features"].pop()
    elif change == "add":
        candidate["features"].append({"id": "new"})
    elif change in {"label", "id"}:
        candidate["features"][1][change] = "different"
    elif change == "upstream":
        candidate["features"][0]["sketch"]["r"] = 100
    elif change == "unchanged":
        candidate = proposal.document
    with pytest.raises(host.error, match="Repair"):
        host.module.accept(host.context, proposal.token, candidate)
    assert host.module.current(host.context) is proposal
    assert not host.published


def test_explicit_discard_and_lifecycle_cleanup_never_commit_proposal(host):
    before = host.state.document_json
    proposal = retain(host)
    host.module.discard(host.context, proposal.token)
    assert host.module.current(host.context) is None
    retain(host)
    host.module.cancel_all("Save keeps the accepted model only")
    assert host.module.current(host.context) is None
    assert not host.registered
    assert host.state.document_json == before and not host.published
    assert host.state.last_action_error == "Save keeps the accepted model only"


@pytest.mark.parametrize(
    "change",
    [
        "source",
        "projection_target",
        "remove_projection",
        "remove_point",
        "add_point",
        "reorder_points",
        "remove_line",
        "remove_circle",
        "remove_constraint",
        "reorder_constraints",
        "constraint_kind",
        "constraint_refs",
    ],
)
def test_repair_preserves_external_source_entities_and_dependent_relations(host, change):
    proposal = retain(host)
    candidate = repaired(proposal)
    target = candidate["features"][1]
    sketch = target["sketch"]
    if change == "source":
        target["inputs"]["external"] = "somewhere_else"
    elif change == "projection_target":
        target["projections"][0]["target"] = "different"
    elif change == "remove_projection":
        target["projections"] = []
    elif change == "add_point":
        sketch["points"].append({"id": "new"})
    elif change.startswith("remove_"):
        name = change.removeprefix("remove_") + "s"
        sketch[name].pop()
    elif change.startswith("reorder_"):
        name = change.removeprefix("reorder_")
        sketch[name].reverse()
    elif change == "constraint_kind":
        sketch["constraints"][1]["kind"] = "diameter"
    elif change == "constraint_refs":
        sketch["constraints"][1]["refs"] = ["outline", "reference"]
    with pytest.raises(host.error, match="Repair"):
        host.module.accept(host.context, proposal.token, candidate)
    assert host.module.current(host.context) is proposal
    assert not host.published


def test_repair_cannot_succeed_by_reverting_retained_upstream_sketch(host):
    proposal = retain(host)
    candidate = proposal.document
    candidate["features"][0] = copy.deepcopy(host.base["features"][0])
    with pytest.raises(host.error, match="Repair|failed|downstream"):
        host.module.accept(host.context, proposal.token, candidate)
    assert host.module.current(host.context) is proposal
    assert not host.published


@pytest.mark.parametrize("changed", ["scene", "workspace"])
def test_supervisor_retires_proposal_outside_draw_without_deleting_saved_intent(host, changed):
    proposal = retain(host)
    host.state.repair_intent_json = "  {unsupported raw\n"
    if changed == "scene":
        host.context.window.scene = object()
    else:
        host.context.workspace = object()
    for _ in range(5):
        assert host.module.current(host.context) is proposal
    assert host.module._supervise() is None
    assert host.module.current(host.context) is None
    assert "context changed" in host.state.last_action_error
    assert host.state.repair_intent_json == "  {unsupported raw\n"
    assert not host.published


def test_passive_lookup_is_scene_local_and_does_not_retire_another_scenes_owner(host):
    proposal = retain(host)
    other_scene = types.SimpleNamespace(as_pointer=lambda: 1234)
    other = types.SimpleNamespace(scene=other_scene)
    for _ in range(5):
        assert host.module.current(other) is None
        assert host.module.current(host.context) is proposal
    with pytest.raises(host.error, match="retained"):
        host.module.staged_edit_store.require_no_live_edit(other)
    assert host.module.current(host.context) is proposal
    assert not host.published


def test_explicit_admission_retires_stale_owner_but_saved_intent_still_blocks_edit(host):
    retain(host)
    host.state.repair_intent_json = "  {unsupported raw\n"
    host.context.workspace = object()
    with pytest.raises(host.error, match="Saved unapplied repair intent"):
        host.module.require_none(host.context)
    assert host.module.current(host.context) is None
    assert host.state.repair_intent_json == "  {unsupported raw\n"
    assert "context, units or backend changed" in host.state.last_action_error
    assert not host.published


def test_only_explicit_saved_discard_deletes_raw_after_stale_owner_cleanup(host):
    proposal = retain(host)
    host.state.repair_intent_json = "  {unsupported raw\n"
    with pytest.raises(host.error, match="live proposed edit"):
        host.module.discard_saved(host.context)
    assert host.module.current(host.context) is proposal
    assert host.state.repair_intent_json == "  {unsupported raw\n"
    host.context.workspace = object()
    host.module.discard_saved(host.context)
    assert host.module.current(host.context) is None
    assert host.state.repair_intent_json == ""
    assert not host.published


@pytest.fixture
def redraw(host):
    events = []

    def area(kind, label):
        return types.SimpleNamespace(
            type=kind,
            tag_redraw=lambda: events.append(label),
            regions=[
                types.SimpleNamespace(tag_redraw=lambda: events.append(label + "/UI")),
                types.SimpleNamespace(tag_redraw=lambda: events.append(label + "/WINDOW")),
            ],
        )

    host.context.window.screen = types.SimpleNamespace(
        areas=[area("VIEW_3D", "primary"), area("TEXT_EDITOR", "unrelated")]
    )
    host.context.window_manager.windows.append(
        types.SimpleNamespace(screen=types.SimpleNamespace(areas=[area("VIEW_3D", "secondary")]))
    )
    return events


@pytest.mark.parametrize("end", ["discard", "accept", "cancel_all", "stale", "supervise"])
def test_proposal_transitions_immediately_tag_viewports_and_sidebars(host, redraw, end):
    proposal = retain(host)
    expected = [
        "primary",
        "primary/UI",
        "primary/WINDOW",
        "secondary",
        "secondary/UI",
        "secondary/WINDOW",
    ]
    assert redraw == expected
    redraw.clear()
    assert host.module.current(host.context) is proposal
    assert redraw == []  # Read-only panel draws do not create a redraw loop.
    if end == "discard":
        host.module.discard(host.context, proposal.token)
    elif end == "accept":
        assert host.module.accept(host.context, proposal.token, repaired(proposal))
    elif end == "cancel_all":
        host.module.cancel_all("File save retired the proposal")
    elif end == "stale":
        host.context.deflection += 0.1
        assert host.module.current(host.context) is proposal
        assert not redraw
        with pytest.raises(host.error, match="expired"):
            host.module.require(host.context, proposal.token)
    else:
        host.context.window.scene = object()
        assert host.module._supervise() is None
    assert redraw == expected
    redraw.clear()
    host.module.cancel_all()
    assert redraw == []  # Empty/idempotent cleanup needs no notification.


def test_closed_redraw_area_does_not_block_other_views_or_proposal_cleanup(host, redraw):
    def closed():
        raise ReferenceError("Area was closed")

    host.context.window.screen.areas[0].tag_redraw = closed
    proposal = retain(host)
    assert redraw == ["secondary", "secondary/UI", "secondary/WINDOW"]
    redraw.clear()
    host.module.discard(host.context, proposal.token)
    assert host.module.current(host.context) is None
    assert redraw == ["secondary", "secondary/UI", "secondary/WINDOW"]


def test_unrelated_failure_does_not_join_reference_repair_transaction(host):
    host.response["result"]["features"][-1]["status"] = "failed"
    assert not host.module.retain(host.context, host.proposed, "source", object(), host.binding)
    assert host.module.current(host.context) is None


def test_timer_failure_does_not_leave_orphaned_proposal(host, monkeypatch, redraw):
    def fail(*args, **kwargs):
        raise RuntimeError("timer unavailable")

    monkeypatch.setattr(sys.modules["bpy"].app.timers, "register", fail)
    with pytest.raises(RuntimeError, match="timer unavailable"):
        retain(host)
    assert host.module.current(host.context) is None
    assert redraw == []  # Failed ownership transfer must not announce a proposal.


def test_changed_annotation_layout_blocks_repair_without_overwriting_it(host):
    store = importlib.import_module(host.module.__package__ + ".staged_edit_store")
    host.state.sketch_annotation_json = "original labels"
    assert store.retain_validated(
        host.context,
        host.proposed,
        "source",
        host.response["result"],
        host.binding,
        assert_binding=host.doc._assert_binding,
        annotation_before="original labels",
        annotation_after="proposed labels",
    )
    proposal = host.module.current(host.context)
    host.state.sketch_annotation_json = "externally changed labels"
    with pytest.raises(host.error, match="annotation layout changed"):
        host.module.accept(host.context, proposal.token, repaired(proposal))
    assert host.state.sketch_annotation_json == "externally changed labels"
    assert host.module.current(host.context) is proposal
    assert not host.published


def test_independent_blocked_consumer_does_not_join_reference_repair(host):
    host.proposed["features"][-1]["inputs"] = {"profile": "source"}
    assert not host.module.retain(host.context, host.proposed, "source", object(), host.binding)
    assert host.module.current(host.context) is None


def two_failures(host):
    target = copy.deepcopy(host.proposed["features"][1])
    target["id"] = "second"
    host.proposed["features"].append(target)
    host.base["features"].append(copy.deepcopy(target))
    host.state.document_json = json.dumps(host.base)
    host.binding["document_json"] = host.state.document_json
    host.response["result"]["features"].append(
        {
            "id": "second",
            "status": "failed",
            "error": {"code": "invalid_sketch_projection", "message": "Missing source"},
        }
    )
    return retain(host)


def test_partial_repair_undo_rotates_tokens_and_keeps_base_and_annotations(host, redraw):
    proposal = two_failures(host)
    candidate = repaired(proposal)
    host.response["result"]["features"][1]["status"] = "ok"
    host.response["result"]["features"][2]["status"] = "ok"
    host.doc._commit_candidate_locked = lambda *a, validate_result, **k: validate_result(None, None)
    redraw.clear()
    assert host.module.accept(host.context, proposal.token, candidate) is None
    partial = host.module.current(host.context)
    assert partial.token != proposal.token and partial.document == candidate
    assert partial.base_json == proposal.base_json and partial.binding == proposal.binding
    assert partial.repairs == ((proposal.candidate_json, proposal.failed_json),)
    assert [r["id"] for r in partial.failures] == ["second"]
    assert redraw and not host.published
    assert host.state.document_json == proposal.base_json
    with pytest.raises(host.error, match="expired"):
        host.module.accept(host.context, proposal.token, candidate)
    host.module.undo_repair(host.context, partial.token)
    undone = host.module.current(host.context)
    assert undone.document == proposal.document and undone.failures == proposal.failures
    assert undone.token not in {proposal.token, partial.token} and not undone.repairs
    with pytest.raises(host.error, match="no proposal repair"):
        host.module.undo_repair(host.context, undone.token)


@pytest.mark.parametrize("code", ["kernel_error", "sketch_constraint_conflict", "unknown", None])
def test_partial_repair_rejects_non_reference_remaining_failure(host, code):
    proposal = two_failures(host)
    host.response["result"]["features"][1]["status"] = "ok"
    host.response["result"]["features"][2]["status"] = "ok"
    host.response["result"]["features"][-1]["error"]["code"] = code

    def commit(*args, validate_result, **kwargs):
        validate_result(None, None)
        raise host.error("Full replay failed")

    host.doc._commit_candidate_locked = commit
    with pytest.raises(host.error, match="Full replay failed"):
        host.module.accept(host.context, proposal.token, repaired(proposal))
    assert host.module.current(host.context) is proposal
    assert not host.published


def test_partial_repair_and_proposal_undo_preserve_deferred_annotation_intent(host):
    original = two_failures(host)
    host.module.discard(host.context)
    host.state.sketch_annotation_json = "accepted annotations"
    store = importlib.import_module(host.module.__package__ + ".staged_edit_store")
    assert store.retain_validated(
        host.context,
        original.document,
        "source",
        host.response["result"],
        host.binding,
        assert_binding=host.doc._assert_binding,
        annotation_before="accepted annotations",
        annotation_after="deferred annotations",
    )
    proposal = host.module.current(host.context)
    host.response["result"]["features"][1]["status"] = "ok"
    host.response["result"]["features"][2]["status"] = "ok"
    host.doc._commit_candidate_locked = lambda *a, validate_result, **k: validate_result(None, None)
    assert host.module.accept(host.context, proposal.token, repaired(proposal)) is None
    partial = host.module.current(host.context)
    assert partial.annotation_before == "accepted annotations"
    assert partial.annotation_after == "deferred annotations"
    host.module.undo_repair(host.context, partial.token)
    undone = host.module.current(host.context)
    assert undone.annotation_before == proposal.annotation_before
    assert undone.annotation_after == proposal.annotation_after
    assert host.state.sketch_annotation_json == "accepted annotations"


def test_proposal_repair_cannot_switch_projection_port(host):
    before = copy.deepcopy(host.base["features"][1])
    before["inputs"]["external_2"] = "second_source"
    after = copy.deepcopy(before)
    after["projections"][0]["input"] = "external_2"
    with pytest.raises(ValueError, match="bound source port"):
        host.module.repair_scope.repair_target(before, after)


def test_successful_repair_checkpoint_and_save_are_not_errors(host, monkeypatch):
    proposal = retain(host)
    host.state.repair_intent_json = ""
    host.state.last_action_error = "Obsolete failed edit"
    store = host.module.staged_edit_store
    monkeypatch.setattr(store.repair_intent, "encode", lambda proposal: "checkpoint intent")
    store.before_save()
    assert host.state.repair_intent_json == "checkpoint intent"
    assert host.state.last_action_error == ""
    assert host.module.current(host.context) is proposal
    store.after_save(succeeded=True)
    assert host.state.last_action_error == ""
    assert host.module.current(host.context) is None
    assert not host.published


def test_failed_checkpoint_warning_survives_successful_blend_save(host, monkeypatch):
    proposal = retain(host)
    host.state.repair_intent_json = ""
    store = host.module.staged_edit_store

    def fail(proposal):
        raise ValueError("injected checkpoint failure")

    monkeypatch.setattr(store.repair_intent, "encode", fail)
    store.before_save()
    warning = host.state.last_action_error
    assert "checkpoint failed" in warning.lower()
    assert "injected checkpoint failure" in warning
    store.after_save(succeeded=True)
    assert host.state.last_action_error == warning
    assert host.module.current(host.context) is proposal
    assert not host.state.repair_intent_json


def test_failed_save_warning_and_dormant_resume_error_stay_visible(host, monkeypatch):
    proposal = retain(host)
    host.state.repair_intent_json = ""
    store = host.module.staged_edit_store
    monkeypatch.setattr(store.repair_intent, "encode", lambda proposal: "checkpoint intent")
    store.before_save()
    store.after_save(succeeded=False)
    assert "Blender Save failed" in host.state.last_action_error
    assert host.module.current(host.context) is proposal
    host.module.cancel_all()
    host.state.last_action_error = "Cannot resume saved repair: unsupported version"
    store.before_save()
    store.after_save(succeeded=True)
    assert host.state.last_action_error == "Cannot resume saved repair: unsupported version"
    assert host.state.repair_intent_json == "checkpoint intent"
