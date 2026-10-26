"""Native-free settled-transaction fence for the optional recovery observer."""
from functools import wraps

_DEPTH = 0


def is_settled():
    return _DEPTH == 0


def settled_transaction(function):
    """Prevent reentrant observation of mutations awaiting their postchecks."""
    @wraps(function)
    def guarded(*args, **kwargs):
        global _DEPTH
        _DEPTH += 1
        try:
            return function(*args, **kwargs)
        finally:
            _DEPTH -= 1
    return guarded
