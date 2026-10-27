"""Typed insertion preview admission executes actual adapter without native work."""

import ast
import copy
import importlib
import json

import pytest
from test_assembly_pending_admission_order import PACKAGE, ROOT, lease
from test_assembly_source_preview_admission import adapter  # noqa: F401

Draft = importlib.import_module(PACKAGE + ".assembly_insert_preview_draft").InsertPreviewDraft


@pytest.fixture
def insertion(adapter):  # noqa: F811
    h = adapter
    draft = Draft(
        h.original,
        h.original["parts"][0]["id"],
        parent=h.original["grounded_instance"],
        parent_frame="origin",
        child_frame="origin",
        kind="fixed",
        name="New child",
    )
    h.env["InsertPreviewDraft"] = Draft
    h.env["assembly_bridge"] = type(
        "Fingerprint", (), {"fingerprint": staticmethod(lambda d: json.dumps(d, sort_keys=True))}
    )
    path = ROOT / "blender_addon/mechanical_cad_blender/assembly_pending.py"
    node = next(
        n
        for n in ast.parse(path.read_text(encoding="utf-8")).body
        if isinstance(n, ast.FunctionDef) and n.name == "prepare_insert_preview"
    )
    node.body = [n for n in node.body if not isinstance(n, (ast.Import, ast.ImportFrom))]
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), h.env)
    h.draft = draft

    def invoke(value=draft):
        return h.env["prepare_insert_preview"](
            h.context, value, expected_json="accepted", expected_working_part="working"
        )

    h.invoke = invoke
    return h


def test_insert_busy_excludes_before_rna_or_draft_access(insertion):
    h = insertion
    token = lease.try_acquire()
    h.calls.clear()
    with pytest.raises(ValueError, match="Another CAD operation"):
        h.invoke(object())
    h.state._state.assert_not_called()
    assert h.calls == [] and lease._TOKEN is token


@pytest.mark.parametrize("value", [None, {}, "candidate-json"])
def test_untyped_insert_candidate_has_no_authority(insertion, value):
    with pytest.raises(ValueError, match="newly constructed insertion draft"):
        insertion.invoke(value)
    insertion.state._state.assert_not_called()
    assert not insertion.acquired


def test_draft_subclasses_are_not_accepted_authority(insertion):
    class OtherDraft(Draft):
        pass

    fake = OtherDraft.__new__(OtherDraft)
    with pytest.raises(ValueError, match="newly constructed insertion draft"):
        insertion.invoke(fake)
    assert not insertion.acquired


@pytest.mark.parametrize("changed", ["json", "working", "accepted"])
def test_stale_insertion_inputs_reject_before_preflight(insertion, changed):
    h = insertion
    if changed == "json":
        h.context.scene.document_json = "new"
    elif changed == "working":
        h.state._working_part.return_value = "new"
    else:
        h.original["name"] += " changed"
    with pytest.raises(ValueError, match="changed|different accepted"):
        h.invoke()
    h.state._preflight_assembly.assert_not_called()
    assert not h.acquired


def test_insert_full_detached_candidate_preview_only_with_stable_ids(insertion):
    h = insertion
    before = copy.deepcopy(h.original)
    expected = h.draft.candidate()
    assert h.invoke() is h.pending
    assert h.calls.index("preflight") < h.calls.index("acquire")
    prepared = h.env["_JOB_FACTORY"].call_args.args[0]
    assert prepared["assembly"] == expected and prepared["assembly"] is not h.draft._candidate
    assert h.draft.candidate() == expected and h.original == before
    h.env["PendingReport"].assert_called_once_with(
        h.transaction,
        prepared,
        h.job,
        h.acquired[0],
        preview=True,
        source_preview=True,
        insert_preview=True,
    )
    h.state.commit_candidate.assert_not_called()
    h.canonical.assert_not_called()  # No recapture or regenerated insertion identity.


@pytest.mark.parametrize("failure", ["preflight", "capture", "rebind", "operation", "job"])
def test_insertion_failure_releases_only_acquired_lease(insertion, failure):
    h = insertion
    if failure == "preflight":
        h.state._preflight_assembly.side_effect = ValueError("bad candidate")
    elif failure == "capture":
        h.state._prepare_report.side_effect = ValueError("capture failed")
    elif failure == "rebind":
        h.transaction["snapshot"] = dict(h.opening, working_part="new")
    elif failure == "operation":
        h.state._prepare_operation.side_effect = ValueError("prepare failed")
    else:
        h.env["_JOB_FACTORY"].side_effect = ValueError("job failed")
    with pytest.raises(ValueError):
        h.invoke()
    assert h.released == h.acquired
    assert len(h.acquired) == (0 if failure == "preflight" else 1)
    assert not lease.is_busy() and not h.env["_ACTIVE"]
    h.state.commit_candidate.assert_not_called()
