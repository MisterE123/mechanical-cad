"""Automatic setup policy stays separate from operation and publication authority."""

import importlib
import sys
import threading
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "mcad_bundled_runtime_tests"
package = sys.modules.setdefault(PACKAGE, types.ModuleType(PACKAGE))
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
r = importlib.import_module(PACKAGE + ".backend_runtime")


class Job:
    instances = []

    def __init__(self, *args, **kwargs):
        self.args, self.kwargs = args, kwargs
        self.state, self.starts, self.consumes = "created", 0, 0
        self.descriptor = object()
        self.instances.append(self)

    def start(self):
        self.starts += 1
        self.state = "running"

    def cancel(self):
        if self.state == "cleanup_blocked":
            return False
        self.state = "cancelling" if self.state in {"running", "cancelling"} else "cancelled"
        return True

    def poll(self):
        return self.state

    @property
    def done(self):
        return self.state in {"ready", "failed", "cancelled", "consumed"}

    def result(self):
        self.consumes += 1
        previous, self.state = self.state, "consumed"
        if previous != "ready":
            raise RuntimeError(previous)
        return self.descriptor


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    for name, value in {
        "_BUNDLE_REQUIRED": False,
        "_BUNDLE_ENABLED": False,
        "_BUNDLE_JOB": None,
        "_BUNDLE_JOB_REQUEST": None,
        "_BUNDLE_REQUEST": None,
        "_BUNDLE_POLICY": None,
        "_BUNDLE_STATE": "external",
        "_BUNDLE_MESSAGE": "External backend.",
        "_INVALIDATE": None,
        "_OBSERVED": None,
    }.items():
        monkeypatch.setattr(r, name, value)
    Job.instances = []
    monkeypatch.setattr(r, "BundlePreparationJob", Job)
    monkeypatch.setattr(r, "capture_bundled_policy", lambda descriptor, **kw: (descriptor, kw))
    r.new_lifetime()


def constants():
    result = dict.fromkeys(r.LAUNCH_CONSTANT_FIELDS, "bounded")
    result.update(PLATFORM="linux-x64", RELEASE_IDENTITY_BYTES=b"release")
    return result


def begin(**overrides):
    args = dict(
        package_root="/installed/package", cache_root="/private/cache", constants=constants()
    )
    args.update(overrides)
    return r.begin_bundled_setup(**args)


def ready():
    begin()
    job = Job.instances[-1]
    job.state = "ready"
    assert not r.poll_bundled_setup()
    return job


def test_prepare_transfer_is_once_only_and_never_current_before_cleanup():
    before = r.stamp()
    assert begin()
    job = Job.instances[0]
    assert r.bundled_mode() and r.bundle_status()[0] == "preparing"
    assert r._BUNDLE_POLICY is None and r.stamp()[1] == before[1] + 1
    for _ in range(5):
        assert r.poll_bundled_setup()
    assert job.consumes == 0 and job.starts == 1
    job.state = "ready"
    assert not r.poll_bundled_setup()
    assert r.bundle_status() == ("ready", "Bundled backend ready.")
    assert r._BUNDLE_POLICY[0] is job.descriptor
    assert r.stamp()[1] == before[1] + 2
    assert not r.poll_bundled_setup() and job.consumes == 1
    assert r._BUNDLE_JOB is None


def test_callbacks_see_no_old_or_new_policy_at_each_transition():
    observations = []
    r.configure_invalidation(lambda reason: observations.append((r.stamp(), r._BUNDLE_POLICY)))
    ready()
    r.stop_bundled_setup()
    begin()
    assert [stamp[1] for stamp, _ in observations] == [1, 2, 3, 4]
    assert all(policy is None for _, policy in observations)


def test_disable_reenable_waits_for_original_cleanup_before_replacement():
    begin()
    original = Job.instances[0]
    r.stop_bundled_setup()
    assert r._BUNDLE_JOB is original and original.state == "cancelling"
    assert not r.poll_bundled_setup()
    assert begin(cache_root="/private/replacement")
    assert r._BUNDLE_JOB is original and len(Job.instances) == 1
    original.state = "cancelled"
    assert r.poll_bundled_setup()
    replacement = Job.instances[1]
    assert replacement.args[1] == "/private/replacement"
    assert replacement is r._BUNDLE_JOB and original.consumes == 1
    assert r._BUNDLE_POLICY is None
    replacement.state = "ready"
    assert not r.poll_bundled_setup()
    assert r._BUNDLE_POLICY[0] is replacement.descriptor


@pytest.mark.parametrize("before", ["running", "ready", "failed", "cleanup_blocked"])
def test_stop_retains_original_owner_and_revokes_ready_or_pending_policy(before):
    begin()
    owner = Job.instances[0]
    owner.state = before
    r.stop_bundled_setup()
    assert r._BUNDLE_JOB is owner and r._BUNDLE_POLICY is None
    assert r.bundled_mode() and not r._BUNDLE_ENABLED
    assert r.bundle_status()[0] == "disabled"
    assert not r.poll_bundled_setup()
    assert owner.consumes == 0


def test_uncertain_cleanup_is_absorbing_across_reenable_and_never_consumed():
    begin()
    owner = Job.instances[0]
    owner.state = "cleanup_blocked"
    assert not r.poll_bundled_setup()
    assert "restart Blender" in r.bundle_status()[1]
    for _ in range(3):
        r.stop_bundled_setup()
        assert not begin()
        assert r.bundle_status()[0] == "cleanup_blocked"
        assert r._BUNDLE_JOB is owner and r._BUNDLE_POLICY is None
    assert len(Job.instances) == 1 and owner.consumes == 0


@pytest.mark.parametrize("state", ["failed", "cancelled"])
def test_clean_failure_has_no_policy_or_automatic_retry(state):
    begin()
    owner = Job.instances[0]
    owner.state = state
    assert not r.poll_bundled_setup() and r.bundle_status()[0] == "failed"
    assert len(Job.instances) == 1
    assert r._BUNDLE_POLICY is None


def test_missing_generated_metadata_cannot_use_external_preferences():
    r.fail_bundled_setup("Installed metadata missing.")
    assert r.bundled_mode() and r.bundle_status() == ("failed", "Installed metadata missing.")
    context = types.SimpleNamespace(preferences=types.SimpleNamespace(addons={}))
    with pytest.raises(r.bridge.BridgeError, match="metadata missing"):
        r.configuration(context)


def test_bad_metadata_rejects_before_any_preparation_worker():
    data = constants()
    data["UNEXPECTED"] = "x"
    assert not begin(constants=data)
    assert r.bundled_mode() and r.bundle_status()[0] == "failed"
    assert not Job.instances


@pytest.mark.parametrize("platform", ["win32", "darwin"])
def test_unqualified_host_has_no_worker_or_fallback(monkeypatch, platform):
    monkeypatch.setattr(r.sys, "platform", platform)
    assert not begin()
    assert "not qualified" in r.bundle_status()[1]
    assert not Job.instances and r._BUNDLE_POLICY is None


def test_captured_generated_literals_are_detached():
    data = constants()
    begin(constants=data)
    data["RELEASE_IDENTITY_BYTES"] = b"changed"
    data["PLATFORM"] = "windows-x64"
    owner = Job.instances[0]
    owner.state = "ready"
    assert not r.poll_bundled_setup()
    kw = r._BUNDLE_POLICY[1]
    assert kw["release_data"] == b"release" and kw["constants"]["PLATFORM"] == "linux-x64"


def test_policy_validation_failure_cannot_publish_or_restart(monkeypatch):
    begin()
    Job.instances[0].state = "ready"

    def reject(*args, **kwargs):
        raise ValueError("descriptor mismatch")

    monkeypatch.setattr(r, "capture_bundled_policy", reject)
    assert not r.poll_bundled_setup()
    assert "descriptor mismatch" in r.bundle_status()[1]
    assert r._BUNDLE_POLICY is None and r._BUNDLE_REQUEST is None
    assert not r.poll_bundled_setup() and len(Job.instances) == 1


def test_notification_failure_after_preparation_keeps_authority_closed():
    begin()
    Job.instances[0].state = "ready"
    before = r.stamp()

    def reject(reason):
        raise RuntimeError("owner failure")

    r.configure_invalidation(reject)
    assert not r.poll_bundled_setup()
    assert r.stamp()[1] == before[1] + 1
    assert r._BUNDLE_POLICY is None and "restart Blender" in r.bundle_status()[1]


def test_bundle_configuration_ignores_manual_paths_and_environment(monkeypatch):
    ready()
    observed = []

    class Prefs:
        timeout_seconds, linear_deflection = 42.0, 0.25

        @property
        def project_root(self):
            raise AssertionError("manual root read")

        @property
        def python_executable(self):
            raise AssertionError("manual interpreter read")

    context = types.SimpleNamespace(
        preferences=types.SimpleNamespace(
            addons={PACKAGE: types.SimpleNamespace(preferences=Prefs())}
        )
    )
    sentinel = object()

    def capture(policy, timeout, **identity):
        observed.append((policy, timeout, identity))
        return sentinel

    monkeypatch.setattr(r.BackendSelection, "capture_bundled", capture)
    monkeypatch.setattr(r, "_settings_key", lambda selected, tolerance: (selected, tolerance))
    monkeypatch.setenv("MCAD_ROOT", "/wrong/source")
    monkeypatch.setenv("MCAD_PYTHON", "/wrong/python")
    assert r.configuration(context) == (sentinel, 0.25)
    assert observed == [
        (r._BUNDLE_POLICY, 42.0, dict(generation=r.stamp()[1], lifetime_id=r.stamp()[0]))
    ]


def test_status_drawing_does_not_poll_start_or_consume():
    begin()
    job = Job.instances[0]
    job.state = "ready"
    for _ in range(20):
        assert r.bundle_status()[0] == "preparing"
        assert r.bundled_mode()
    assert job.consumes == 0 and job.starts == 1 and r._BUNDLE_POLICY is None


def test_worker_cannot_control_setup_or_transfer_policy():
    operations = [
        begin,
        r.stop_bundled_setup,
        r.poll_bundled_setup,
        r.bundle_status,
        r.bundled_mode,
    ]
    errors = []

    def run():
        for operation in operations:
            try:
                operation()
            except r.bridge.BridgeError as exc:
                errors.append(str(exc))

    thread = threading.Thread(target=run)
    thread.start()
    thread.join(2)
    assert not thread.is_alive() and len(errors) == len(operations)
    assert not Job.instances
