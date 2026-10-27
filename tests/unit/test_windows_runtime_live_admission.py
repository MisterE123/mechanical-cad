"""Live policy controls independent of historical inverse-fixture setup."""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "live_runtime_policy_helpers", ROOT / "tests/unit/test_standalone_runtime_boundary.py"
)
gates = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gates)


def check(root):
    gates.assert_import_boundary(root)
    gates.assert_windows_cache_dependency_leaf(root)
    gates.assert_windows_cache_query_is_dormant(root)


def test_clean_current_source_passes_live_cache_policy():
    check(ROOT)


@pytest.mark.parametrize(
    "filename,before,after",
    [
        ("backend_selection.py", b"_DEFAULT_TIMEOUT = object()", b"_DEFAULT_TIMEOUT = None"),
        (
            "backend_selection.py",
            b'return 240.0 if bundled_platform == "windows-x64" else 60.0',
            b'return 241.0 if bundled_platform == "windows-x64" else 60.0',
        ),
        (
            "windows_cache.py",
            b'provider: str = "local-app-data"',
            b'provider: str = "caller-selected"',
        ),
    ],
)
def test_later_reviewed_policy_symbols_require_exact_current_bytes(
    tmp_path, filename, before, after
):
    gates.assert_windows_runtime_cache_finite_symbols(ROOT)
    for name in (
        "backend_selection.py",
        "runtime_bundle_launch.py",
        "windows_cache.py",
        "windows_runtime.py",
    ):
        source = ROOT / "blender_addon/mechanical_cad_blender" / name
        target = tmp_path / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    target = tmp_path / "blender_addon/mechanical_cad_blender" / filename
    raw = target.read_bytes()
    assert raw.count(before) == 1
    target.write_bytes(raw.replace(before, after))
    with pytest.raises(AssertionError):
        gates.assert_windows_runtime_cache_finite_symbols(tmp_path)


@pytest.mark.parametrize(
    "filename, statement",
    [
        ("registration.py", "query_windows_cache_location()"),
        ("registration.py", "alias = windows_cache.query_windows_cache_location"),
        ("registration.py", "getattr(windows_cache, 'query_windows_cache_location')()"),
        ("registration.py", "from .windows_cache import query_windows_cache_location as hidden"),
        ("registration.py", "def query_windows_cache_location(): pass"),
        ("windows_cache.py", "from .windows_package_cache import PackageCacheAPI as hidden"),
        (
            "windows_cache.py",
            "from .windows_package_cache import PackageCacheAPI, PackageCacheCleanupError",
        ),
        ("windows_cache.py", "from .windows_package_host import WindowsPackageHost"),
        (
            "windows_cache.py",
            "def delayed():\n    from .windows_package_host import WindowsPackageHost",
        ),
        ("windows_cache.py", "from .runtime_bundle_launch import _windows_path"),
        (
            "windows_cache.py",
            "def delayed():\n    from .runtime_bundle_prepare import BundlePreparationJob",
        ),
        ("windows_cache.py", "import OCP"),
        ("windows_cache.py", "__import__('windows_package_host')"),
        ("windows_cache.py", "importlib.import_module('windows_package_cache')"),
        ("backend_runtime.py", "from .windows_package_cache import PackageCacheAPI"),
        (
            "runtime_bundle_prepare.py",
            "from .windows_cache import query_windows_automatic_cache_location as hidden",
        ),
    ],
)
def test_unreviewed_live_edges_aliases_dynamic_names_and_call_scopes_reject(
    tmp_path, filename, statement
):
    # Copy current production bytes only. No inverse or historical source is
    # substituted, and the clean copied positive must pass before each mutation.
    for prefix in ("src", "blender_addon"):
        for source in (ROOT / prefix).rglob("*.py"):
            target = tmp_path / source.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
    check(tmp_path)
    target = tmp_path / "blender_addon/mechanical_cad_blender" / filename
    target.write_bytes(target.read_bytes() + b"\n" + statement.encode() + b"\n")
    with pytest.raises(AssertionError):
        check(tmp_path)


@pytest.mark.parametrize(
    "damage",
    [
        "missing",
        "duplicate",
        "misplaced",
        "wrong_error",
        "wrong_cause",
        "changed_guard",
        "later_checkpoint",
        "finally_cleanup",
        "extra_call",
    ],
)
def test_live_failed_start_insertion_requires_exact_bytes_and_location(tmp_path, damage):
    gates.assert_windows_runtime_cache_finite_symbols(ROOT)
    for name in (
        "backend_selection.py",
        "runtime_bundle_launch.py",
        "windows_cache.py",
        "windows_runtime.py",
    ):
        source = ROOT / "blender_addon/mechanical_cad_blender" / name
        target = tmp_path / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    gates.assert_windows_runtime_cache_finite_symbols(tmp_path)
    target = tmp_path / "blender_addon/mechanical_cad_blender/windows_runtime.py"
    raw = target.read_bytes()
    reviewed = (
        b"            if self.process.error is not None:\n"
        b"                raise self.process.error\n"
    )
    assert raw.count(reviewed) == 1
    if damage == "missing":
        changed = raw.replace(reviewed, b"", 1)
    elif damage == "duplicate":
        changed = raw.replace(reviewed, reviewed * 2, 1)
    elif damage == "misplaced":
        changed = raw.replace(reviewed, b"", 1)
        anchor = b"            self.process.start()\n"
        assert changed.count(anchor) == 1
        changed = changed.replace(anchor, reviewed + anchor, 1)
    elif damage in {"wrong_error", "wrong_cause", "changed_guard", "extra_call"}:
        replacement = {
            "wrong_error": reviewed.replace(
                b"raise self.process.error", b'raise ProcessError("injected")'
            ),
            "wrong_cause": reviewed.replace(
                b"raise self.process.error", b"raise self.process.error from None"
            ),
            "changed_guard": reviewed.replace(b"is not None", b"!= None"),
            "extra_call": reviewed + b"            self.checkpoint()\n",
        }[damage]
        changed = raw.replace(reviewed, replacement, 1)
    else:
        before, after = {
            "later_checkpoint": (
                b"            stdout = self.process.read_output()\n            self.checkpoint()\n",
                b"            stdout = self.process.read_output()\n            self.cleanup_checkpoint()\n",
            ),
            "finally_cleanup": (
                b"        finally:\n            self.cleanup()\n",
                b"        finally:\n            self.cleanup_checkpoint()\n",
            ),
        }[damage]
        assert raw.count(before) == 1
        changed = raw.replace(before, after, 1)
    assert changed != raw
    target.write_bytes(changed)
    with pytest.raises(AssertionError):
        gates.assert_windows_runtime_cache_finite_symbols(tmp_path)
