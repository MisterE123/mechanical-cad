"""Pure synthetic bootstrap contracts: no native CAD/Blender/Windows launch."""

import ast
import hashlib
import importlib.machinery
import importlib.util
import io
import json
import os
import stat
import sys
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
PROJECT_VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
SCRIPT = ROOT / "scripts/standalone_child_bootstrap.py"
SPEC = importlib.util.spec_from_file_location("_mcad_bootstrap_pure_test", SCRIPT)
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)


class Finder:
    def __init__(self, origins):
        self.origins = origins
        self.calls = []

    def find_spec(self, name, search):
        self.calls.append((name, tuple(search)))
        origin, package = self.origins[name]
        loader_type = (
            importlib.machinery.SourceFileLoader
            if origin.endswith(".py")
            else importlib.machinery.ExtensionFileLoader
        )
        spec = importlib.machinery.ModuleSpec(
            name, loader_type(name, origin), origin=origin, is_package=package
        )
        if package:
            spec.submodule_search_locations = [str(Path(origin).parent)]
        return spec


class DLLHandle:
    def __init__(self, path, events):
        self.path, self.events = path, events
        self.closed, self.fail = False, False

    def close(self):
        assert not self.closed
        self.closed = True
        self.events.append(("close", self.path))
        if self.fail:
            raise OSError("untrusted exception details")


class DLLPolicyFunction:
    def __init__(self, events):
        self.events = events
        self.result = 1

    def __call__(self, flags):
        self.events.append(("default", flags))
        return self.result


def fixture(tmp_path, monkeypatch, *, windows=False):
    platform = "windows-x64" if windows else "linux-x64"
    source, lock = "1" * 40, "2" * 64
    bundle_id = hashlib.sha256(
        json.dumps([source, lock, platform], separators=(",", ":")).encode("ascii")
    ).hexdigest()
    root = tmp_path / "private cache 測定" / bundle_id
    prefix = root / "python"
    stdlib = prefix / "Lib" if windows else prefix / "lib/python3.12"
    native = prefix / "DLLs" if windows else stdlib / "lib-dynload"
    executable = prefix / "python.exe" if windows else prefix / "bin/python3.12"
    placeholder = prefix / "python312.zip" if windows else prefix / "lib/python312.zip"
    suffix = ".cp312-win_amd64.pyd" if windows else ".cpython-312-x86_64-linux-gnu.so"
    origins = {}
    for name, directory in (
        ("mechanical_cad", root / "src/mechanical_cad"),
        ("OCP", root / "packages/OCP"),
        ("slvs", root / "packages/slvs"),
    ):
        directory.mkdir(parents=True)
        target = directory / "__init__.py"
        target.write_bytes(b"# synthetic package; never imported\n")
        origins[name] = str(target), True
    for name, target in (
        ("mechanical_cad.sidecar", root / "src/mechanical_cad/sidecar.py"),
        ("OCP.OCP", root / ("packages/OCP/OCP" + suffix)),
        (
            "slvs.solvespace",
            root / ("packages/slvs/solvespace.pyd" if windows else "packages/slvs/solvespace.so"),
        ),
    ):
        target.write_bytes(b"INERT SYNTHETIC FILE; NOT NATIVE CODE")
        origins[name] = str(target), False
    for path in (stdlib, native, executable.parent, root / "packages/cadquery_ocp_novtk.libs"):
        path.mkdir(parents=True, exist_ok=True)
    executable.write_bytes(b"INERT SYNTHETIC EXECUTABLE")
    if windows:
        (prefix / "python312.dll").write_bytes(b"INERT SYNTHETIC DLL")
    (root / "bootstrap.py").write_bytes(SCRIPT.read_bytes())
    descriptor = dict(
        schema_version=1,
        bundle_id=bundle_id,
        source_commit=source,
        runtime_lock_sha256=lock,
        platform=platform,
        manifest_sha256="3" * 64,
        payload_sha256="4" * 64,
        root=str(root),
        python_path=str(executable),
        bootstrap_path=str(root / "bootstrap.py"),
    )
    (root / ".bundle-ready.json").write_bytes(
        json.dumps(
            {key: descriptor[key] for key in ("bundle_id", "manifest_sha256", "payload_sha256")},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    )
    startup = [placeholder, native, stdlib, prefix] if windows else [placeholder, stdlib, native]
    flags = SimpleNamespace(
        **dict.fromkeys(
            (
                "isolated",
                "ignore_environment",
                "no_site",
                "no_user_site",
                "dont_write_bytecode",
                "safe_path",
                "utf8_mode",
            ),
            1,
        ),
        optimize=0,
    )
    system = SimpleNamespace(
        flags=flags,
        dont_write_bytecode=True,
        _xoptions={"utf8": True},
        orig_argv=[str(executable), "-I", "-S", "-B", "-X", "utf8", "-c", "trusted", "88"],
        argv=["-c", "88"],
        implementation=SimpleNamespace(name="cpython", cache_tag="cpython-312"),
        version_info=(3, 12, 10 if windows else 15, "final", 0),
        maxsize=2**63 - 1,
        abiflags="",
        platform="win32" if windows else "linux",
        executable=str(executable),
        prefix=str(prefix),
        base_prefix=str(prefix),
        exec_prefix=str(prefix),
        base_exec_prefix=str(prefix),
        _base_executable=str(executable),
        _stdlib_dir=str(stdlib),
        path=[str(path) for path in startup],
        modules={},
        builtin_module_names=sys.builtin_module_names,
        stdlib_module_names=sys.stdlib_module_names,
        meta_path=[
            importlib.machinery.BuiltinImporter,
            importlib.machinery.FrozenImporter,
            importlib.machinery.PathFinder,
        ],
        path_importer_cache={"external": "must be cleared"},
        stdin=io.BytesIO(b"unused"),
    )
    operating_system = SimpleNamespace(**{key: getattr(os, key) for key in dir(os)})
    operating_system.name = "nt" if windows else "posix"
    operating_system.getcwd = lambda: str(root)
    handles, events, imported = [], [], []
    policy = DLLPolicyFunction(events)
    if windows:
        import ctypes

        def load_kernel(name, *, use_last_error):
            assert name == "kernel32" and use_last_error is True
            events.append(("bind", name))

            class Function:
                def __init__(self, callback):
                    self.callback = callback

                def __call__(self, *args):
                    return self.callback(*args)

            images = [
                str(executable),
                str(prefix / "python312.dll"),
                origins["OCP.OCP"][0],
                origins["slvs.solvespace"][0],
            ]

            def enumerate_images(process, modules, size, needed, flags):
                for index in range(len(images)):
                    modules[index] = index + 1
                ctypes.cast(needed, ctypes.POINTER(ctypes.c_uint32))[0] = len(
                    images
                ) * ctypes.sizeof(ctypes.c_void_p)
                return 1

            def module_name(handle, output, size):
                output.value = images[handle - 1]
                return len(output.value)

            def system_name(output, size):
                output.value = "C:\\Windows\\System32"
                return len(output.value)

            return SimpleNamespace(
                SetDefaultDllDirectories=policy,
                GetCurrentProcess=Function(lambda: 1),
                K32EnumProcessModulesEx=Function(enumerate_images),
                GetModuleFileNameW=Function(module_name),
                GetSystemDirectoryW=Function(system_name),
            )

        monkeypatch.setattr(ctypes, "WinDLL", load_kernel, raising=False)

    def add_dll_directory(path):
        events.append(("open", path))
        handle = DLLHandle(path, events)
        handles.append(handle)
        return handle

    operating_system.add_dll_directory = add_dll_directory
    finder = Finder(origins)
    package = SimpleNamespace(
        __version__=PROJECT_VERSION,
        __file__=origins["mechanical_cad"][0],
        __spec__=SimpleNamespace(origin=origins["mechanical_cad"][0]),
        __path__=[str(root / "src/mechanical_cad")],
    )
    sidecar = SimpleNamespace(
        __file__=origins["mechanical_cad.sidecar"][0],
        __spec__=SimpleNamespace(origin=origins["mechanical_cad.sidecar"][0]),
        main=lambda: 17,
    )

    def importer(name):
        imported.append(name)
        if name in ("OCP.OCP", "slvs.solvespace"):
            origin = origins[name][0]
            return SimpleNamespace(
                __file__=origin,
                __spec__=SimpleNamespace(
                    origin=origin, loader=importlib.machinery.ExtensionFileLoader(name, origin)
                ),
            )
        return {"mechanical_cad": package, "mechanical_cad.sidecar": sidecar}[name]

    monkeypatch.setattr("_imp.extension_suffixes", lambda: [suffix])
    return SimpleNamespace(
        root=root,
        prefix=prefix,
        stdlib=stdlib,
        native=native,
        executable=executable,
        placeholder=placeholder,
        suffix=suffix,
        descriptor=descriptor,
        system=system,
        os=operating_system,
        finder=finder,
        importer=importer,
        imported=imported,
        package=package,
        sidecar=sidecar,
        handles=handles,
        events=events,
        policy=policy,
        data=lambda: json.dumps(descriptor).encode("utf-8"),
    )


def run(value):
    return bootstrap.bootstrap(
        value.data(),
        system=value.system,
        operating_system=value.os,
        finder=value.finder,
        importer=value.importer,
    )


@pytest.mark.parametrize("windows", [False, True])
def test_fixed_dispatch_and_exact_stdin_are_preserved(tmp_path, monkeypatch, windows):
    value = fixture(tmp_path, monkeypatch, windows=windows)
    exact = b' { "nonce": "012345", "raw": "\\u6e2c", "n": 1.00 }\r\n'
    stream = io.BytesIO(exact)
    value.system.stdin = stream

    def main():
        assert value.system.stdin is stream and stream.tell() == 0
        assert stream.read() == exact
        assert all(not handle.closed for handle in value.handles)
        assert value.system.path == [
            str(value.stdlib),
            str(value.native),
            str(value.root / "src"),
            str(value.root / "packages"),
        ]
        assert not value.system.path_importer_cache
        assert value.os.getcwd() == str(value.root)
        return 17

    value.sidecar.main = main
    assert run(value) == 17
    assert value.imported == (
        (["OCP.OCP", "slvs.solvespace"] if value.system.platform == "win32" else [])
        + ["mechanical_cad", "mechanical_cad.sidecar"]
    )
    assert [call[0] for call in value.finder.calls] == [
        "mechanical_cad",
        "OCP",
        "slvs",
        "mechanical_cad.sidecar",
        "OCP.OCP",
        "slvs.solvespace",
    ]
    assert len(value.handles) == (5 if windows else 0)
    assert all(handle.closed for handle in value.handles)
    assert [event[1] for event in value.events if event[0] == "close"] == [
        handle.path for handle in reversed(value.handles)
    ]


@pytest.mark.parametrize(
    "data",
    [
        b"",
        "{}",
        b"x" * (16 * 1024 + 1),
        b"\xff",
        b"{} {}",
        b"[]",
        b"null",
        b'{"schema_version":1,"schema_version":1}',
        b'{"x":NaN}',
        b"[" * 7000 + b"]" * 7000,
        b'{"schema_version": Infinity}',
    ],
    ids=[
        "empty",
        "text-not-bytes",
        "over-byte-budget",
        "invalid-utf8",
        "trailing-json",
        "array",
        "null",
        "duplicate-key",
        "nan",
        "over-depth-budget",
        "infinity",
    ],
)
def test_malformed_or_oversized_descriptor_is_rejected(data):
    with pytest.raises(bootstrap.BootstrapError):
        bootstrap.parse_descriptor(data)


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", True),
        ("schema_version", 2),
        ("root", ["/root"]),
        ("root", "x" * 4097),
        ("root", "bad\0path"),
        ("root", "\ud800"),
        ("source_commit", "A" * 40),
        ("bundle_id", "f" * 64),
        ("runtime_lock_sha256", "not a hash"),
        ("platform", "darwin-arm64"),
    ],
)
def test_descriptor_wrong_values_fail_closed(tmp_path, monkeypatch, field, value):
    case = fixture(tmp_path, monkeypatch)
    case.descriptor[field] = value
    with pytest.raises(bootstrap.BootstrapError):
        run(case)
    assert case.imported == [] and case.system.stdin.tell() == 0


@pytest.mark.parametrize("field", ["entry_point", "capabilities", "sys_path", "code"])
def test_descriptor_cannot_select_code_or_authority(tmp_path, monkeypatch, field):
    value = fixture(tmp_path, monkeypatch)
    value.descriptor[field] = "arbitrary executable text"
    with pytest.raises(bootstrap.BootstrapError, match="descriptor_fields"):
        run(value)


@pytest.mark.parametrize(
    "flag",
    [
        "isolated",
        "ignore_environment",
        "no_site",
        "no_user_site",
        "dont_write_bytecode",
        "safe_path",
        "utf8_mode",
    ],
)
def test_every_isolation_flag_required(tmp_path, monkeypatch, flag):
    value = fixture(tmp_path, monkeypatch)
    setattr(value.system.flags, flag, 0)
    with pytest.raises(bootstrap.BootstrapError, match="isolated_flags_required"):
        run(value)


@pytest.mark.parametrize(
    "attribute,replacement",
    [
        ("version_info", (3, 12, 14, "final", 0)),
        ("maxsize", 2**31 - 1),
        ("abiflags", "t"),
        ("platform", "darwin"),
        ("executable", "/external/python"),
        ("prefix", "/external"),
        ("base_prefix", "/external"),
        ("exec_prefix", "/external"),
        ("base_exec_prefix", "/external"),
        ("_base_executable", "/external/python"),
        ("_stdlib_dir", "/external/stdlib"),
        ("_xoptions", {"utf8": True, "dev": True}),
        ("argv", ["-c", "88", "extra"]),
        ("meta_path", []),
    ],
)
def test_runtime_observation_mismatches_reject(tmp_path, monkeypatch, attribute, replacement):
    value = fixture(tmp_path, monkeypatch)
    setattr(value.system, attribute, replacement)
    with pytest.raises(bootstrap.BootstrapError):
        run(value)
    assert value.imported == []


def test_wrong_native_abi_rejected_before_dispatch(tmp_path, monkeypatch):
    value = fixture(tmp_path, monkeypatch)
    monkeypatch.setattr("_imp.extension_suffixes", lambda: [".cpython-312-aarch64-linux-gnu.so"])
    with pytest.raises(bootstrap.BootstrapError, match="runtime_architecture_mismatch"):
        run(value)


@pytest.mark.parametrize("extra", ["", ".", "/external/packages", "src", "site-packages"])
def test_external_startup_import_path_rejected(tmp_path, monkeypatch, extra):
    value = fixture(tmp_path, monkeypatch)
    value.system.path.append(extra)
    with pytest.raises(bootstrap.BootstrapError, match="startup_import_path_mismatch"):
        run(value)


@pytest.mark.parametrize(
    "name",
    [
        "site",
        "sitecustomize",
        "usercustomize",
        "bpy",
        "OCP",
        "OCP.OCP",
        "slvs",
        "mechanical_cad",
        "mechanical_cad.sidecar",
    ],
)
def test_forbidden_preloaded_module_rejected(tmp_path, monkeypatch, name):
    value = fixture(tmp_path, monkeypatch)
    value.system.modules[name] = SimpleNamespace()
    with pytest.raises(bootstrap.BootstrapError, match="forbidden_preloaded_module"):
        run(value)


@pytest.mark.parametrize("origin", ["/external/json/__init__.py", "built-in", "frozen", None])
def test_external_or_spoofed_preloaded_modules_reject(tmp_path, monkeypatch, origin):
    value = fixture(tmp_path, monkeypatch)
    name = "external_package" if origin == "frozen" else "json"
    value.system.modules[name] = SimpleNamespace(
        __spec__=SimpleNamespace(origin=origin), __file__="/external/json/__init__.py"
    )
    with pytest.raises(bootstrap.BootstrapError, match="external_preloaded_module"):
        run(value)


@pytest.mark.parametrize(
    "name",
    ["mechanical_cad", "OCP", "slvs", "mechanical_cad.sidecar", "OCP.OCP", "slvs.solvespace"],
)
def test_wrong_fixed_package_origin_rejected(tmp_path, monkeypatch, name):
    value = fixture(tmp_path, monkeypatch)
    _, package = value.finder.origins[name]
    value.finder.origins[name] = "/external/file.py", package
    with pytest.raises(bootstrap.BootstrapError, match="origin_mismatch"):
        run(value)
    assert value.imported == []


@pytest.mark.parametrize("field", ["root", "python_path", "bootstrap_path"])
def test_descriptor_origins_must_match_observed_final_root(tmp_path, monkeypatch, field):
    value = fixture(tmp_path, monkeypatch)
    value.descriptor[field] = "/external"
    with pytest.raises(bootstrap.BootstrapError, match="descriptor_origin_mismatch"):
        run(value)


@pytest.mark.parametrize(
    "relative", ["python/python._pth", "python/python312._pth", "python/pyvenv.cfg", "pyvenv.cfg"]
)
def test_alternate_python_configuration_rejected(tmp_path, monkeypatch, relative):
    value = fixture(tmp_path, monkeypatch)
    (value.root / relative).write_text("import site\n")
    with pytest.raises(bootstrap.BootstrapError, match="unexpected_python_configuration"):
        run(value)


def test_no_site_or_pth_execution_and_no_environment_lookup(tmp_path, monkeypatch):
    value = fixture(tmp_path, monkeypatch)
    sentinel = tmp_path / "should not exist"
    for path in (
        value.stdlib / "sitecustomize.py",
        value.root / "packages/sitecustomize.py",
        value.root / "packages/evil.pth",
    ):
        path.write_text(f"raise RuntimeError({str(sentinel)!r})\n")
    value.os.environ = None
    value.os.getenv = lambda *_args: pytest.fail("environment lookup")
    assert run(value) == 17
    assert not sentinel.exists()
    assert "site" not in value.imported


def test_present_startup_zip_placeholder_is_rejected(tmp_path, monkeypatch):
    value = fixture(tmp_path, monkeypatch)
    value.placeholder.write_bytes(b"not a supported archive")
    with pytest.raises(bootstrap.BootstrapError, match="unexpected_stdlib_archive"):
        run(value)


@pytest.mark.parametrize("damage", ["missing", "wrong", "oversize"])
def test_final_publication_marker_consistency_required(tmp_path, monkeypatch, damage):
    value = fixture(tmp_path, monkeypatch)
    marker = value.root / ".bundle-ready.json"
    if damage == "missing":
        marker.unlink()
    else:
        marker.write_bytes(b"x" * (513 if damage == "oversize" else 1))
    with pytest.raises((bootstrap.BootstrapError, OSError)):
        run(value)
    assert value.imported == []


@pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX links/FIFO contract; no Windows privilege changes"
)
def test_symlink_and_hardlink_runtime_anchors_rejected(tmp_path, monkeypatch):
    value = fixture(tmp_path, monkeypatch)
    original = value.executable.read_bytes()
    value.executable.unlink()
    outside = tmp_path / "external"
    outside.write_bytes(original)
    value.executable.symlink_to(outside)
    with pytest.raises(bootstrap.BootstrapError, match="noncanonical_runtime_path"):
        run(value)
    value.executable.unlink()
    os.link(outside, value.executable)
    with pytest.raises(bootstrap.BootstrapError, match="nonregular_runtime_file"):
        run(value)


@pytest.mark.parametrize("which", ["package", "sidecar"])
def test_imported_origin_rechecked_before_main(tmp_path, monkeypatch, which):
    value = fixture(tmp_path, monkeypatch)
    getattr(value, which).__file__ = "/external/module.py"
    value.sidecar.main = lambda: pytest.fail("wrong origin dispatched")
    with pytest.raises(bootstrap.BootstrapError, match="imported_.*_origin_mismatch"):
        run(value)


@pytest.mark.parametrize("failure_index", range(5))
def test_windows_dll_acquisition_failure_closes_prior_handles(tmp_path, monkeypatch, failure_index):
    value = fixture(tmp_path, monkeypatch, windows=True)
    original = value.os.add_dll_directory

    def add(path):
        if len(value.handles) == failure_index:
            raise OSError("synthetic DLL directory failure")
        return original(path)

    value.os.add_dll_directory = add
    with pytest.raises(OSError):
        run(value)
    assert len(value.handles) == failure_index
    assert all(handle.closed for handle in value.handles)
    assert value.imported == []


@pytest.mark.parametrize("exception", [RuntimeError("dispatch failure"), SystemExit(1)])
def test_windows_handles_survive_dispatch_and_close_on_exception(tmp_path, monkeypatch, exception):
    value = fixture(tmp_path, monkeypatch, windows=True)

    def main():
        assert all(not handle.closed for handle in value.handles)
        raise exception

    value.sidecar.main = main
    with pytest.raises(type(exception)):
        run(value)
    assert all(handle.closed for handle in value.handles)


def test_dll_close_failure_attempts_all_closures_once_and_fails(tmp_path, monkeypatch):
    value = fixture(tmp_path, monkeypatch, windows=True)

    def main():
        value.handles[2].fail = True
        return 0

    value.sidecar.main = main
    with pytest.raises(bootstrap.BootstrapError, match="dll_directory_cleanup_failed"):
        run(value)
    assert all(handle.closed for handle in value.handles)
    assert len([event for event in value.events if event[0] == "close"]) == 5


def test_windows_default_dll_policy_precedes_exact_cookies_and_private_imports(
    tmp_path, monkeypatch
):
    import ctypes

    value = fixture(tmp_path, monkeypatch, windows=True)
    original = value.importer
    expected = [
        str(value.prefix),
        str(value.native),
        str(value.root / "packages/OCP"),
        str(value.root / "packages/slvs"),
        str(value.root / "packages/cadquery_ocp_novtk.libs"),
    ]

    def importer(name):
        assert value.events[:2] == [("bind", "kernel32"), ("default", 0x200 | 0x800 | 0x400)]
        assert [event[1] for event in value.events if event[0] == "open"] == expected
        assert len(value.handles) == 5 and all(not handle.closed for handle in value.handles)
        assert value.policy.argtypes == [ctypes.c_uint32]
        assert value.policy.restype is ctypes.c_int
        return original(name)

    value.importer = importer
    assert run(value) == 17
    assert value.imported == (
        (["OCP.OCP", "slvs.solvespace"] if value.system.platform == "win32" else [])
        + ["mechanical_cad", "mechanical_cad.sidecar"]
    )
    assert value.events == (
        [("bind", "kernel32"), ("default", 0xE00)]
        + [("open", path) for path in expected]
        + [("bind", "kernel32")]
        + [("close", path) for path in reversed(expected)]
    )


@pytest.mark.parametrize("damage", ["file", "spec", "loader"])
@pytest.mark.parametrize("name", ["OCP.OCP", "slvs.solvespace"])
def test_imported_native_origin_and_exact_extension_loader_are_required(
    tmp_path, monkeypatch, damage, name
):
    value = fixture(tmp_path, monkeypatch, windows=True)
    original = value.importer

    def importer(key):
        module = original(key)
        if key == name:
            if damage == "file":
                module.__file__ += ".foreign"
            elif damage == "spec":
                module.__spec__.origin += ".foreign"
            else:
                module.__spec__.loader = object()
        return module

    value.importer = importer
    with pytest.raises(bootstrap.BootstrapError, match="imported_native_origin_mismatch"):
        run(value)
    assert "mechanical_cad.sidecar" not in value.imported
    assert len(value.handles) == 5 and all(handle.closed for handle in value.handles)


@pytest.mark.parametrize("failure", ["bind", "missing_api", "zero", "call"])
def test_windows_default_dll_policy_failure_prevents_cookies_and_private_imports(
    tmp_path, monkeypatch, failure
):
    import ctypes

    value = fixture(tmp_path, monkeypatch, windows=True)
    startup = list(value.system.path)

    def fail(*args, **kwargs):
        raise OSError("untrusted API exception details")

    if failure == "bind":
        monkeypatch.setattr(ctypes, "WinDLL", fail)
    elif failure == "missing_api":
        monkeypatch.setattr(ctypes, "WinDLL", lambda *args, **kwargs: SimpleNamespace())
    elif failure == "zero":
        value.policy.result = 0
    else:
        monkeypatch.setattr(
            ctypes, "WinDLL", lambda *args, **kwargs: SimpleNamespace(SetDefaultDllDirectories=fail)
        )
    with pytest.raises(bootstrap.BootstrapError, match="^dll_search_policy_failed$"):
        run(value)
    assert value.handles == value.imported == []
    assert value.system.path == startup
    assert not any(event[0] == "open" for event in value.events)


@pytest.mark.parametrize("failure_index", range(5))
@pytest.mark.parametrize("cookie", [None, object(), SimpleNamespace(close=0)])
def test_invalid_windows_dll_cookie_fails_before_dispatch_and_closes_prior_cookies(
    tmp_path, monkeypatch, failure_index, cookie
):
    value = fixture(tmp_path, monkeypatch, windows=True)
    original = value.os.add_dll_directory

    def add(path):
        if len(value.handles) == failure_index:
            return cookie
        return original(path)

    value.os.add_dll_directory = add
    with pytest.raises(bootstrap.BootstrapError, match="^dll_directory_cookie_invalid$"):
        run(value)
    assert value.imported == [] and len(value.handles) == failure_index
    assert all(handle.closed for handle in value.handles)
    assert [event[1] for event in value.events if event[0] == "close"] == [
        handle.path for handle in reversed(value.handles)
    ]


def test_linux_dispatch_never_binds_windows_dll_policy(tmp_path, monkeypatch):
    import ctypes

    value = fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(
        ctypes,
        "WinDLL",
        lambda *args, **kwargs: pytest.fail("Windows API used on Linux"),
        raising=False,
    )
    assert run(value) == 17 and value.events == [] and value.handles == []


@pytest.mark.parametrize(
    "token",
    ["", "0", "1", "2", "01", "-4", "+4", " 4", "4.0", "４", "18446744073709551615", "9" * 30],
)
def test_descriptor_handle_syntax_rejects_standard_streams(token):
    # Synthetic Windows standard handles; never submit random integers to Win32.
    crt = SimpleNamespace(get_osfhandle=lambda index: (1, 2, 4)[index])
    with pytest.raises(bootstrap.BootstrapError):
        bootstrap.read_descriptor(token, system=SimpleNamespace(platform="win32"), windows_crt=crt)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX descriptor contract uses fcntl")
def test_readonly_descriptor_is_bounded_consumed_and_closed(tmp_path):
    target = tmp_path / "descriptor.json"
    raw = b' { "only": "setup bytes" } \n'
    target.write_bytes(raw)
    descriptor = os.open(target, os.O_RDONLY)
    assert bootstrap.read_descriptor(str(descriptor)) == raw
    with pytest.raises(OSError):
        os.fstat(descriptor)


@pytest.mark.parametrize("damage", ["writable", "oversize", "empty", "offset"])
@pytest.mark.skipif(sys.platform == "win32", reason="POSIX descriptor contract uses fcntl")
def test_descriptor_file_rules_fail_and_close(tmp_path, damage):
    target = tmp_path / "descriptor.json"
    target.write_bytes(
        b"x" * (16 * 1024 + 1 if damage == "oversize" else 0 if damage == "empty" else 4)
    )
    descriptor = os.open(target, os.O_RDWR if damage == "writable" else os.O_RDONLY)
    if damage == "offset":
        os.lseek(descriptor, 1, os.SEEK_SET)
    with pytest.raises(bootstrap.BootstrapError):
        bootstrap.read_descriptor(str(descriptor))
    with pytest.raises(OSError):
        os.fstat(descriptor)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX descriptor contract uses fcntl")
def test_pipe_descriptor_rejected_without_blocking():
    read, write = os.pipe()
    try:
        with pytest.raises(bootstrap.BootstrapError, match="descriptor_file_required"):
            bootstrap.read_descriptor(str(read))
    finally:
        os.close(write)


def read_fixture_descriptor(descriptor, *, operating_system):
    if sys.platform != "win32":
        return bootstrap.read_descriptor(str(descriptor), operating_system=operating_system)
    operating_system.set_handle_inheritable = lambda handle, inherit: None
    crt = SimpleNamespace(
        get_osfhandle=lambda index: 100 + index, open_osfhandle=lambda handle, flags: descriptor
    )
    return bootstrap.read_descriptor(
        "9999999",
        system=SimpleNamespace(platform="win32"),
        operating_system=operating_system,
        windows_crt=crt,
    )


def test_windows_handle_adapter_reads_only_the_separate_handle(tmp_path):
    target = tmp_path / "descriptor.json"
    target.write_bytes(b"descriptor")
    descriptor = os.open(target, os.O_RDONLY)
    calls = []
    operating_system = SimpleNamespace(**{key: getattr(os, key) for key in dir(os)})
    operating_system.O_BINARY = 0
    operating_system.set_handle_inheritable = lambda handle, inherit: calls.append(
        (handle, inherit)
    )
    crt = SimpleNamespace(
        get_osfhandle=lambda index: index + 100,
        open_osfhandle=lambda handle, flags: (
            descriptor
            if (handle, flags) == (999, os.O_RDONLY)
            else pytest.fail("wrong handle adapter")
        ),
    )
    assert (
        bootstrap.read_descriptor(
            "999",
            system=SimpleNamespace(platform="win32"),
            operating_system=operating_system,
            windows_crt=crt,
        )
        == b"descriptor"
    )
    assert calls == [(999, False)]
    with pytest.raises(OSError):
        os.fstat(descriptor)


def test_fixed_loader_is_bounded_only_digest_can_vary_and_never_uses_stdin():
    digest = hashlib.sha256(SCRIPT.read_bytes()).hexdigest()
    loader = bootstrap.entry_loader(digest)
    assert len(loader) <= 4096 and len(SCRIPT.read_bytes()) <= bootstrap.MAX_BOOTSTRAP_BYTES
    assert digest in loader
    compile(loader, "<fixed child loader>", "exec")
    assert "stdin" not in loader and "getenv" not in loader and "os.environ" not in loader
    assert 'compile(data,b,"exec")' in loader
    assert "hashlib.sha256(data).hexdigest()" in loader
    for invalid in (None, 1, "x" * 64, "a" * 63, "a" * 64 + "\n", "a' ; exit()"):
        with pytest.raises(bootstrap.BootstrapError):
            bootstrap.entry_loader(invalid)


def test_script_has_no_live_runtime_imports_or_dynamic_request_evaluation():
    tree = ast.parse(SCRIPT.read_bytes())
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert not {"mechanical_cad", "OCP", "slvs", "bpy", "site", "runpy"} & imports
    assert not any(isinstance(node, ast.ImportFrom) for node in ast.walk(tree))
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    assert not any(
        isinstance(node.func, ast.Name) and node.func.id in {"exec", "eval"} for node in calls
    )


def execute_loader(value, digest):
    """Run only local authored loader text with fake child state and inert source."""
    import builtins

    imports = []
    value.system.stderr = io.StringIO()

    def import_fake(name, *args, **kwargs):
        imports.append(name)
        return {"sys": value.system, "os": value.os, "hashlib": hashlib, "stat": stat}[name]

    namespace = {"__builtins__": dict(vars(builtins), __import__=import_fake)}
    exec(compile(bootstrap.entry_loader(digest), "<pure loader fixture>", "exec"), namespace)
    return imports


def test_loader_hashes_and_executes_the_same_bounded_captured_bytes(tmp_path, monkeypatch):
    value = fixture(tmp_path, monkeypatch)
    target = value.root / "bootstrap.py"
    original = b'import sys\nsys.executed = "captured"\n'
    target.write_bytes(original)

    original_read = value.os.read

    def read(descriptor, count):
        data = original_read(descriptor, count)
        if not data:
            target.write_bytes(b'raise RuntimeError("changed after read")')
        return data

    value.os.read = read
    imports = execute_loader(value, hashlib.sha256(original).hexdigest())
    assert value.system.executed == "captured"
    assert imports == ["sys", "os", "hashlib", "stat", "sys"]
    assert value.system.stdin.tell() == 0 and not value.system.stderr.getvalue()


@pytest.mark.parametrize(
    "damage",
    ["digest", "oversize", "external_path", "wrong_flag", "preloaded_site", "preloaded_external"],
)
def test_fixed_loader_rejects_before_any_bootstrap_execution(tmp_path, monkeypatch, damage):
    value = fixture(tmp_path, monkeypatch)
    target = value.root / "bootstrap.py"
    original = b'import sys\nsys.executed = "should not run"\n'
    target.write_bytes(original)
    digest = hashlib.sha256(original).hexdigest()
    if damage == "digest":
        target.write_bytes(original + b"# changed")
    elif damage == "oversize":
        target.write_bytes(b"#" * 65537)
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
    elif damage == "external_path":
        value.system.path.append("/external")
    elif damage == "wrong_flag":
        value.system.flags.no_site = 0
    else:
        name = "site" if damage == "preloaded_site" else "untrusted"
        value.system.modules[name] = SimpleNamespace()
    with pytest.raises(SystemExit) as result:
        execute_loader(value, digest)
    assert result.value.code == 78
    assert not hasattr(value.system, "executed")
    assert value.system.stderr.getvalue() == "standalone_bootstrap: entry_rejected\n"
    assert value.system.stdin.tell() == 0


def test_spec_with_wrong_loader_rejected_even_when_origin_matches(tmp_path, monkeypatch):
    value = fixture(tmp_path, monkeypatch)
    original = value.finder.find_spec

    def find(name, search):
        spec = original(name, search)
        spec.loader = object()
        return spec

    value.finder.find_spec = find
    with pytest.raises(bootstrap.BootstrapError, match="package_origin_mismatch"):
        run(value)


def test_other_core_version_is_not_dispatched(tmp_path, monkeypatch):
    value = fixture(tmp_path, monkeypatch)
    value.package.__version__ = "0.5.2"
    with pytest.raises(bootstrap.BootstrapError, match="imported_core_origin_mismatch"):
        run(value)


@pytest.mark.parametrize(
    "failure",
    [
        bootstrap.BootstrapError("descriptor_fields"),
        RuntimeError("private model and environment details"),
    ],
)
def test_main_setup_failure_has_bounded_stderr_no_stdout_or_stdin(tmp_path, monkeypatch, failure):
    value = fixture(tmp_path, monkeypatch)
    value.system.stderr, value.system.stdout = io.StringIO(), io.StringIO()
    monkeypatch.setattr(bootstrap, "sys", value.system)
    monkeypatch.setattr(bootstrap, "_layout", lambda *_args: {})
    monkeypatch.setattr(bootstrap, "_loaded_modules", lambda *_args: None)

    def reader(_token):
        raise failure

    monkeypatch.setattr(bootstrap, "read_descriptor", reader)
    assert bootstrap.main() == 78
    expected = (
        "descriptor_fields" if isinstance(failure, bootstrap.BootstrapError) else "setup_failed"
    )
    assert value.system.stderr.getvalue() == "standalone_bootstrap: " + expected + "\n"
    assert not value.system.stdout.getvalue() and value.system.stdin.tell() == 0


@pytest.mark.parametrize("entry", ["bounded_file", "loader"])
@pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX links/FIFO contract; no Windows privilege changes"
)
def test_preexisting_fifo_rejected_without_open(tmp_path, monkeypatch, entry):
    value = fixture(tmp_path, monkeypatch)
    target = value.root / "bootstrap.py"
    target.unlink()
    os.mkfifo(target)
    value.os.open = lambda *_args: pytest.fail("preexisting FIFO must not be opened")
    if entry == "bounded_file":
        with pytest.raises(bootstrap.BootstrapError, match="nonregular_runtime_file"):
            bootstrap._bounded_file(str(target), 65536, value.os)
    else:
        with pytest.raises(SystemExit) as result:
            execute_loader(value, "a" * 64)
        assert result.value.code == 78


@pytest.mark.parametrize("entry", ["bounded_file", "loader"])
@pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX links/FIFO contract; no Windows privilege changes"
)
def test_fifo_replacement_cannot_block_open_and_is_rejected_before_read(
    tmp_path, monkeypatch, entry
):
    value = fixture(tmp_path, monkeypatch)
    target = value.root / "bootstrap.py"
    original_open = value.os.open
    opened, closed = [], []

    def replace_before_open(path, flags):
        assert path == str(target)
        assert flags & os.O_NONBLOCK and flags & os.O_NOFOLLOW
        target.unlink()
        os.mkfifo(target)
        descriptor = original_open(path, flags)
        opened.append(descriptor)
        return descriptor

    def close(descriptor):
        closed.append(descriptor)
        os.close(descriptor)

    value.os.open, value.os.close = replace_before_open, close
    value.os.fdopen = lambda *_args: pytest.fail(
        "nonregular opened object must not be wrapped/read"
    )
    if entry == "bounded_file":
        with pytest.raises(bootstrap.BootstrapError, match="nonregular_setup_file"):
            bootstrap._bounded_file(str(target), 65536, value.os)
    else:
        with pytest.raises(SystemExit) as result:
            execute_loader(value, "a" * 64)
        assert result.value.code == 78
    assert len(opened) == 1 and closed == opened
    with pytest.raises(OSError):
        os.fstat(opened[0])


@pytest.mark.parametrize("entry", ["bounded_file", "loader"])
@pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX links/FIFO contract; no Windows privilege changes"
)
def test_symlink_replacement_is_rejected_without_following(tmp_path, monkeypatch, entry):
    value = fixture(tmp_path, monkeypatch)
    target = value.root / "bootstrap.py"
    outside = tmp_path / "external.py"
    outside.write_bytes(b"# external")
    original_open = value.os.open

    def replace_before_open(path, flags):
        assert flags & os.O_NONBLOCK and flags & os.O_NOFOLLOW
        target.unlink()
        target.symlink_to(outside)
        return original_open(path, flags)

    value.os.open = replace_before_open
    value.os.fdopen = lambda *_args: pytest.fail("symlink replacement must not be read")
    if entry == "bounded_file":
        with pytest.raises(OSError):
            bootstrap._bounded_file(str(target), 65536, value.os)
    else:
        with pytest.raises(SystemExit) as result:
            execute_loader(value, "a" * 64)
        assert result.value.code == 78


@pytest.mark.parametrize("entry", ["bounded_file", "loader", "descriptor"])
@pytest.mark.parametrize("close_fails", [False, True])
def test_raw_read_failure_closes_once_without_calling_destructive_fdopen(
    tmp_path, monkeypatch, entry, close_fails
):
    value = fixture(tmp_path, monkeypatch)
    target = value.root / "bootstrap.py"
    target.write_bytes(b"# synthetic bootstrap")
    original_open = value.os.open
    opened, closed = [], []

    def opening(path, flags):
        descriptor = original_open(path, flags)
        opened.append(descriptor)
        return descriptor

    wrappers = []
    replacements = []
    victim = tmp_path / "unrelated_file"
    victim.write_bytes(b"unrelated file must remain open")

    def fdopen(descriptor, _mode):
        # Model CPython constructor error after it has consumed the descriptor.
        wrappers.append(descriptor)
        os.close(descriptor)
        reused = os.open(victim, os.O_RDONLY)
        assert reused == descriptor
        replacements.append(reused)
        raise OSError("constructor consumed and reused numeric descriptor")

    def read(_descriptor, _count):
        raise OSError("synthetic raw read failure; descriptor is still owned")

    # Positive control proves the destructive constructor actually creates ABA.
    control = os.open(victim, os.O_RDONLY)
    with pytest.raises(OSError):
        fdopen(control, "rb")
    assert wrappers == [control] and replacements == [control]

    def close(descriptor):
        closed.append(descriptor)
        os.close(descriptor)
        if close_fails:
            raise OSError("synthetic close uncertainty")

    value.os.open, value.os.fdopen, value.os.close = opening, fdopen, close
    value.os.read = read
    if entry == "bounded_file":
        with pytest.raises(OSError):
            bootstrap._bounded_file(str(target), 65536, value.os)
    elif entry == "descriptor":
        descriptor = opening(str(target), os.O_RDONLY)
        with pytest.raises(OSError):
            read_fixture_descriptor(descriptor, operating_system=value.os)
    else:
        with pytest.raises(SystemExit) as result:
            execute_loader(value, "a" * 64)
        assert result.value.code == 78
    assert len(opened) == 1 and closed == opened
    assert wrappers == [control]  # No production route invoked the consuming wrapper.
    assert os.read(control, 1024) == b"unrelated file must remain open"
    os.close(control)
    with pytest.raises(OSError):
        os.fstat(opened[0])


@pytest.mark.parametrize("entry", ["bounded_file", "loader"])
def test_opened_object_stat_failure_closes_raw_descriptor(tmp_path, monkeypatch, entry):
    value = fixture(tmp_path, monkeypatch)
    target = value.root / "bootstrap.py"
    original_open = value.os.open
    opened, closed = [], []

    def opening(path, flags):
        descriptor = original_open(path, flags)
        opened.append(descriptor)
        return descriptor

    def fstat(_descriptor):
        raise OSError("synthetic stat failure")

    def close(descriptor):
        closed.append(descriptor)
        os.close(descriptor)

    value.os.open, value.os.fstat, value.os.close = opening, fstat, close
    if entry == "bounded_file":
        with pytest.raises(OSError):
            bootstrap._bounded_file(str(target), 65536, value.os)
    else:
        with pytest.raises(SystemExit):
            execute_loader(value, "a" * 64)
    assert len(opened) == 1 and closed == opened
    with pytest.raises(OSError):
        os.fstat(opened[0])


def test_windows_descriptor_raw_read_failure_closes_transferred_crt_descriptor(tmp_path):
    target = tmp_path / "descriptor.json"
    target.write_bytes(b"setup data")
    descriptor = os.open(target, os.O_RDONLY)
    calls = []
    operating_system = SimpleNamespace(**{key: getattr(os, key) for key in dir(os)})
    operating_system.O_BINARY = 0
    operating_system.set_handle_inheritable = lambda *args: calls.append(("inherit", args))

    def transfer(handle, flags):
        calls.append(("transfer", handle, flags))
        return descriptor

    def wrapping(*_args):
        pytest.fail("No constructor may receive raw descriptor ownership")

    def read(*_args):
        raise OSError("synthetic raw read failure")

    def close(value):
        calls.append(("close", value))
        os.close(value)

    operating_system.fdopen, operating_system.close = wrapping, close
    operating_system.read = read
    crt = SimpleNamespace(get_osfhandle=lambda index: index + 100, open_osfhandle=transfer)
    with pytest.raises(OSError):
        bootstrap.read_descriptor(
            "999",
            system=SimpleNamespace(platform="win32"),
            operating_system=operating_system,
            windows_crt=crt,
        )
    assert calls == [
        ("inherit", (999, False)),
        ("transfer", 999, os.O_RDONLY),
        ("close", descriptor),
    ]
    with pytest.raises(OSError):
        os.fstat(descriptor)


@pytest.mark.parametrize("entry", ["bounded_file", "loader", "descriptor"])
def test_successful_raw_reads_tolerate_short_reads_without_stream_wrapping(
    tmp_path, monkeypatch, entry
):
    value = fixture(tmp_path, monkeypatch)
    target = value.root / "bootstrap.py"
    data = b'import sys\nsys.executed = "short reads preserved"\n'
    target.write_bytes(data)
    original_read = value.os.read
    requests = []

    def read(descriptor, count):
        requests.append(count)
        return original_read(descriptor, min(count, 3))

    value.os.read = read
    value.os.fdopen = lambda *_args: pytest.fail("stream wrapper must never receive ownership")
    if entry == "bounded_file":
        assert bootstrap._bounded_file(str(target), 65536, value.os) == data
    elif entry == "descriptor":
        descriptor = os.open(target, os.O_RDONLY)
        assert read_fixture_descriptor(descriptor, operating_system=value.os) == data
        with pytest.raises(OSError):
            os.fstat(descriptor)
    else:
        execute_loader(value, hashlib.sha256(data).hexdigest())
        assert value.system.executed == "short reads preserved"
    assert len(requests) > 1 and all(0 < count <= 65537 for count in requests)


def test_all_setup_read_routes_keep_raw_ownership_without_fdopen():
    source = SCRIPT.read_text()
    assert "fdopen" not in source
    assert "os.read(fd," in bootstrap.entry_loader("a" * 64)
    assert "finally:" in bootstrap.entry_loader("a" * 64)
