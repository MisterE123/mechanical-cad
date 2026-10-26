"""Typed paired insertion admission retains existing lease and transient replay guards."""

import ast
import copy
import importlib
import json

import pytest
from test_assembly_pending_admission_order import PACKAGE, ROOT, lease
from test_assembly_source_preview_admission import adapter  # noqa: F401

Insertion = importlib.import_module(PACKAGE + ".assembly_insert_preview_draft").InsertPreviewDraft

Mate = importlib.import_module(PACKAGE + ".assembly_insert_mate_draft").InsertMateDraft


@pytest.fixture
def insertion(adapter):  # noqa: F811
    h = adapter
    insertion_draft = Insertion(
        h.original,
        h.original["parts"][0]["id"],
        parent=h.original["grounded_instance"],
        parent_frame="origin",
        child_frame="origin",
        kind="fixed",
        name="New child",
    )
    seed = insertion_draft.candidate()
    response = dict(ok=True, result=dict(
        canonical_assembly=seed, assembly_digest="a" * 64,
        source_hashes={"source": "b" * 64}, instances=copy.deepcopy(seed["instances"]),
        parts=[dict(id="block", topology=[
            dict(id=face, provenance={"semantic_status": "stable"},
                 signature=dict(surface="plane", area=100, centroid=[5, 5, z], normal=[0, 0, n]))
            for face, z, n in [("top", 10, 1), ("bottom", 0, -1)]
        ])], source_replays=[{"id": "source"}],
    ), report={"base_pose": {"transforms": {
        i["id"]: {"xyz_mm": [0, 0, 0], "wxyz": [1, 0, 0, 0]}
        for i in seed["instances"]
    }}})
    draft = Mate(insertion_draft, response)
    h.unpaired = Mate(insertion_draft, response)
    h.insertion_draft = insertion_draft
    draft.attach_face_pair("top", "bottom")
    h.env["InsertMateDraft"] = Mate
    h.env["assembly_bridge"] = type(
        "Fingerprint", (), {"fingerprint": staticmethod(lambda d: json.dumps(d, sort_keys=True))}
    )
    path = ROOT / "blender_addon/mechanical_cad_blender/assembly_pending.py"
    node = next(
        n
        for n in ast.parse(path.read_text()).body
        if isinstance(n, ast.FunctionDef) and n.name == "prepare_insert_mate_preview"
    )
    node.body = [n for n in node.body if not isinstance(n, (ast.Import, ast.ImportFrom))]
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), h.env)
    h.draft = draft

    def invoke(value=draft):
        return h.env["prepare_insert_mate_preview"](
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
    with pytest.raises(ValueError, match="newly constructed insertion mate draft"):
        insertion.invoke(value)
    insertion.state._state.assert_not_called()
    assert not insertion.acquired


def test_draft_subclasses_are_not_accepted_authority(insertion):
    class OtherDraft(Mate):
        pass

    fake = OtherDraft.__new__(OtherDraft)
    with pytest.raises(ValueError, match="newly constructed insertion mate draft"):
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
    assert prepared["assembly"] == expected and prepared["assembly"] is not h.draft._seed
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


def test_unpaired_mate_and_original_insert_type_cannot_enter_mate_adapter(insertion):
    h = insertion
    with pytest.raises(ValueError, match="both stable planar faces"):
        h.invoke(h.unpaired)
    with pytest.raises(ValueError, match="insertion mate draft"):
        h.invoke(h.insertion_draft)
    h.state._state.assert_not_called()
    assert not h.acquired


def test_original_insert_adapter_still_rejects_mate(insertion):
    h = insertion
    h.env["InsertPreviewDraft"] = Insertion
    path = ROOT / "blender_addon/mechanical_cad_blender/assembly_pending.py"
    node = next(n for n in ast.parse(path.read_text()).body
                if isinstance(n, ast.FunctionDef) and n.name == "prepare_insert_preview")
    node.body = [n for n in node.body if not isinstance(n, (ast.Import, ast.ImportFrom))]
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), h.env)
    with pytest.raises(ValueError, match="newly constructed insertion draft"):
        h.env["prepare_insert_preview"](h.context, h.draft,
            expected_json="accepted", expected_working_part="working")
    assert not h.acquired


def test_racing_lease_refuses_without_starting_transaction(insertion, monkeypatch):
    h = insertion
    monkeypatch.setattr(lease, "try_acquire", lambda: None)
    with pytest.raises(ValueError, match="Another CAD operation"):
        h.invoke()
    h.state._prepare_report.assert_not_called()
    h.env["_JOB_FACTORY"].assert_not_called()


def test_started_job_failure_uses_existing_abort_and_finish_cleanup(insertion):
    h = insertion
    h.job.start.side_effect = ValueError("start failed")
    with pytest.raises(ValueError, match="start failed"):
        h.invoke()
    h.env["_abort"].assert_called_once()
    assert h.env["_abort"].call_args.args[0] is h.pending
    h.env["_finish_failure"].assert_called_once_with(h.pending)
    h.state.commit_candidate.assert_not_called()
