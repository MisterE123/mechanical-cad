"""Exact captured host records for synthetic receipts; never native qualification.

Linux retains its real manual selection. Windows uses public bundled capture and
regular inert files in the test's own directory, so real path/type/currentness
checks remain active. No interpreter, solver, DLL or Blender is executed.
"""

import importlib
import sys
import types
from dataclasses import asdict
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def capture_windows_fixture(selections, directory, *, generation, lifetime_id):
    """Construct the namespace's exact records on the actual Windows host."""
    if sys.platform != "win32":
        raise AssertionError("Inert Windows receipt fixtures require the actual Windows host")
    from test_windows_runtime import Fixture

    data = Fixture(
        **{
            "src/mechanical_cad/__init__.py": b"# Inert receipt fixture, not project source.\n",
            "src/mechanical_cad/sketch_solver.py": b"# Inert receipt fixture, not a solver.\n",
        }
    )
    directory = Path(directory).resolve()
    package_root = directory / "Installed"
    known_folder = directory / "Local"
    cache_root = known_folder / "MechanicalCAD" / "r"
    bundle_root = cache_root / data.bundle_id
    package_root.mkdir(parents=True, exist_ok=True)
    for relative, raw in data.contents.items():
        path = bundle_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)

    namespace = selections.__package__
    manifest = importlib.import_module(namespace + ".runtime_bundle_manifest")
    cache = importlib.import_module(namespace + ".windows_cache")
    launch = importlib.import_module(namespace + ".runtime_bundle_launch")
    descriptor = manifest.BundleDescriptor(
        **{
            **asdict(data.descriptor),
            "root": str(bundle_root),
            "python_path": str(bundle_root / "python" / "python.exe"),
            "bootstrap_path": str(bundle_root / "bootstrap.py"),
        }
    )
    policy = launch.capture_bundled_policy(
        descriptor,
        package_root=str(package_root),
        cache_root=str(cache_root),
        release_data=data.release,
        constants=dict(data.constants),
        windows_cache=cache.WindowsCacheLocation(str(known_folder), str(cache_root)),
    )
    return selections.BackendSelection.capture_bundled(
        policy, 60.0, generation=generation, lifetime_id=lifetime_id
    )


@pytest.fixture
def captured_backend(tmp_path_factory, monkeypatch):
    """Factory preserving production guards while forbidding native work."""
    attempts, guarded = [], set()
    directory = None

    def no_native(*args, **kwargs):
        attempts.append("native process/API attempted")
        pytest.fail("Synthetic receipt fixture attempted native process/API work")

    def capture(selections, *, generation, lifetime_id):
        nonlocal directory
        namespace = selections.__package__
        if namespace not in guarded:
            jobs = importlib.import_module(namespace + ".sidecar_job")
            windows = importlib.import_module(namespace + ".windows_runtime")
            monkeypatch.setattr(
                jobs,
                "subprocess",
                types.SimpleNamespace(
                    Popen=no_native, TimeoutExpired=jobs.subprocess.TimeoutExpired
                ),
            )
            monkeypatch.setattr(windows, "WindowsRuntimeAPI", no_native)
            monkeypatch.setattr(windows, "Win32API", no_native)
            guarded.add(namespace)
        if sys.platform == "win32":
            # Avoid pytest's long per-node directory names: production requires
            # ordinary short DOS paths, including the full bundle-id suffix.
            if directory is None:
                directory = tmp_path_factory.mktemp("w")
                capture.windows_directory = directory
            return capture_windows_fixture(
                selections, directory, generation=generation, lifetime_id=lifetime_id
            )
        if sys.platform == "linux":
            return selections.BackendSelection.capture(
                str(ROOT),
                sys.executable,
                generation=generation,
                lifetime_id=lifetime_id,
                environment={},
            )
        pytest.skip("no qualified captured host profile")

    capture.windows_directory = directory
    yield capture
    # Expected failure/cancellation paths cannot swallow an accidental launch.
    assert attempts == []
