# Native execution lease

The add-on's `execution_lease.py` is a pure process-wide gate. `try_acquire()`
returns one fresh immutable opaque identity token, or `None` immediately if busy.
`release(token)` succeeds only for that exact current token; stale, copied and
unknown tokens cannot release newer work. `is_busy()` is read-only. The token
contains no Blender data, callback, exception, model identity or serialized state.

- Part `replay_guard` acquires the gate while preserving `_REPLAY_RUNNING` and
  its existing Object Mode and nested-call checks.
- Synchronous assembly `_run_sidecar` acquires the same gate and releases it even
  if configuration, request construction or execution fails.
- Explicit assembly Part capture (`canonical_working_part`) also holds the gate
  through its snapshot sidecar and freshness checks. Canonical serialization is
  native-kernel-free, but still launches a sidecar; it must not bypass exclusion.
  The following assembly replay acquires its own token after capture releases.
- Async assembly preparation acquires before capturing or launching work. All
  pre-launch construction failures release it. Once a pending job exists, that
  job owns the token until `SidecarJob.done` confirms process reaping and temporary
  file cleanup, including cancellation, start failure and abandoned interaction.
- Assembly `_BUSY` remains a separate per-scene canonical/display transaction
  lock. Neither this set nor `_REPLAY_RUNNING` substitutes for execution ownership.
- Busy callers receive an immediate explanation. There is no request queue,
  automatic retry, resumed acceptance or result publication from cleanup.
- `detach_all` keeps the pure token on the pending handle and only numeric keys
  in its transaction. It removes captured RNA and exception traceback references.
  Existing load/history/disable supervision can release the token after cleanup
  without restoring or publishing anything. Unregister must never reset the gate.

This migration adds no general sketch adapter and no new lifecycle registrations.
Focused gates are `tests/unit/test_execution_lease.py` and native
`tests/blender_execution_lease_smoke.py`; the existing assembly pending, modal,
load, Undo and actual owned-process exit suites remain required.

Part authoring, geometry and rectangle-entry polls consult the shared lease.
Poll is advisory: Regenerate and Activate Feature also handle a late/direct busy
rejection through the normal operator error path. Activate acquires before
changing the canonical active feature; its already-locked replay preserves the
existing failed-replay behavior. The focused native suite covers these races and
confirms unchanged canonical/display state apart from the readable action error.
