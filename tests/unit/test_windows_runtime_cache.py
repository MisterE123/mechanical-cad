"""Dormant cache/operation binding with concrete owners and inert OS leaves only."""

import ntpath
from dataclasses import replace

import pytest
from test_windows_runtime import (
    Fixture,
    cache,
    cache_tests,
    install,
    jobs,
    launch,
    prepared,
    run_job,
    selection,
    w,
)

REAL_VERIFY_CACHED_TREE = w._verify_cached_tree


class Poison:
    def __eq__(self, other):
        pytest.fail("unvalidated equality callback")

    def __bool__(self):
        pytest.fail("unvalidated truth callback")

    def __str__(self):
        pytest.fail("unvalidated string callback")

    def __fspath__(self):
        pytest.fail("unvalidated path callback")

    def __deepcopy__(self, memo):
        pytest.fail("unvalidated deepcopy callback")

    __hash__ = object.__hash__


def capture(fixture, **changes):
    values = dict(
        descriptor=fixture.descriptor,
        package_root=fixture.package,
        cache_root=fixture.cache,
        release_data=fixture.release,
        constants=fixture.constants,
        windows_cache=fixture.location,
    )
    values.update(changes)
    return launch.capture_bundled_policy(**values)


@pytest.mark.parametrize("value", [None, Poison(), lambda: None, "C:\\Other"])
def test_windows_policy_requires_exact_detached_automatic_recipe(value):
    fixture = Fixture()
    with pytest.raises(launch.BundleLaunchError):
        capture(fixture, windows_cache=value)


def test_windows_recipe_is_detached_at_policy_selection_and_operation_capture():
    fixture = Fixture()
    policy = fixture.policy()
    selected = selection.BackendSelection._capture_windows_bundled_transport(
        policy, generation=0, lifetime_id="test"
    )
    owner = w.WindowsOperationOwner(policy, b"{}")
    assert (
        policy.windows_cache == selected.bundled_policy.windows_cache == owner.policy.windows_cache
    )
    assert policy.windows_cache is not fixture.location
    assert selected.bundled_policy.windows_cache is not policy.windows_cache
    assert owner.policy.windows_cache is not policy.windows_cache
    original = selected.bundled_policy.descriptor_bytes()
    object.__setattr__(fixture.location, "known_folder", Poison())
    object.__setattr__(policy.windows_cache, "known_folder", Poison())
    assert selected.bundled_policy.descriptor_bytes() == original
    assert owner.policy.windows_cache.known_folder == fixture.known_folder


@pytest.mark.parametrize(
    "target", ["platform", "descriptor", "scalar", "version", "flags", "recipe"]
)
@pytest.mark.parametrize("entry", ["capture", "selection", "operation", "acquire", "before_write"])
def test_poisoned_exact_fields_reject_before_callbacks_or_model_write(monkeypatch, target, entry):
    env = install(monkeypatch)
    fixture, policy = env.fixture, env.fixture.policy()

    def poison(p):
        if target == "platform":
            object.__setattr__(p.constants, "PLATFORM", Poison())
        elif target == "descriptor":
            object.__setattr__(p.descriptor, "bundle_id", Poison())
        elif target == "scalar":
            object.__setattr__(p.constants, "PYTHON_BITS", Poison())
        elif target == "version":
            object.__setattr__(p.constants, "PYTHON_VERSION", (3, 12, Poison(), "final", 0))
        elif target == "flags":
            object.__setattr__(
                p.constants, "PYTHON_FLAGS", ("-I", "-S", "-B", "-X", "utf8", Poison())
            )
        else:
            object.__setattr__(p.windows_cache, "cache_root", Poison())

    if entry == "capture":
        poison(policy)
        constants = {
            name: getattr(policy.constants, name) for name in launch.LAUNCH_CONSTANT_FIELDS
        }
        with pytest.raises(launch.BundleLaunchError):
            capture(
                fixture,
                descriptor=policy.descriptor,
                constants=constants,
                windows_cache=policy.windows_cache,
            )
    elif entry in {"selection", "operation"}:
        poison(policy)
        with pytest.raises(launch.BundleLaunchError):
            if entry == "selection":
                selection.BackendSelection._capture_windows_bundled_transport(
                    policy, generation=0, lifetime_id="test"
                )
            else:
                w.WindowsOperationOwner(policy, b"{}")
    elif entry == "acquire":
        owner = w.WindowsOperationOwner(policy, b"{}")
        poison(owner.policy)
        with pytest.raises(launch.BundleLaunchError):
            owner.acquire(timeout=10, cancelled=lambda: False)
        assert owner.cache_owner is None
    else:
        job = jobs.SidecarJob.from_selection(prepared(), fixture.selected())
        env.process.hook = lambda event: (
            poison(job._bundle_owner.policy) if event == "open_file0" else None
        )
        job.start()
        assert job.wait(5) and job.state == "failed"
        assert env.process.contents["file0"] == b""
        assert "initialize_file0" not in env.events and "create" not in env.events
        return
    assert not env.events


def test_windows_dict_shape_rejects_nonprimitive_keys_without_callbacks():
    fixture = Fixture()
    values = fixture.constants | {Poison(): "forbidden"}
    with pytest.raises(launch.BundleLaunchError):
        capture(fixture, constants=values)


def test_windows_dict_subclass_is_rejected_without_iteration():
    class CallbackDict(dict):
        def __iter__(self):
            pytest.fail("unvalidated mapping iteration")

    with pytest.raises(launch.BundleLaunchError):
        capture(Fixture(), constants=CallbackDict())


@pytest.mark.parametrize(
    "name,value",
    [
        ("PYTHON_VERSION", Poison()),
        ("PYTHON_FLAGS", Poison()),
        ("PYTHON_VERSION", (3, 12)),
        ("PYTHON_FLAGS", ("-I",)),
        ("SCHEMA_VERSION", True),
        ("RELEASE_IDENTITY_BYTES", Poison()),
    ],
)
def test_windows_constant_containers_reject_before_constructor_comparisons(name, value):
    fixture = Fixture()
    with pytest.raises(launch.BundleLaunchError):
        capture(fixture, constants=fixture.constants | {name: value})


def test_original_cache_owner_precedes_one_shared_pin_and_full_verify(monkeypatch):
    env = install(monkeypatch)

    def execute():
        owner = w.WindowsOperationOwner(env.fixture.policy(), b"{}")
        try:
            owner.acquire(timeout=10, cancelled=lambda: False)
            assert owner.cache_owner is env.cache.owner
            assert owner.validation.windows_storage is owner.cache_owner
            assert owner.spec.bundle == owner.policy.descriptor
            assert owner.spec.bundle is not owner.policy.descriptor
            assert owner.spec.descriptor_payload == owner.policy.descriptor_bytes()
        finally:
            owner.cleanup()

    cache_tests.worker(execute)
    assert env.events.index("cache_open") < env.events.index("acquire_pin")
    assert env.events.index("acquire_pin") < env.events.index("verify_tree")
    assert env.events[-1] == "pin_release"


def test_original_owner_is_forwarded_to_the_one_existing_full_verifier(monkeypatch):
    env = install(monkeypatch)
    policy = env.fixture.policy()
    release = w.parse_release_manifest(
        policy.release_data, expected_platform="windows-x64", limits=w.BundleLimits()
    )
    owner = cache.WindowsCacheOwner(
        policy.windows_cache,
        package_root=policy.package_root,
        expected_platform="windows-x64",
        release=release,
    )
    calls = []

    def cancelled():
        return False

    def verify(*args, **kwargs):
        calls.append((args, kwargs))
        return policy.descriptor

    monkeypatch.setattr(w.materialize, "verify_cached_bundle", verify)
    assert (
        REAL_VERIFY_CACHED_TREE(policy, env.pin, cancelled, windows_storage=owner)
        == policy.descriptor
    )
    assert len(calls) == 1
    assert calls[0][0] == (policy.package_root, policy.cache_root, policy.release_data)
    assert calls[0][1]["windows_storage"] is owner
    assert calls[0][1]["pin"] is env.pin and calls[0][1]["cancelled"] is cancelled
    assert not env.events


def test_recipe_is_part_of_selection_currentness_without_descriptor_fields():
    fixture = Fixture()
    first, second = fixture.selected(), fixture.selected()
    assert first == second
    original = first.bundled_policy.descriptor_bytes()
    object.__setattr__(second.bundled_policy.windows_cache, "known_folder", "C:\\Other")
    assert first != second
    with pytest.raises(selection.SelectionError):
        first.assert_current(second)
    assert first.bundled_policy.descriptor_bytes() == original
    assert first.bundled_policy.__dataclass_fields__["windows_cache"].compare


@pytest.mark.parametrize("index", range(4))
def test_every_original_stream_acl_precedes_its_first_write(monkeypatch, index):
    env = install(monkeypatch)
    original = env.cache.security_descriptor

    def denied(handle, output):
        if handle == 1000000 + index:
            raise OSError("inert denied READ_CONTROL or private ACL")
        return original(handle, output)

    env.cache.security_descriptor = denied
    job = run_job(env)
    assert job.state == "failed" and env.pin.releases == 1
    assert env.process.contents[f"file{index}"] == b""
    assert f"initialize_file{index}" not in env.events and "create" not in env.events
    assert env.process.files == [f"file{i}" for i in range(index + 1)]
    assert all(file in env.process.closed for file in env.process.files)
    assert not any(handle >= 1000000 for handle in env.cache.close_calls)


@pytest.mark.parametrize(
    "change", ["path", "links", "reparse", "offline", "inherit", "size", "handle", "identity"]
)
def test_initial_stream_identity_rejects_without_raw_request_write(monkeypatch, change):
    env = install(monkeypatch)
    if change == "handle":
        env.runtime.stream_handle = lambda file: 0
    else:
        values = {
            "path": {"final_path": "C:\\Other\\tmp"},
            "links": {"links": 2},
            "reparse": {"reparse": True},
            "offline": {"offline": True},
            "inherit": {"inheritable": True},
            "size": {"size": 1},
            "identity": {"identity": (1, True, 1)},
        }
        env.runtime.stream_change = lambda info: replace(info, **values[change])
    job = run_job(env)
    assert job.state == "failed" and "create" not in env.events
    assert env.process.contents["file0"] == b""
    assert "initialize_file0" not in env.events


@pytest.mark.parametrize("index", range(4))
def test_changed_original_stream_handle_rejects_before_process_create(monkeypatch, index):
    env = install(monkeypatch)
    original = env.runtime.stream_handle

    def observe(file):
        handle = original(file)
        complete = len(env.process.files) == 4 and bool(env.process.contents["file3"])
        return handle + 10 if complete and file == f"file{index}" else handle

    env.runtime.stream_handle = observe
    job = run_job(env)
    assert job.state == "failed" and "create" not in env.events and env.pin.releases == 1


@pytest.mark.parametrize("where", ["parent", "job"])
def test_job_directory_original_private_handle_is_checked_before_files(monkeypatch, where):
    env = install(monkeypatch)
    original = env.cache.security_descriptor

    def denied(handle, output):
        if handle in env.runtime.handles:
            path = env.runtime.handles[handle][0]
            if (where == "parent" and path.endswith("\\.jobs")) or (
                where == "job" and ntpath.basename(ntpath.dirname(path)) == ".jobs"
            ):
                raise OSError("inert insecure inherited directory")
        return original(handle, output)

    env.cache.security_descriptor = denied
    job = run_job(env)
    assert job.state == "failed" and not env.process.files and env.pin.releases == 1


@pytest.mark.parametrize("where", ["cache", "pin", "directory", "stream"])
@pytest.mark.parametrize("outcome", ["timeout", "cancelled"])
def test_original_deadline_and_cancel_latch_survive_cache_wrapping(monkeypatch, where, outcome):
    env = install(monkeypatch)
    job = jobs.SidecarJob.from_selection(prepared(), env.fixture.selected())
    fired = []

    def disrupt(event):
        match = (
            (where == "cache" and event[0] == "token_user")
            or (where == "pin" and event[0] == "open" and ".bundle-pins" in event[1])
            or (where == "directory" and event[0] == "borrowed_info" and event[1] < 1000000)
            or (where == "stream" and event[0] == "borrowed_info" and event[1] >= 1000000)
        )
        if match and not fired:
            fired.append(event)
            if outcome == "timeout":
                env.clock.now += 11
            else:
                job.cancel()

    env.cache.hook = disrupt
    job.start()
    assert job.wait(5) and job.state in {"failed", "cancelled"}
    assert fired and job._bundle_owner.failure_code == outcome
    assert "create" not in env.events and job._response is None
    if where == "cache":
        assert "acquire_pin" not in env.events
    if where == "stream":
        assert env.process.contents["file0"] == b"" and "initialize_file0" not in env.events


@pytest.mark.parametrize("outcome", ["late", "error"])
def test_cache_cleanup_uncertainty_blocks_pin_output_and_retry(monkeypatch, outcome):
    env = install(monkeypatch)
    original = env.cache.close_handle

    def close(handle):
        if "rmdir" in env.events:
            if outcome == "error":
                raise OSError("inert close uncertainty")
            original(handle)
            env.clock.now += 6
        else:
            original(handle)

    env.cache.close_handle = close
    job = run_job(env)
    owner = job._bundle_owner
    assert job.state == "cleanup_uncertain" and job._response is None and env.pin.releases == 0
    assert (
        owner.cache_owner is env.cache.owner
        and owner.validation.windows_storage is owner.cache_owner
    )
    before = tuple(env.cache.close_calls)
    with pytest.raises(launch.BundleCleanupUncertain):
        owner.cleanup()
    assert tuple(env.cache.close_calls) == before
    assert owner.cache_owner.cleanup_uncertain


def test_changed_cache_owner_binding_rejects_before_first_model_write(monkeypatch):
    env = install(monkeypatch)
    env.process.hook = lambda event: (
        setattr(env.cache.owner, "_package_root", Poison()) if event == "open_file0" else None
    )
    job = run_job(env)
    assert job.state == "failed" and env.process.contents["file0"] == b""
    assert "create" not in env.events and "initialize_file0" not in env.events


@pytest.mark.parametrize("change", ["duplicate", "fifth"])
def test_bounded_original_stream_observations_reject_duplicates_and_fifth_entry(
    monkeypatch, change
):
    env = install(monkeypatch)
    if change == "duplicate":
        env.runtime.stream_handle = lambda file: 1000000
    else:

        def extra(event):
            if event == "initialize_file3":
                validation = env.process._validation
                validation.streams.append(object())
                validation.before_write(validation.streams[-1])

        env.process.hook = extra
    job = run_job(env)
    assert job.state == "failed" and "create" not in env.events and env.pin.releases == 1
    assert len(job._bundle_owner.validation._stream_observations) <= 4
    if change == "duplicate":
        assert env.process.contents["file1"] == b"" and "initialize_file1" not in env.events


def test_cache_owner_acquisition_cannot_substitute_an_incoming_owner(monkeypatch):
    env = install(monkeypatch)
    original = cache.WindowsCacheOwner.acquire_existing

    def substitute(self, **kwargs):
        original(self, **kwargs)
        return object()

    monkeypatch.setattr(cache.WindowsCacheOwner, "acquire_existing", substitute)
    job = run_job(env)
    assert job.state == "failed" and "acquire_pin" not in env.events
    assert not env.cache.handles and not env.process.files


@pytest.mark.parametrize("barrier", ["before_write", "before_create"])
@pytest.mark.parametrize("invalid_metadata", [False, True])
def test_metadata_and_private_acl_use_original_borrowed_handle(
    monkeypatch, barrier, invalid_metadata
):
    env = install(monkeypatch)
    original_info = env.runtime.info
    counts, queried, proved = {}, [], []

    def active():
        initialized = bool(env.process.contents.get("file3"))
        return not initialized if barrier == "before_write" else initialized

    def borrow(file):
        index = env.process.files.index(file)
        if active():
            counts[file] = counts.get(file, 0) + 1
            return (1000000 if counts[file] % 2 else 2000000) + index
        return 1000000 + index

    def info(handle):
        if handle < 1000000:
            return original_info(handle)
        index = handle % 1000000
        value = replace(
            original_info(1000000 + index),
            identity=(1, handle // 1000000, index + 1),
            reparse=invalid_metadata and active() and handle < 2000000,
        )
        queried.append((handle, value.identity))
        return value

    original_proof = cache.WindowsCacheOwner.check_private_handle

    def prove(self, handle, path, *, directory):
        if handle >= 1000000:
            proved.append(handle)
        return original_proof(self, handle, path, directory=directory)

    env.runtime.stream_handle = borrow
    env.runtime.info = info
    monkeypatch.setattr(cache.WindowsCacheOwner, "check_private_handle", prove)
    job = run_job(env)
    observations = job._bundle_owner.validation._stream_observations
    assert queried and all(handle < 2000000 for handle, _ in queried)
    assert all(handle < 2000000 for handle in proved)
    for _, handle, identity, _ in observations:
        assert identity == (1, handle // 1000000, handle % 1000000 + 1)
    if invalid_metadata:
        assert job.state == "failed" and "create" not in env.events
        if barrier == "before_write":
            assert env.process.contents["file0"] == b""
            assert "initialize_file0" not in env.events and not observations
    else:
        assert job.state == "ready" and len(observations) == 4
        assert set(proved) == {1000000, 1000001, 1000002, 1000003}
        assert all(count == 1 for count in counts.values())


@pytest.mark.parametrize("barrier", ["before_write", "before_create"])
@pytest.mark.parametrize("invalid_handle", [None, True, 0, -1, 1.0, Poison()])
def test_invalid_borrowed_handle_rejects_without_query(monkeypatch, barrier, invalid_handle):
    env = install(monkeypatch)
    original_borrow, original_info = env.runtime.stream_handle, env.runtime.info
    rejected = []

    def borrow(file):
        initialized = bool(env.process.contents.get("file3"))
        active = not initialized if barrier == "before_write" else initialized
        if active:
            rejected.append(file)
            return invalid_handle
        return original_borrow(file)

    def info(handle):
        if type(handle) is not int or handle <= 0:
            pytest.fail("invalid borrowed handle entered metadata query")
        return original_info(handle)

    env.runtime.stream_handle = borrow
    env.runtime.info = info
    job = run_job(env)
    assert rejected and job.state == "failed" and "create" not in env.events
    if barrier == "before_write":
        assert env.process.contents["file0"] == b"" and "initialize_file0" not in env.events
