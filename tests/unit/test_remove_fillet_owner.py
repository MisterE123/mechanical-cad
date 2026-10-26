"""Pure owner ports, with a mocked Check capability and no native evidence."""

from types import SimpleNamespace

import pytest
from test_arc_gesture_owner import dispatch, load, promote, store
from test_arc_gesture_owner import host as gesture_host

host = gesture_host

c = load("general_sketch_commands")


def rounded(host, monkeypatch):
    promote(host)
    owner = host.owner
    owner.commands.execute(c.AddRectangle(c.PointSeed(0, 0), c.PointSeed(20, 10)))
    lines = [line["id"] for line in owner.commands.sketch["lines"]]
    points = {p["id"]: (p["u"], p["v"]) for p in owner.commands.sketch["points"]}
    owner.commands.execute(c.CornerFillet(tuple(lines[:2]), 2, points))
    arc = owner.commands.sketch["arcs"][0]
    radius = next(r for r in owner.commands.sketch["constraints"] if r["kind"] == "radius")
    owner.draft.place_annotation(radius["id"], (4, 7), display="diameter")
    owner.draft.select((("arc", arc["id"]),))
    baseline = {"ok": True, "result": {"sketch": {"solved": owner.commands.sketch}}}
    owner.guarded_evidence = object()
    owner.expected_prepared = object()
    owner.current_solution_response = lambda: baseline  # Pure capability port, not evidence.
    owner._removal_read = lambda pair, action="solve_sketch": baseline if pair[0] is owner.guarded_evidence else host.candidate_response
    host.jobs = []
    owner._start_job = lambda context, request, kind: host.jobs.append((request, kind))
    monkeypatch.setattr(type(owner.commands), "record_guarded_solution", lambda *_, **__: True)
    monkeypatch.setattr(type(owner.commands), "has_current_solution", property(lambda _: True))
    owner._retain_outline = lambda: None
    host.context.window_manager.invoke_props_dialog = lambda *_, **__: {"RUNNING_MODAL"}
    store(host)
    return arc, radius


def test_review_cancel_apply_repeat_and_exact_annotation_undo_redo(host, monkeypatch):
    arc, radius = rounded(host, monkeypatch)
    owner, context = host.owner, host.context
    cls = host.viewport.MCAD_OT_remove_sketch_fillet
    before = owner.commands.sketch
    annotations = owner.draft.annotations
    saved = store(host)
    op = cls()
    assert cls.poll(context)
    assert op.invoke(context, None) == {"RUNNING_MODAL"}
    assert cls.poll(context)  # Same gesture is eligible for props-dialog repoll.
    op.cancel(context)
    assert store(host) == saved and owner.commands.sketch == before
    assert op.execute(context) == {"CANCELLED"}
    op = cls()
    assert op.invoke(context, None) == {"RUNNING_MODAL"}
    assert op.execute(context) == {"FINISHED"}
    assert owner.commands.sketch == before  # Detached until the candidate passes.
    candidate = dispatch.restore(owner.removal_attempt.candidate, owner.draft.document_json)
    host.candidate_response = {"ok": True, "result": {"sketch": {"solved": candidate.command_draft.sketch}}}
    evidence = SimpleNamespace(publication=SimpleNamespace(consume=lambda *_, **__: None))
    prepared = SimpleNamespace(operation_request=lambda: host.jobs[-1][0])
    owner.complete_fillet_removal(context, evidence, prepared, host.candidate_response)
    after = owner.commands.sketch
    assert not after["arcs"] and owner.draft.selection == []
    retired_annotations = {radius["id"]: load("annotation_retirement").mark_retired(annotations[radius["id"]])}
    assert owner.draft.annotations == retired_annotations
    assert owner.draft.status.annotations[0].state == "retired"
    assert owner.draft.display_annotations == {}
    assert not owner.draft.status.conflicts
    assert op.execute(context) == {"CANCELLED"}
    assert owner.commands.sketch == after
    owner.local_history(context)
    assert owner.commands.sketch == before and owner.draft.annotations == annotations
    assert owner.draft.status.annotations[0].available
    owner.local_history(context, redo=True)
    assert owner.commands.sketch == after and owner.draft.annotations == retired_annotations
    assert owner.draft.status.annotations[0].state == "retired"
    restored = dispatch.restore(store(host), owner.draft.document_json)
    removal = restored.command_draft.checkpoint_payload()["journal"]["entries"][-1]["command"]
    restored.command_draft.undo()
    load("sketch_remove_fillet").restore_removal_ui(restored, removal)
    assert restored.command_draft.sketch == before
    assert restored.annotations == annotations
    assert len(host.checks) == 2
    assert len(host.jobs) == 1


@pytest.mark.parametrize("change", ["selection", "target", "saved_slot", "backend", "check", "viewport"])
def test_stale_removal_refuses_without_mutating_canonical_or_geometry(host, monkeypatch, change):
    arc, _ = rounded(host, monkeypatch)
    owner, context = host.owner, host.context
    op = host.viewport.MCAD_OT_remove_sketch_fillet()
    assert op.invoke(context, None) == {"RUNNING_MODAL"}
    before = owner.commands.sketch
    canonical = host.state.document_json
    if change == "selection":
        owner.draft.select(())
    elif change == "target":
        op.arc_id = "wrong"
    elif change == "saved_slot":
        host.state.sketch_draft_json += " "
    elif change == "backend":
        owner.invalidate_backend()
    elif change == "check":
        owner.current_solution_response = lambda: None
    else:
        context.area = object()
    assert op.execute(context) == {"CANCELLED"}
    assert owner.commands.sketch == before
    assert host.state.document_json == canonical
    assert host.checks == []


@pytest.mark.parametrize("failure", ["drift", "missing_point", "wrong_candidate", "cancel", "changed_source"])
def test_detached_removal_trial_failure_keeps_original_history_and_layout(host, monkeypatch, failure):
    import copy

    rounded(host, monkeypatch)
    owner = host.owner
    original = store(host)
    owner.request_fillet_removal(host.context, owner.draft.selection[0]["id"])
    assert store(host) == original
    attempt = owner.removal_attempt
    candidate = dispatch.restore(attempt.candidate, owner.draft.document_json)
    solved = candidate.command_draft.sketch
    if failure == "drift":
        solved["points"][-1]["u"] += 0.01
    elif failure == "missing_point":
        solved["points"].pop()
    elif failure == "cancel":
        owner.cancel_native()
    elif failure == "changed_source":
        owner.draft.select(())
        original = store(host)
    host.candidate_response = {"ok": True, "result": {"sketch": {"solved": solved}}}
    evidence = SimpleNamespace(publication=SimpleNamespace(consume=lambda *_, **__: None))
    request = copy.deepcopy(host.jobs[-1][0])
    if failure == "wrong_candidate":
        request["document"]["name"] += " changed"
    prepared = SimpleNamespace(operation_request=lambda: request)
    with pytest.raises(ValueError):
        owner.complete_fillet_removal(host.context, evidence, prepared, host.candidate_response)
    assert store(host) == original
    assert owner.commands.sketch["arcs"]


@pytest.mark.parametrize("failure", [None, "drift", "failed"])
def test_consumed_removal_waits_for_exact_replay_before_acceptance(host, monkeypatch, failure):
    import copy

    rounded(host, monkeypatch)
    owner = host.owner
    monkeypatch.setattr(type(owner.commands), "consumed_by", property(lambda _: ("pad",)))
    load("sketch_remove_fillet_session").backend_runtime.configuration = lambda _: (host.current[0], 0.1)
    owner._start_job = lambda context, request, kind, **kw: host.jobs.append((request, kind))
    original = store(host)
    owner.request_fillet_removal(host.context, owner.draft.selection[0]["id"])
    candidate = dispatch.restore(owner.removal_attempt.candidate, owner.draft.document_json)
    host.candidate_response = {"ok": True, "result": {"sketch": {"solved": candidate.command_draft.sketch}}}
    solve_pair = (SimpleNamespace(publication=SimpleNamespace(consume=lambda *_, **__: None)),
                  SimpleNamespace(operation_request=lambda: host.jobs[0][0]))
    owner.complete_fillet_removal(host.context, *solve_pair, host.candidate_response)
    assert host.jobs[-1][1] == "remove_fillet_replay"
    assert store(host) == original
    solved = copy.deepcopy(candidate.command_draft.sketch)
    if failure == "drift":
        solved["points"][-1]["v"] += 0.01
    replay = {"ok": failure != "failed", "result": {"features": [
        {"id": candidate.feature_id, "status": "ok", "sketch": {"solved": solved}}]},
        "error": {"message": "A downstream feature failed."}}
    baseline_read = owner._removal_read
    owner._removal_read = lambda pair, action="solve_sketch": replay if action == "replay" else baseline_read(pair)
    replay_pair = (SimpleNamespace(publication=SimpleNamespace(consume=lambda *_, **__: None)),
                   SimpleNamespace(operation_request=lambda: host.jobs[-1][0]))
    if failure:
        with pytest.raises(ValueError):
            owner.complete_fillet_removal(host.context, *replay_pair, replay, kind="remove_fillet_replay")
        assert store(host) == original
    else:
        owner.complete_fillet_removal(host.context, *replay_pair, replay, kind="remove_fillet_replay")
        assert not owner.commands.sketch["arcs"]
        assert owner.commands._solution_evidence == (solve_pair[0], replay_pair[0])
        assert owner.commands._solution_prepared == (solve_pair[1], replay_pair[1])


def test_removal_authority_calls_bind_independent_request_version_action_and_owner():
    import ast

    from test_arc_live_owner_boundary import ADDON, authority_inventory

    source = (ADDON / "sketch_remove_fillet_session.py").read_text()
    calls, aliases = authority_inventory(source)
    assert not aliases
    assert calls == [("RemoveFilletSession.complete_fillet_removal", "evidence.publication.consume", {
        "owner_token": "self.owner_token", "expected_action": "action",
        "expected_result_version": "prepared.operation_request()['result_version']",
        "require_success": "True"})]
    tree = ast.parse(source)
    reads = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Name) and node.func.id == "read_guarded_operation"]
    assert len(reads) == 1
    assert [ast.unparse(arg) for arg in reads[0].args] == [
        "pair[0]", "pair[1]", "self._backend_current_selection()"]
    assert {kw.arg: ast.unparse(kw.value) for kw in reads[0].keywords} == {
        "owner_token": "self.owner_token", "action": "action", "require_success": "True"}


def test_palette_poll_and_review_redraw_never_serialize_or_validate_candidate(host, monkeypatch):
    rounded(host, monkeypatch)
    owner, context = host.owner, host.context
    cls = host.viewport.MCAD_OT_remove_sketch_fillet
    op = cls()
    assert op.invoke(context, None) == {"RUNNING_MODAL"}

    def forbidden(*args, **kwargs):
        raise AssertionError("Redraw must not capture/serialize/validate a transaction")

    monkeypatch.setattr(dispatch, "dumps", forbidden)
    monkeypatch.setattr(dispatch, "clone", forbidden)
    monkeypatch.setattr(owner, "current_solution_response", forbidden)
    monkeypatch.setattr(owner, "prepare_gesture", forbidden)
    monkeypatch.setattr(op, "_review", forbidden)
    op.layout = SimpleNamespace(label=lambda **kw: None)
    for _ in range(20):
        assert cls.poll(context)  # Live props-dialog hint, not full acceptance.
        op.draw(context)
    op.cancel(context)
    for _ in range(20):
        assert owner.can_use_tool("RemoveFillet")
        assert cls.poll(context)
