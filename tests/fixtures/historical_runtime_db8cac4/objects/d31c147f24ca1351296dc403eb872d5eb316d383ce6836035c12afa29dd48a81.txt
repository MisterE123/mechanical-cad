"""Pure execution ownership: no bpy, native kernel, queue or reset hook."""

import copy
import importlib.util
import threading
from pathlib import Path

import pytest

PATH = (
    Path(__file__).resolve().parents[2] / "blender_addon/mechanical_cad_blender/execution_lease.py"
)


@pytest.fixture
def lease():
    spec = importlib.util.spec_from_file_location("isolated_execution_lease", PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    yield module
    assert not module.is_busy(), "test left native execution ownership outstanding"


def test_opaque_immutable_token_and_read_only_status(lease):
    assert lease.is_busy() is False
    token = lease.try_acquire()
    try:
        assert type(token) is object
        assert not hasattr(token, "__dict__")
        with pytest.raises(AttributeError):
            token.scene = object()
        assert lease.is_busy() is True
        assert lease.is_busy() is True
        assert lease.try_acquire() is None
        assert not lease.release(None)
        assert not lease.release(object())
        assert not lease.release(copy.deepcopy(token))
        assert lease.is_busy()
    finally:
        assert lease.release(token)
    assert not lease.release(token)


def test_release_never_uses_equality_or_boolean_coercion(lease):
    class Hostile:
        def __eq__(self, other):
            raise AssertionError("Do not invoke caller equality")

        def __bool__(self):
            raise AssertionError("Do not invoke caller boolean coercion")

    token = lease.try_acquire()
    try:
        assert not lease.release(Hostile())
        assert lease.is_busy()
    finally:
        assert lease.release(token)


def test_stale_finalizer_cannot_release_newer_work(lease):
    old = lease.try_acquire()
    assert lease.release(old)
    current = lease.try_acquire()
    try:
        assert current is not old
        assert not lease.release(old)
        assert lease.try_acquire() is None
    finally:
        assert lease.release(current)


def test_simultaneous_acquisition_has_exactly_one_owner_and_no_queue(lease):
    start = threading.Barrier(17)
    attempts = []
    lock = threading.Lock()

    def attempt():
        start.wait(timeout=5)
        token = lease.try_acquire()
        with lock:
            attempts.append(token)

    threads = [threading.Thread(target=attempt) for _ in range(16)]
    for thread in threads:
        thread.start()
    start.wait(timeout=5)
    for thread in threads:
        thread.join(timeout=5)
        assert not thread.is_alive()
    owners = [token for token in attempts if token is not None]
    assert len(attempts) == 16
    assert len(owners) == 1
    assert lease.release(owners[0])
    assert not lease.is_busy()
    # Rejected callers are never launched or granted ownership after release.
    assert attempts.count(None) == 15
    explicit_retry = lease.try_acquire()
    assert explicit_retry is not None
    assert lease.release(explicit_retry)
