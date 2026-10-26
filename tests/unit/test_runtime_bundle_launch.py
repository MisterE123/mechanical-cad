"""Portable bundled contracts and native-host admission; no CAD/native child launch.

Linux descriptor/flock/process lifecycle coverage lives in the explicit Linux
module. Windows transport/kernel-leaf mocks remain in test_windows_transport.
"""

import importlib
import os
import sys
from dataclasses import asdict
from types import SimpleNamespace

import pytest


def profile_for(platform, tmp_path):
    if platform == "linux-x64":
        import test_runtime_bundle_launch_linux as implementation

        fixture = implementation.Fixture(tmp_path, materialize=False)
        release = fixture.release_data
        location = None
    else:
        import test_windows_runtime as implementation

        fixture = implementation.Fixture()
        release = fixture.release
        location = fixture.location

    def capture(**changes):
        arguments = dict(
            descriptor=fixture.descriptor,
            package_root=str(fixture.package),
            cache_root=str(fixture.cache),
            release_data=release,
            constants=fixture.constants,
            windows_cache=location,
        )
        arguments.update(changes)
        return implementation.launch.capture_bundled_policy(**arguments)

    return SimpleNamespace(
        fixture=fixture,
        capture=capture,
        launch=implementation.launch,
        manifests=implementation.m,
        selection=implementation.selection,
    )


@pytest.fixture(
    params=[
        pytest.param(
            "linux-x64",
            marks=pytest.mark.skipif(
                sys.platform != "linux", reason="Linux policy capture requires a real Linux host"
            ),
        ),
        "windows-x64",
    ]
)
def profile(request, tmp_path):
    # Pure records only; no materialization, chmod, filesystem links or Win32 API.
    value = profile_for(request.param, tmp_path)
    assert list(tmp_path.iterdir()) == []
    value.capture()  # Clean positive prevents vacuous mutation rejection.
    return value


@pytest.mark.parametrize("platform", ["linux-x64", "windows-x64"])
def test_constant_record_shape_and_immutability_are_portable(tmp_path, platform):
    profile = profile_for(platform, tmp_path)
    original = dict(profile.fixture.constants)
    constants = profile.launch.BundledLaunchConstants(**original)
    assert asdict(constants) == original
    assert constants.PLATFORM == platform
    profile.fixture.constants["ENTRY_LOADER"] = "caller mutation"
    assert constants.ENTRY_LOADER == original["ENTRY_LOADER"]
    with pytest.raises((AttributeError, TypeError)):
        constants.ENTRY_LOADER = "mutated capture"
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("damage", ["missing", "unknown"])
def test_constant_field_membership_rejects_before_host_dependent_work(profile, damage):
    constants = dict(profile.fixture.constants)
    if damage == "missing":
        del constants["ENTRY_LOADER"]
    else:
        constants["EXTRA"] = "never accepted"
    with pytest.raises(profile.manifests.BundleError, match="constant fields"):
        profile.capture(constants=constants)


def test_public_capture_matches_the_actual_host_profile(profile):
    policy = profile.capture()
    expected = {("linux", "posix"): "linux-x64", ("win32", "nt"): "windows-x64"}.get(
        (sys.platform, os.name)
    )
    if policy.constants.PLATFORM == expected:
        captured = profile.selection.BackendSelection.capture_bundled(
            policy, generation=0, lifetime_id="actual-host"
        )
        assert captured.bundled_policy.constants.PLATFORM == expected
    else:
        with pytest.raises(
            profile.selection.SelectionError, match="does not match this operating system"
        ):
            profile.selection.BackendSelection.capture_bundled(
                policy, generation=0, lifetime_id="actual-host"
            )


@pytest.mark.skipif(sys.platform != "win32", reason="actual Windows host admission guard")
def test_native_windows_host_admits_windows_profile_without_manual_backend_bypass(tmp_path):
    assert os.name == "nt"
    profile = profile_for("windows-x64", tmp_path)
    policy = profile.capture()
    capture = profile.selection.BackendSelection.capture_bundled
    selected = capture(policy, generation=3, lifetime_id="native-windows-test")
    assert selected.timeout == 240.0
    assert selected.bundled_policy.constants.PLATFORM == "windows-x64"
    assert selected.project_root == profile.fixture.root
    selected.assert_current(capture(policy, generation=3, lifetime_id="native-windows-test"))
    with pytest.raises(profile.selection.SelectionError):
        selected.assert_current(capture(policy, generation=4, lifetime_id="native-windows-test"))
    assert capture(policy, 23.0, generation=3, lifetime_id="native-windows-test").timeout == 23.0
    evidence = importlib.import_module(profile.selection.__package__ + ".guarded_evidence")
    jobs = importlib.import_module(profile.selection.__package__ + ".sidecar_job")
    for record in (selected, policy, policy.descriptor):
        assert type(record) is not evidence.GuardedEvidence
    with pytest.raises(jobs.bridge.BridgeError, match="prepared request"):
        jobs.SidecarJob.from_selection(policy.descriptor, selected)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.skipif(sys.platform != "win32", reason="actual Windows unsupported-backend guard")
def test_native_windows_host_rejects_linux_policy_and_manual_backend_before_io(
    tmp_path, monkeypatch
):
    profile = profile_for("linux-x64", tmp_path)
    profile.launch.BundledLaunchConstants(
        **profile.fixture.constants
    )  # Valid data, unsupported host.
    with pytest.raises(profile.launch.BundleLaunchError, match="Linux only"):
        profile.capture()
    monkeypatch.setattr(
        profile.selection, "resolved_path", lambda *a: pytest.fail("external path resolved")
    )
    with pytest.raises(profile.selection.SelectionError, match="Linux only"):
        profile.selection.BackendSelection.capture(generation=0, lifetime_id="native-windows-test")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("SCHEMA_VERSION", True),
        ("BUILD_STATUS", "QUALIFIED"),
        ("PLATFORM", "windows-x64"),
        ("PYTHON_VERSION", [3, 12, 15, "final", 0]),
        ("PYTHON_VERSION", (3, 12, 15, "final", False)),
        ("PYTHON_FLAGS", ("-c",)),
        ("PYTHON_BITS", True),
        ("PYTHON_PATH", "/usr/bin/python"),
        ("BOOTSTRAP_PATH", "other.py"),
        ("RELEASE_IDENTITY_PATH", "other.json"),
        ("RELEASE_IDENTITY_BYTES", b"{}"),
        ("RELEASE_IDENTITY_SHA256", "d" * 64),
        ("BUNDLE_MANIFEST_SHA256", "d" * 64),
        ("PAYLOAD_SHA256", "d" * 64),
        ("RUNTIME_LOCK_SHA256", "d" * 64),
        ("SOURCE_COMMIT", "d" * 40),
        ("ENTRY_LOADER", ""),
        ("ENTRY_LOADER", "x" * 4097),
        ("ENTRY_LOADER", "Ã©"),
        ("ENTRY_LOADER", "x\0y"),
        ("EXTRA", 1),
    ],
)
def test_inconsistent_or_mutable_constants_are_rejected(profile, field, value):
    constants = dict(profile.fixture.constants)
    if field == "PLATFORM":
        value = "linux-x64" if constants["PLATFORM"] == "windows-x64" else "windows-x64"
    constants[field] = value
    with pytest.raises(profile.manifests.BundleError):
        profile.capture(constants=constants)
