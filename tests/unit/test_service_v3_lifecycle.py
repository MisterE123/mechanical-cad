"""Actual dormant-service admission without a platform or exact-class waiver.

Manual-profile lifecycle/receipt/process cases are retained unchanged in
test_service_v3_lifecycle_linux.py. Production deliberately rejects bundled
profiles here; Windows tests prove rejection with a real public capture.
"""

import importlib
import sys
import types
from dataclasses import dataclass, fields
from pathlib import Path

import pytest
from captured_backend_fixture import captured_backend as captured_backend

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "mcad_data_only_admission_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[PACKAGE] = package
service = importlib.import_module(PACKAGE + ".service_v3")
selections = importlib.import_module(PACKAGE + ".backend_selection")


@dataclass(frozen=True)
class LogicalStamp:
    """A foreign lifecycle stamp cannot satisfy a production admission gate."""

    generation: int = 0
    lifetime_id: str = "foreign-port"
    bundled_policy: object = None

    def assert_current(self, *args):
        pytest.fail("Foreign stamp reached currentness")


@pytest.mark.parametrize("kind", ["none", "dict", "object", "namespace", "logical-stamp"])
def test_foreign_records_reject_before_model_currentness_or_job(monkeypatch, kind):
    candidates = {
        "none": None,
        "dict": {},
        "object": object(),
        "namespace": types.SimpleNamespace(bundled_policy=None),
        "logical-stamp": LogicalStamp(),
    }

    def forbidden(*args, **kwargs):
        pytest.fail("Foreign selection reached a later admission leaf")

    monkeypatch.setattr(service.result_v3, "validate_request", forbidden)
    monkeypatch.setattr(service.SidecarJob, "from_selection", forbidden)
    with pytest.raises(service.bridge.BridgeError, match="captured backend selection"):
        service.DataOnlyJob({}, candidates[kind], current_selection=forbidden)


@pytest.mark.skipif(sys.platform != "win32", reason="actual public Windows host capture")
@pytest.mark.parametrize("kind", ["selection", "policy", "descriptor"])
def test_windows_public_profile_cannot_enter_dormant_service(
    captured_backend, monkeypatch, kind
):
    selected = captured_backend(selections, generation=0, lifetime_id="windows-dormant-gate")
    assert type(selected) is selections.BackendSelection
    candidates = {
        "selection": selected,
        "policy": selected.bundled_policy,
        "descriptor": selected.bundled_policy.descriptor,
    }

    def forbidden(*args, **kwargs):
        pytest.fail("Dormant bundled rejection reached a later admission leaf")

    monkeypatch.setattr(service.result_v3, "validate_request", forbidden)
    monkeypatch.setattr(service.SidecarJob, "from_selection", forbidden)
    expected = "dormant" if kind == "selection" else "captured backend selection"
    with pytest.raises(service.bridge.BridgeError, match=expected):
        service.DataOnlyJob({}, candidates[kind], current_selection=forbidden)


@pytest.mark.skipif(sys.platform != "win32", reason="actual public Windows host capture")
def test_windows_public_record_subclass_rejects_at_exact_class_gate(captured_backend, monkeypatch):
    selected = captured_backend(selections, generation=0, lifetime_id="windows-exact-class-gate")
    assert type(selected) is selections.BackendSelection
    assert selected.bundled_policy is not None

    class ForeignSelection(selections.BackendSelection):
        pass

    foreign = ForeignSelection(
        **{field.name: getattr(selected, field.name) for field in fields(selected)}
    )
    assert isinstance(foreign, selections.BackendSelection)
    assert type(foreign) is not selections.BackendSelection

    def forbidden(*args, **kwargs):
        pytest.fail("Rejected public record reached a later admission leaf")

    monkeypatch.setattr(service.result_v3, "validate_request", forbidden)
    monkeypatch.setattr(service.SidecarJob, "from_selection", forbidden)
    monkeypatch.setattr(ForeignSelection, "assert_current", forbidden)
    # The exact supported public record reaches the intentional dormant gate.
    with pytest.raises(service.bridge.BridgeError, match="dormant"):
        service.DataOnlyJob({}, selected, current_selection=forbidden)
    # A subclass must fail sooner, even though it carries the same valid policy.
    with pytest.raises(service.bridge.BridgeError, match="captured backend selection"):
        service.DataOnlyJob({}, foreign, current_selection=forbidden)
