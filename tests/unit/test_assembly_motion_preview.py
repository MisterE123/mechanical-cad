"""Motion intent and UI-owner tests; native evidence is covered by Blender smoke."""

import copy
import importlib
import math
import sys
from types import SimpleNamespace

import pytest
from test_assembly_gears import PACKAGE, mechanism
from test_visual_joint_owner import host  # noqa: F401

MotionDraft = importlib.import_module(PACKAGE + ".assembly_motion_draft").MotionDraft


def test_only_independent_scalar_changes_and_all_followers_derive():
    original = mechanism().to_dict()
    before = copy.deepcopy(original)
    draft = MotionDraft(original, "driver")
    draft.coordinate = 0.5
    candidate = draft.candidate()
    expected = copy.deepcopy(before)
    expected["joints"][0]["coordinate"] = 0.5
    assert candidate == expected
    assert original == before
    assert draft.effective_coordinates() == {"driver": 0.5, "follower": 0.25, "tail": -0.125}
    candidate["joints"][0]["name"] = "detached"
    assert draft.candidate() == expected


@pytest.mark.parametrize("value", [True, float("nan"), float("inf"), -10001, 10001, "1", 2.0])
def test_invalid_driver_or_derived_limit_cannot_become_candidate(value):
    draft = MotionDraft(mechanism().to_dict(), "driver")
    draft.coordinate = value
    with pytest.raises(ValueError):
        draft.candidate()


def test_driven_joint_names_ultimate_driver_and_never_becomes_independent():
    data = mechanism().to_dict()
    for identity in ("follower", "tail"):
        with pytest.raises(ValueError, match="read-only.*driver"):
            MotionDraft(data, identity)
    data["joints"][0]["kind"] = "slider"
    with pytest.raises(ValueError, match="revolute"):
        MotionDraft(data, "driver")


def test_scalar_edit_does_not_insert_absent_fields():
    data = mechanism(relations=False).to_dict()
    data["joints"][0].pop("limits")
    draft = MotionDraft(data, "driver")
    draft.coordinate = 0.3
    assert "limits" not in draft.candidate()["joints"][0]


@pytest.fixture
def motion(host, monkeypatch, request):  # noqa: F811
    owner = host.owner
    assembly = copy.deepcopy(host.assembly)
    first, second = assembly["joints"]
    for joint in assembly["joints"]:
        joint["kind"] = "revolute"
        joint["limits"] = None
    first["coordinate"], second["coordinate"] = 0.1, None
    assembly["gear_relations"] = [
        {
            "id": "gear",
            "name": "Cross branch",
            "driver_joint": first["id"],
            "driven_joint": second["id"],
            "ratio": -2.0,
            "offset_rad": 0.5,
        }
    ]
    if getattr(request, "param", "revolute") == "slider":
        first["kind"], first["coordinate"], first["limits"] = "slider", 10.0, [0, 20]
        second["coordinate"] = 0.2
        assembly.pop("gear_relations")
    host.storage.document_json = host.state_api._json(assembly)
    host.response["result"]["canonical_assembly"] = copy.deepcopy(assembly)
    host.runtime["display_document_json"] = host.storage.document_json
    jobs, clock = [], [0.0]
    monkeypatch.setattr(owner.time, "monotonic", lambda: clock[0])

    def prepare(context, joint_id, coordinate, *, expected_json):
        assert context is host.context and expected_json == host.storage.document_json
        job = SimpleNamespace(done=False, cancelled=False, coordinate=coordinate, result=None)
        jobs.append(job)
        return job

    def poll(context, job):
        if job.cancelled:
            job.done = True
            raise owner.BridgeError("Superseded")
        if job.result is not None:
            job.done = True
            return copy.deepcopy(job.result)
        return None

    def cancel(job, reason):
        job.cancelled = True

    pending = SimpleNamespace(prepare_motion_preview=prepare, poll=poll, cancel=cancel)
    job_ui = SimpleNamespace(ensure_supervisor=lambda: None)
    package = sys.modules[owner.__package__]
    for name, module in (("assembly_pending", pending), ("assembly_job_ui", job_ui)):
        monkeypatch.setitem(sys.modules, owner.__package__ + "." + name, module)
        monkeypatch.setattr(package, name, module, raising=False)
    session = owner.MotionViewportSession(host.context, first["id"]).start()

    def complete():
        response = copy.deepcopy(host.response)
        response["report"]["base_pose"]["effective_coordinates"] = {
            first["id"]: session.draft.coordinate,
            second["id"]: 0.5 - 2 * session.draft.coordinate if first["kind"] == "revolute" else 0.2,
        }
        response["report"]["base_pose"]["transforms"][second["child"]]["xyz_mm"] = [40, 20, 10]
        jobs[-1].result = response
        session.tick(host.context)

    return SimpleNamespace(host=host, session=session, jobs=jobs, clock=clock, complete=complete)


def test_coalesces_queued_values_and_full_result_not_subtree(motion):
    m = motion
    before = vars(m.host.storage).copy()
    for angle in (1, 2, 3):
        m.session.set_distance(m.host.context, angle)
        m.session.tick(m.host.context)
    assert not m.jobs and not m.session.ghost_positions
    m.clock[0] = 1
    m.session.tick(m.host.context)
    assert len(m.jobs) == 1 and m.jobs[0].coordinate == math.radians(3)
    assert not m.session.ready()
    m.complete()
    assert m.session.ready()
    assert len(m.session.preview_transforms) == len(m.host.assembly["instances"])
    assert m.session.preview_transforms["sector_b"]["xyz_mm"] == [40, 20, 10]
    assert vars(m.host.storage) == before and not m.host.publication_calls
    m.session.cancel()
    assert vars(m.host.storage) == before


def test_superseded_ready_response_cannot_restore_old_ghost(motion):
    m = motion
    m.clock[0] = 1
    m.session.tick(m.host.context)
    m.jobs[-1].result = copy.deepcopy(m.host.response)
    m.session.set_distance(m.host.context, 4)
    assert m.jobs[0].cancelled and not m.session.ghost_positions
    m.clock[0] = 2
    m.session.tick(m.host.context)
    assert len(m.jobs) == 2 and not m.session.ready()
    m.complete()
    assert m.session.ready()
    assert m.session._ready_candidate["joints"][0]["coordinate"] == math.radians(4)


@pytest.mark.parametrize("motion", ["revolute", "slider"], indirect=True)
def test_raw_edit_revokes_ghost_and_apply_without_parsing_text(motion):
    m = motion
    m.clock[0] = 1
    m.session.tick(m.host.context)
    m.complete()
    m.session.click_action(m.host.context, "distance")
    m.session.field_raw = "invalid unfinished input"
    assert not m.session.ready() and not m.session.ghost_positions
    assert not m.session.apply(m.host.context)
    assert not m.host.publication_calls
    m.session.cancel()


@pytest.mark.parametrize("motion", ["revolute", "slider"], indirect=True)
def test_failed_admission_does_not_auto_retry(motion, monkeypatch):
    m = motion
    pending = sys.modules[m.host.owner.__package__ + ".assembly_pending"]
    calls = []

    def fail(*args, **kwargs):
        calls.append(1)
        raise m.host.owner.BridgeError("Backend not ready")

    monkeypatch.setattr(pending, "prepare_motion_preview", fail)
    m.clock[0] = 1
    m.session.tick(m.host.context)
    m.clock[0] = 100
    m.session.tick(m.host.context)
    assert calls == [1] and "Backend not ready" in m.session.error
    assert not m.session.ready() and not m.session.ghost_positions


@pytest.mark.parametrize("motion", ["revolute", "slider"], indirect=True)
def test_apply_bound_to_exact_completed_candidate_and_pose(motion, monkeypatch):
    m = motion
    m.clock[0] = 1
    m.session.tick(m.host.context)
    m.complete()
    expected = copy.deepcopy(m.session._ready_pose)
    calls = []

    def publish(context, candidate, expected_json=None, *, expected_preview=None):
        calls.append((copy.deepcopy(candidate), expected_json, expected_preview))
        return m.host.response

    monkeypatch.setattr(m.host.state_api, "commit_candidate", publish)
    assert m.session.apply(m.host.context)
    assert calls[0][2] == expected
    assert not m.session.alive and m.session.finished


@pytest.mark.parametrize("change", ["units", "canonical", "backend", "area"])
@pytest.mark.parametrize("motion", ["revolute", "slider"], indirect=True)
def test_changed_binding_cancels_owner_and_running_job(motion, change):
    m = motion
    m.clock[0] = 1
    m.session.tick(m.host.context)
    context = m.host.context
    if change == "units":
        context.scene.unit_settings.scale_length = 0.1
    elif change == "canonical":
        m.host.storage.document_json += " "
    elif change == "backend":
        from dataclasses import replace

        m.host.current[0] = replace(m.host.current[0], generation=3)
    else:
        context.area.type = "CONSOLE"
    operator = m.host.owner.MCAD_OT_assembly_visual_joint()
    operator.owner = m.session
    event = SimpleNamespace(type="TIMER", value="NOTHING")
    assert operator.modal(context, event) == {"CANCELLED"}
    assert not m.session.alive and m.jobs[0].cancelled


@pytest.fixture
def pending_host(host, monkeypatch):  # noqa: F811
    """Synthetic transport/projection ports; real admission/freshness/cleanup owner."""
    pending = importlib.import_module(host.owner.__package__ + ".assembly_pending")
    assembly = copy.deepcopy(host.assembly)
    assembly["joints"][0].update(kind="revolute", coordinate=0.1, limits=None)
    host.storage.document_json = host.state_api._json(assembly)
    host.runtime["display_document_json"] = host.storage.document_json
    host.response["result"]["canonical_assembly"] = copy.deepcopy(assembly)
    jobs, receipts = [], []

    class Job:
        def __init__(self, prepared, selection, *, owner_token):
            self.request = prepared.guarded_request()
            self.state, self.done, self.fail = "created", False, False
            jobs.append(self)

        def start(self, selection):
            self.state = "running"

        def poll(self, selection):
            return self.state

        def request_snapshot(self):
            return copy.deepcopy(self.request)

        def result(self, selection, *, owner_token):
            if self.fail:
                raise host.owner.BridgeError("Native replay failed")
            receipt = SimpleNamespace(cancelled=False)
            receipt.cancel = lambda: setattr(receipt, "cancelled", True)
            receipts.append(receipt)
            return SimpleNamespace(publication=receipt)

        def cancel(self):
            self.state, self.done = "cancelled", True

    monkeypatch.setattr(pending, "_JOB_FACTORY", Job)
    monkeypatch.setattr(host.state_api, "_projection", lambda *a, **k: copy.deepcopy(host.response))

    def no_recovery(*args):
        raise AssertionError("Transient preview must never recover/write report state")

    monkeypatch.setattr(host.state_api, "_recover_report", no_recovery)
    return SimpleNamespace(
        host=host, api=pending, jobs=jobs, receipts=receipts, joint_id=assembly["joints"][0]["id"]
    )


def start_pending(fixture):
    return fixture.api.prepare_motion_preview(
        fixture.host.context,
        fixture.joint_id,
        0.2,
        expected_json=fixture.host.storage.document_json,
    )


def test_transient_projection_revokes_receipt_without_writing_report(pending_host):
    p = pending_host
    before = vars(p.host.storage).copy()
    pending = start_pending(p)
    assert pending.status()["preview"]
    assert pending.request_snapshot()["action"] == "assembly_replay"
    p.jobs[0].state, p.jobs[0].done = "ready", True
    assert p.api.poll(p.host.context, pending) == p.host.response
    assert p.receipts[0].cancelled and pending.done
    assert vars(p.host.storage) == before
    assert not p.host.owner.execution_lease.is_busy()
    assert p.api.poll(p.host.context, pending) is None


@pytest.mark.parametrize(
    "failure", ["cancel", "failed", "tampered_request", "tampered_report", "backend"]
)
def test_transient_failure_never_recovers_or_publishes_accepted_state(pending_host, failure):
    p = pending_host
    pending = start_pending(p)
    p.jobs[0].state, p.jobs[0].done = "ready", True
    if failure == "tampered_report":
        p.host.storage.report_json = "newer external report"
    elif failure == "backend":
        from dataclasses import replace

        p.host.current[0] = replace(p.host.current[0], generation=3)
    elif failure == "failed":
        p.jobs[0].fail = True
    elif failure == "tampered_request":
        p.jobs[0].request["action"] = "assembly_check"
    before = vars(p.host.storage).copy()
    if failure == "cancel":
        assert p.api.cancel(pending)
    else:
        with pytest.raises((p.host.owner.BridgeError, ValueError)):
            p.api.poll(p.host.context, pending)
    assert vars(p.host.storage) == before and not p.receipts
    assert not p.host.owner.execution_lease.is_busy()
    assert p.api.active_for_scene(p.host.context.scene) is None


def test_preview_admission_rejection_does_not_mutate_status(pending_host, monkeypatch):
    p = pending_host
    before = vars(p.host.storage).copy()
    monkeypatch.setattr(p.host.state_api, "display_is_current", lambda *a, **k: False)
    with pytest.raises(p.host.owner.BridgeError, match="Replay"):
        start_pending(p)
    assert vars(p.host.storage) == before
    assert not p.host.owner.execution_lease.is_busy() and not p.jobs


@pytest.mark.parametrize("motion", ["slider"], indirect=True)
def test_slider_millimetres_buttons_and_superseded_preview(motion):
    m = motion
    before = vars(m.host.storage).copy()
    m.session.click_action(m.host.context, "plus")
    assert m.session.draft.coordinate == 11.0  # One millimetre, not one radian/degree.
    m.session.click_action(m.host.context, "minus")
    assert m.session.draft.coordinate == 10.0
    m.session.set_distance(m.host.context, 12.5)
    assert m.session.draft.coordinate == 12.5
    m.clock[0] = 1
    m.session.tick(m.host.context)
    assert m.jobs[-1].coordinate == 12.5
    m.jobs[-1].result = copy.deepcopy(m.host.response)
    m.session.set_distance(m.host.context, 13.5)
    assert m.jobs[0].cancelled and not m.session.ready() and not m.session.ghost_positions
    m.clock[0] = 2
    m.session.tick(m.host.context)
    assert len(m.jobs) == 2 and m.jobs[-1].coordinate == 13.5
    m.complete()
    assert m.session.ready()
    assert m.session._ready_candidate["joints"][0]["coordinate"] == 13.5
    panel = m.session.panel_layout()
    distance = next(button for button in panel.buttons if button.action == "distance")
    assert distance.label == "13.5 mm"
    assert vars(m.host.storage) == before and not m.host.publication_calls
    m.session.cancel()


@pytest.mark.parametrize("motion", ["slider"], indirect=True)
@pytest.mark.parametrize("value", [-1, 21, float("nan"), float("inf")])
def test_slider_invalid_coordinate_revokes_ready_ghost_and_apply(motion, value):
    m = motion
    before = vars(m.host.storage).copy()
    m.clock[0] = 1
    m.session.tick(m.host.context)
    m.complete()
    assert m.session.ready()
    with pytest.raises(ValueError, match="Slider displacement"):
        m.session.set_distance(m.host.context, value)
    assert not m.session.ready() and not m.session.ghost_positions
    assert not m.session.apply(m.host.context) and not m.host.publication_calls
    assert vars(m.host.storage) == before
    assert "Invalid slide" in m.session.message
    m.session.cancel()
