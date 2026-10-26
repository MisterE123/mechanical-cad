"""Transient source-review owner identity shared with other Assembly tools."""

_ACTIVE = None


def active(context=None):
    owner = _ACTIVE
    return (
        owner
        if owner and owner.alive and (context is None or owner.light_binding(context))
        else None
    )


