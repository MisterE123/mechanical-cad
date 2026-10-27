"""Tiny ZIP preparation tests with explicit fake lifetime pins; no native launch."""

import hashlib
import importlib
import io
import json
import os
import stat
import sys
import threading
import types
import warnings
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest
from windows_materializer_fixture import ComposedStorage, short_root

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "mcad_runtime_bundle_tests"
package = sys.modules.setdefault(PACKAGE, types.ModuleType(PACKAGE))
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
m = importlib.import_module(PACKAGE + ".runtime_bundle_manifest")
u = importlib.import_module(PACKAGE + ".runtime_bundle_materialize")
LIMITS = m.BundleLimits(chunk_bytes=3, reserve_free_bytes=0)


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()


class Pin:
    def __init__(self, bundle_id, mode="exclusive"):
        self.bundle_id, self.mode, self.held, self.checks = bundle_id, mode, True, 0

    def assert_held(self):
        assert self.held, "pin no longer held"
        self.checks += 1


class Fixture:
    def __init__(self, tmp_path, platform=None):
        platform = platform or ("windows-x64" if os.name == "nt" else "linux-x64")
        if os.name == "nt":
            tmp_path = short_root(tmp_path)
        self.package, self.cache = tmp_path / "package é", tmp_path / "cache 中文"
        self.package.mkdir()
        if os.name == "nt":
            self.known = tmp_path / "k"
            self.known.mkdir()
            self.cache = self.known / "MechanicalCAD" / "r"
            self.cache.mkdir(parents=True)
        else:
            self.cache.mkdir()
        self.platform = platform
        self.bundle_id = m.bundle_identity("a" * 40, "b" * 64, platform)
        python_path = "python/python.exe" if platform == "windows-x64" else "python/bin/python3.12"
        self.contents = {
            python_path: b"fake interpreter",
            "bootstrap.py": b"fake bootstrap",
            "src/mechanical_cad/__init__.py": b"source",
            "packages/OCP.libs/codec.dll": b"resource neighbor",
            "packages/OCP-8.dist-info/METADATA": b"metadata",
            "packages/OCP/data/中文 name.txt": b"resource data",
            "python/empty": b"",
        }
        self.files = [
            {
                "path": p,
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "mode": 0o755 if p == python_path else 0o644,
            }
            for p, data in self.contents.items()
        ]
        self.manifest = {
            "schema_version": 1,
            "bundle_id": self.bundle_id,
            "platform": platform,
            "python_path": python_path,
            "bootstrap_path": "bootstrap.py",
            "files": self.files,
        }
        self.folder = self.package / "_backend" / self.bundle_id
        self.folder.mkdir(parents=True)
        self.pin = Pin(self.bundle_id)
        self.write()
        self.storage = None
        if os.name == "nt" and platform == "windows-x64":
            c = importlib.import_module(PACKAGE + ".windows_cache")
            release = m.parse_release_manifest(
                encode(self.release), expected_platform=platform, limits=LIMITS
            )
            self.storage = ComposedStorage(c, self.package, self.known, release)

    def write(self, mutate=None, compression=zipfile.ZIP_DEFLATED):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=compression) as archive:
            entries = list(self.contents.items())
            if mutate:
                entries = mutate(entries)
            for path, data in entries:
                info = zipfile.ZipInfo(path)
                info.create_system = 3
                info.compress_type = compression
                item = next((f for f in self.files if f["path"] == path), self.files[-1])
                info.external_attr = (stat.S_IFREG | item["mode"]) << 16
                archive.writestr(info, data)
        self.payload = output.getvalue()
        self.save()

    def save(self):
        data = encode(self.manifest)
        (self.folder / "bundle-manifest.json").write_bytes(data)
        (self.folder / "payload.zip").write_bytes(self.payload)
        self.release = {
            "schema_version": 1,
            "bundle_id": self.bundle_id,
            "source_commit": "a" * 40,
            "runtime_lock_sha256": "b" * 64,
            "platform": self.platform,
            "manifest_path": f"_backend/{self.bundle_id}/bundle-manifest.json",
            "manifest_sha256": hashlib.sha256(data).hexdigest(),
            "payload_path": f"_backend/{self.bundle_id}/payload.zip",
            "payload_sha256": hashlib.sha256(self.payload).hexdigest(),
            "payload_size": len(self.payload),
        }

    @property
    def final(self):
        return self.cache / self.bundle_id

    def run(self, **kwargs):
        options = dict(expected_platform=self.platform, limits=LIMITS, pin=self.pin)
        options.update(kwargs)
        if self.storage is not None:
            self.storage.release = m.parse_release_manifest(
                encode(self.release), expected_platform=self.platform, limits=LIMITS
            )
            return self.storage.invoke(
                u.materialize_bundle, release_data=encode(self.release), **options
            )
        return u.materialize_bundle(self.package, self.cache, encode(self.release), **options)

    def recheck(self, **kwargs):
        options = dict(expected_platform=self.platform, limits=LIMITS, pin=self.pin)
        options.update(kwargs)
        if self.storage is not None:
            self.storage.release = m.parse_release_manifest(
                encode(self.release), expected_platform=self.platform, limits=LIMITS
            )
            return self.storage.invoke(
                u.verify_cached_bundle, release_data=encode(self.release), **options
            )
        return u.verify_cached_bundle(self.package, self.cache, encode(self.release), **options)


@pytest.mark.parametrize(
    "platform",
    [
        pytest.param(
            "linux-x64",
            marks=pytest.mark.skipif(
                os.name == "nt",
                reason="Linux payload uses POSIX mode/link inventory; Windows payload runs below",
            ),
        ),
        "windows-x64",
    ],
)
def test_complete_offline_materialization_and_shared_recheck(tmp_path, platform):
    f = Fixture(tmp_path, platform)
    before = {p.relative_to(f.package): p.read_bytes() for p in f.package.rglob("*") if p.is_file()}
    result = f.run()
    assert isinstance(result, m.BundleDescriptor)
    assert result.root == str(f.final)
    for name, data in f.contents.items():
        assert (f.final / name).read_bytes() == data
    assert not list(f.cache.glob(".stage-*"))
    assert f.pin.held and f.pin.checks > 10
    f.pin.mode = "shared"
    assert f.recheck() == result
    assert before == {
        p.relative_to(f.package): p.read_bytes() for p in f.package.rglob("*") if p.is_file()
    }


def test_cached_tree_is_rehashed_not_marker_trusted_and_never_replaced(tmp_path):
    f = Fixture(tmp_path)
    f.run()
    target = f.final / "bootstrap.py"
    target.write_bytes(b"x" * len(f.contents["bootstrap.py"]))
    marker = (f.final / ".bundle-ready.json").read_bytes()
    with pytest.raises(m.BundleError, match="digest"):
        f.recheck()
    with pytest.raises(u.BundlePreparationError, match="digest"):
        f.run()
    assert target.read_bytes().startswith(b"x")
    assert (f.final / ".bundle-ready.json").read_bytes() == marker
    assert not list(f.cache.glob(".stage-*"))


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "extra",
        "directory",
        pytest.param(
            "mode",
            marks=pytest.mark.skipif(
                os.name == "nt", reason="POSIX mode mutation; Windows ACL negatives are separate"
            ),
        ),
        "symlink",
        "hardlink",
        "marker",
    ],
)
def test_exact_final_inventory_rejects_every_unlisted_change(tmp_path, mutation):
    f = Fixture(tmp_path)
    f.run()
    target = f.final / "bootstrap.py"
    if mutation == "missing":
        target.unlink()
    elif mutation == "extra":
        (f.final / "extra").write_bytes(b"bad")
    elif mutation == "directory":
        (f.final / "extra").mkdir()
    elif mutation == "mode":
        target.chmod(0o777)
    elif os.name == "nt" and mutation in {"symlink", "hardlink"}:

        def configure(owner, api):
            def changed(info):
                if info.path == str(target):
                    return replace(
                        info,
                        **(
                            {"attributes": info.attributes | 0x400}
                            if mutation == "symlink"
                            else {"links": 2}
                        ),
                    )
                return info

            api.info_change = changed

        f.storage.configure = configure
    elif mutation == "symlink":
        target.unlink()
        target.symlink_to(f.folder / "bundle-manifest.json")
    elif mutation == "hardlink":
        os.link(target, tmp_path / "outside-hardlink")
    else:
        (f.final / ".bundle-ready.json").write_bytes(b"{}")
    with pytest.raises(m.BundleError):
        f.recheck()


@pytest.mark.parametrize(
    "mutation",
    [
        lambda e: e + [("../outside", b"x")],
        lambda e: e + [("/absolute", b"x")],
        lambda e: e + [e[0]],
        lambda e: [(e[0][0].upper(), e[0][1])] + e[1:],
        lambda e: e[:-1],
        lambda e: [("python/", b"")] + e[1:],
    ],
)
def test_zip_inventory_and_traversal_are_checked_before_staging(tmp_path, mutation):
    f = Fixture(tmp_path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        f.write(mutate=mutation)
    with pytest.raises(u.BundlePreparationError):
        f.run()
    assert not f.final.exists()
    assert not list(f.cache.glob(".stage-*"))


def test_symlink_zip_mode_rejected_before_any_output(tmp_path):
    f = Fixture(tmp_path)
    data = bytearray(f.payload)
    offset = data.index(b"PK\x01\x02")
    data[offset + 38 : offset + 42] = ((stat.S_IFLNK | 0o777) << 16).to_bytes(4, "little")
    f.payload = bytes(data)
    f.save()
    with pytest.raises(u.BundlePreparationError, match="regular-file"):
        f.run()
    assert not list(f.cache.iterdir())


def test_corrupt_payload_hash_never_opens_zip_or_writes(tmp_path, monkeypatch):
    f = Fixture(tmp_path)
    (f.folder / "payload.zip").write_bytes(b"x" * len(f.payload))
    monkeypatch.setattr(u.zipfile, "ZipFile", lambda *_: pytest.fail("unverified ZIP opened"))
    with pytest.raises(u.BundlePreparationError, match="digest"):
        f.run()
    assert not list(f.cache.iterdir())


def test_corrupt_file_hash_retains_partial_attempt(tmp_path):
    f = Fixture(tmp_path)
    f.files[1]["sha256"] = "f" * 64
    f.save()
    with pytest.raises(u.BundlePreparationError, match="digest") as error:
        f.run()
    assert not f.final.exists()
    retained = Path(error.value.staging_path)
    assert retained.is_dir()
    assert not (retained / ".bundle-ready.json").exists()
    assert (retained / f.files[0]["path"]).exists()


def test_cancel_before_start_and_mid_copy_retains_only_owned_stage(tmp_path):
    f = Fixture(tmp_path)
    with pytest.raises(u.BundleCancelled) as error:
        f.run(cancelled=lambda: True)
    assert error.value.staging_path is None

    def cancelled():
        return any(
            p.stat().st_size > 0 for p in f.cache.glob(".stage-*/" + f.manifest["python_path"])
        )

    with pytest.raises(u.BundleCancelled) as error:
        f.run(cancelled=cancelled)
    assert Path(error.value.staging_path).is_dir()
    assert not f.final.exists()
    assert not list(f.cache.glob(".stage-*/.bundle-ready.json"))


def test_rename_failure_keeps_verified_stage_unselectable_then_new_attempt_succeeds(
    tmp_path, monkeypatch
):
    f = Fixture(tmp_path)
    rename = u.os.rename
    monkeypatch.setattr(u.os, "rename", lambda *_: (_ for _ in ()).throw(OSError("rename denied")))
    with pytest.raises(u.BundlePreparationError, match="rename denied") as error:
        f.run()
    first = Path(error.value.staging_path)
    assert (first / ".bundle-ready.json").is_file()
    assert not f.final.exists()
    with pytest.raises(FileNotFoundError):
        f.recheck()
    monkeypatch.setattr(u.os, "rename", rename)
    assert f.run().root == str(f.final)
    assert first.exists()


def test_concurrent_publish_is_serialized_by_caller_pin_and_cache_rechecked(tmp_path):
    f = Fixture(tmp_path)
    lock = threading.Lock()

    def prepare():
        with lock:
            return f.run(pin=Pin(f.bundle_id))

    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = list(pool.map(lambda _: prepare(), range(2)))
    assert a == b
    assert list(f.cache.iterdir()) == [f.final]


def test_payload_path_replacement_after_open_cannot_switch_verified_stream(tmp_path, monkeypatch):
    f = Fixture(tmp_path)
    original = u._zip_directory

    def replace_path(stream, size, limits):
        replacement = f.folder / "other.zip"
        replacement.write_bytes(b"not a ZIP")
        replacement.replace(f.folder / "payload.zip")
        return original(stream, size, limits)

    monkeypatch.setattr(u, "_zip_directory", replace_path)
    # Unlink/replacement changes the open inode ctime on this host: detecting it
    # is also acceptable; reopening the new path must never supply extracted data.
    try:
        result = f.run()
    except u.BundlePreparationError as error:
        if os.name == "nt" and isinstance(error.__cause__, PermissionError):
            # A retained Windows input handle can deny replacement outright.
            # The original bytes must remain; no switched stream was extracted.
            assert error.__cause__.winerror in {5, 32}
            assert (f.folder / "payload.zip").read_bytes() == f.payload
            assert not f.final.exists()
        else:
            assert "changed during" in str(error)
    else:
        assert Path(result.python_path).read_bytes() == b"fake interpreter"


def test_limits_disk_and_pin_fail_without_output(tmp_path, monkeypatch):
    f = Fixture(tmp_path)
    with pytest.raises(u.BundlePreparationError, match="exclusive"):
        f.run(pin=Pin(f.bundle_id, "shared"))
    with pytest.raises(u.BundlePreparationError, match="Wrong"):
        f.run(pin=Pin("f" * 64))
    with pytest.raises(u.BundlePreparationError, match="metadata"):
        f.run(limits=replace(LIMITS, max_zip_metadata_bytes=1))
    monkeypatch.setattr(u.shutil, "disk_usage", lambda _: types.SimpleNamespace(free=0))
    with pytest.raises(u.BundlePreparationError, match="space"):
        f.run()
    assert not list(f.cache.iterdir())


def test_package_cache_overlap_and_symlink_roots_rejected(tmp_path, monkeypatch):
    f = Fixture(tmp_path)
    with pytest.raises(u.BundlePreparationError, match="disjoint"):
        u.materialize_bundle(
            f.package,
            f.folder,
            encode(f.release),
            expected_platform=f.platform,
            limits=LIMITS,
            pin=f.pin,
        )
    link = tmp_path / "cache-link"
    if os.name == "nt":
        link.mkdir()
        assert u._safe_path(link) == link
        original = Path.lstat

        def reparse(path):
            if path == link:
                return types.SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
            return original(path)

        monkeypatch.setattr(Path, "lstat", reparse)
    else:
        link.symlink_to(f.cache, target_is_directory=True)
    with pytest.raises(u.BundlePreparationError, match="Symlink"):
        u.materialize_bundle(
            f.package,
            link,
            encode(f.release),
            expected_platform=f.platform,
            limits=LIMITS,
            pin=f.pin,
        )


@pytest.mark.parametrize(
    "mutation", ["crc", "size", "compression", "flags", "count", "comment", "truncate"]
)
def test_zip_structural_and_content_corruption_is_bounded(tmp_path, mutation):
    f = Fixture(tmp_path)
    f.write(compression=zipfile.ZIP_STORED)
    data = bytearray(f.payload)
    central = data.index(b"PK\x01\x02")
    if mutation == "crc":
        name_size = int.from_bytes(data[26:28], "little")
        extra_size = int.from_bytes(data[28:30], "little")
        data[30 + name_size + extra_size] ^= 1
    elif mutation == "size":
        data[central + 24 : central + 28] = (999).to_bytes(4, "little")
    elif mutation == "compression":
        data[central + 10 : central + 12] = (99).to_bytes(2, "little")
    elif mutation == "flags":
        data[central + 8 : central + 10] = (1).to_bytes(2, "little")
    elif mutation == "count":
        data[-14:-12] = (65535).to_bytes(2, "little")
        data[-12:-10] = (65535).to_bytes(2, "little")
    elif mutation == "comment":
        data[-2:] = (1).to_bytes(2, "little")
        data += b"x"
    else:
        data = data[:10]
    f.payload = bytes(data)
    f.save()
    with pytest.raises(u.BundlePreparationError):
        f.run()
    assert not f.final.exists()


def test_partial_disk_failure_retains_files_and_is_not_reused(tmp_path, monkeypatch):
    f = Fixture(tmp_path)
    original = u.os.fsync
    monkeypatch.setattr(u.os, "fsync", lambda *_: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(u.BundlePreparationError, match="disk full") as error:
        f.run()
    stage = Path(error.value.staging_path)
    assert stage.exists() and not f.final.exists()
    monkeypatch.setattr(u.os, "fsync", original)
    f.run()
    assert stage.exists()


def test_final_name_is_absent_until_exact_inventory_and_marker_are_verified(tmp_path, monkeypatch):
    f = Fixture(tmp_path)
    original, phases = u._inventory, []

    def inventory(root, *args, **kwargs):
        if root.name.startswith(".stage-"):
            assert not f.final.exists()
            phases.append(kwargs["ready"])
        return original(root, *args, **kwargs)

    monkeypatch.setattr(u, "_inventory", inventory)
    result = f.run()
    assert phases == [False, True]
    assert Path(result.root).is_dir()


def test_cancel_at_publication_checkpoint_retains_verified_stage(tmp_path, monkeypatch):
    f = Fixture(tmp_path)
    original = u._inventory
    cancel = False

    def inventory(root, *args, **kwargs):
        nonlocal cancel
        result = original(root, *args, **kwargs)
        if root.name.startswith(".stage-") and kwargs["ready"]:
            cancel = True
        return result

    monkeypatch.setattr(u, "_inventory", inventory)
    with pytest.raises(u.BundleCancelled) as error:
        f.run(cancelled=lambda: cancel)
    assert not f.final.exists()
    assert (Path(error.value.staging_path) / ".bundle-ready.json").exists()


def test_lost_pin_aborts_before_publication(tmp_path, monkeypatch):
    f = Fixture(tmp_path)
    original = u._inventory

    def inventory(root, *args, **kwargs):
        result = original(root, *args, **kwargs)
        if root.name.startswith(".stage-") and kwargs["ready"]:
            f.pin.held = False
        return result

    monkeypatch.setattr(u, "_inventory", inventory)
    with pytest.raises(u.BundlePreparationError, match="lifetime pin") as error:
        f.run()
    assert Path(error.value.staging_path).exists()
    assert not f.final.exists()


def test_read_only_package_is_not_modified(tmp_path):
    f = Fixture(tmp_path)
    for path in f.package.rglob("*"):
        path.chmod(0o555 if path.is_dir() else 0o444)
    f.package.chmod(0o555)
    assert f.run().bundle_id == f.bundle_id
    assert (f.folder / "payload.zip").stat().st_mode & 0o777 == 0o444


def test_materialization_detects_broken_installed_payload_even_with_good_cache(tmp_path):
    f = Fixture(tmp_path)
    result = f.run()
    (f.folder / "payload.zip").write_bytes(b"x" * len(f.payload))
    with pytest.raises(u.BundlePreparationError, match="archive digest"):
        f.run()
    # This explicit API verifies the existing tree only, without repairing or
    # asserting that the installed package is complete or authorizing a launch.
    assert f.recheck() == result


def test_imports_are_native_and_blender_free():
    import ast

    allowed = {
        "__future__",
        "contextlib",
        "hashlib",
        "json",
        "re",
        "unicodedata",
        "dataclasses",
        "os",
        "shutil",
        "stat",
        "struct",
        "tempfile",
        "zipfile",
        "zlib",
        "pathlib",
        "typing",
        "runtime_bundle_manifest",
    }
    for path in (Path(m.__file__), Path(u.__file__)):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(alias.name in allowed for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.module == "windows_cache":
                    assert path == Path(u.__file__)
                    assert ast.unparse(node) == (
                        "from .windows_cache import WindowsCacheCancelled, WindowsCacheOwner"
                    )
                else:
                    assert node.module in allowed


def test_malformed_deflate_reports_typed_failure_and_retains_staging(tmp_path):
    f = Fixture(tmp_path)
    data = bytearray(f.payload)
    name_size = int.from_bytes(data[26:28], "little")
    extra_size = int.from_bytes(data[28:30], "little")
    start = 30 + name_size + extra_size
    data[start] = (data[start] & ~6) | 6  # Reserved DEFLATE block type, unlike a CRC error.
    f.payload = bytes(data)
    f.save()
    with pytest.raises(u.BundlePreparationError) as error:
        f.run()
    assert isinstance(error.value.__cause__, u.zlib.error)
    stage = Path(error.value.staging_path)
    assert stage.is_dir()
    assert not (stage / ".bundle-ready.json").exists()
    assert not f.final.exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX FIFO-only input regression")
def test_fifo_is_rejected_before_open_without_waiting_for_a_writer(tmp_path, monkeypatch):
    fifo = tmp_path / "input.fifo"
    os.mkfifo(fifo)

    def forbidden_open(*args, **kwargs):
        pytest.fail("A known FIFO must be rejected before os.open.")

    monkeypatch.setattr(u.os, "open", forbidden_open)
    with pytest.raises(m.BundleError, match="regular file"):
        with u._open_regular(fifo):
            pytest.fail("Known FIFO input was admitted.")


@pytest.mark.skipif(os.name != "posix", reason="POSIX regular-to-FIFO race regression")
def test_regular_to_fifo_open_race_uses_nonblocking_and_closes_descriptor(tmp_path, monkeypatch):
    path = tmp_path / "swapped-input"
    path.write_bytes(b"regular before open")
    original_open, opened = u.os.open, []

    def swap_before_open(target, flags, *args, **kwargs):
        # Assert before calling the actual open, so regressing O_NONBLOCK fails
        # promptly rather than leaving a test thread blocked on a FIFO writer.
        assert flags & os.O_NONBLOCK
        path.unlink()
        os.mkfifo(path)
        fd = original_open(target, flags, *args, **kwargs)
        opened.append(fd)
        return fd

    monkeypatch.setattr(u.os, "open", swap_before_open)
    with pytest.raises(m.BundleError, match="regular file"):
        with u._open_regular(path):
            pytest.fail("Nonregular input was admitted.")
    assert len(opened) == 1
    with pytest.raises(OSError):
        os.fstat(opened[0])


@pytest.mark.parametrize(
    "path", [".BUNDLE-READY.JSON", ".bundle-ready.json/child", ".BUNDLE-READY.JSON/child"]
)
def test_reserved_marker_input_is_rejected_before_creating_a_stage(tmp_path, path):
    f = Fixture(tmp_path)
    f.contents[path] = b"x"
    f.files.append(
        {"path": path, "size": 1, "sha256": hashlib.sha256(b"x").hexdigest(), "mode": 0o644}
    )
    f.write()
    with pytest.raises(u.BundlePreparationError, match="Reserved materialization marker") as error:
        f.run()
    assert error.value.staging_path is None
    assert not list(f.cache.iterdir())


@pytest.mark.parametrize("failure", ["fstat", "fdopen", "body", "wrapper_close", "none"])
def test_input_stream_keeps_raw_owner_until_one_close(tmp_path, monkeypatch, failure):
    path = tmp_path / "owned-input"
    path.write_bytes(b"known input")
    original_open, original_close = os.open, os.close
    original_fdopen, original_fstat = os.fdopen, os.fstat
    opened, closed, streams = [], [], []

    def tracked_open(*args, **kwargs):
        fd = original_open(*args, **kwargs)
        opened.append(fd)
        return fd

    def checked_fstat(fd):
        if failure == "fstat" and fd in opened:
            raise OSError("injected fstat failure")
        return original_fstat(fd)

    def checked_fdopen(fd, *args, **kwargs):
        assert kwargs.get("closefd") is False
        # Match CPython's partial-construction cleanup: closing a wrapper
        # with closefd=False must not consume its caller-owned raw descriptor.
        stream = original_fdopen(fd, *args, **kwargs)
        streams.append(stream)
        if failure == "fdopen":
            stream.close()
            assert original_fstat(fd)
            raise OSError("injected fdopen failure")
        if failure == "wrapper_close":

            class Wrapper:
                def read(self):
                    return stream.read()

                def close(self):
                    stream.close()
                    assert original_fstat(fd)
                    raise OSError("injected wrapper close failure")

            return Wrapper()
        return stream

    def tracked_close(fd):
        closed.append(fd)
        return original_close(fd)

    monkeypatch.setattr(os, "open", tracked_open)
    monkeypatch.setattr(os, "close", tracked_close)
    monkeypatch.setattr(os, "fstat", checked_fstat)
    monkeypatch.setattr(os, "fdopen", checked_fdopen)

    def exercise():
        with u._open_regular(path) as stream:
            assert stream.read() == b"known input"
            if failure == "body":
                raise OSError("injected body failure")

    if failure == "none":
        exercise()
    else:
        with pytest.raises(OSError, match="injected"):
            exercise()
    assert len(opened) == 1 and closed == opened
    assert all(stream.closed for stream in streams)
    with pytest.raises(OSError):
        original_fstat(opened[0])


def test_uncertain_input_close_never_retries_reused_descriptor(tmp_path, monkeypatch):
    path = tmp_path / "owned-input"
    path.write_bytes(b"known input")
    replacement = tmp_path / "unrelated-input"
    replacement.write_bytes(b"unrelated")
    original_close, original_open = os.close, os.open
    closed, reused = [], []

    def close_and_reuse(fd):
        closed.append(fd)
        original_close(fd)
        other = original_open(replacement, os.O_RDONLY)
        reused.append(other)
        assert other == fd
        raise OSError("uncertain raw close")

    monkeypatch.setattr(os, "close", close_and_reuse)
    try:
        with pytest.raises(OSError, match="uncertain raw close"):
            with u._open_regular(path) as stream:
                assert stream.read() == b"known input"
        assert len(closed) == 1 and closed == reused
        assert os.read(reused[0], 20) == b"unrelated"
    finally:
        for fd in reused:
            original_close(fd)


def windows_composed_hook_fixture(tmp_path, monkeypatch):
    """Observe and fault real owner methods around fake metadata leaves only."""
    c = importlib.import_module(PACKAGE + ".windows_cache")
    f = Fixture(tmp_path, "windows-x64")
    state = types.SimpleNamespace(
        owner=None,
        stage=None,
        events=[],
        fail_stage=None,
        fail_entry=None,
        fail_before=None,
        fail_after=None,
        c=c,
        f=f,
    )

    def configure(owner, api):
        state.owner = owner

    f.storage.configure = configure

    def wrap(name, event):
        original = getattr(c.WindowsCacheOwner, name)

        def observed(actual, *args, **kwargs):
            if name == "before_stage_rename" and state.fail_before:
                raise state.fail_before
            result = original(actual, *args, **kwargs)
            if actual is not state.owner:
                return result  # Constructor's pure binding check precedes configure.
            if name == "create_stage":
                state.stage = actual.owned_stage_path
                state.events.append(event)
                if state.fail_stage:
                    raise state.fail_stage
            elif name == "check_private_entry":
                state.events.append((event, str(args[0]), kwargs["directory"]))
                if state.fail_entry and state.fail_entry(Path(args[0]), kwargs["directory"]):
                    raise m.BundleError("injected private-entry rejection")
            else:
                state.events.append(event)
            if name == "after_stage_rename" and state.fail_after:
                raise state.fail_after
            return result

        monkeypatch.setattr(c.WindowsCacheOwner, name, observed)

    for method, event in (
        ("check_installed_paths", "installed"),
        ("check_manifest_paths", "paths"),
        ("assert_held", "held"),
        ("create_stage", "created_stage"),
        ("check_private_entry", "private"),
        ("before_stage_rename", "before_rename"),
        ("after_stage_rename", "after_rename"),
    ):
        wrap(method, event)
    state.run, state.recheck = f.run, f.recheck
    return state


# These inert POSIX fixtures instrument named methods on the concrete owner.
# Literal DOS strings name ordinary temporary POSIX directories here; they do
# not model Windows path resolution, DACL inheritance or native sharing/rename.
# The existing extractor, payload hashes, inventory, marker and rename stay real.
def windows_hook_fixture(tmp_path, monkeypatch):
    c = importlib.import_module(PACKAGE + ".windows_cache")
    if os.name == "nt":
        return windows_composed_hook_fixture(tmp_path, monkeypatch)
    f = Fixture(tmp_path, "windows-x64")
    package_text = r"C:\extension"
    known = r"C:\Users\Alice\AppData\Local"
    cache_text = known + r"\MechanicalCAD\r"
    package, cache = tmp_path / package_text, tmp_path / cache_text
    f.package.rename(package)
    f.cache.rename(cache)
    f.package, f.cache = package, cache
    monkeypatch.chdir(tmp_path)
    release = m.parse_release_manifest(
        encode(f.release), expected_platform="windows-x64", limits=LIMITS
    )
    owner = c.WindowsCacheOwner(
        c.WindowsCacheLocation(known, cache_text),
        package_root=package_text,
        expected_platform="windows-x64",
        release=release,
    )
    state = types.SimpleNamespace(
        owner=owner,
        stage=None,
        events=[],
        fail_stage=None,
        fail_entry=None,
        fail_before=None,
        fail_after=None,
        c=c,
        f=f,
    )

    def installed(actual, package_root, value):
        assert actual is owner and value == release
        assert str(package_root) in {package_text, str(package)}
        state.events.append("installed")

    def paths(actual, value, manifest, stage=None):
        assert actual is owner and value == release and manifest.bundle_id == release.bundle_id
        state.events.append(("paths", None if stage is None else str(stage)))

    def create(actual, value, manifest):
        assert actual is owner and value == release
        stage = cache / (".stage-" + release.bundle_id + "-01234567")
        stage.mkdir(mode=0o700)
        state.stage = str(stage)
        state.events.append("created_stage")
        if state.fail_stage:
            raise state.fail_stage
        return str(stage)

    def private(actual, path, *, directory):
        assert actual is owner
        state.events.append(("private", str(path), directory))
        if state.fail_entry and state.fail_entry(Path(path), directory):
            raise m.BundleError("injected private-entry rejection")

    def before(actual, stage, final):
        assert actual is owner and str(stage) == state.stage
        state.events.append("before_rename")
        if state.fail_before:
            raise state.fail_before

    def after(actual, final):
        assert actual is owner and final == f.final
        state.events.append("after_rename")
        if state.fail_after:
            raise state.fail_after

    monkeypatch.setattr(c.WindowsCacheOwner, "check_installed_paths", installed)
    monkeypatch.setattr(c.WindowsCacheOwner, "check_manifest_paths", paths)
    monkeypatch.setattr(
        c.WindowsCacheOwner, "assert_held", lambda actual: state.events.append("held")
    )
    monkeypatch.setattr(c.WindowsCacheOwner, "create_stage", create)
    monkeypatch.setattr(c.WindowsCacheOwner, "check_private_entry", private)
    monkeypatch.setattr(c.WindowsCacheOwner, "before_stage_rename", before)
    monkeypatch.setattr(c.WindowsCacheOwner, "after_stage_rename", after)
    monkeypatch.setattr(
        c.WindowsCacheOwner, "owned_stage_path", property(lambda actual: state.stage)
    )

    def run(**kwargs):
        return u.materialize_bundle(
            package_text,
            cache_text,
            encode(f.release),
            expected_platform="windows-x64",
            limits=LIMITS,
            pin=f.pin,
            windows_storage=owner,
            **kwargs,
        )

    def recheck():
        return u.verify_cached_bundle(
            package_text,
            cache_text,
            encode(f.release),
            expected_platform="windows-x64",
            limits=LIMITS,
            pin=f.pin,
            windows_storage=owner,
        )

    state.run, state.recheck = run, recheck
    return state


def test_windows_concrete_hooks_keep_real_extraction_hash_inventory_and_rename(
    tmp_path, monkeypatch
):
    state = windows_hook_fixture(tmp_path, monkeypatch)
    result = state.run()
    assert result.root == str(state.f.final)
    assert state.events.index("before_rename") < state.events.index("after_rename")
    private = [
        entry for entry in state.events if isinstance(entry, tuple) and entry[0] == "private"
    ]
    assert any(Path(entry[1]).name == ".bundle-ready.json" and not entry[2] for entry in private)
    assert state.recheck() == result
    assert state.events.count("created_stage") == 1
    for name, value in state.f.contents.items():
        assert (state.f.final / name).read_bytes() == value
    target = state.f.final / "bootstrap.py"
    target.write_bytes(b"x" * target.stat().st_size)
    with pytest.raises(m.BundleError, match="digest mismatch"):
        state.recheck()
    with pytest.raises(u.BundlePreparationError, match="digest mismatch"):
        state.run()
    assert target.read_bytes().startswith(b"x")


def test_windows_zero_direntry_links_require_concrete_proof_even_for_marker(tmp_path, monkeypatch):
    state = windows_hook_fixture(tmp_path, monkeypatch)
    original = os.scandir

    class Scan:
        def __init__(self, path):
            self.scan = original(path)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.scan.close()

        def __iter__(self):
            for entry in self.scan:

                def observe(*, follow_symlinks, entry=entry):
                    info = entry.stat(follow_symlinks=follow_symlinks)
                    return types.SimpleNamespace(
                        st_mode=info.st_mode,
                        st_size=info.st_size,
                        st_nlink=0,
                        st_file_attributes=0,
                    )

                yield types.SimpleNamespace(name=entry.name, stat=observe)

    monkeypatch.setattr(u.os, "scandir", Scan)
    assert state.run().root == str(state.f.final)
    original_read = u._read_bounded

    def marker_read(path, maximum):
        if Path(path).name == ".bundle-ready.json":
            pytest.fail("marker was read before rejecting missing private one-link proof")
        return original_read(path, maximum)

    state.fail_entry = lambda path, directory: path.name == ".bundle-ready.json"
    monkeypatch.setattr(u, "_read_bounded", marker_read)
    with pytest.raises(m.BundleError, match="private-entry rejection"):
        state.recheck()


@pytest.mark.parametrize("failure", ["error", "cancelled", "windows_cancelled"])
def test_windows_created_stage_failure_retains_original_error_without_exists(
    tmp_path,
    monkeypatch,
    failure,
):
    state = windows_hook_fixture(tmp_path, monkeypatch)
    classes = {
        "error": RuntimeError,
        "cancelled": u.BundleCancelled,
        "windows_cancelled": state.c.WindowsCacheCancelled,
    }
    original = (
        classes[failure]()
        if failure == "windows_cancelled"
        else classes[failure]("original_stage_failure")
    )
    state.fail_stage = original

    def forbidden(*args, **kwargs):
        pytest.fail("Windows diagnostic recovery called exists()")

    monkeypatch.setattr(Path, "exists", forbidden)
    if failure == "error":
        with pytest.raises(u.BundlePreparationError) as raised:
            state.run()
        assert raised.value.__cause__ is original
        assert str(raised.value) == "original_stage_failure"
    else:
        with pytest.raises(classes[failure]) as raised:
            state.run()
        assert raised.value is original
    assert raised.value.staging_path == state.stage
    assert state.stage is not None and "before_rename" not in state.events


@pytest.mark.parametrize("phase", ["entry", "before", "after"])
def test_windows_stage_record_survives_later_failures_and_renamed_path(
    tmp_path, monkeypatch, phase
):
    state = windows_hook_fixture(tmp_path, monkeypatch)
    if phase == "entry":
        state.fail_entry = lambda path, directory: path.name == "bootstrap.py"
    elif phase == "before":
        state.fail_before = RuntimeError("original before failure")
    else:
        state.fail_after = RuntimeError("original after failure")

    def forbidden(*args, **kwargs):
        pytest.fail("Windows error diagnostic attempted exists()")

    monkeypatch.setattr(Path, "exists", forbidden)
    with pytest.raises(u.BundlePreparationError) as raised:
        state.run()
    assert raised.value.staging_path == state.stage
    assert raised.value.__cause__ is not None
    if phase == "after":
        assert not os.path.lexists(state.stage) and os.path.lexists(state.f.final)
    else:
        assert os.path.lexists(state.stage) and not os.path.lexists(state.f.final)


def test_windows_unrelated_final_at_publication_keeps_stage_and_skips_stage_identity_compare(
    tmp_path,
    monkeypatch,
):
    import shutil

    state = windows_hook_fixture(tmp_path, monkeypatch)
    original = os.path.lexists
    calls = []

    def appears(path):
        calls.append(str(path))
        if len(calls) == 2:
            shutil.copytree(state.stage, state.f.final)
        return original(path)

    monkeypatch.setattr(u.os.path, "lexists", appears)
    assert state.run().root == str(state.f.final)
    assert Path(state.stage).is_dir()
    assert "before_rename" not in state.events and "after_rename" not in state.events


@pytest.mark.parametrize("function", ["materialize_bundle", "verify_cached_bundle"])
@pytest.mark.parametrize(
    "owner_kind", ["callback", "subclass", "other_cache", "other_package", "other_release"]
)
def test_windows_storage_binding_rejects_before_safe_root_io(
    tmp_path,
    monkeypatch,
    function,
    owner_kind,
):
    c = importlib.import_module(PACKAGE + ".windows_cache")
    f = Fixture(tmp_path, "windows-x64")
    release = m.parse_release_manifest(
        encode(f.release), expected_platform="windows-x64", limits=LIMITS
    )
    known = r"C:\Users\Alice\AppData\Local"
    cache = known + r"\MechanicalCAD\r"
    owner = c.WindowsCacheOwner(
        c.WindowsCacheLocation(known, cache),
        package_root=r"C:\extension",
        expected_platform="windows-x64",
        release=release,
    )
    package = r"C:\extension"
    incoming_release = encode(f.release)
    if owner_kind == "callback":

        def owner():
            return None
    elif owner_kind == "subclass":

        class Subclass(c.WindowsCacheOwner):
            pass

        owner = object.__new__(Subclass)
    elif owner_kind == "other_cache":
        cache = r"C:\other"
    elif owner_kind == "other_release":
        incoming_release = encode(dict(f.release, manifest_sha256="e" * 64))
    else:
        package = r"C:\other"

    def forbidden(*args, **kwargs):
        pytest.fail("invalid Windows storage binding reached root I/O")

    monkeypatch.setattr(u, "_safe_path", forbidden)
    with pytest.raises(m.BundleError):
        getattr(u, function)(
            package,
            cache,
            incoming_release,
            expected_platform="windows-x64",
            limits=LIMITS,
            pin=f.pin,
            windows_storage=owner,
        )


@pytest.mark.skipif(os.name != "nt", reason="Concrete DOS owner on host Windows paths")
@pytest.mark.parametrize(
    "fault", ["links", "reparse", "acl", "rename_identity", "cancel", "cleanup", "native"]
)
def test_windows_composed_owner_positive_then_metadata_fault(tmp_path, fault):
    # A clean complete tree must pass before any negative observation is useful.
    good = Fixture(tmp_path)
    descriptor = good.run()
    good.pin.mode = "shared"
    assert good.recheck() == descriptor
    for owner, api in good.storage.attempts:
        assert owner._state == "closed" and not owner.cleanup_uncertain
        assert not api.handles and not api.allocations
        assert all(resource.closed for resource in owner._resources)
    original_owner = good.storage.attempts[0][0]
    assert original_owner.owned_stage_path is not None
    assert not os.path.lexists(original_owner.owned_stage_path)

    f = Fixture(tmp_path)
    c = f.storage.w
    cancelled = False
    f.storage.cancelled = lambda: cancelled

    def configure(owner, api):
        def info_change(info):
            if info.path.endswith("\\bootstrap.py"):
                if fault == "links":
                    return replace(info, links=2)
                if fault == "reparse":
                    return replace(info, attributes=info.attributes | 0x400)
            if fault == "rename_identity" and info.path == str(f.final):
                return replace(info, identity=(info.identity[0], info.identity[1] + 1))
            return info

        def security_change(value):
            if fault == "acl" and api.security_path.endswith("\\bootstrap.py"):
                return replace(value, owner=bytes.fromhex("010100000000000100000000"))
            return value

        def hook(event):
            nonlocal cancelled
            if fault == "cancel" and event[0] == "attributes" and "\\.stage-" in event[1]:
                cancelled = True
            if fault == "cleanup" and event[0] == "free" and owner.owned_stage_path:
                raise OSError("injected uncertain metadata cleanup")
            if fault == "native" and event[0] == "token_open":
                c._WindowsAPI()

        api.info_change, api.security_change, api.hook = info_change, security_change, hook

    f.storage.configure = configure
    expected = c.WindowsCacheCancelled if fault == "cancel" else u.BundlePreparationError
    # Native factory poisoning fails in owner acquisition, before materializer.
    if fault == "native":
        expected = c.WindowsCacheError
    with pytest.raises(expected) as raised:
        f.run()
    owner, api = f.storage.attempts[-1]
    assert len(api.closed) == len(set(api.closed))
    assert len(api.freed) == len(set(api.freed))
    if fault == "native":
        assert isinstance(raised.value.__cause__, AssertionError)
        assert "must not bind native" in str(raised.value.__cause__)
        assert owner.owned_stage_path is None
    else:
        assert raised.value.staging_path == owner.owned_stage_path
        assert owner.owned_stage_path is not None
        assert os.path.lexists(f.final if fault == "rename_identity" else owner.owned_stage_path)
        if fault != "cancel":
            assert type(raised.value.__cause__) is c.WindowsCacheError
            assert (
                raised.value.__cause__.code
                == {
                    "links": "windows_cache_unsupported_location",
                    "reparse": "windows_cache_unsupported_location",
                    "acl": "windows_cache_not_private",
                    "rename_identity": "windows_cache_unsupported_location",
                    "cleanup": "cleanup_blocked",
                }[fault]
            )
    if fault == "cleanup":
        assert owner.cleanup_uncertain
        assert any(resource.attempted and not resource.closed for resource in owner._resources)
        assert api.allocations  # Uncertain cleanup stays owned; no retry or deletion.
    else:
        assert owner._state == "closed"
        assert not api.handles and not api.allocations
