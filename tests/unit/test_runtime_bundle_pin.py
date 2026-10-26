"""Real Linux flock processes and fake Win32 calls; no CAD/native backend launch."""

import ctypes
import errno
import importlib.util
import json
import os
import selectors
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "blender_addon/mechanical_cad_blender/runtime_bundle_pin.py"
SPEC = importlib.util.spec_from_file_location("mcad_bundle_pin_tests", MODULE_PATH)
p = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = p
SPEC.loader.exec_module(p)
BUNDLE = "a" * 64
POSIX = pytest.mark.skipif(sys.platform != "linux", reason="genuine Linux flock test")


def worker(function, *args, **kwargs):
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(function, *args, **kwargs).result(timeout=10)


def acquire(root, mode="shared", **kwargs):
    return worker(p.acquire_bundle_pin, root, BUNDLE, mode, **kwargs)


def injected(root, api, mode="shared", **kwargs):
    options = {"timeout": 1, "cancelled": lambda: False, "api": api}
    options.update(kwargs)
    return worker(p._acquire, root, BUNDLE, mode, **options)


@pytest.fixture
def cache(tmp_path):
    root = tmp_path / "cache 中文 é"
    root.mkdir()
    return root


def test_main_thread_acquisition_rejected_before_io(cache):
    with pytest.raises(p.BundlePinError, match="worker_acquisition_required"):
        p.acquire_bundle_pin(cache, BUNDLE, "shared")
    assert list(cache.iterdir()) == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("bundle_id", "../" + "a" * 64),
        ("bundle_id", "A" * 64),
        ("bundle_id", "a" * 63),
        ("bundle_id", None),
        ("mode", "upgrade"),
        ("mode", None),
        ("timeout", 0),
        ("timeout", -1),
        ("timeout", float("inf")),
        ("timeout", float("nan")),
        ("timeout", True),
        ("timeout", 301),
        ("cancelled", False),
        ("cache_root", "relative"),
        ("cache_root", b"/tmp"),
        ("cache_root", "/tmp/../tmp"),
        ("cache_root", "/tmp/\0bad"),
    ],
)
def test_reject_invalid_contract_before_cache_writes(cache, field, value):
    args = dict(
        cache_root=cache, bundle_id=BUNDLE, mode="shared", timeout=1, cancelled=lambda: False
    )
    args[field] = value
    with pytest.raises(p.BundlePinError):
        worker(p.acquire_bundle_pin, **args)
    assert list(cache.iterdir()) == []


@POSIX
def test_stable_outside_tree_no_content_or_runtime_writes(cache):
    final = cache / BUNDLE
    final.mkdir()
    sentinel = final / "runtime"
    sentinel.write_bytes(b"immutable")
    pin = acquire(cache, "exclusive")
    pin.assert_held()
    lock = cache / ".bundle-pins" / (BUNDLE + ".lock")
    identity = lock.stat().st_ino
    assert lock.read_bytes() == b""
    assert all(not os.get_inheritable(a.handle) for a in pin._anchors)
    with pytest.raises(AttributeError):
        pin.mode = "shared"
    with pytest.raises(AttributeError):
        pin.bundle_id = "b" * 64
    pin.release()
    pin.release()
    with pytest.raises(p.BundlePinError, match="pin_not_held"):
        pin.assert_held()
    second = acquire(cache)
    try:
        assert second.mode == "shared" and second.bundle_id == BUNDLE
        assert lock.stat().st_ino == identity
        assert sentinel.read_bytes() == b"immutable"
        assert sorted(item.name for item in cache.iterdir()) == [".bundle-pins", BUNDLE]
    finally:
        second.release()


@POSIX
@pytest.mark.parametrize(
    "kind",
    [
        "ancestor_link",
        "cache_link",
        "lock_root_link",
        "file_link",
        "dangling_link",
        "hardlink",
        "fifo",
        "directory",
    ],
)
def test_unsafe_paths_fail_closed_without_repair(cache, tmp_path, kind):
    lock_root = cache / ".bundle-pins"
    lock_root.mkdir()
    lock = lock_root / (BUNDLE + ".lock")
    target = tmp_path / "original"
    target.write_bytes(b"untouched")
    root = cache
    if kind == "ancestor_link":
        link = tmp_path / "ancestor"
        link.symlink_to(tmp_path, target_is_directory=True)
        root = link / cache.name
    elif kind == "cache_link":
        root = tmp_path / "cache link"
        root.symlink_to(cache, target_is_directory=True)
    elif kind == "lock_root_link":
        lock_root.rmdir()
        lock_root.symlink_to(tmp_path, target_is_directory=True)
    elif kind in {"file_link", "dangling_link"}:
        lock.symlink_to(target if kind == "file_link" else tmp_path / "absent")
    elif kind == "hardlink":
        os.link(target, lock)
    elif kind == "fifo":
        os.mkfifo(lock)
    else:
        lock.mkdir()
    started = time.monotonic()
    with pytest.raises(p.BundlePinError):
        acquire(root)
    assert time.monotonic() - started < 3
    assert target.read_bytes() == b"untouched"
    assert lock_root.exists()


@POSIX
@pytest.mark.parametrize("where", ["file", "lock_directory", "cache", "ancestor"])
def test_path_replacement_revokes_but_releases_original_handles(cache, tmp_path, where):
    pin = acquire(cache)
    path = {
        "file": cache / ".bundle-pins" / (BUNDLE + ".lock"),
        "lock_directory": cache / ".bundle-pins",
        "cache": cache,
        "ancestor": tmp_path,
    }[where]
    moved = path.with_name(path.name + "-moved")
    path.rename(moved)
    if where == "file":
        path.write_bytes(b"replacement")
    else:
        path.mkdir()
    handles = [a.handle for a in pin._anchors]
    with pytest.raises(p.BundlePinError, match="pin_identity_unavailable"):
        pin.assert_held()
    pin.release()
    for handle in handles:
        with pytest.raises(OSError):
            os.fstat(handle)
    if where == "file":
        assert path.read_bytes() == b"replacement"
    # Restore pytest's own temporary ancestor for ordinary fixture cleanup.
    if where == "ancestor":
        path.rmdir()
        moved.rename(path)


@POSIX
def test_other_bundle_publication_does_not_invalidate_directory_anchors(cache):
    pin = acquire(cache)
    try:
        (cache / ("b" * 64)).mkdir()
        pin.assert_held()
    finally:
        pin.release()


class RecordingAPI:
    def __init__(self):
        self.real = p._PosixAPI()
        self.opened, self.closed = [], []
        self.locks, self.unlocks = 0, 0
        self.fail_info = False
        self.fail_unlock = False
        self.fail_close = False
        self.close_replacement = None

    def open(self, path, *, directory, parent=None):
        value = self.real.open(path, directory=directory, parent=parent)
        self.opened.append(value)
        return value

    def mkdir(self, path, *, parent):
        self.real.mkdir(path, parent=parent)

    def info(self, handle):
        if self.fail_info:
            raise OSError("metadata unavailable")
        return self.real.info(handle)

    def check_path_identity(self, actual, observed):
        self.real.check_path_identity(actual, observed)

    def try_lock(self, handle, mode):
        self.locks += 1
        return self.real.try_lock(handle, mode)

    def unlock(self, handle):
        self.unlocks += 1
        if self.fail_unlock:
            raise OSError("uncertain unlock")
        self.real.unlock(handle)

    def close(self, handle):
        self.closed.append(handle)
        self.real.close(handle)
        if self.fail_close:
            self.fail_close = False
            self.close_replacement = os.open(os.devnull, os.O_RDONLY)
            raise OSError("close succeeded before transport failure")


@POSIX
def test_partial_open_failure_closes_owned_handle(cache):
    api = RecordingAPI()
    api.fail_info = True
    with pytest.raises(p.BundlePinError, match="pin_acquisition_failed") as error:
        injected(cache, api)
    assert error.value.pin is None
    assert len(api.opened) == 1 and api.closed == api.opened


@POSIX
def test_partial_close_uncertainty_exposes_owner_and_never_retries(cache):
    api = RecordingAPI()
    api.fail_info = api.fail_close = True
    try:
        with pytest.raises(p.BundlePinError, match="pin_release_uncertain") as error:
            injected(cache, api)
        retained = error.value.pin
        assert retained is not None
        with pytest.raises(p.BundlePinError, match="pin_release_uncertain"):
            retained.release()
        assert len(api.closed) == 1
        os.fstat(api.close_replacement)
    finally:
        if api.close_replacement is not None:
            os.close(api.close_replacement)


@POSIX
@pytest.mark.parametrize("failure", ["close", "unlock"])
def test_release_uncertainty_never_retries_and_caller_retains_lease(cache, failure):
    api = RecordingAPI()
    pin = injected(cache, api)
    setattr(api, "fail_" + failure, True)
    try:
        with pytest.raises(p.BundlePinError, match="pin_release_uncertain") as error:
            pin.release()
        assert error.value.pin is pin
        with pytest.raises(p.BundlePinError, match="pin_not_held"):
            pin.assert_held()
        with pytest.raises(p.BundlePinError, match="pin_release_uncertain"):
            pin.release()
        assert len(api.closed) == len(api.opened)
        assert len(set(api.closed)) == len(api.closed)
        assert api.unlocks == 1
        if api.close_replacement is not None:
            os.fstat(api.close_replacement)  # Numeric handle was reused, not closed twice.
    finally:
        if api.close_replacement is not None:
            os.close(api.close_replacement)


@POSIX
def test_cancelled_after_successful_lock_releases_before_return(cache):
    api = RecordingAPI()
    with pytest.raises(p.BundlePinCancelled):
        injected(cache, api, cancelled=lambda: api.locks > 0)
    assert api.unlocks == 1 and len(api.closed) == len(api.opened)
    pin = acquire(cache, "exclusive")
    pin.release()


@POSIX
def test_initial_cancellation_writes_nothing(cache):
    with pytest.raises(p.BundlePinCancelled):
        acquire(cache, cancelled=lambda: True)
    assert list(cache.iterdir()) == []


@POSIX
def test_fixed_deadline_and_poll_interval_do_not_reset_on_contention(cache):
    api = RecordingAPI()
    now, sleeps = [10.0], []

    def blocked(handle, mode):
        api.locks += 1
        return False

    def sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    api.try_lock = blocked
    with pytest.raises(p.BundlePinTimeout):
        injected(cache, api, timeout=0.035, clock=lambda: now[0], sleep=sleep)
    assert api.locks == 4
    assert all(0 < value <= p.POLL_SECONDS for value in sleeps)
    assert sum(sleeps) == pytest.approx(0.035)
    assert len(api.closed) == len(api.opened)


@POSIX
def test_post_lock_deadline_cannot_return_late_pin(cache):
    api = RecordingAPI()
    now = [10.0]
    real = api.try_lock

    def delayed(handle, mode):
        locked = real(handle, mode)
        now[0] += 2
        return locked

    api.try_lock = delayed
    with pytest.raises(p.BundlePinTimeout):
        injected(cache, api, clock=lambda: now[0])
    assert api.unlocks == 1


@POSIX
def test_post_lock_identity_check_cannot_return_after_deadline(cache):
    api = RecordingAPI()
    now = [10.0]
    real = api.info

    def delayed(handle):
        if api.locks:
            now[0] += 2
        return real(handle)

    api.info = delayed
    with pytest.raises(p.BundlePinTimeout):
        injected(cache, api, clock=lambda: now[0])
    assert api.unlocks == 1


@POSIX
def test_cancel_during_contention_is_observed_without_deadline_reset(cache):
    first = acquire(cache, "exclusive")
    cancelled = threading.Event()
    timer = threading.Timer(0.04, cancelled.set)
    timer.start()
    try:
        with pytest.raises(p.BundlePinCancelled):
            acquire(cache, timeout=2, cancelled=cancelled.is_set)
        first.assert_held()
    finally:
        timer.cancel()
        first.release()


@POSIX
def test_flock_unexpected_error_is_not_treated_as_contention(cache):
    api = RecordingAPI()

    def failure(handle, mode):
        raise OSError(errno.EBADF, "bad fd")

    api.try_lock = failure
    with pytest.raises(p.BundlePinError, match="pin_acquisition_failed"):
        injected(cache, api)
    assert len(api.closed) == len(api.opened)


@POSIX
@pytest.mark.parametrize("replacement", ["symlink", "fifo"])
def test_replacement_between_observation_and_open_cannot_follow_or_block(
    cache, tmp_path, replacement
):
    api = RecordingAPI()
    real = api.open
    target = tmp_path / "target"
    target.write_bytes(b"unmodified")

    def replace_then_open(path, *, directory, parent=None):
        if not directory:
            if replacement == "symlink":
                path.symlink_to(target)
            else:
                os.mkfifo(path)
        return real(path, directory=directory, parent=parent)

    api.open = replace_then_open
    with pytest.raises(p.BundlePinError):
        injected(cache, api)
    assert target.read_bytes() == b"unmodified"
    assert len(api.closed) == len(api.opened)


@POSIX
@pytest.mark.parametrize("during", ["mkdir", "file_open"])
def test_retained_parent_descriptor_prevents_ancestry_swap_redirect(cache, tmp_path, during):
    api = RecordingAPI()
    outside = tmp_path / "outside"
    outside.mkdir()
    if during == "mkdir":
        real = api.mkdir

        def replace_then_mkdir(path, *, parent):
            cache.rename(tmp_path / "retained-cache")
            cache.symlink_to(outside, target_is_directory=True)
            return real(path, parent=parent)

        api.mkdir = replace_then_mkdir
    else:
        real = api.open

        def replace_then_open(path, *, directory, parent=None):
            if not directory:
                path.parent.rename(cache / "retained-pins")
                path.parent.symlink_to(outside, target_is_directory=True)
            return real(path, directory=directory, parent=parent)

        api.open = replace_then_open
    with pytest.raises(p.BundlePinError):
        injected(cache, api)
    assert list(outside.iterdir()) == []
    assert len(api.closed) == len(api.opened)


CHILD = r"""
import importlib.util, json, pathlib, sys
from concurrent.futures import ThreadPoolExecutor
spec = importlib.util.spec_from_file_location("pin_child", sys.argv[1])
p = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = p
spec.loader.exec_module(p)
try:
    with ThreadPoolExecutor(max_workers=1) as pool:
        pin = pool.submit(p.acquire_bundle_pin, pathlib.Path(sys.argv[2]),
                          sys.argv[3], sys.argv[4], timeout=float(sys.argv[5])).result()
except p.BundlePinError as error:
    print(json.dumps({"error": error.code}), flush=True)
else:
    print(json.dumps({"held": pin.mode}), flush=True)
    sys.stdin.readline()
    pin.assert_held()
    pin.release()
    print(json.dumps({"released": True}), flush=True)
"""


def line(process):
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ)
        if not selector.select(5):
            raise AssertionError("child process did not report within five seconds")
        value = process.stdout.readline()
        assert value, process.stderr.read()
        return json.loads(value)


@contextmanager
def child(cache, mode, *, bundle=BUNDLE, timeout=0.15):
    process = subprocess.Popen(
        [
            sys.executable,
            "-B",
            "-c",
            CHILD,
            str(MODULE_PATH),
            str(cache),
            bundle,
            mode,
            str(timeout),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={"PATH": os.defpath, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    try:
        yield process, line(process)
    finally:
        if process.poll() is None:
            try:
                process.communicate("release\n", timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=5)
        else:
            process.communicate(timeout=5)


@POSIX
@pytest.mark.parametrize(
    "first,second,allowed",
    [
        ("shared", "shared", True),
        ("shared", "exclusive", False),
        ("exclusive", "shared", False),
        ("exclusive", "exclusive", False),
    ],
)
def test_real_linux_multiprocess_shared_exclusive_matrix(cache, first, second, allowed):
    with child(cache, first) as (owner, receipt):
        assert receipt == {"held": first}
        with child(cache, second) as (other, observed):
            assert observed == (
                {"held": second} if allowed else {"error": "pin_acquisition_timeout"}
            )
        assert owner.poll() is None
    with child(cache, "exclusive") as (owner, receipt):
        assert receipt == {"held": "exclusive"}


@POSIX
def test_each_process_retains_independent_shared_lock(cache):
    with child(cache, "shared") as (first, receipt):
        assert receipt == {"held": "shared"}
        with child(cache, "shared") as (second, receipt):
            assert receipt == {"held": "shared"}
            first.communicate("release\n", timeout=5)
            with child(cache, "exclusive") as (_, blocked):
                assert blocked == {"error": "pin_acquisition_timeout"}
            assert second.poll() is None


@POSIX
def test_different_bundle_locks_do_not_interfere(cache):
    with child(cache, "exclusive") as (_, receipt):
        assert receipt == {"held": "exclusive"}
        with child(cache, "exclusive", bundle="b" * 64) as (_, other):
            assert other == {"held": "exclusive"}


@POSIX
def test_parent_process_death_releases_os_lock_without_deleting_any_tree(cache):
    runtime = cache / BUNDLE
    runtime.mkdir()
    (runtime / "sentinel").write_bytes(b"retained")
    with child(cache, "exclusive") as (owner, receipt):
        assert receipt == {"held": "exclusive"}
        lock = cache / ".bundle-pins" / (BUNDLE + ".lock")
        identity = lock.stat().st_ino
        owner.kill()
        owner.wait(timeout=5)
    with child(cache, "exclusive") as (_, receipt):
        assert receipt == {"held": "exclusive"}
    assert lock.stat().st_ino == identity
    assert (runtime / "sentinel").read_bytes() == b"retained"
    # This tests only the lock-owning Python process. No surviving child cleanup
    # or CAD/native process containment is established or used to retire a cache.


class Function:
    def __init__(self, callback):
        self.callback = callback

    def __call__(self, *args):
        return self.callback(*args)


class FakeKernel:
    def __init__(self):
        self.error = 0
        self.calls = []
        self.attributes = 0x80
        self.inheritable = 0
        self.file_type = 1
        self.links = 1
        self.lock_ok = self.unlock_ok = self.close_ok = self.info_ok = True
        self.handle = 101
        for name in (
            "CreateFileW",
            "GetFileInformationByHandle",
            "GetHandleInformation",
            "GetFileType",
            "LockFileEx",
            "UnlockFileEx",
            "CloseHandle",
        ):
            setattr(self, name, Function(getattr(self, "_" + name)))

    def _CreateFileW(self, *args):
        self.calls.append(("open", args))
        return self.handle

    def _GetFileInformationByHandle(self, handle, output):
        info = output._obj
        info.attributes, info.links = self.attributes, self.links
        info.volume, info.index_high, info.index_low = 11, 22, 33
        return self.info_ok

    def _GetHandleInformation(self, handle, output):
        output._obj.value = self.inheritable
        return True

    def _GetFileType(self, handle):
        return self.file_type

    def _LockFileEx(self, handle, flags, reserved, low, high, overlap):
        self.calls.append(
            (
                "lock",
                (
                    handle,
                    flags,
                    reserved,
                    low,
                    high,
                    overlap._obj.offset,
                    overlap._obj.offset_high,
                    overlap._obj.event,
                ),
            )
        )
        return self.lock_ok

    def _UnlockFileEx(self, handle, reserved, low, high, overlap):
        self.calls.append(
            ("unlock", (handle, reserved, low, high, overlap._obj.offset, overlap._obj.offset_high))
        )
        return self.unlock_ok

    def _CloseHandle(self, handle):
        self.calls.append(("close", handle))
        return self.close_ok


def winapi():
    kernel = FakeKernel()
    return kernel, p._Win32API(kernel=kernel, last_error=lambda: kernel.error)


def test_win32_binding_uses_fixed_width_structures_and_declared_signatures():
    kernel, api = winapi()
    assert ctypes.sizeof(api._Info) == 52
    assert ctypes.sizeof(api._Overlapped) == (32 if ctypes.sizeof(ctypes.c_void_p) == 8 else 20)
    assert len(kernel.CreateFileW.argtypes) == 7
    assert len(kernel.LockFileEx.argtypes) == 6


@pytest.mark.parametrize("directory", [True, False])
def test_win32_open_is_noninheritable_no_delete_sharing_no_truncation(directory):
    kernel, api = winapi()
    assert api.open(Path("cache é"), directory=directory) == 101
    _, arguments = kernel.calls[-1]
    path, access, share, security, disposition, flags, template = arguments
    assert path == "cache é"
    assert share == 3 and security is None and template is None
    assert disposition == (3 if directory else 4)  # OPEN_EXISTING / OPEN_ALWAYS.
    assert access == (0x80 if directory else 0xC0000000)
    assert flags & 0x00200000  # FILE_FLAG_OPEN_REPARSE_POINT.
    assert bool(flags & 0x02000000) == directory
    assert not flags & 0x40000000  # No FILE_FLAG_OVERLAPPED/pending locks.


@pytest.mark.parametrize("mode,flags", [("shared", 1), ("exclusive", 3)])
def test_win32_lock_exact_original_handle_one_byte_nonblocking(mode, flags):
    kernel, api = winapi()
    assert api.try_lock(101, mode)
    assert kernel.calls[-1] == ("lock", (101, flags, 0, 1, 0, 0, 0, None))
    api.unlock(101)
    api.close(101)
    assert kernel.calls[-2:] == [("unlock", (101, 0, 1, 0, 0, 0)), ("close", 101)]


@pytest.mark.parametrize("error,contention", [(33, True), (997, False), (5, False), (6, False)])
def test_win32_only_lock_violation_retries(error, contention):
    kernel, api = winapi()
    kernel.lock_ok, kernel.error = False, error
    if contention:
        assert api.try_lock(101, "shared") is False
    else:
        with pytest.raises(p.BundlePinError, match="win32_pin_lock_failed"):
            api.try_lock(101, "shared")


@pytest.mark.parametrize("change", ["reparse", "directory", "hardlink", "device", "inheritable"])
def test_win32_rejects_unsafe_handle_metadata(change):
    kernel, api = winapi()
    if change == "reparse":
        kernel.attributes |= 0x400
    elif change == "directory":
        kernel.attributes |= 0x10
    elif change == "hardlink":
        kernel.links = 2
    elif change == "device":
        kernel.file_type = 2
    else:
        kernel.inheritable = 1
    with pytest.raises(p.BundlePinError):
        p._validate(api.info(101), directory=False)


@pytest.mark.parametrize("operation", ["open", "info", "unlock", "close"])
def test_win32_api_errors_fail_closed(operation):
    kernel, api = winapi()
    kernel.error = 5
    if operation == "open":
        kernel.handle = ctypes.c_void_p(-1).value

        def call():
            return api.open(Path("cache"), directory=False)
    else:
        setattr(kernel, operation + "_ok", False)

        def call():
            return getattr(api, operation)(101)

    with pytest.raises(p.BundlePinError, match="win32_pin_" + operation + "_failed"):
        call()


def test_module_import_does_not_bind_win32_or_import_cad_and_has_no_live_importers():
    assert "bpy" not in p.__dict__ and "OCP" not in p.__dict__
    assert not hasattr(p, "kernel32")
    entry = ROOT / "blender_addon/mechanical_cad_blender/__init__.py"
    if entry.exists():
        assert "runtime_bundle_pin" not in entry.read_text()


class FakePathKernel(FakeKernel):
    """Host file handles only supply fixtures; no Win32 locking is exercised."""

    def __init__(self):
        super().__init__()
        self.opened, self.closed = [], []
        self.fail_close_once = False
        self.replacement = None
        self.fail_info_after = None

    def _CreateFileW(self, path, access, share, security, disposition, flags, template):
        self.calls.append(("open", (path, access, share, security, disposition, flags, template)))
        directory = bool(flags & 0x02000000)
        handle = p._PosixAPI().open(Path(path), directory=directory)
        self.opened.append(handle)
        return handle

    def _GetFileInformationByHandle(self, handle, output):
        original = os.fstat(handle)
        info = output._obj
        info.attributes = 0x10 if os.path.isdir(f"/proc/self/fd/{handle}") else 0x80
        info.links = original.st_nlink
        info.volume, info.index_high, info.index_low = original.st_dev, 0, original.st_ino
        if self.fail_info_after is not None and len(self.opened) >= self.fail_info_after:
            self.error = 5
            return False
        return True

    def _CloseHandle(self, handle):
        self.calls.append(("close", handle))
        self.closed.append(handle)
        os.close(handle)
        if self.fail_close_once:
            self.fail_close_once = False
            self.replacement = os.open(os.devnull, os.O_RDONLY)
            self.error = 6
            return False
        return True


@POSIX
@pytest.mark.parametrize("mode", ["shared", "exclusive"])
def test_fake_win32_owner_closes_original_handle_after_unlock(cache, mode):
    kernel = FakePathKernel()
    api = p._Win32API(kernel=kernel, last_error=lambda: kernel.error)
    pin = injected(cache, api, mode)
    handle = kernel.opened[-1]
    pin.assert_held()
    pin.release()
    assert ("unlock", (handle, 0, 1, 0, 0, 0)) in kernel.calls
    assert kernel.closed == list(reversed(kernel.opened))
    assert [call[1][1] for call in kernel.calls if call[0] == "lock"] == [
        1 if mode == "shared" else 3
    ]


@POSIX
def test_fake_win32_partial_failure_retains_and_closes_acquired_resources(cache):
    kernel = FakePathKernel()
    kernel.fail_info_after = 3
    api = p._Win32API(kernel=kernel, last_error=lambda: kernel.error)
    with pytest.raises(p.BundlePinError, match="win32_pin_info_failed"):
        injected(cache, api)
    assert kernel.closed == list(reversed(kernel.opened))


@POSIX
def test_fake_win32_close_uncertainty_never_closes_reused_handle(cache):
    kernel = FakePathKernel()
    api = p._Win32API(kernel=kernel, last_error=lambda: kernel.error)
    pin = injected(cache, api)
    kernel.fail_close_once = True
    try:
        with pytest.raises(p.BundlePinError, match="pin_release_uncertain") as error:
            pin.release()
        assert error.value.pin is pin
        with pytest.raises(p.BundlePinError, match="pin_release_uncertain"):
            pin.release()
        assert kernel.closed == list(reversed(kernel.opened))
        os.fstat(kernel.replacement)
    finally:
        if kernel.replacement is not None:
            os.close(kernel.replacement)
