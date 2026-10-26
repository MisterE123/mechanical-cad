"""Opt-in, native-free local recovery copies; never canonical model authority.

Paths are application supplied, not read from models. Unknown/corrupt files are
never repaired or removed. A failed write leaves the previous generation intact.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import bridge, draft_dispatch, part_snapshot_bridge

MAX_DOCUMENT_BYTES = 2 * 1024 * 1024
MAX_DRAFT_BYTES = 8 * 1024 * 1024
MAX_ENVELOPE_BYTES = 12 * 1024 * 1024
MAX_STORE_BYTES = 128 * 1024 * 1024
MAX_SCOPES = 32
_NAME = re.compile(r"([0-9a-f]{32})\.([01])\.recovery\.json\Z")
_TEMP_NAME = re.compile(r"\.([0-9a-f]{32})\.[0-9a-f]{32}\.tmp\Z")
_LOCK = threading.RLock()


class RecoveryError(ValueError):
    """Recovery unavailable; original documents and recovery files are retained."""


@dataclass(frozen=True)
class Record:
    scope: str
    sequence: int
    document_json: str
    draft_json: str
    created: str


@dataclass(frozen=True)
class Entry:
    scope: str
    slot: int
    sequence: int | None
    created: str | None
    error: str = ""
    document_name: str = ""


def _require(condition, message):
    if not condition:
        raise RecoveryError(message)


def _scope(value):
    _require(type(value) is str and re.fullmatch(r"[0-9a-f]{32}", value),
             "Recovery scope must be a lowercase UUID hex identifier.")
    return value


def _text(value, limit, label):
    _require(type(value) is str and len(value) <= limit, f"{label} exceeds its text bound.")
    try:
        encoded = value.encode("utf-8")
    except UnicodeError as exc:
        raise RecoveryError(f"{label} is not UTF-8 text.") from exc
    _require(len(encoded) <= limit, f"{label} exceeds its byte bound.")
    return encoded


def _validate_graph(document):
    """Check reference existence and DAG structure, not geometry or expressions."""
    features = document["features"]
    identifiers = {feature["id"] for feature in features}
    _require(document["active_feature"] is None or document["active_feature"] in identifiers,
             "Recovery document has a missing active feature.")
    pending = {feature["id"]: set(feature["inputs"].values()) for feature in features}
    _require(all(dependencies <= identifiers for dependencies in pending.values()),
             "Recovery document has a dangling feature reference.")
    completed = set()
    while pending:
        ready = [identifier for identifier, dependencies in pending.items()
                 if dependencies <= completed]
        _require(ready, "Recovery document has a feature dependency cycle.")
        for identifier in ready:
            del pending[identifier]
        completed.update(ready)


def _validate(record):
    _scope(record.scope)
    _require(type(record.sequence) is int and 0 < record.sequence < 2**63,
             "Recovery sequence must be a bounded positive integer.")
    _require(type(record.created) is str and len(record.created) <= 40,
             "Recovery timestamp must be UTC text.")
    try:
        stamp = datetime.fromisoformat(record.created.replace("Z", "+00:00"))
        _require(stamp.tzinfo is not None and stamp.utcoffset().total_seconds() == 0,
                 "Recovery timestamp must be UTC.")
        _text(record.document_json, MAX_DOCUMENT_BYTES, "Canonical document")
        _text(record.draft_json, MAX_DRAFT_BYTES, "Sketch draft")
        # Validation only: allowlisted normalization must NOT replace exact bytes.
        document = bridge.parse_document_json(record.document_json)
        draft_dispatch._validate_decoded_strings(document)
        normalized = part_snapshot_bridge._expected_document(document)
        _validate_graph(normalized)
        if record.draft_json:
            descriptor = draft_dispatch.inspect(record.draft_json)
            _require(descriptor.document_json == record.document_json,
                     "Recovery draft belongs to different canonical document bytes.")
    except (ValueError, TypeError, KeyError, UnicodeError, OverflowError, RecursionError,
            bridge.BridgeError) as exc:
        if isinstance(exc, RecoveryError):
            raise
        raise RecoveryError(f"Recovery payload is invalid: {exc}") from exc


def _digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _envelope_digest(value):
    data = {key: item for key, item in value.items() if key != "envelope_sha256"}
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def encode(scope: str, sequence: int, document_json: str, draft_json: str = "",
           created: str | None = None) -> bytes:
    """Validate and wrap exact canonical/draft strings without normalizing them."""
    record = Record(scope, sequence, document_json, draft_json,
                    created if created is not None else datetime.now(timezone.utc).isoformat())
    _validate(record)
    value = {"kind": "mechanical_cad_local_recovery", "schema_version": 1,
             **record.__dict__, "document_sha256": _digest(document_json),
             "draft_sha256": _digest(draft_json)}
    value["envelope_sha256"] = _envelope_digest(value)
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    _require(len(raw) <= MAX_ENVELOPE_BYTES, "Recovery envelope exceeds its byte bound.")
    return raw


def decode(raw: bytes) -> Record:
    """Reject unknown fields/versions, duplicate keys, corruption and stale binding."""
    _require(type(raw) is bytes and len(raw) <= MAX_ENVELOPE_BYTES,
             "Recovery envelope exceeds its byte bound or is not bytes.")
    try:
        value = bridge.parse_document_json(raw.decode("utf-8"))
        fields = {"kind", "schema_version", "scope", "sequence", "document_json", "draft_json",
                  "created", "document_sha256", "draft_sha256", "envelope_sha256"}
        _require(set(value) == fields, "Recovery envelope has unknown or missing fields.")
        _require(value["kind"] == "mechanical_cad_local_recovery"
                 and type(value["schema_version"]) is int and value["schema_version"] == 1,
                 "Unsupported recovery envelope version or kind.")
        record = Record(*(value[key] for key in
                          ("scope", "sequence", "document_json", "draft_json", "created")))
        _validate(record)
        _require(value["envelope_sha256"] == _envelope_digest(value),
                 "Recovery envelope checksum mismatch.")
        _require(value["document_sha256"] == _digest(record.document_json)
                 and value["draft_sha256"] == _digest(record.draft_json),
                 "Recovery checksum mismatch.")
        return record
    except (ValueError, TypeError, KeyError, UnicodeError, OverflowError, RecursionError,
            bridge.BridgeError) as exc:
        if isinstance(exc, RecoveryError):
            raise
        raise RecoveryError(f"Recovery envelope cannot be read: {exc}") from exc


class Store:
    """Two generations per random process/scene scope in a private app directory.

    Construction and listing do not create directories. Only explicit write does.
    Linux/POSIX writers use a nonblocking advisory lock; other OS writes fail closed.
    Independently running sessions use random scopes. Static symlinks are refused;
    hostile same-user concurrent parent-directory replacement is not defended.
    All regular files, including abandoned temporary/unknown files, count to quota.
    """

    def __init__(self, root):
        self.root = Path(os.path.abspath(os.fspath(root)))

    def _check_root(self, *, create=False):
        for path in reversed((self.root, *self.root.parents)):
            try:
                info = path.lstat()
            except FileNotFoundError:
                if not create:
                    return False
                path.mkdir(mode=0o700)
                info = path.lstat()
            _require(stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode),
                     "Recovery root or ancestor is not a real directory.")
        info = self.root.stat()
        if os.name == "posix":
            _require(info.st_uid == os.getuid() and not info.st_mode & 0o022,
                     "Recovery root must be owned by this user and not writable by others.")
        return True

    def _inventory(self):
        if not self._check_root():
            return [], 0
        names, total = [], 0
        for path in self.root.iterdir():
            info = path.lstat()
            _require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode)
                     and info.st_nlink == 1,
                     "Recovery directory contains a symlink or non-private regular entry.")
            total += info.st_size
            match = _NAME.fullmatch(path.name)
            if match:
                names.append((match[1], int(match[2])))
        return names, total

    def _reserved_scopes(self, names):
        # A generated temporary also reserves its scope until replacement. This
        # prevents separate sessions from each claiming the last free scope.
        scopes = {scope for scope, _ in names}
        for path in self.root.iterdir():
            match = _TEMP_NAME.fullmatch(path.name)
            if match:
                scopes.add(match[1])
        return scopes

    def _path(self, scope, slot):
        _scope(scope)
        _require(type(slot) is int and slot in (0, 1), "Invalid recovery slot.")
        return self.root / f"{scope}.{slot}.recovery.json"

    def _read(self, scope, slot):
        path = self._path(scope, slot)
        _require(self._check_root(), "Recovery directory does not exist.")
        info = path.lstat()
        _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1,
                 "Recovery entry is not a private regular file.")
        _require(info.st_size <= MAX_ENVELOPE_BYTES, "Recovery entry exceeds its byte bound.")
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as stream:
            actual = os.fstat(stream.fileno())
            _require(stat.S_ISREG(actual.st_mode) and actual.st_nlink == 1
                     and (actual.st_dev, actual.st_ino) == (info.st_dev, info.st_ino),
                     "Recovery entry changed during read.")
            raw = stream.read(MAX_ENVELOPE_BYTES + 1)
        record = decode(raw)
        _require(record.scope == scope, "Recovery entry scope does not match its filename.")
        return record

    def read(self, scope: str, slot: int) -> Record:
        with _LOCK:
            try:
                return self._read(scope, slot)
            except OSError as exc:
                raise RecoveryError(f"Cannot read local recovery: {exc}") from exc

    def entries(self) -> tuple[Entry, ...]:
        with _LOCK:
            try:
                names, _ = self._inventory()
                entries = []
                for scope, slot in sorted(names):
                    try:
                        record = self._read(scope, slot)
                        name = bridge.parse_document_json(record.document_json)["name"]
                        entries.append(Entry(scope, slot, record.sequence, record.created,
                                             document_name=name))
                    except (RecoveryError, OSError) as exc:
                        entries.append(Entry(scope, slot, None, None, str(exc)))
                return tuple(entries)
            except OSError as exc:
                raise RecoveryError(f"Cannot list local recovery: {exc}") from exc

    @contextmanager
    def _writer_lock(self):
        """Retain an empty private lock entry; never prune or unlink it."""
        import fcntl

        path = self.root / ".writer.lock"
        if path.exists() or path.is_symlink():
            info = path.lstat()
            _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1,
                     "Recovery writer lock is not a private regular file.")
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(fd)
            _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                     and info.st_size == 0 and info.st_uid == os.getuid()
                     and not info.st_mode & 0o077,
                     "Recovery writer lock must be an empty private regular file.")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RecoveryError("Local recovery is busy in another process; retry later.") from exc
            try:
                yield
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    def write(self, value: bytes | Record) -> Record:
        """Atomically replace the older slot, never an unreadable original."""
        with _LOCK:
            _require(os.name == "posix" and hasattr(os, "O_NOFOLLOW"),
                     "Local recovery writes currently require a POSIX filesystem lock; "
                     "this platform is not supported.")
            raw = encode(**value.__dict__) if type(value) is Record else value
            record = decode(raw)
            try:
                self._check_root(create=True)
                with self._writer_lock():
                    return self._write_locked(raw, record)
            except OSError as exc:
                raise RecoveryError(f"Cannot write local recovery: {exc}") from exc

    def _write_locked(self, raw, record):
        temporary = None
        temporary_created = False
        try:
            names, total = self._inventory()
            scopes = self._reserved_scopes(names)
            _require(record.scope in scopes or len(scopes) < MAX_SCOPES,
                     "Local recovery scope quota reached; existing copies retained.")
            # Account for the complete temporary before replacing anything.
            _require(total + len(raw) <= MAX_STORE_BYTES,
                     "Local recovery disk quota reached; existing copies retained.")
            previous = [(self._read(scope, slot), slot) for scope, slot in names
                        if scope == record.scope]
            latest = max(previous, key=lambda item: item[0].sequence) if previous else None
            _require(latest is None or record.sequence > latest[0].sequence,
                     "Stale recovery sequence refused; newer copy retained.")
            slot = 1 - latest[1] if latest else 0
            target = self._path(record.scope, slot)
            temporary = self.root / f".{record.scope}.{uuid.uuid4().hex}.tmp"
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                         | getattr(os, "O_NOFOLLOW", 0), 0o600)
            temporary_created = True
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            self._check_root()
            # Recheck security before replacement, including all other entries.
            current_names, occupied = self._inventory()
            _require(len(self._reserved_scopes(current_names)) <= MAX_SCOPES,
                     "Local recovery scope quota changed; existing copies retained.")
            _require(occupied <= MAX_STORE_BYTES,
                     "Local recovery disk quota changed; existing copies retained.")
            os.replace(temporary, target)
            temporary = None
            # Directory durability is best effort where supported. The replace
            # already succeeded; a directory-fsync error must not imply rollback.
            if hasattr(os, "O_DIRECTORY"):
                try:
                    directory = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY
                                        | getattr(os, "O_NOFOLLOW", 0))
                    try:
                        os.fsync(directory)
                    finally:
                        os.close(directory)
                except OSError:
                    pass
            return record
        except OSError as exc:
            raise RecoveryError(f"Cannot write local recovery: {exc}") from exc
        finally:
            if temporary is not None and temporary_created:
                try:
                    temporary.unlink()
                except OSError:
                    pass
