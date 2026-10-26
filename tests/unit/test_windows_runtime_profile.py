"""Preparatory Windows profile and fail-closed redirection diagnostics.

These pure checks are not native runtime or public-admission qualification.
"""

import hashlib
import importlib
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest
from test_windows_cache import recipe, release, w

PACKAGE = "mcad_windows_profile_test"
package = types.ModuleType(PACKAGE)
package.__path__ = [
    str(Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender")
]
sys.modules[PACKAGE] = package
launch = importlib.import_module(PACKAGE + ".runtime_bundle_launch")


def constants(platform, version):
    raw = b"{}"
    digest = hashlib.sha256(raw).hexdigest()
    return dict(
        SCHEMA_VERSION=1,
        BUILD_STATUS="UNQUALIFIED_CONTRACT_ARTIFACT",
        SOURCE_COMMIT="a" * 40,
        RUNTIME_LOCK_SHA256="b" * 64,
        BUNDLE_ID="c" * 64,
        PLATFORM=platform,
        PYTHON_IMPLEMENTATION="cpython",
        PYTHON_VERSION=(3, 12, version, "final", 0),
        PYTHON_CACHE_TAG="cpython-312",
        PYTHON_BITS=64,
        PYTHON_PATH="python/python.exe" if platform == "windows-x64" else "python/bin/python3.12",
        PYTHON_FLAGS=launch.PYTHON_FLAGS,
        BOOTSTRAP_PATH="bootstrap.py",
        BOOTSTRAP_SHA256="d" * 64,
        RELEASE_IDENTITY_PATH="release_identity.json",
        RELEASE_IDENTITY_BYTES=raw,
        RELEASE_IDENTITY_SHA256=digest,
        BUNDLE_MANIFEST_SHA256="e" * 64,
        PAYLOAD_SHA256="f" * 64,
        ENTRY_LOADER="raise SystemExit('inert fixture')",
    )


@pytest.mark.parametrize("platform,version", [("windows-x64", 10), ("linux-x64", 15)])
def test_exact_platform_specific_python_profile(platform, version):
    assert (
        launch.BundledLaunchConstants(**constants(platform, version)).PYTHON_VERSION[2] == version
    )


@pytest.mark.parametrize(
    "platform,version", [("windows-x64", 15), ("windows-x64", 11), ("linux-x64", 10)]
)
def test_other_patch_profile_is_not_silently_accepted(platform, version):
    with pytest.raises(launch.BundleLaunchError, match="isolated Python profile"):
        launch.BundledLaunchConstants(**constants(platform, version))


def test_redirected_cache_still_rejects_with_specific_diagnostic():
    owner = w.WindowsCacheOwner(
        recipe(), package_root="C:\\Installed", expected_platform="windows-x64", release=release()
    )
    actual = w._Info((1, 2), "C:\\DifferentPhysicalFolder", 0x10, True, True, 0, False)
    with pytest.raises(w.WindowsCacheError) as error:
        owner._validate_info(actual, recipe().known_folder, directory=True)
    assert error.value.code == "windows_cache_redirected_location"
    assert not owner._created_paths


@pytest.mark.parametrize(
    "attribute,value", [("disk", False), ("attributes", 0x410), ("path", None)]
)
def test_bad_observation_does_not_become_a_redirection_alias(attribute, value):
    from dataclasses import replace

    owner = w.WindowsCacheOwner(
        recipe(), package_root="C:\\Installed", expected_platform="windows-x64", release=release()
    )
    actual = w._Info((1, 2), recipe().known_folder, 0x10, True, True, 0, False)
    with pytest.raises(w.WindowsCacheError) as error:
        owner._validate_info(
            replace(actual, **{attribute: value}), recipe().known_folder, directory=True
        )
    assert error.value.code == "windows_cache_unsupported_location"


@pytest.fixture
def image_audit(monkeypatch):
    """Pure API observations; not native DLL-origin qualification."""
    import ctypes

    path = Path(__file__).resolve().parents[2] / "scripts/standalone_child_bootstrap.py"
    spec = importlib.util.spec_from_file_location("windows_origin_unit", path)
    bootstrap = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bootstrap)
    images = [
        "C:\\Trusted\\python\\python.exe",
        "C:\\Trusted\\python\\python312.dll",
        "C:\\Trusted\\packages\\OCP\\OCP.cp312-win_amd64.pyd",
        "C:\\Trusted\\packages\\slvs\\solvespace.pyd",
        "C:\\Windows\\System32\\ntdll.dll",
    ]

    class Function:
        def __init__(self, callback):
            self.callback = callback

        def __call__(self, *args):
            return self.callback(*args)

    def enumerate_images(process, modules, size, needed, flags):
        for i in range(len(images)):
            modules[i] = layout.get("test_handles", list(range(1, len(images) + 1)))[i]
        ctypes.cast(needed, ctypes.POINTER(ctypes.c_uint32))[0] = layout.get(
            "test_needed", len(images) * ctypes.sizeof(ctypes.c_void_p)
        )
        return layout.get("test_success", 1)

    def module_name(handle, output, count):
        output.value = images[handle - 1]
        return len(output.value)

    def system_name(output, count):
        output.value = "C:\\Windows\\System32"
        return len(output.value)

    kernel = types.SimpleNamespace(
        GetCurrentProcess=Function(lambda: 1),
        K32EnumProcessModulesEx=Function(enumerate_images),
        GetModuleFileNameW=Function(module_name),
        GetSystemDirectoryW=Function(system_name),
    )
    monkeypatch.setattr(ctypes, "WinDLL", lambda *args, **kwargs: kernel, raising=False)
    checked = []
    monkeypatch.setattr(bootstrap, "_checked_path", lambda path, kind, os: checked.append(path))
    monkeypatch.setattr(bootstrap, "_checked_windows_image", lambda path: checked.append(path))
    layout = dict(
        platform="windows-x64",
        prefix="C:\\Trusted\\python",
        native="C:\\Trusted\\python\\DLLs",
        packages="C:\\Trusted\\packages",
        executable=images[0],
        suffix=".cp312-win_amd64.pyd",
    )
    return bootstrap, images, layout, checked


def test_mapped_images_accept_only_private_runtime_and_direct_system32(image_audit, capsys):
    bootstrap, images, layout, checked = image_audit
    bootstrap._verify_windows_images(layout)
    assert checked == images[:-1]
    output = capsys.readouterr()
    assert output.out == ""
    assert json.loads(output.err) == {
        "windows_mapped_images_checked": 5,
        "private_images": 4,
        "platform": "windows-x64",
    }
    assert not any(path in output.err for path in images)


@pytest.mark.parametrize(
    "foreign", ["C:\\HostileCwd\\injected.dll", "C:\\Trusted\\python-other\\fake.dll"]
)
def test_unexpected_mapped_image_is_refused(image_audit, foreign):
    bootstrap, images, layout, checked = image_audit
    images.append(foreign)
    with pytest.raises(bootstrap.BootstrapError, match="mapped_dll_origin_rejected"):
        bootstrap._verify_windows_images(layout)


@pytest.mark.parametrize("missing", range(4))
def test_each_required_native_image_must_appear(image_audit, missing):
    bootstrap, images, layout, checked = image_audit
    images.pop(missing)
    with pytest.raises(bootstrap.BootstrapError, match="mapped_dll_inventory_incomplete"):
        bootstrap._verify_windows_images(layout)


@pytest.mark.parametrize(
    "key,value",
    [
        ("test_needed", 0),
        ("test_needed", 4097),
        ("test_needed", 3),
        ("test_success", 0),
        ("test_handles", [1, 1, 3, 4, 5]),
        ("test_handles", [1, 0, 3, 4, 5]),
    ],
)
def test_empty_truncated_failed_or_duplicate_inventory_is_refused(image_audit, key, value):
    bootstrap, images, layout, checked = image_audit
    layout[key] = value
    with pytest.raises(bootstrap.BootstrapError, match="mapped_dll_inventory_unavailable"):
        bootstrap._verify_windows_images(layout)


def test_duplicate_image_paths_are_refused(image_audit):
    bootstrap, images, layout, checked = image_audit
    images.append(images[0])
    with pytest.raises(bootstrap.BootstrapError, match="mapped_dll_inventory_unavailable"):
        bootstrap._verify_windows_images(layout)


@pytest.mark.parametrize("damage", [None, "identity", "alias", "reparse", "hardlink", "close"])
def test_loader_case_only_origin_needs_two_full_file_identities_and_certain_closes(
    monkeypatch, damage
):
    import ntpath
    import stat

    path = Path(__file__).resolve().parents[2] / "scripts/standalone_child_bootstrap.py"
    spec = importlib.util.spec_from_file_location("windows_case_proof_unit", path)
    bootstrap = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bootstrap)
    original, canonical = "C:\\Trusted\\VCRUNTIME140.dll", "C:\\Trusted\\vcruntime140.dll"
    opened, closed = [], []
    file = types.SimpleNamespace(
        st_mode=stat.S_IFREG,
        st_nlink=1,
        st_dev=1,
        st_ino=123456789012345678901,
        st_size=4096,
        st_file_attributes=0,
    )

    def open_file(name, flags):
        opened.append(name)
        return len(opened)

    def info(descriptor):
        value = dict(vars(file))
        if damage == "identity" and descriptor == 2:
            value["st_ino"] += 1
        if damage == "hardlink":
            value["st_nlink"] = 2
        return types.SimpleNamespace(**value)

    def close_file(descriptor):
        closed.append(descriptor)
        if damage == "close":
            raise OSError("uncertain close")

    fake = types.SimpleNamespace(
        path=types.SimpleNamespace(
            realpath=lambda value: (
                canonical if damage != "alias" else "C:\\Other\\vcruntime140.dll"
            ),
            normpath=ntpath.normpath,
            isabs=ntpath.isabs,
            dirname=ntpath.dirname,
        ),
        lstat=lambda name: types.SimpleNamespace(
            st_mode=stat.S_IFREG, st_file_attributes=0x400 if damage == "reparse" else 0
        ),
        O_RDONLY=0,
        O_BINARY=0x8000,
        open=open_file,
        fstat=info,
        close=close_file,
    )
    monkeypatch.setattr(bootstrap, "_checked_path", lambda *args: None)
    if damage is None:
        assert bootstrap._checked_windows_image(original, fake) == canonical
        assert opened == [original, canonical] and closed == [2, 1]
    else:
        with pytest.raises(bootstrap.BootstrapError):
            bootstrap._checked_windows_image(original, fake)
        assert closed == list(reversed(range(1, len(opened) + 1)))
        assert len(set(closed)) == len(closed)
