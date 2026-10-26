"""End-face proposal scope and lifecycle, with no fabricated native authority.

Only Blender storage and the replay/publication boundary are controlled. The
real service, scope, version-1 codec and proposal store run unchanged. Native
shape behavior is covered separately by the end-face integration regressions.
"""

import copy
import importlib
import json
import sys
import types
from contextlib import nullcontext
from pathlib import Path

import pytest

ADDON = Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender"


def feature(document, identifier):
    return next(row for row in document["features"] if row["id"] == identifier)


def document():
    return {
        "schema_version": 1,
        "id": "end_face_repair",
        "name": "Two explicit end-face consumers",
        "units": "mm",
        "parameters": {"gap": 2},
        "active_feature": "downstream",
        "features": [
            {
                "id": "target_profile",
                "kind": "sketch_rectangle",
                "params": {"width": 20, "height": 20, "z": 10},
            },
            {
                "id": "target",
                "kind": "extrude",
                "inputs": {"profile": "target_profile"},
                "params": {"length": 5},
            },
            {
                "id": "replacement",
                "kind": "extrude",
                "inputs": {"profile": "target_profile"},
                "params": {"length": 8},
            },
            {"id": "profile", "kind": "sketch_circle", "params": {"radius": 2}},
            {
                "id": "pad",
                "kind": "extrude_to_face",
                "label": "First exact stop",
                "inputs": {"profile": "profile", "target": "target"},
                "params": {"direction": 1, "offset": "gap / 2"},
                "end_face": "target/face/cap.start",
            },
            {
                "id": "second",
                "kind": "extrude_to_face",
                "inputs": {"profile": "profile", "target": "target"},
                "params": {"direction": 1.0, "offset": 0.25},
                "end_face": "target/face/cap.start",
            },
            {
                "id": "downstream",
                "kind": "cut",
                "inputs": {"base": "pad", "tool": "second"},
                "params": {},
            },
        ],
    }


def failure_result(candidate, *, repaired=(), message="End face no longer resolves"):
    rows = []
    for item in candidate["features"]:
        row = {"id": item["id"], "status": "ok"}
        if item["id"] in {"pad", "second"} - set(repaired):
            row.update(
                status="failed",
                error={"code": "invalid_extrusion_end_face", "message": message},
            )
        elif item["id"] == "downstream" and set(repaired) != {"pad", "second"}:
            row["status"] = "blocked"
        rows.append(row)
    return {
        "status": "ok" if all(r["status"] == "ok" for r in rows) else "failed",
        "features": rows,
    }


def result_row(result, identifier):
    return next(row for row in result["features"] if row["id"] == identifier)


def repaired(candidate, identifier="pad", target="replacement"):
    candidate = copy.deepcopy(candidate)
    item = feature(candidate, identifier)
    item["inputs"]["target"] = target
    item["end_face"] = target + "/face/cap.end"
    return candidate


@pytest.fixture
def host(monkeypatch):
    name = "mcad_staged_end_face_tests"
    package = types.ModuleType(name)
    package.__path__ = [str(ADDON)]
    monkeypatch.setitem(sys.modules, name, package)

    def stub(suffix, **attributes):
        module = types.ModuleType(name + "." + suffix)
        module.__dict__.update(attributes)
        monkeypatch.setitem(sys.modules, module.__name__, module)
        return module

    error = type("BridgeError", (RuntimeError,), {})
    stub("bridge", BridgeError=error)
    doc = stub("document_state")
    stub("backend_runtime", configuration=lambda context: (None, context.deflection))
    stub("workspace", active_draft=lambda: None)
    base = document()
    proposed = copy.deepcopy(base)
    feature(proposed, "target")["params"]["length"] = 6
    state = types.SimpleNamespace(
        document_json=json.dumps(base, indent=2),
        owner_id="owner",
        document_path="",
        repair_intent_json="",
        sketch_annotation_json="",
        last_action_error="",
    )
    scene = types.SimpleNamespace(
        mechanical_cad=state, unit_settings=types.SimpleNamespace(scale=0.001)
    )
    scene.as_pointer = lambda: id(scene)
    window = types.SimpleNamespace(scene=scene)
    context = types.SimpleNamespace(scene=scene, window=window, backend_revision=1, deflection=0.1)
    context.window_manager = types.SimpleNamespace(windows=[window])
    context.temp_override = lambda **kwargs: nullcontext()
    registered = set()
    bpy = types.ModuleType("bpy")
    bpy.context = context
    bpy.app = types.SimpleNamespace(
        timers=types.SimpleNamespace(
            is_registered=lambda callback: callback in registered,
            register=lambda callback, **kwargs: registered.add(callback),
            unregister=lambda callback: registered.remove(callback),
        )
    )
    monkeypatch.setitem(sys.modules, "bpy", bpy)

    def capture(current):
        return {
            "scene": current.scene,
            "window": current.window,
            "document_json": state.document_json,
            "owner_id": state.owner_id,
            "scale": scene.unit_settings.scale,
            "backend_revision": current.backend_revision,
            "deflection": current.deflection,
        }

    def assert_binding(current, binding):
        if capture(current) != binding:
            raise error("stale native binding")

    response = {"result": failure_result(proposed)}
    published, replays, cancelled = [], [], []
    replay_results = {}

    def replay(context, candidate, *, binding):
        assert_binding(context, binding)
        replays.append(copy.deepcopy(candidate))
        result = replay_results[json.dumps(candidate, sort_keys=True)]
        if isinstance(result, Exception):
            raise result
        return types.SimpleNamespace(
            result=copy.deepcopy(result),
            publication=types.SimpleNamespace(cancel=lambda: cancelled.append(True)),
        )

    def commit(context, candidate, path, *, validate_result, staged_token):
        validate_result(None, None)
        if response["result"]["status"] != "ok":
            raise error("Full replay failed")
        published.append((copy.deepcopy(candidate), path, staged_token))
        state.document_json = json.dumps(candidate)
        return True

    doc._assert_binding = assert_binding
    doc._capture_binding = capture
    doc._run_sidecar = replay
    doc._evidence_projection = lambda c, d, e, b: (
        {"result": e.result} if e is not None and hasattr(e, "result") else response
    )
    doc.current_part_result = lambda context: {"status": "ok"}
    doc.require_no_sketch_draft = lambda context: None
    doc.replay_guard = lambda context: nullcontext()
    doc._commit_candidate_locked = commit
    module = importlib.import_module(name + ".staged_edit")
    result = types.SimpleNamespace(
        module=module,
        store=module.staged_edit_store,
        scope=module.repair_scope,
        codec=module.repair_intent,
        doc=doc,
        context=context,
        base=base,
        proposed=proposed,
        state=state,
        binding=capture(context),
        response=response,
        error=error,
        published=published,
        replays=replays,
        replay_results=replay_results,
        cancelled=cancelled,
    )
    yield result
    module.cancel_all()
    for module_name in tuple(sys.modules):
        if module_name.startswith(name + "."):
            sys.modules.pop(module_name, None)


def retain(host):
    assert host.module.retain(host.context, host.proposed, "target", object(), host.binding)
    return host.module.current(host.context)


def partial(host):
    proposal = retain(host)
    candidate = repaired(proposal.document)
    host.response["result"] = failure_result(candidate, repaired={"pad"})
    assert host.module.accept(host.context, proposal.token, candidate) is None
    return proposal, host.module.current(host.context)


def save(host):
    host.module.before_save()
    raw = host.state.repair_intent_json
    assert raw
    host.module.after_save(succeeded=True)
    host.module.cancel_all()  # Reopening retires all process-only ownership.
    assert host.module.current(host.context) is None
    assert host.state.repair_intent_json == raw
    return raw


def prepare_resume(host, raw):
    value = host.codec.decode(raw)
    host.replay_results[json.dumps(host.base, sort_keys=True)] = failure_result(
        host.base, repaired={"pad", "second"}
    )
    for index, text in enumerate(value["states"]):
        candidate = json.loads(text)
        host.replay_results[json.dumps(candidate, sort_keys=True)] = failure_result(
            candidate,
            repaired={"pad"} if index else (),
            message=f"Fresh replay {index + 1}",
        )
    return value


def test_typed_end_face_failure_is_retained_without_accepting_geometry(host):
    before = host.state.document_json
    proposal = retain(host)
    assert proposal.feature_id == "target"
    assert {row["id"] for row in proposal.failures} == {"pad", "second"}
    assert proposal.document == host.proposed
    assert proposal.base_json == before == host.state.document_json
    assert not host.published
    host.proposed["features"][1]["params"]["length"] = 999
    assert feature(proposal.document, "target")["params"]["length"] == 6


@pytest.mark.parametrize(
    "case",
    [
        "kernel_error",
        "invalid_sketch_support",
        "invalid_sketch_projection",
        "unknown",
        "no_code",
        "upstream_failed",
        "blocked_ancestor",
        "unrelated_failure",
        "not_descendant",
        "wrong_kind",
    ],
)
def test_admission_rejects_non_end_face_and_unrelated_failures(host, case):
    row = result_row(host.response["result"], "pad")
    if case == "no_code":
        row.pop("error")
    elif case == "upstream_failed":
        result_row(host.response["result"], "target")["status"] = "failed"
    elif case == "blocked_ancestor":
        result_row(host.response["result"], "target_profile")["status"] = "blocked"
    elif case == "unrelated_failure":
        result_row(host.response["result"], "replacement").update(
            status="failed", error={"code": "kernel_error"}
        )
    elif case == "not_descendant":
        feature(host.proposed, "pad")["inputs"]["target"] = "replacement"
    elif case == "wrong_kind":
        feature(host.proposed, "pad")["kind"] = "extrude"
    else:
        row["error"]["code"] = case
    before = host.state.document_json
    assert not host.module.retain(host.context, host.proposed, "target", object(), host.binding)
    assert host.module.current(host.context) is None
    assert host.state.document_json == before and not host.published


@pytest.mark.parametrize("target", ["target", "replacement"])
def test_scope_allows_only_end_face_and_earlier_solid_target(host, target):
    candidate = repaired(host.proposed, target=target)
    assert host.scope.validate_transition(host.proposed, candidate, "target", {"pad"}) == (
        "pad",
        None,
    )
    actual = feature(candidate, "pad")
    original = feature(host.proposed, "pad")
    assert actual["inputs"]["profile"] == original["inputs"]["profile"]
    assert actual["params"] == original["params"]
    assert actual["label"] == original["label"]


@pytest.mark.parametrize(
    "change",
    [
        "profile",
        "direction",
        "direction_type",
        "offset",
        "add_param",
        "label",
        "kind",
        "id",
        "extra_input",
        "upstream",
        "second_repair",
        "envelope",
        "remove_feature",
        "reorder",
        "not_failed",
        "self",
        "downstream",
        "later",
        "missing",
        "non_solid",
        "empty_face",
        "snapshot_face",
        "pending_face",
    ],
)
def test_scope_rejects_every_non_binding_or_unsafe_target_change(host, change):
    candidate = repaired(host.proposed)
    item = feature(candidate, "pad")
    failed = {"pad", "second"}
    if change == "profile":
        item["inputs"]["profile"] = "target_profile"
    elif change == "direction":
        item["params"]["direction"] = -1
    elif change == "direction_type":
        item["params"]["direction"] = 1.0
    elif change == "offset":
        item["params"]["offset"] = 1
    elif change == "add_param":
        item["params"]["length"] = 10
    elif change in {"label", "kind", "id"}:
        item[change] = "changed"
    elif change == "extra_input":
        item["inputs"]["base"] = "target"
    elif change == "upstream":
        feature(candidate, "target")["params"]["length"] = 5
    elif change == "second_repair":
        candidate = repaired(candidate, "second")
    elif change == "envelope":
        candidate["parameters"]["gap"] = 4
    elif change == "remove_feature":
        candidate["features"].pop()
    elif change == "reorder":
        candidate["features"][0:2] = reversed(candidate["features"][0:2])
    elif change == "not_failed":
        failed = {"second"}
    elif change in {"self", "downstream", "later", "missing", "non_solid"}:
        item["inputs"]["target"] = {
            "self": "pad",
            "downstream": "downstream",
            "later": "second",
            "missing": "absent",
            "non_solid": "profile",
        }[change]
        item["end_face"] = item["inputs"]["target"] + "/face/cap.end"
    else:
        item["end_face"] = {
            "empty_face": "",
            "snapshot_face": "snapshot:replacement:face:0",
            "pending_face": "pending:face",
        }[change]
    with pytest.raises(ValueError):
        host.scope.validate_transition(host.proposed, candidate, "target", failed)


@pytest.mark.parametrize("status", ["failed", "blocked", "missing"])
@pytest.mark.parametrize("target", [None, "pretend_projection_target"])
def test_live_binding_requires_successful_extrusion_not_sketch_shortcuts(
    host, monkeypatch, status, target
):
    monkeypatch.setattr(
        host.module,
        "_binding_probe",
        lambda *args: pytest.fail("Extrusions cannot use sketch probes"),
    )
    row = {
        "id": "pad",
        "status": status,
        "support_plane": {"origin": [0, 0, 5]},
        "error": {"code": "invalid_sketch_projection"},
    }
    rows = {} if status == "missing" else {"pad": row}
    assert not host.module._binding_succeeds(host.context, host.proposed, "pad", target, rows)
    row["status"] = "ok"
    assert host.module._binding_succeeds(host.context, host.proposed, "pad", target, {"pad": row})


def test_partial_repair_and_undo_rotate_tokens_without_publishing(host):
    original, kept = partial(host)
    assert kept.token != original.token
    assert kept.document == repaired(original.document)
    assert kept.repairs == ((original.candidate_json, original.failed_json),)
    assert [row["id"] for row in kept.failures] == ["second"]
    assert host.state.document_json == original.base_json and not host.published
    with pytest.raises(host.error, match="expired"):
        host.module.accept(host.context, original.token, repaired(original.document))
    with pytest.raises(host.error, match="expired"):
        host.module.discard(host.context, original.token)
    host.module.undo_repair(host.context, kept.token)
    undone = host.module.current(host.context)
    assert undone.document == original.document and undone.failures == original.failures
    assert undone.token not in {original.token, kept.token} and not undone.repairs
    with pytest.raises(host.error, match="expired"):
        host.module.accept(host.context, kept.token, repaired(kept.document, "second"))
    assert host.state.document_json == original.base_json and not host.published


def test_final_complete_repair_publishes_both_bindings_in_one_transaction(host):
    original, kept = partial(host)
    candidate = repaired(kept.document, "second")
    host.response["result"] = failure_result(candidate, repaired={"pad", "second"})
    assert host.module.accept(host.context, kept.token, candidate)
    assert len(host.published) == 1
    assert host.published[0][0] == candidate
    assert json.loads(host.state.document_json) == candidate
    assert host.module.current(host.context) is None
    assert feature(candidate, "target")["params"]["length"] == 6
    assert feature(original.document, "pad")["params"] == feature(candidate, "pad")["params"]


@pytest.mark.parametrize("failure", ["still_failed", "blocked", "kernel_error", "exception"])
def test_unsuccessful_binding_or_unexpected_kernel_failure_keeps_exact_revision(host, failure):
    proposal = retain(host)
    candidate = repaired(proposal.document)
    host.response["result"] = failure_result(candidate, repaired={"pad"})
    if failure == "still_failed":
        host.response["result"] = failure_result(candidate)
    elif failure == "blocked":
        result_row(host.response["result"], "pad")["status"] = "blocked"
    elif failure == "kernel_error":
        result_row(host.response["result"], "second")["error"]["code"] = "kernel_error"
    else:

        def fail(*args, **kwargs):
            raise RuntimeError("Unexpected native failure")

        host.doc._commit_candidate_locked = fail
    with pytest.raises((host.error, RuntimeError)):
        host.module.accept(host.context, proposal.token, candidate)
    assert host.module.current(host.context) is proposal
    assert host.state.document_json == proposal.base_json and not host.published


def test_version_one_codec_keeps_exact_saved_history_without_native_evidence(host):
    original, kept = partial(host)
    raw = host.codec.encode(kept)
    value = host.codec.decode(raw)
    assert value["schema_version"] == 1
    assert value["base_json"] == original.base_json
    assert value["states"] == [original.candidate_json, kept.candidate_json]
    assert set(value) == host.codec._FIELDS
    for forbidden in (original.token, kept.token, "failed_json", "support_plane", "publication"):
        assert forbidden not in raw
    assert host.codec.decode(json.dumps(value)) == value


@pytest.mark.parametrize("change", ["profile", "direction", "offset", "second_binding", "new_kind"])
def test_saved_end_face_transition_cannot_smuggle_other_changes(host, change):
    _, kept = partial(host)
    value = json.loads(host.codec.encode(kept))
    candidate = json.loads(value["states"][-1])
    item = feature(candidate, "pad")
    if change == "profile":
        item["inputs"]["profile"] = "target_profile"
    elif change == "direction":
        item["params"]["direction"] = -1
    elif change == "offset":
        item["params"]["offset"] = "gap"
    elif change == "second_binding":
        candidate = repaired(candidate, "second")
    else:
        item["kind"] = "extrude"
    value["states"][-1] = json.dumps(candidate)
    with pytest.raises(ValueError):
        host.codec.decode(json.dumps(value))


def test_save_reopen_replays_exact_base_and_each_state_with_new_diagnostics(host):
    original, kept = partial(host)
    raw = save(host)
    value = prepare_resume(host, raw)
    host.context.backend_revision = 2  # Old native authority is intentionally gone.
    resumed = host.module.resume(host.context)
    assert host.replays == [host.base] + [json.loads(text) for text in value["states"]]
    assert len(host.cancelled) == 3  # No projection probe was requested.
    assert resumed.token not in {original.token, kept.token}
    assert resumed.document == kept.document
    assert resumed.base_json == original.base_json == host.state.document_json
    assert resumed.binding["backend_revision"] == 2
    assert resumed.failures[0]["error"]["message"] == "Fresh replay 2"
    assert "Fresh replay 1" in resumed.repairs[0][1]
    assert not host.state.repair_intent_json and not host.published
    host.module.undo_repair(host.context, resumed.token)
    undone = host.module.current(host.context)
    assert undone.candidate_json == original.candidate_json
    assert undone.failures[0]["error"]["message"] == "Fresh replay 1"


@pytest.mark.parametrize(
    "failure", ["base", "former_success", "kernel_error", "repaired_failed", "exception"]
)
def test_resume_failure_retains_exact_dormant_bytes_without_owner_or_publication(host, failure):
    _, kept = partial(host)
    raw = save(host)
    value = prepare_resume(host, raw)
    key = json.dumps(json.loads(value["states"][-1]), sort_keys=True)
    if failure == "base":
        host.replay_results[json.dumps(host.base, sort_keys=True)]["status"] = "failed"
    elif failure == "former_success":
        host.replay_results[key] = failure_result(kept.document, repaired={"pad", "second"})
    elif failure == "kernel_error":
        result_row(host.replay_results[key], "second")["error"]["code"] = "kernel_error"
    elif failure == "repaired_failed":
        host.replay_results[key] = failure_result(kept.document)
    else:
        host.replay_results[key] = RuntimeError("Unexpected native failure during Resume")
    with pytest.raises((host.error, RuntimeError)):
        host.module.resume(host.context)
    assert host.state.repair_intent_json == raw
    assert host.module.current(host.context) is None
    assert host.state.document_json == kept.base_json and not host.published


def test_resume_cannot_treat_extrusion_as_resolved_sketch_support(host, monkeypatch):
    _, kept = partial(host)
    raw = save(host)
    value = prepare_resume(host, raw)
    result = host.replay_results[json.dumps(json.loads(value["states"][-1]), sort_keys=True)]
    result_row(result, "pad").update(
        status="failed",
        support_plane={"origin": [0, 0, 5]},
        error={"code": "invalid_sketch_projection"},
    )
    # Isolate the selected-binding gate; the admission classifier is separately
    # tested above and must not be the only protection against sketch shortcuts.
    monkeypatch.setattr(host.store, "repairable_failures", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        host.module, "_binding_probe", lambda *args: pytest.fail("No extrusion sketch probe")
    )
    with pytest.raises(host.error, match="transition"):
        host.module.resume(host.context)
    assert host.state.repair_intent_json == raw
    assert host.state.document_json == kept.base_json and not host.published
    assert host.module.current(host.context) is None


def test_cancel_resume_keeps_dormant_intent_and_can_restart_or_discard(host):
    _, kept = partial(host)
    raw = save(host)
    prepare_resume(host, raw)
    plan = host.module.ResumeValidation(host.context)
    plan.advance(host.context, failure_result(host.base, repaired={"pad", "second"}))
    assert plan.completed_requests == 1 and not plan.complete
    plan.retire()
    plan.retire()
    with pytest.raises(host.error, match="retired"):
        plan.install(host.context)
    assert host.state.repair_intent_json == raw and not host.published
    resumed = host.module.resume(host.context)
    host.module.before_save()
    checkpoint = host.state.repair_intent_json
    assert checkpoint
    # Cancelling a review does not own store retirement. Releasing its read-only
    # evidence leaves this same live token and the independently saved checkpoint.
    assert host.module.require(host.context, resumed.token) is resumed
    host.module.discard(host.context, resumed.token)
    assert not host.state.repair_intent_json
    assert host.module.current(host.context) is None
    assert host.state.document_json == kept.base_json and not host.published
    host.state.repair_intent_json = raw
    host.module.discard_saved(host.context)
    assert not host.state.repair_intent_json
    assert host.state.document_json == kept.base_json


def catalog_result(candidate):
    result = failure_result(candidate)
    result_row(result, "profile").update(output={"kind": "profile"}, resolved_params={"z": 0})
    result_row(result, "pad")["resolved_params"] = {"direction": 1, "offset": 1}
    for identifier, height in (("target", 10), ("replacement", 20)):
        result_row(result, identifier).update(
            output={"kind": "solid"},
            topology=[
                {
                    "id": "ancestor/face/cap.end",
                    "role": "cap.end",
                    "provenance": {"semantic_status": "stable"},
                    "signature": {
                        "surface": "plane",
                        "normal": [0, 0, 1],
                        "centroid": [0, 0, height],
                    },
                }
            ],
        )
    return result


def helper(host):
    return importlib.import_module(host.module.__package__ + ".end_face_repair")


def test_helper_targets_are_earlier_solids_and_exclude_reordered_descendants(host):
    api = helper(host)
    assert api.eligible_target_ids(host.proposed, "pad") == {"target", "replacement"}
    candidate = copy.deepcopy(host.proposed)
    item = feature(candidate, "replacement")
    item["kind"] = "transform"
    item["inputs"] = {"solid": "downstream"}
    # Dependency closure, not apparent history position, rules out this target.
    assert api.eligible_target_ids(candidate, "pad") == {"target"}
    unsafe = repaired(candidate)
    with pytest.raises(ValueError, match="dependency-safe"):
        host.scope.validate_transition(candidate, unsafe, "target", {"pad"})
    for identifier in ("profile", "absent"):
        with pytest.raises(ValueError):
            api.terminated_feature(candidate, identifier)


def test_helper_qualifies_face_by_exact_target_and_never_mutates_other_intent(host):
    api = helper(host)
    before = copy.deepcopy(host.proposed)
    result = catalog_result(host.proposed)
    choices = api.end_face_candidates(host.proposed, "pad", result)
    assert choices == [
        {
            "target": "target",
            "face": "ancestor/face/cap.end",
            "role": "cap.end",
            "reach": 10,
            "length": 11,
        },
        {
            "target": "replacement",
            "face": "ancestor/face/cap.end",
            "role": "cap.end",
            "reach": 20,
            "length": 21,
        },
    ]
    candidate = api.replace_end_face(
        host.proposed, "pad", "replacement", "ancestor/face/cap.end", result
    )
    item = feature(candidate, "pad")
    assert item["inputs"] == {"profile": "profile", "target": "replacement"}
    assert item["params"] == {"direction": 1, "offset": "gap / 2"}
    assert type(item["params"]["direction"]) is int
    assert host.proposed == before
    item["inputs"]["target"] = "target"
    item["end_face"] = "target/face/cap.start"
    assert candidate == before
    result_row(result, "replacement")["topology"] = []
    with pytest.raises(ValueError):
        api.replace_end_face(host.proposed, "pad", "replacement", "ancestor/face/cap.end", result)
    assert host.proposed == before


@pytest.mark.parametrize(
    "case",
    [
        "split",
        "curved",
        "nonparallel",
        "behind",
        "zero_reach",
        "duplicate",
        "failed",
        "profile_output",
    ],
)
def test_catalog_omits_unproven_or_incompatible_faces(host, case):
    api = helper(host)
    result = catalog_result(host.proposed)
    row = result_row(result, "replacement")
    face = row["topology"][0]
    if case == "split":
        face["provenance"]["semantic_status"] = "split"
    elif case == "curved":
        face["signature"]["surface"] = "cylinder"
    elif case == "nonparallel":
        face["signature"]["normal"] = [1, 0, 0]
    elif case in {"behind", "zero_reach"}:
        face["signature"]["centroid"][2] = -10 if case == "behind" else 0
    elif case == "duplicate":
        row["topology"].append(copy.deepcopy(face))
    elif case == "failed":
        row["status"] = "failed"
    else:
        row["output"]["kind"] = "profile"
    assert [
        choice["target"] for choice in api.end_face_candidates(host.proposed, "pad", result)
    ] == ["target"]
    with pytest.raises(ValueError):
        api.replace_end_face(host.proposed, "pad", "replacement", face["id"], result)


@pytest.mark.parametrize(
    "direction,offset,targets",
    [(1, 0, {"target", "replacement"}), (-1, 0, set()), (1, -10, {"replacement"}), (1, -20, set())],
)
def test_catalog_preserves_saved_travel_direction_and_signed_offset(
    host, direction, offset, targets
):
    result = catalog_result(host.proposed)
    result_row(result, "pad")["resolved_params"] = {"direction": direction, "offset": offset}
    before = copy.deepcopy(host.proposed)
    assert {
        choice["target"]
        for choice in helper(host).end_face_candidates(host.proposed, "pad", result)
    } == targets
    assert host.proposed == before


@pytest.mark.parametrize(
    "case",
    [
        "profile_failed",
        "profile_unavailable",
        "missing_direction",
        "bool_direction",
        "unresolved_offset",
    ],
)
def test_catalog_requires_fresh_profile_and_resolved_parameter_values(host, case):
    result = catalog_result(host.proposed)
    profile = result_row(result, "profile")
    params = result_row(result, "pad")["resolved_params"]
    if case == "profile_failed":
        profile["status"] = "failed"
    elif case == "profile_unavailable":
        profile["output"] = {"kind": "sketch", "profile": {"state": "unavailable"}}
    elif case == "missing_direction":
        params.pop("direction")
    elif case == "bool_direction":
        params["direction"] = True
    else:
        params["offset"] = "gap / 2"
    with pytest.raises(ValueError):
        helper(host).end_face_candidates(host.proposed, "pad", result)


def test_legacy_projection_states_keep_the_same_version_one_codec_meaning(host, monkeypatch):
    import hashlib

    monkeypatch.syspath_prepend(str(ADDON.parents[1] / "tests"))
    from staged_edit_cases import multiple_projection_case

    base, proposed = multiple_projection_case()
    updated = copy.deepcopy(proposed)
    feature(updated, "target")["projections"][0]["source"] = "replacement_ring"
    base_json = json.dumps(base, indent=2)
    proposal = types.SimpleNamespace(
        base_json=base_json,
        base_hash=hashlib.sha256(base_json.encode()).hexdigest(),
        binding={"owner_id": "owner", "scale": 0.001},
        feature_id="source",
        candidate_json=json.dumps(updated),
        repairs=((json.dumps(proposed), "untrusted old diagnostic"),),
        annotation_before=None,
        annotation_after=None,
    )
    value = host.codec.decode(host.codec.encode(proposal))
    assert value["schema_version"] == 1 and value["base_json"] == base_json
    assert value["states"] == [json.dumps(proposed), json.dumps(updated)]
    assert host.scope.validate_transition(proposed, updated, "source", {"target"}) == (
        "target",
        "reference",
    )


def _mixed_branch(host):
    sketch = {
        "id": "attached",
        "kind": "sketch_constrained",
        "params": {},
        "inputs": {"support": "pad"},
        "support_face": "pad/face/cap.end",
        "sketch": {
            "schema_version": 2,
            "id": "geometry",
            "units": "mm",
            "plane": {"id": "local", "origin": [0, 0, 0], "quaternion": [1, 0, 0, 0]},
            "points": [{"id": "center", "u": 0, "v": 0}],
            "lines": [],
            "circles": [{"id": "circle", "center": "center", "radius": 1}],
            "constraints": [],
        },
    }
    for candidate in (host.base, host.proposed):
        candidate["schema_version"] = 2
        candidate["features"].append(copy.deepcopy(sketch))
    host.state.document_json = json.dumps(host.base, indent=2)
    host.binding = host.doc._capture_binding(host.context)
    host.response["result"] = failure_result(host.proposed)
    result_row(host.response["result"], "attached")["status"] = "blocked"


def test_retarget_then_new_support_failure_keeps_initial_branch_through_save_resume_undo(host):
    _mixed_branch(host)
    original = retain(host)
    first = repaired(original.document)
    host.response["result"] = failure_result(first, repaired={"pad"})
    result_row(host.response["result"], "attached").update(
        status="failed",
        error={"code": "invalid_sketch_support", "message": "Newly exposed strict support failure"},
    )
    assert not host.store.repairable_failures(first, "target", host.response["result"])
    assert host.module.accept(host.context, original.token, first) is None
    after_end = host.module.current(host.context)
    second = copy.deepcopy(first)
    feature(second, "attached")["inputs"]["support"] = "replacement"
    feature(second, "attached")["support_face"] = "replacement/face/cap.end"
    host.response["result"] = failure_result(second, repaired={"pad"})
    assert host.module.accept(host.context, after_end.token, second) is None
    after_support = host.module.current(host.context)
    assert len(after_support.repairs) == 2 and not host.published
    raw = save(host)
    saved = host.codec.decode(raw)
    assert saved["states"] == [
        original.candidate_json,
        after_end.candidate_json,
        after_support.candidate_json,
    ]
    base_result = failure_result(host.base, repaired={"pad", "second"})
    initial_result = failure_result(original.document)
    result_row(initial_result, "attached")["status"] = "blocked"
    first_result = failure_result(first, repaired={"pad"})
    result_row(first_result, "attached").update(
        status="failed", error={"code": "invalid_sketch_support"}
    )
    for candidate, result in (
        (host.base, base_result),
        (original.document, initial_result),
        (first, first_result),
        (second, failure_result(second, repaired={"pad"})),
    ):
        host.replay_results[json.dumps(candidate, sort_keys=True)] = result
    resumed = host.module.resume(host.context)
    assert len(resumed.repairs) == 2 and resumed.document == second
    assert host.replays == [host.base, original.document, first, second]
    host.module.undo_repair(host.context, resumed.token)
    undone = host.module.current(host.context)
    assert undone.document == first and len(undone.repairs) == 1
    assert {row["id"] for row in undone.failures} == {"second", "attached"}
    assert host.state.document_json == original.base_json and not host.published


def test_initial_branch_eligibility_does_not_admit_unrelated_new_support_failures(host):
    _mixed_branch(host)
    for candidate in (host.base, host.proposed):
        feature(candidate, "attached")["inputs"]["support"] = "replacement"
    host.state.document_json = json.dumps(host.base, indent=2)
    host.binding = host.doc._capture_binding(host.context)
    result_row(host.response["result"], "attached")["status"] = "ok"
    original = retain(host)
    first = repaired(original.document)
    host.response["result"] = failure_result(first, repaired={"pad"})
    result_row(host.response["result"], "attached").update(
        status="failed", error={"code": "invalid_sketch_support"}
    )
    with pytest.raises(host.error, match="Full replay"):
        host.module.accept(host.context, original.token, first)
    assert host.module.current(host.context) is original and not host.published


def test_new_end_face_proposal_requires_exactly_one_initial_upstream_edit(host):
    feature(host.proposed, "replacement")["params"]["length"] = 20
    assert not host.module.retain(host.context, host.proposed, "target", object(), host.binding)
    assert host.module.current(host.context) is None
