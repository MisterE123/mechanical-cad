"""Runtime-only shared generation revokes authority before owner callbacks."""

import importlib
import sys
import threading
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "mcad_backend_runtime_test"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[PACKAGE] = package
runtime = importlib.import_module(PACKAGE + ".backend_runtime")


@pytest.fixture(autouse=True)
def fresh_lifetime():
    runtime.configure_invalidation(None)
    runtime.new_lifetime()
    yield
    runtime.configure_invalidation(None)
    runtime.new_lifetime()


@pytest.fixture
def context(tmp_path):
    (tmp_path / "src/mechanical_cad").mkdir(parents=True)
    prefs = types.SimpleNamespace(
        project_root=str(tmp_path),
        python_executable=sys.executable,
        timeout_seconds=60.0,
        linear_deflection=0.1,
    )
    return types.SimpleNamespace(
        preferences=types.SimpleNamespace(
            addons={PACKAGE: types.SimpleNamespace(preferences=prefs)}
        )
    )


def prefs(context):
    return context.preferences.addons[PACKAGE].preferences


def test_current_recapture_does_not_revoke_or_change_captured_launch(context):
    notifications = []
    runtime.configure_invalidation(notifications.append)
    selected, tolerance = runtime.configuration(context)
    assert tolerance == 0.1
    assert runtime.assert_current(selected, context) == selected
    assert notifications == []
    assert runtime.stamp() == (selected.lifetime_id, selected.generation)


def test_supported_preference_aba_revokes_twice_even_without_operation_between(context):
    selected = runtime.capture(context)
    notifications = []
    runtime.configure_invalidation(notifications.append)
    prefs(context).timeout_seconds = 70
    runtime.revoke("A to B")
    prefs(context).timeout_seconds = 60
    runtime.revoke("B to A")
    assert not runtime.is_current(selected, context)
    assert runtime.capture(context).generation == selected.generation + 2
    assert notifications == ["A to B", "B to A"]


@pytest.mark.parametrize("field,value", [("timeout_seconds", 70), ("linear_deflection", 0.2)])
def test_observed_policy_change_revokes_completed_evidence(context, field, value):
    selected = runtime.capture(context)
    setattr(prefs(context), field, value)
    assert not runtime.is_current(selected, context)
    assert runtime.capture(context).generation == selected.generation + 1


def test_effective_environment_change_is_observed_without_mutating_selection(context, monkeypatch):
    old_root = prefs(context).project_root
    new_root = Path(old_root) / "different-backend"
    (new_root / "src/mechanical_cad").mkdir(parents=True)
    prefs(context).project_root = ""
    monkeypatch.setenv("MCAD_ROOT", old_root)
    selected = runtime.capture(context)
    environment = selected.launch_environment()
    monkeypatch.setenv("MCAD_ROOT", str(new_root))
    assert not runtime.is_current(selected, context)
    assert selected.launch_environment() == environment


def test_invalid_configuration_revokes_once_and_does_not_restore_after_fix(context):
    selected = runtime.capture(context)
    previous = prefs(context).project_root
    prefs(context).project_root = "/definitely/missing/cad-root"
    assert not runtime.is_current(selected, context)
    stamp = runtime.stamp()
    assert not runtime.is_current(selected, context)
    assert runtime.stamp() == stamp
    prefs(context).project_root = previous
    assert not runtime.is_current(selected, context)


def test_callback_sees_revocation_before_failure_and_cannot_roll_it_back(context):
    selected = runtime.capture(context)
    observed = []

    def fail(reason):
        observed.append(runtime.stamp())
        raise RuntimeError("injected cleanup failure")

    runtime.configure_invalidation(fail)
    with pytest.raises(RuntimeError, match="cleanup failure"):
        runtime.revoke()
    assert observed == [runtime.stamp()]
    assert runtime.stamp()[1] == selected.generation + 1
    runtime.configure_invalidation(None)
    assert not runtime.is_current(selected, context)


def test_reentrant_callback_recapture_does_not_recursively_revoke(context):
    selected = runtime.capture(context)
    captured = []
    runtime.configure_invalidation(lambda reason: captured.append(runtime.capture(context)))
    prefs(context).timeout_seconds = 80
    changed = runtime.capture(context)
    assert captured == [changed]
    assert changed.generation == selected.generation + 1


def test_new_epoch_does_not_match_even_when_generation_resets(context):
    selected = runtime.capture(context)
    runtime.new_lifetime()
    current = runtime.capture(context)
    assert selected.generation == current.generation == 0
    assert selected.lifetime_id != current.lifetime_id
    assert not runtime.is_current(selected, context)


def test_worker_cannot_advance_or_capture_runtime(context):
    errors = []
    before = runtime.stamp()

    def run():
        for operation in (lambda: runtime.capture(context), runtime.revoke, runtime.new_lifetime):
            try:
                operation()
            except runtime.bridge.BridgeError as exc:
                errors.append(str(exc))

    thread = threading.Thread(target=run)
    thread.start()
    thread.join()
    assert len(errors) == 3 and runtime.stamp() == before


def test_duck_typed_selection_cannot_claim_current(context):
    forged = types.SimpleNamespace(assert_current=lambda value: None)
    assert not runtime.is_current(forged, context)


def test_missing_preferences_revokes_instead_of_substituting_environment_defaults(context):
    selected = runtime.capture(context)
    unavailable = types.SimpleNamespace()
    with pytest.raises(runtime.bridge.BridgeError, match="preferences are unavailable"):
        runtime.capture(unavailable)
    assert not runtime.is_current(selected, context)


@pytest.mark.parametrize("error_type", [ReferenceError, AttributeError])
@pytest.mark.parametrize(
    "field",
    ["preferences", "project_root", "python_executable", "timeout_seconds", "linear_deflection"],
)
def test_unavailable_rna_observation_cannot_revive_old_selection_after_restoration(
    context, field, error_type
):
    selected = runtime.capture(context)
    original = context.preferences.addons[PACKAGE]

    class Unavailable:
        def __init__(self, source):
            self.source = source

        def __getattr__(self, name):
            if name == field:
                raise error_type("RNA struct removed")
            return getattr(self.source, name)

    context.preferences.addons[PACKAGE] = (
        Unavailable(original)
        if field == "preferences"
        else types.SimpleNamespace(preferences=Unavailable(original.preferences))
    )
    assert not runtime.is_current(selected, context)
    revoked = runtime.stamp()
    assert revoked[1] == selected.generation + 1
    assert not runtime.is_current(selected, context)
    assert runtime.stamp() == revoked
    context.preferences.addons[PACKAGE] = original
    assert not runtime.is_current(selected, context)
