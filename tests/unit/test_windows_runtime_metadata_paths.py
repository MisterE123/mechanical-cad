"""Synthetic metadata paths only; no drives/files/native processes are created."""

import ctypes
import ntpath
import sys
from dataclasses import replace

import pytest
import test_windows_runtime as f

WINDOWS_HOST = pytest.mark.skipif(sys.platform != "win32", reason="Actual Windows public profile")


@pytest.fixture
def finite_metadata(monkeypatch):
    attempts = []

    def forbidden(*args, **kwargs):
        attempts.append("native API/process/private capture")
        pytest.fail(attempts[-1])

    monkeypatch.setattr(ctypes, "WinDLL", forbidden, raising=False)
    monkeypatch.setattr(f.cache, "_WindowsAPI", forbidden)
    monkeypatch.setattr(f.jobs.subprocess, "Popen", forbidden)
    monkeypatch.setattr(
        f.selection.BackendSelection, "_capture_windows_bundled_transport", classmethod(forbidden)
    )

    def make(drive):
        v = f.Fixture()
        base = drive + r":\a\_temp\release-tests-1\pytest\wp0"
        v.package, v.known_folder = ntpath.join(base, "package"), ntpath.join(base, "Local")
        v.location = f.cache.WindowsCacheLocation(
            v.known_folder, ntpath.join(v.known_folder, "MechanicalCAD", "r")
        )
        v.cache = v.location.cache_root
        v.root = ntpath.join(v.cache, v.bundle_id)
        v.descriptor = replace(
            v.descriptor,
            root=v.root,
            python_path=ntpath.join(v.root, "python", "python.exe"),
            bootstrap_path=ntpath.join(v.root, "bootstrap.py"),
        )
        return f.install(monkeypatch, v)

    yield make
    assert attempts == []


def run_public_selection_job(env):
    selected = f.selection.BackendSelection.capture_bundled(
        env.fixture.policy(), 10, generation=0, lifetime_id="cross-drive-metadata"
    )
    assert type(selected) is f.selection.BackendSelection
    job = f.jobs.SidecarJob.from_selection(f.prepared(), selected)
    job.start()
    assert job.wait(5)
    return job


@WINDOWS_HOST
@pytest.mark.parametrize("drive", ["C", "D"])
def test_public_owner_accepts_same_or_cross_drive_directory_metadata(finite_metadata, drive):
    env = finite_metadata(drive)
    assert env.runtime.system == r"C:\Windows"
    job = run_public_selection_job(env)
    assert job.state == "ready"
    assert job.result() == {"protocol_version": 1, "ok": True}
    assert job._bundle_owner.cleanup_complete and not job._bundle_owner.cleanup_uncertain
    assert env.events.count("create") == 1 and env.pin.releases == 1 and not env.pin.held


@WINDOWS_HOST
@pytest.mark.parametrize("damage", ["two_links", "reparse", "unrelated_error"])
def test_cross_drive_metadata_correction_keeps_rejections(finite_metadata, damage):
    env = finite_metadata("D")
    if damage == "two_links":
        env.runtime.info_change = lambda info: (
            replace(info, links=2) if not info.directory else info
        )
    elif damage == "reparse":
        env.runtime.info_change = lambda info: replace(info, reparse=True)
    else:

        def fail(event):
            if event == "anchor_info":
                raise RuntimeError("unrelated metadata fault")

        env.runtime.hook = fail
    job = run_public_selection_job(env)
    assert job.state == "failed" and job._response is None and "create" not in env.events
    with pytest.raises(f.jobs.bridge.BridgeError):
        job.result()
    assert job._bundle_owner.cleanup_complete and not job._bundle_owner.cleanup_uncertain
    assert env.pin.releases == 1 and not env.pin.held


@WINDOWS_HOST
def test_cross_drive_file_lookup_still_rejects_unexpected_mount(finite_metadata):
    env = finite_metadata("D")
    handle = env.runtime.open_anchor(r"C:\unexpected.bin", directory=False)
    try:
        with pytest.raises(ValueError, match="mount"):
            env.runtime.info(handle)
    finally:
        env.runtime.close_anchor(handle)
    assert env.events == ["open_anchor", "anchor_info", "close_anchor"]
