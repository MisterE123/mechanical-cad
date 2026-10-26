"""Setup worker tests: fake ownership plus tiny real Linux stdlib composition."""

import ast
import hashlib
import importlib
import io
import json
import stat
import sys
import threading
import types
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "mcad_bundle_prepare_tests"
package = sys.modules.setdefault(PACKAGE, types.ModuleType(PACKAGE))
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
m = importlib.import_module(PACKAGE + ".runtime_bundle_manifest")
u = importlib.import_module(PACKAGE + ".runtime_bundle_materialize")
p = importlib.import_module(PACKAGE + ".runtime_bundle_pin")
w = importlib.import_module(PACKAGE + ".runtime_bundle_prepare")
LIMITS = m.BundleLimits(chunk_bytes=3, reserve_free_bytes=0)
BUNDLE = m.bundle_identity("a" * 40, "b" * 64, "linux-x64")
POSIX = pytest.mark.skipif(sys.platform != "linux", reason="genuine Linux pin composition")


def encode(value):
    return json.dumps(value, separators=(",", ":")).encode("ascii")


def release_bytes():
    return encode(
        {
            "schema_version": 1,
            "bundle_id": BUNDLE,
            "source_commit": "a" * 40,
            "runtime_lock_sha256": "b" * 64,
            "platform": "linux-x64",
            "manifest_path": f"_backend/{BUNDLE}/bundle-manifest.json",
            "manifest_sha256": "c" * 64,
            "payload_path": f"_backend/{BUNDLE}/payload.zip",
            "payload_sha256": "d" * 64,
            "payload_size": 100,
        }
    )


def descriptor(cache):
    root = Path(cache) / BUNDLE
    return m.BundleDescriptor(
        BUNDLE,
        "a" * 40,
        "b" * 64,
        "linux-x64",
        "c" * 64,
        "d" * 64,
        str(root),
        str(root / "python/bin/python3.12"),
        str(root / "bootstrap.py"),
    )


def job(tmp_path, **kwargs):
    values = dict(
        package_root=str(tmp_path / "package"),
        cache_root=str(tmp_path / "cache"),
        release_data=release_bytes(),
        expected_platform="linux-x64",
        limits=LIMITS,
        pin_timeout=1,
    )
    values.update(kwargs)
    return w.BundlePreparationJob(**values)


def finish(owner):
    owner._worker.join(timeout=5)
    assert not owner._worker.is_alive(), "setup worker failed to finish"
    return owner.poll()


def wait(event):
    assert event.wait(5), "controlled worker checkpoint was not reached"


class Pin:
    def __init__(self, release=None):
        self.release_calls = 0
        self.release_hook = release
        self.held = True

    def release(self):
        assert threading.current_thread() is not threading.main_thread()
        self.release_calls += 1
        assert self.release_calls == 1
        if self.release_hook:
            self.release_hook()
        self.held = False


@pytest.fixture
def fake(monkeypatch):
    state = types.SimpleNamespace(pin=Pin(), acquisitions=[], materializations=[])

    def acquire(cache_root, bundle_id, mode, **options):
        assert threading.current_thread() is not threading.main_thread()
        assert (bundle_id, mode) == (BUNDLE, "exclusive")
        state.acquisitions.append((cache_root, options))
        return state.pin

    def materialize(package_root, cache_root, release_data, **options):
        assert threading.current_thread() is not threading.main_thread()
        assert options["pin"] is state.pin and state.pin.held
        state.materializations.append((package_root, cache_root, release_data, options))
        return descriptor(cache_root)

    monkeypatch.setattr(w, "acquire_bundle_pin", acquire)
    monkeypatch.setattr(w, "materialize_bundle", materialize)
    return state


def test_success_captures_exact_inputs_and_returns_descriptor_only_once(
    tmp_path, fake, monkeypatch
):
    limits = m.BundleLimits(chunk_bytes=7, reserve_free_bytes=0)
    data = release_bytes() + b" \n"
    owner = job(tmp_path, limits=limits, release_data=data)
    object.__setattr__(limits, "chunk_bytes", 999)
    original = w.parse_release_manifest
    calls = []

    def parse(*args, **kwargs):
        assert threading.current_thread() is not threading.main_thread()
        calls.append(args[0])
        return original(*args, **kwargs)

    monkeypatch.setattr(w, "parse_release_manifest", parse)
    assert owner.poll() == "created" and not owner.done
    with pytest.raises(w.BundlePreparationJobError, match="not_ready"):
        owner.result()
    assert owner.start() is owner
    assert finish(owner) == "ready" and owner.done
    assert calls == [data]
    assert fake.acquisitions[0][0] == str(tmp_path / "cache")
    assert fake.acquisitions[0][1]["timeout"] == 1
    package_root, cache_root, captured, options = fake.materializations[0]
    assert package_root == str(tmp_path / "package") and cache_root == str(tmp_path / "cache")
    assert captured is data and options["limits"] is not limits
    assert options["limits"].chunk_bytes == 7 and options["expected_platform"] == "linux-x64"
    assert fake.pin.release_calls == 1 and owner._pin is None
    result = owner.result()
    assert result == descriptor(cache_root)
    assert owner.poll() == "consumed" and owner.done
    assert not owner.cancel()
    with pytest.raises(w.BundlePreparationJobError, match="already_consumed"):
        owner.result()
    with pytest.raises(w.BundlePreparationJobError, match="already_started"):
        owner.start()


def test_capture_prestart_cancel_poll_and_result_do_no_work(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("capture or main-thread lifecycle performed worker work")

    for name in ("parse_release_manifest", "acquire_bundle_pin", "materialize_bundle"):
        monkeypatch.setattr(w, name, forbidden)
    monkeypatch.setattr(w.threading, "Thread", forbidden)
    owner = job(tmp_path, release_data=b"not parsed on construction")
    assert owner.poll() == "created" and owner.diagnostic == ""
    assert owner.staging_path is None
    assert owner.cancel() and not owner.cancel()
    assert owner.start() is owner and owner.poll() == "cancelled" and owner.done
    with pytest.raises(w.BundlePreparationJobError, match="cancelled"):
        owner.result()
    assert owner.poll() == "consumed"


@pytest.mark.parametrize(
    "field,value",
    [
        ("release_data", bytearray(b"{}")),
        ("release_data", "{}"),
        ("limits", {}),
        ("expected_platform", None),
        ("expected_platform", "other"),
        ("package_root", "relative"),
        ("package_root", "/tmp/../tmp"),
        ("package_root", "/tmp/\0bad"),
        ("package_root", "/tmp/\ud800"),
        ("package_root", "/" + "x" * w.MAX_ROOT_CHARS),
        ("package_root", "/" + "x/" * 129),
        ("cache_root", Path("/tmp/cache")),
        ("cache_root", b"/tmp/cache"),
        ("pin_timeout", True),
        ("pin_timeout", 0),
        ("pin_timeout", -1),
        ("pin_timeout", 301),
        ("pin_timeout", float("inf")),
        ("pin_timeout", float("nan")),
    ],
)
def test_capture_rejects_invalid_primitives_without_work(tmp_path, field, value, fake):
    with pytest.raises(w.BundlePreparationJobError):
        job(tmp_path, **{field: value})
    assert not fake.acquisitions and not fake.materializations


def test_release_size_rejected_before_json_parsing(tmp_path, fake):
    with pytest.raises(w.BundlePreparationJobError, match="invalid_release_bytes"):
        job(tmp_path, limits=m.BundleLimits(max_json_bytes=2))
    assert not fake.acquisitions


@pytest.mark.parametrize(
    "data", [b"", b"not JSON", release_bytes().replace(b"linux-x64", b"other")]
)
def test_invalid_release_fails_on_worker_before_pin_acquisition(tmp_path, fake, data):
    owner = job(tmp_path, release_data=data).start()
    assert finish(owner) == "failed" and owner.done
    assert not fake.acquisitions and not fake.materializations
    with pytest.raises(w.BundlePreparationJobError, match="preparation_failed"):
        owner.result()
    assert owner.poll() == "consumed"


def test_descriptor_waits_for_release_and_ui_poll_does_not_wait(tmp_path, fake):
    entered, proceed = threading.Event(), threading.Event()

    def release():
        entered.set()
        wait(proceed)

    fake.pin.release_hook = release
    owner = job(tmp_path).start()
    try:
        wait(entered)
        assert owner.poll() == "running" and not owner.done
        with pytest.raises(w.BundlePreparationJobError, match="not_ready"):
            owner.result()
        assert owner._descriptor is None
    finally:
        proceed.set()
    assert finish(owner) == "ready"
    assert owner.result().bundle_id == BUNDLE


def test_cancel_during_release_revokes_completion_but_waits_for_cleanup(tmp_path, fake):
    entered, proceed = threading.Event(), threading.Event()
    fake.pin.release_hook = lambda: (entered.set(), wait(proceed))
    owner = job(tmp_path).start()
    try:
        wait(entered)
        assert owner.cancel()
        assert owner.poll() == "cancelling" and not owner.done
        assert not owner.cancel()
        with pytest.raises(w.BundlePreparationJobError, match="not_ready"):
            owner.result()
    finally:
        proceed.set()
    assert finish(owner) == "cancelled" and owner.done
    with pytest.raises(w.BundlePreparationJobError, match="cancelled"):
        owner.result()
    assert fake.pin.release_calls == 1


def test_cancel_during_acquire_that_returns_pin_still_releases_once(tmp_path, fake, monkeypatch):
    entered, proceed = threading.Event(), threading.Event()

    def acquire(*args, **kwargs):
        entered.set()
        wait(proceed)
        assert kwargs["cancelled"]()
        return fake.pin

    monkeypatch.setattr(w, "acquire_bundle_pin", acquire)
    owner = job(tmp_path).start()
    try:
        wait(entered)
        assert owner.cancel() and owner.poll() == "cancelling"
    finally:
        proceed.set()
    assert finish(owner) == "cancelled"
    assert fake.pin.release_calls == 1 and not fake.materializations


def test_cancel_during_materialize_uses_callback_and_retains_staging(tmp_path, fake, monkeypatch):
    entered, proceed = threading.Event(), threading.Event()
    stage = str(tmp_path / "retained-stage")

    def materialize(*args, **kwargs):
        entered.set()
        wait(proceed)
        assert kwargs["cancelled"]()
        raise u.BundleCancelled("stopped", stage)

    monkeypatch.setattr(w, "materialize_bundle", materialize)
    owner = job(tmp_path).start()
    try:
        wait(entered)
        assert owner.cancel() and owner.poll() == "cancelling"
    finally:
        proceed.set()
    assert finish(owner) == "cancelled"
    assert owner.staging_path == stage and fake.pin.release_calls == 1
    with pytest.raises(w.BundlePreparationJobError) as error:
        owner.result()
    assert error.value.code == "cancelled" and error.value.staging_path == stage


@pytest.mark.parametrize("failure", [False, True])
def test_late_cancellation_revokes_unconsumed_ready_or_failed(tmp_path, fake, monkeypatch, failure):
    if failure:

        def broken(*args, **kwargs):
            raise u.BundlePreparationError("invalid package")

        monkeypatch.setattr(w, "materialize_bundle", broken)
    owner = job(tmp_path).start()
    assert finish(owner) == ("failed" if failure else "ready")
    assert owner.cancel() and owner.poll() == "cancelled"
    with pytest.raises(w.BundlePreparationJobError, match="cancelled"):
        owner.result()
    assert fake.pin.release_calls == 1


@pytest.mark.parametrize("winner", ["cancel", "result"])
def test_cancel_result_pair_is_linearized_by_one_state_lock(tmp_path, fake, winner):
    owner = job(tmp_path).start()
    assert finish(owner) == "ready"
    first_finished = threading.Event()
    outcomes = {}

    def take_result():
        try:
            outcomes["result"] = owner.result()
        except w.BundlePreparationJobError as exc:
            outcomes["result"] = exc.code

    def first():
        if winner == "cancel":
            outcomes["cancel"] = owner.cancel()
        else:
            take_result()
        first_finished.set()

    def second():
        wait(first_finished)
        if winner == "cancel":
            take_result()
        else:
            outcomes["cancel"] = owner.cancel()

    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = pool.submit(first), pool.submit(second)
        a.result(timeout=5)
        b.result(timeout=5)
    if winner == "cancel":
        assert outcomes == {"cancel": True, "result": "cancelled"}
    else:
        assert outcomes["result"] == descriptor(str(tmp_path / "cache"))
        assert outcomes["cancel"] is False
    assert owner.poll() == "consumed"


@pytest.mark.parametrize("error_type", [RuntimeError, OSError, KeyboardInterrupt, SystemExit])
def test_materialize_failure_always_releases_and_diagnostic_is_bounded(
    tmp_path, fake, monkeypatch, error_type
):
    def broken(*args, **kwargs):
        raise error_type("x" * 10000)

    monkeypatch.setattr(w, "materialize_bundle", broken)
    owner = job(tmp_path).start()
    assert finish(owner) == "failed" and owner.done
    assert fake.pin.release_calls == 1 and owner._pin is None
    assert len(owner.diagnostic) < w.MAX_DIAGNOSTIC_CHARS + 64
    with pytest.raises(w.BundlePreparationJobError, match="preparation_failed"):
        owner.result()


def test_failure_retains_staging_path_and_cancellation_does_not_erase_it(
    tmp_path, fake, monkeypatch
):
    stage = str(tmp_path / "retained")

    def broken(*args, **kwargs):
        raise u.BundlePreparationError("disk unavailable", stage)

    monkeypatch.setattr(w, "materialize_bundle", broken)
    owner = job(tmp_path).start()
    assert finish(owner) == "failed" and owner.staging_path == stage
    assert owner.cancel() and owner.staging_path == stage
    with pytest.raises(w.BundlePreparationJobError) as error:
        owner.result()
    assert error.value.staging_path == stage


@pytest.mark.parametrize(
    "error,code",
    [
        (p.BundlePinTimeout("timeout"), "pin_timeout"),
        (p.BundlePinCancelled("cancelled"), "cancelled"),
        (p.BundlePinError("unavailable"), "pin_acquisition_failed"),
    ],
)
def test_clean_acquisition_failure_has_no_owner_to_release(
    tmp_path, fake, monkeypatch, error, code
):
    def broken(*args, **kwargs):
        raise error

    monkeypatch.setattr(w, "acquire_bundle_pin", broken)
    owner = job(tmp_path).start()
    assert finish(owner) == ("cancelled" if code == "cancelled" else "failed")
    assert owner.done and fake.pin.release_calls == 0 and not fake.materializations
    with pytest.raises(w.BundlePreparationJobError) as caught:
        owner.result()
    assert caught.value.code == code


@pytest.mark.parametrize("cancel_first", [False, True])
def test_partial_acquisition_retains_poisoned_owner_without_release_retry(
    tmp_path, fake, monkeypatch, cancel_first
):
    entered, proceed = threading.Event(), threading.Event()

    def broken(*args, **kwargs):
        entered.set()
        wait(proceed)
        raise p.BundlePinError("pin_release_uncertain", pin=fake.pin)

    monkeypatch.setattr(w, "acquire_bundle_pin", broken)
    owner = job(tmp_path).start()
    try:
        wait(entered)
        if cancel_first:
            assert owner.cancel()
    finally:
        proceed.set()
    assert finish(owner) == "cleanup_blocked" and not owner.done
    assert owner._pin is fake.pin and fake.pin.release_calls == 0
    assert not fake.materializations and owner._descriptor is None
    owner.cancel()
    for _ in range(3):
        assert owner.poll() == "cleanup_blocked" and not owner.done
        with pytest.raises(w.BundlePreparationJobError, match="cleanup_blocked"):
            owner.result()
    with pytest.raises(w.BundlePreparationJobError, match="already_started"):
        owner.start()
    assert fake.pin.release_calls == 0 and owner._pin is fake.pin


@pytest.mark.parametrize("failure", [None, "materialize", "cancel", "base_exception"])
def test_release_uncertainty_blocks_success_failure_and_cancel_without_retry(
    tmp_path, fake, monkeypatch, failure
):
    stage = str(tmp_path / "retained")
    owner = job(tmp_path)

    def materialize(*args, **kwargs):
        if failure == "materialize":
            raise u.BundlePreparationError("bad inventory", stage)
        if failure == "cancel":
            owner.cancel()
        return descriptor(str(tmp_path / "cache"))

    def release():
        if failure == "base_exception":
            raise KeyboardInterrupt()
        raise p.BundlePinError("pin_release_uncertain", pin=fake.pin)

    monkeypatch.setattr(w, "materialize_bundle", materialize)
    fake.pin.release_hook = release
    owner.start()
    assert finish(owner) == "cleanup_blocked" and not owner.done
    assert owner._pin is fake.pin and owner._descriptor is None
    if failure == "materialize":
        assert owner.staging_path == stage
    owner.cancel()
    assert owner.poll() == "cleanup_blocked"
    for _ in range(3):
        with pytest.raises(w.BundlePreparationJobError, match="cleanup_blocked"):
            owner.result()
    assert fake.pin.release_calls == 1 and owner._pin is fake.pin


def test_wrong_materializer_return_cannot_become_ready(tmp_path, fake, monkeypatch):
    monkeypatch.setattr(w, "materialize_bundle", lambda *args, **kwargs: {"ready": True})
    owner = job(tmp_path).start()
    assert finish(owner) == "failed" and fake.pin.release_calls == 1
    with pytest.raises(w.BundlePreparationJobError, match="invalid_descriptor"):
        owner.result()


@pytest.mark.parametrize("after_launch", [False, True])
def test_worker_start_failure_cannot_escape_locked_launch_gate(
    tmp_path, fake, monkeypatch, after_launch
):
    actual = threading.Thread

    class BrokenThread(actual):
        def start(self):
            if after_launch:
                super().start()
            raise RuntimeError("cannot start worker")

    monkeypatch.setattr(w.threading, "Thread", BrokenThread)
    owner = job(tmp_path).start()
    if after_launch:
        assert finish(owner) == "failed"
    assert owner.done and not fake.acquisitions and not fake.materializations
    with pytest.raises(w.BundlePreparationJobError, match="worker_start_failed"):
        owner.result()


class SyntheticPackage:
    def __init__(self, tmp_path):
        self.package, self.cache = tmp_path / "package é", tmp_path / "cache 中文"
        self.package.mkdir()
        self.cache.mkdir()
        self.contents = {
            "python/bin/python3.12": b"not an executable runtime",
            "bootstrap.py": b"not an executable bootstrap",
            "src/mechanical_cad/__init__.py": b"synthetic source only",
        }
        output = io.BytesIO()
        files = []
        with zipfile.ZipFile(output, "w") as archive:
            for name, data in self.contents.items():
                mode = 0o755 if name.startswith("python/") else 0o644
                info = zipfile.ZipInfo(name)
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | mode) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, data)
                files.append(
                    dict(
                        path=name,
                        size=len(data),
                        sha256=hashlib.sha256(data).hexdigest(),
                        mode=mode,
                    )
                )
        payload = output.getvalue()
        manifest = encode(
            dict(
                schema_version=1,
                bundle_id=BUNDLE,
                platform="linux-x64",
                python_path="python/bin/python3.12",
                bootstrap_path="bootstrap.py",
                files=files,
            )
        )
        folder = self.package / "_backend" / BUNDLE
        folder.mkdir(parents=True)
        (folder / "bundle-manifest.json").write_bytes(manifest)
        (folder / "payload.zip").write_bytes(payload)
        release = json.loads(release_bytes())
        release.update(
            manifest_sha256=hashlib.sha256(manifest).hexdigest(),
            payload_sha256=hashlib.sha256(payload).hexdigest(),
            payload_size=len(payload),
        )
        self.release = encode(release)

    def job(self, **kwargs):
        return w.BundlePreparationJob(
            str(self.package),
            str(self.cache),
            self.release,
            expected_platform="linux-x64",
            limits=LIMITS,
            **kwargs,
        )


@POSIX
def test_real_linux_materialization_then_new_shared_pin_full_reverification(tmp_path, monkeypatch):
    f = SyntheticPackage(tmp_path)
    before = {
        str(p.relative_to(f.package)): p.read_bytes() for p in f.package.rglob("*") if p.is_file()
    }
    original_parse, original_materialize, original_acquire = (
        w.parse_release_manifest,
        w.materialize_bundle,
        w.acquire_bundle_pin,
    )
    phases = []

    def checked(function, name):
        def call(*args, **kwargs):
            assert threading.current_thread() is not threading.main_thread()
            phases.append(name)
            return function(*args, **kwargs)

        return call

    monkeypatch.setattr(w, "parse_release_manifest", checked(original_parse, "parse"))
    monkeypatch.setattr(w, "materialize_bundle", checked(original_materialize, "materialize"))
    monkeypatch.setattr(w, "acquire_bundle_pin", checked(original_acquire, "acquire"))
    owner = f.job().start()
    assert finish(owner) == "ready"
    result = owner.result()
    assert phases == ["parse", "acquire", "materialize"] and owner._pin is None
    assert result.root == str(f.cache / BUNDLE)
    assert sorted(p.name for p in f.cache.iterdir()) == [".bundle-pins", BUNDLE]
    lock = f.cache / ".bundle-pins" / (BUNDLE + ".lock")
    inode = lock.stat().st_ino

    def recheck():
        pin = p.acquire_bundle_pin(str(f.cache), BUNDLE, "shared", timeout=1)
        try:
            return u.verify_cached_bundle(
                f.package,
                f.cache,
                f.release,
                expected_platform="linux-x64",
                limits=LIMITS,
                pin=pin,
            )
        finally:
            pin.release()

    with ThreadPoolExecutor(max_workers=1) as pool:
        assert pool.submit(recheck).result(timeout=5) == result
        target = Path(result.bootstrap_path)
        target.write_bytes(b"x" * len(f.contents["bootstrap.py"]))
        with pytest.raises(m.BundleError, match="digest"):
            pool.submit(recheck).result(timeout=5)
    # A remembered descriptor still exists but cannot authorize changed contents.
    failed = f.job().start()
    assert finish(failed) == "failed" and failed.done
    with pytest.raises(w.BundlePreparationJobError, match="digest"):
        failed.result()
    assert target.read_bytes().startswith(b"x") and lock.stat().st_ino == inode
    assert before == {
        str(p.relative_to(f.package)): p.read_bytes() for p in f.package.rglob("*") if p.is_file()
    }


@POSIX
@pytest.mark.parametrize("cancel", [False, True])
def test_real_linux_contention_times_out_or_cancels_without_materializing(tmp_path, cancel):
    f = SyntheticPackage(tmp_path)
    entered, release = threading.Event(), threading.Event()

    def holder():
        pin = p.acquire_bundle_pin(str(f.cache), BUNDLE, "exclusive", timeout=1)
        try:
            entered.set()
            wait(release)
        finally:
            pin.release()

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(holder)
        wait(entered)
        owner = f.job(pin_timeout=0.1 if not cancel else 1).start()
        try:
            if cancel:
                owner.cancel()
            assert finish(owner) == ("cancelled" if cancel else "failed")
            with pytest.raises(w.BundlePreparationJobError) as error:
                owner.result()
            assert error.value.code == ("cancelled" if cancel else "pin_timeout")
            assert not (f.cache / BUNDLE).exists()
            assert sorted(item.name for item in f.cache.iterdir()) == [".bundle-pins"]
        finally:
            release.set()
        future.result(timeout=5)


def test_leaf_import_boundary_excludes_native_live_authority_and_cache_deletion():
    tree = ast.parse(Path(w.__file__).read_text())
    allowed = {
        "__future__",
        "math",
        "ntpath",
        "os",
        "threading",
        "dataclasses",
        "pathlib",
        "runtime_bundle_manifest",
        "runtime_bundle_materialize",
        "runtime_bundle_pin",
        "windows_cache",
    }
    allowed_path_joins = {
        "ntpath.join(self._cache_root, '.bundle-pins')",
        "ntpath.join(self._cache_root, '.bundle-pins', release.bundle_id + '.lock')",
    }
    observed_path_joins = set()
    forbidden = {"unlink", "rmdir", "rmtree", "Popen", "exec", "eval", "join", "resolve", "stat"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name in allowed for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module in allowed
        elif isinstance(node, ast.Call):
            name = getattr(node.func, "attr", getattr(node.func, "id", ""))
            if name == "join" and ast.unparse(node) in allowed_path_joins:
                observed_path_joins.add(ast.unparse(node))
                continue
            assert name not in forbidden
    assert observed_path_joins == allowed_path_joins


def test_concurrent_consumers_can_transfer_exactly_one_descriptor(tmp_path, fake):
    owner = job(tmp_path).start()
    assert finish(owner) == "ready"
    barrier = threading.Barrier(12)

    def consume():
        barrier.wait(timeout=5)
        try:
            return owner.result()
        except w.BundlePreparationJobError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(lambda _: consume(), range(12)))
    assert results.count("already_consumed") == 11
    assert sum(type(result) is m.BundleDescriptor for result in results) == 1
    assert owner.poll() == "consumed" and fake.pin.release_calls == 1


@pytest.mark.parametrize("field", ["root", "python_path", "bootstrap_path", "core_path"])
def test_derived_descriptor_paths_obey_existing_4096_ceiling(tmp_path, fake, monkeypatch, field):
    result = descriptor(str(tmp_path / "cache"))
    path = "/" + "x" * (w.MAX_ROOT_CHARS if field != "core_path" else w.MAX_ROOT_CHARS - 2)
    object.__setattr__(result, "root" if field == "core_path" else field, path)
    monkeypatch.setattr(w, "materialize_bundle", lambda *args, **kwargs: result)
    owner = job(tmp_path).start()
    assert finish(owner) == "failed" and owner.done and owner._pin is None
    assert fake.pin.release_calls == 1
    with pytest.raises(w.BundlePreparationJobError, match="prepared_path_too_long"):
        owner.result()


def test_oversized_staging_diagnostic_is_not_exposed(tmp_path, fake, monkeypatch):
    def broken(*args, **kwargs):
        raise u.BundlePreparationError("failed", "/" + "x" * w.MAX_ROOT_CHARS)

    monkeypatch.setattr(w, "materialize_bundle", broken)
    owner = job(tmp_path).start()
    assert finish(owner) == "failed" and owner.staging_path is None
    assert fake.pin.release_calls == 1
