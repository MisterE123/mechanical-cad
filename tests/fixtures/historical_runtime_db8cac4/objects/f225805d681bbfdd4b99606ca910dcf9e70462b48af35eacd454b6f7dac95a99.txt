"""One native-free, process-wide lease for explicitly requested CAD execution.

Tokens are opaque immutable objects. Acquisition never queues work. Synchronous
owner scopes lend their exact token to one atomic transport binding; unscoped busy
callers and reentrant transports are rejected. An uncertain transport is retained
in one absorbing quarantine slot. There is no reset or cleanup retry operation.
Lifecycle restart must not release or replace this module's original ownership.
"""

import threading
from contextlib import contextmanager

BUSY_MESSAGE = (
    "Another CAD operation is running or its native process is still being cleaned up. "
    "Wait for it to finish or cancel it, then explicitly try this operation again."
)
QUARANTINE_MESSAGE = (
    "Bundled backend cleanup could not be confirmed. Native operations remain "
    "disabled. Save your work and restart Blender before trying again."
)

_LOCK = threading.Lock()
_TOKEN = None
_BOUND_TOKEN = None
_QUARANTINE = None
_SCOPE = threading.local()


class LeaseError(RuntimeError):
    """Execution ownership could not be established without replacing another owner."""


def try_acquire():
    """Return a fresh opaque token, or None immediately when already owned."""
    global _TOKEN
    with _LOCK:
        if _TOKEN is not None or _QUARANTINE is not None:
            return None
        _TOKEN = object()
        return _TOKEN


def release(token):
    """Release only this unbound exact token; quarantined/stale owners never clear it."""
    global _TOKEN
    with _LOCK:
        if (
            token is None
            or token is not _TOKEN
            or _BOUND_TOKEN is not None
            or _QUARANTINE is not None
        ):
            return False
        _TOKEN = None
        return True


def is_busy():
    """Read ownership without consuming a token or starting/retrying any work."""
    with _LOCK:
        return _TOKEN is not None or _QUARANTINE is not None


def cleanup_message():
    """Read only the absorbing failure flag; never touch or release its owner."""
    with _LOCK:
        return QUARANTINE_MESSAGE if _QUARANTINE is not None else ""


@contextmanager
def synchronous(token):
    """Expose one existing main-thread owner token only within its lexical scope."""
    if threading.current_thread() is not threading.main_thread():
        raise LeaseError("Synchronous CAD ownership requires the main thread.")
    with _LOCK:
        if _QUARANTINE is not None:
            raise LeaseError(QUARANTINE_MESSAGE)
        if (
            token is None
            or token is not _TOKEN
            or _BOUND_TOKEN is not None
            or getattr(_SCOPE, "token", None) is not None
        ):
            raise LeaseError(BUSY_MESSAGE)
        _SCOPE.token = token
    try:
        yield
    finally:
        # Scope exit grants no cleanup or release authority, even after mismatch.
        if getattr(_SCOPE, "token", None) is token:
            _SCOPE.token = None


def bind_transport():
    """Atomically borrow the current scoped token or acquire an otherwise empty slot.

    Return (exact token, transport_owned). Binding precedes job construction and
    prevents reentrancy or release until finish_transport or absorbing quarantine.
    """
    global _TOKEN, _BOUND_TOKEN
    with _LOCK:
        if _QUARANTINE is not None:
            raise LeaseError(QUARANTINE_MESSAGE)
        if _BOUND_TOKEN is not None:
            raise LeaseError(BUSY_MESSAGE)
        scoped = getattr(_SCOPE, "token", None)
        if scoped is not None:
            if scoped is not _TOKEN:
                raise LeaseError(BUSY_MESSAGE)
            owned = False
        elif _TOKEN is None:
            _TOKEN = object()
            owned = True
        else:
            raise LeaseError(BUSY_MESSAGE)
        _BOUND_TOKEN = _TOKEN
        return _TOKEN, owned


def finish_transport(token, *, transport_owned):
    """Clear only this exact binding, releasing owned tokens only after clean use."""
    global _TOKEN, _BOUND_TOKEN
    with _LOCK:
        if token is None or token is not _BOUND_TOKEN or _QUARANTINE is not None:
            return False
        _BOUND_TOKEN = None
        if transport_owned and token is _TOKEN:
            _TOKEN = None
        return token is _TOKEN or transport_owned and _TOKEN is None


def quarantine(token, owner):
    """Retain the original detached uncertain owner forever; never release/retry.

    A mismatch is an internal invariant failure, not authority over a successor.
    Keep that successor's token unchanged while retaining this original owner and
    blocking all new work. Supported binding/scoping makes mismatch unreachable.
    """
    global _QUARANTINE
    if token is None or owner is None:
        raise LeaseError("Uncertain execution requires its original token and owner.")
    with _LOCK:
        if _QUARANTINE is None:
            _QUARANTINE = (token, owner)
        elif _QUARANTINE[0] is not token or _QUARANTINE[1] is not owner:
            raise LeaseError(QUARANTINE_MESSAGE)
        return token is _TOKEN and token is _BOUND_TOKEN
