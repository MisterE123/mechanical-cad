"""Pure recovery persistence never changes canonical/draft bytes or old copies."""
import importlib
import json
import os
import select
import subprocess
import sys
import types
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "mcad_recovery_store_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT / "blender_addon/mechanical_cad_blender")]
sys.modules[PACKAGE] = package
r = importlib.import_module(PACKAGE + ".recovery_store")
BASE = '{"schema_version":1,"id":"doc","name":"Part","units":"mm","parameters":{},"features":[],"active_feature":null}\n'
SCOPE = "a" * 32
CREATED = "2026-10-25T00:00:00+00:00"


def encoded(sequence=1, scope=SCOPE, document=BASE, draft=""):
    return r.encode(scope, sequence, document, draft, CREATED)


def disk_bytes(root):
    return {path.name: path.read_bytes() for path in root.iterdir()}


def test_exact_strings_and_frozen_record():
    draft = r.draft_dispatch.RectangleDraft(BASE)
    draft.first_point((1, 2))
    draft.second_point((20, 30))
    draft.pending_dimensions = {"width": " 60mm +( 半径 ", "height": "30", "fix_corner": False}
    text = r.draft_dispatch.dumps(draft)
    value = r.decode(encoded(draft=text))
    assert (value.document_json, value.draft_json, value.created) == (BASE, text, CREATED)
    with pytest.raises(AttributeError):
        value.sequence = 99
    with pytest.raises(r.RecoveryError, match="different canonical"):
        encoded(document=BASE.rstrip(), draft=text)


@pytest.mark.parametrize("change", [
    {"surprise": 1}, {"schema_version": True}, {"schema_version": 2},
    {"sequence": True}, {"sequence": 0}, {"sequence": 2**63},
    {"scope": "../escape"}, {"created": "2026-01-01T00:00:00"},
    {"created": "2026-01-01T00:00:00+01:00"}, {"document_sha256": "0" * 64},
    {"draft_sha256": "0" * 64}, {"document_json": BASE + " "},
])
def test_strict_envelope(change):
    data = json.loads(encoded())
    data.update(change)
    with pytest.raises(r.RecoveryError):
        r.decode(json.dumps(data).encode())


@pytest.mark.parametrize("raw", [b"{", b"[]", b"\xff", b"NaN", b'{"x":1,"x":2}', b"[" * 2000])
def test_bad_json(raw):
    with pytest.raises(r.RecoveryError):
        r.decode(raw)


def test_duplicate_known_field():
    raw = encoded().replace(b'"sequence":1', b'"sequence":1,"sequence":1')
    with pytest.raises(r.RecoveryError):
        r.decode(raw)


@pytest.mark.parametrize("document", [
    BASE.replace('"units":"mm"', '"units":"in"'),
    BASE.replace('"schema_version":1', '"schema_version":99'),
    BASE.replace('"features":[]', '"features":[{"kind":"unknown"}]'),
    BASE.replace('"parameters":{}', '"parameters":{"x":NaN}'),
    BASE.replace('"parameters":{}', '"parameters":{"x":1e999}'),
    BASE.replace('"parameters":{}', '"parameters":{},"unknown":1'),
])
def test_invalid_native_free_document(document):
    with pytest.raises(r.RecoveryError):
        encoded(document=document)


def test_bounds_and_unicode(monkeypatch):
    monkeypatch.setattr(r, "MAX_DOCUMENT_BYTES", len(BASE.encode()))
    assert r.decode(encoded()).document_json == BASE
    with pytest.raises(r.RecoveryError):
        encoded(document=BASE + " ")
    with pytest.raises(r.RecoveryError):
        encoded(document=BASE.replace("Part", "🛠🛠🛠🛠"))
    with pytest.raises(r.RecoveryError):
        encoded(document=BASE + "\ud800")
    monkeypatch.setattr(r, "MAX_DRAFT_BYTES", 4)
    with pytest.raises(r.RecoveryError):
        encoded(draft=" " * 5)
    monkeypatch.setattr(r, "MAX_ENVELOPE_BYTES", 5)
    with pytest.raises(r.RecoveryError):
        r.decode(b" " * 6)
    with pytest.raises(r.RecoveryError):
        encoded()


def test_listing_is_read_only_and_missing_root(tmp_path):
    root = tmp_path / "not-created"
    store = r.Store(root)
    assert store.entries() == ()
    assert not root.exists()
    with pytest.raises(r.RecoveryError):
        store.read(SCOPE, 0)
    assert not root.exists()


def test_two_generations_monotonic_and_exact_bytes(tmp_path):
    store = r.Store(tmp_path)
    for sequence in (1, 3, 7):
        value = encoded(sequence)
        assert store.write(value) == r.decode(value)
    assert {entry.sequence for entry in store.entries()} == {3, 7}
    assert len(list(tmp_path.glob("*.recovery.json"))) == 2
    assert (tmp_path / ".writer.lock").stat().st_size == 0
    before = disk_bytes(tmp_path)
    for sequence in (1, 6, 7):
        with pytest.raises(r.RecoveryError, match="Stale"):
            store.write(encoded(sequence))
        assert disk_bytes(tmp_path) == before
    assert store.write(r.decode(encoded(8))).sequence == 8
    for entry in store.entries():
        assert store.read(entry.scope, entry.slot).sequence == entry.sequence
    if os.name == "posix":
        assert all(path.stat().st_mode & 0o777 == 0o600 for path in tmp_path.iterdir())


def test_corruption_visible_and_never_overwritten(tmp_path):
    store = r.Store(tmp_path)
    store.write(encoded())
    path = tmp_path / f"{SCOPE}.0.recovery.json"
    path.write_bytes(b"corrupt original")
    before = disk_bytes(tmp_path)
    entries = store.entries()
    assert len(entries) == 1 and entries[0].error and entries[0].sequence is None
    with pytest.raises(r.RecoveryError):
        store.read(SCOPE, 0)
    with pytest.raises(r.RecoveryError):
        store.write(encoded(2))
    assert disk_bytes(tmp_path) == before


@pytest.mark.parametrize("operation", ["read", "write", "entries"])
def test_entry_symlink_refused_and_target_untouched(tmp_path, operation):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.write_bytes(encoded())
    (root / f"{SCOPE}.0.recovery.json").symlink_to(outside)
    store = r.Store(root)
    with pytest.raises(r.RecoveryError):
        if operation == "read":
            store.read(SCOPE, 0)
        elif operation == "write":
            store.write(encoded(2))
        else:
            store.entries()
    assert outside.read_bytes() == encoded()


def test_root_and_ancestor_symlink_refused(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    for root in (link, link / "nested"):
        store = r.Store(root)
        with pytest.raises(r.RecoveryError):
            store.write(encoded())
        with pytest.raises(r.RecoveryError):
            store.entries()
    assert list(real.iterdir()) == []


def test_path_traversal_and_nonregular_entries(tmp_path):
    store = r.Store(tmp_path)
    for scope, slot in (("../x", 0), (SCOPE, "../x"), (SCOPE, True), (SCOPE, 2)):
        with pytest.raises(r.RecoveryError):
            store.read(scope, slot)
    (tmp_path / "unknown-directory").mkdir()
    with pytest.raises(r.RecoveryError):
        store.write(encoded())
    assert (tmp_path / "unknown-directory").is_dir()


@pytest.mark.parametrize("failure", ["replace", "fsync"])
def test_disk_failure_preserves_both_generations(tmp_path, monkeypatch, failure):
    store = r.Store(tmp_path)
    store.write(encoded(1))
    store.write(encoded(2))
    before = disk_bytes(tmp_path)

    def fail(*args, **kwargs):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(r.os, failure, fail)
    with pytest.raises(r.RecoveryError, match="disk failure"):
        store.write(encoded(3))
    assert disk_bytes(tmp_path) == before


def test_quota_counts_unknown_and_temp_without_eviction(tmp_path, monkeypatch):
    store = r.Store(tmp_path)
    store.write(encoded())
    (tmp_path / "unknown").write_bytes(b"keep me")
    (tmp_path / ".abandoned.tmp").write_bytes(b"keep too")
    before = disk_bytes(tmp_path)
    total = sum(map(len, before.values()))
    monkeypatch.setattr(r, "MAX_STORE_BYTES", total + len(encoded(2)) - 1)
    with pytest.raises(r.RecoveryError, match="quota"):
        store.write(encoded(2))
    assert disk_bytes(tmp_path) == before
    monkeypatch.setattr(r, "MAX_STORE_BYTES", total + len(encoded(2)))
    store.write(encoded(2))
    assert (tmp_path / "unknown").read_bytes() == b"keep me"
    assert (tmp_path / ".abandoned.tmp").read_bytes() == b"keep too"


def test_scope_quota_no_eviction(tmp_path, monkeypatch):
    store = r.Store(tmp_path)
    store.write(encoded())
    before = disk_bytes(tmp_path)
    monkeypatch.setattr(r, "MAX_SCOPES", 1)
    with pytest.raises(r.RecoveryError, match="scope quota"):
        store.write(encoded(scope=uuid.uuid4().hex))
    assert disk_bytes(tmp_path) == before
    store.write(encoded(2))


def test_filename_binding(tmp_path):
    (tmp_path / f'{"b" * 32}.0.recovery.json').write_bytes(encoded())
    entries = r.Store(tmp_path).entries()
    assert entries[0].error and "scope" in entries[0].error


def test_metadata_is_checksummed():
    for key, value in (("sequence", 2), ("scope", "b" * 32),
                       ("created", "2026-10-26T00:00:00+00:00")):
        data = json.loads(encoded())
        data[key] = value
        with pytest.raises(r.RecoveryError, match="checksum"):
            r.decode(json.dumps(data).encode())


def test_temp_collision_never_removes_unknown_file(tmp_path, monkeypatch):
    collision = uuid.UUID("b" * 32)
    path = tmp_path / f".{SCOPE}.{collision.hex}.tmp"
    path.write_bytes(b"unrelated original")
    monkeypatch.setattr(r.uuid, "uuid4", lambda: collision)
    with pytest.raises(r.RecoveryError):
        r.Store(tmp_path).write(encoded())
    assert path.read_bytes() == b"unrelated original"


def test_independent_scopes_retain_their_generations(tmp_path):
    store = r.Store(tmp_path)
    other = "b" * 32
    for sequence in (1, 2, 3):
        store.write(encoded(sequence))
        store.write(encoded(sequence, scope=other))
    assert {(entry.scope, entry.sequence) for entry in store.entries()} == {
        (SCOPE, 2), (SCOPE, 3), (other, 2), (other, 3)}


def test_escaped_lone_surrogate_rejected():
    with pytest.raises(r.RecoveryError):
        encoded(document=BASE.replace("Part", r"\ud800"))


@pytest.mark.skipif(os.name != "posix", reason="POSIX ownership/mode contract")
def test_shared_writable_root_rejected(tmp_path):
    tmp_path.chmod(0o777)
    try:
        with pytest.raises(r.RecoveryError, match="owned by this user"):
            r.Store(tmp_path).write(encoded())
        assert list(tmp_path.iterdir()) == []
    finally:
        tmp_path.chmod(0o700)


def test_embedded_schema3_sector_uses_existing_dispatch():
    from test_result_v3_client import sector_document

    document = json.dumps(sector_document(), indent=3) + "\n"
    assert r.decode(encoded(document=document)).document_json == document


def test_entry_display_name_is_not_a_path(tmp_path):
    document = BASE.replace("Part", "../presentation only")
    store = r.Store(tmp_path)
    store.write(encoded(document=document))
    assert store.entries()[0].document_name == "../presentation only"
    assert {path.name for path in tmp_path.iterdir()} == {f"{SCOPE}.0.recovery.json", ".writer.lock"}


@pytest.mark.parametrize("variant", ["active", "dangling", "self_cycle", "cycle"])
def test_graph_structure_rejected(variant):
    document = json.loads(BASE)
    if variant == "active":
        document["active_feature"] = "missing"
    elif variant == "dangling":
        document["features"] = [{"id": "a", "kind": "transform", "inputs": {"base": "missing"}}]
    elif variant == "self_cycle":
        document["features"] = [{"id": "a", "kind": "transform", "inputs": {"base": "a"}}]
    else:
        document["features"] = [
            {"id": "a", "kind": "transform", "inputs": {"base": "b"}},
            {"id": "b", "kind": "transform", "inputs": {"base": "a"}},
        ]
    with pytest.raises(r.RecoveryError, match="active|dangling|cycle"):
        encoded(document=json.dumps(document))


def test_abandoned_generated_temp_reserves_scope_without_deletion(tmp_path, monkeypatch):
    other = "b" * 32
    path = tmp_path / f".{other}.{'c' * 32}.tmp"
    path.write_bytes(b"abandoned retained bytes")
    monkeypatch.setattr(r, "MAX_SCOPES", 1)
    with pytest.raises(r.RecoveryError, match="scope quota"):
        r.Store(tmp_path).write(encoded())
    assert path.read_bytes() == b"abandoned retained bytes"
    assert {item.name for item in tmp_path.iterdir()} == {path.name, ".writer.lock"}


@pytest.mark.skipif(os.name != "posix", reason="Linux/POSIX advisory lock qualification")
def test_independent_process_contention_is_nonblocking_and_preserves_quota(tmp_path, monkeypatch):
    store = r.Store(tmp_path)
    store.write(encoded(1))
    limit = len(encoded()) * 2
    monkeypatch.setattr(r, "MAX_STORE_BYTES", limit)
    script = f'''
import importlib, sys, types
package = types.ModuleType("recovery_child")
package.__path__ = [{str(ROOT / "blender_addon/mechanical_cad_blender")!r}]
sys.modules[package.__name__] = package
r = importlib.import_module(package.__name__ + ".recovery_store")
r.MAX_STORE_BYTES = {limit}
original = r.os.fsync
paused = False
def pause_once(fd):
    global paused
    if not paused:
        paused = True
        print("LOCKED_WITH_TEMP", flush=True)
        assert sys.stdin.readline().strip() == "continue"
    original(fd)
r.os.fsync = pause_once
r.Store({str(tmp_path)!r}).write({encoded(2)!r})
print("WRITTEN", flush=True)
'''
    process = subprocess.Popen([sys.executable, "-c", script], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert select.select([process.stdout], [], [], 10)[0], "writer failed to reach barrier"
        assert process.stdout.readline().strip() == "LOCKED_WITH_TEMP"
        before = disk_bytes(tmp_path)
        assert sum(map(len, before.values())) <= limit
        with pytest.raises(r.RecoveryError, match="busy.*retry later"):
            store.write(encoded(3))
        assert disk_bytes(tmp_path) == before
        stdout, stderr = process.communicate("continue\n", timeout=10)
        assert process.returncode == 0, stderr
        assert stdout.strip() == "WRITTEN"
        assert {entry.sequence for entry in store.entries()} == {1, 2}
        before = disk_bytes(tmp_path)
        with pytest.raises(r.RecoveryError, match="disk quota"):
            store.write(encoded(3))
        assert disk_bytes(tmp_path) == before
        assert sum(map(len, before.values())) <= limit
        assert before[".writer.lock"] == b""
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=10)


@pytest.mark.parametrize("kind", ["symlink", "nonempty", "directory", "hardlink"])
def test_invalid_lock_entry_never_modified(tmp_path, kind):
    root = tmp_path / "store"
    root.mkdir()
    lock = root / ".writer.lock"
    outside = tmp_path / "outside"
    outside.write_bytes(b"original")
    if kind == "symlink":
        lock.symlink_to(outside)
    elif kind == "nonempty":
        lock.write_bytes(b"original")
        lock.chmod(0o600)
    elif kind == "directory":
        lock.mkdir()
    else:
        os.link(outside, lock)
    with pytest.raises(r.RecoveryError):
        r.Store(root).write(encoded())
    assert outside.read_bytes() == b"original"
    assert set(root.iterdir()) == {lock}
    if kind in ("nonempty", "hardlink"):
        assert lock.read_bytes() == b"original"


def test_unsupported_platform_write_fails_before_filesystem_changes(tmp_path, monkeypatch):
    root = tmp_path / "not-created"
    store = r.Store(root)
    monkeypatch.setattr(r.os, "O_NOFOLLOW", None)
    # Model a platform with no no-follow support without changing global os.name,
    # which would alter pathlib's own platform dispatch in the test harness.
    monkeypatch.delattr(r.os, "O_NOFOLLOW")
    with pytest.raises(r.RecoveryError, match="platform is not supported"):
        store.write(encoded())
    assert not root.exists()


@pytest.mark.skipif(os.name != "posix", reason="Linux/POSIX crash-release qualification")
def test_abrupt_process_exit_releases_lock_and_retains_bounded_orphan(tmp_path):
    store = r.Store(tmp_path)
    store.write(encoded(1))
    first_path = tmp_path / f"{SCOPE}.0.recovery.json"
    first_bytes = first_path.read_bytes()
    limit = len(encoded()) * 3
    setup = f'''
import importlib, os, sys, types
package = types.ModuleType("recovery_crash_child")
package.__path__ = [{str(ROOT / "blender_addon/mechanical_cad_blender")!r}]
sys.modules[package.__name__] = package
r = importlib.import_module(package.__name__ + ".recovery_store")
r.MAX_STORE_BYTES = {limit}
store = r.Store({str(tmp_path)!r})
'''
    # Exit after flush but before replacement, while the writer lock is held.
    # os._exit deliberately bypasses context managers and temporary cleanup.
    crash = setup + f'''
r.os.fsync = lambda fd: os._exit(23)
store.write({encoded(2)!r})
'''
    result = subprocess.run([sys.executable, "-c", crash], capture_output=True,
                            text=True, timeout=10)
    assert result.returncode == 23, result.stderr
    assert first_path.read_bytes() == first_bytes
    orphans = list(tmp_path.glob(".*.tmp"))
    assert len(orphans) == 1
    orphan_bytes = orphans[0].read_bytes()
    assert orphan_bytes == encoded(2)
    assert sum(map(len, disk_bytes(tmp_path).values())) <= limit
    assert (tmp_path / ".writer.lock").read_bytes() == b""

    # A genuinely different process must acquire the crash-released lock.
    resume = setup + f'''
assert store.write({encoded(2)!r}).sequence == 2
print("RECOVERED_WRITER", flush=True)
'''
    result = subprocess.run([sys.executable, "-c", resume], capture_output=True,
                            text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "RECOVERED_WRITER"
    assert {entry.sequence for entry in store.entries()} == {1, 2}
    assert first_path.read_bytes() == first_bytes
    assert orphans[0].read_bytes() == orphan_bytes
    assert sum(map(len, disk_bytes(tmp_path).values())) <= limit
    assert (tmp_path / ".writer.lock").read_bytes() == b""
