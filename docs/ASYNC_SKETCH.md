# General sketch async integration (development)

These are separately tested building blocks. They do not yet register a general
viewport editor or establish an end-to-end interactive acceptance result.

## Completed Part publication

`part_publication.prepare(context, candidate)` captures an explicit protocol-1,
result-version-2 replay request, exact candidate bytes, tessellation tolerance,
backend configuration, original scene/window/view layer, canonical base, display
owner, units, workspace, saved draft slot, and active sketch session/intent. Capture
starts no native work. Request/configuration accessors return detached copies.

The async owner may send only those detached values to `SidecarJob`. After the
child is reaped and its execution lease released, `intent.publish(context, response)`
reacquires the shared main-thread lease, rechecks all captured bindings and fully
revalidates the response. It publishes through the same staged canonical/display
transaction as synchronous replay. It never launches a second native replay.
The editor identity is checked again inside rollback after display publication;
the intentional transition from original canonical base to candidate is allowed.

Busy, stale, malformed, failed replay and publication errors retire the intent;
there is no queued acceptance or automatic retry. Original draft intent remains
the caller's responsibility and is not cleared by this module. A successful caller
must clear its exact owned slot only after publication, then retire the editor.

`retire()` is idempotent and drops captured RNA references. A caller must invoke it
before history/load/disable invalidates the original native context, regardless
of whether its process is running, ready or cancelled. This module does not install
lifecycle callbacks. The subsequent shared coordinator integration must prove that
retirement requirement before any general editor is enabled.

## Evidence

`tests/blender_part_publication_smoke.py` uses real sidecar replay and native
Blender 5.2.2. Its 131 checks cover no duplicate launch, typed open-sketch output,
reacquisition races, changed scene/base/owner/units/slot/configuration, active
editor changes, forged responses, inside-publication editor changes, exact
rollback with unrelated cache protection, blocked downstream extrusion and
explicit retirement before RNA unregister. The existing typed display suite
continues to exercise incomplete cleanup and separate-process persistence.

These headless checks do not qualify pointer interaction, keyboard focus,
registered async lifecycle handling, responsiveness at resource caps, or an
installed-package GUI workflow.

## Process-only sketch jobs

`sketch_pending` accepts only explicit protocol-1/result-version-2 `solve_sketch`
or `replay` requests. It shares the process-wide `execution_lease`; exports and
file destinations are rejected. Its caller-supplied identity is finite detached
JSON bounded to 128 KiB, depth 16 and 4,096 nodes. Object key order is immaterial;
array order, exact raw strings, boolean/integer/float types and signed floating
zero remain distinct. The owner must include all live acceptance bindings.

`prepare` explicitly starts one request. `poll` compares exact identity before
consuming anything, confirms process/file cleanup and validates the full envelope
with the existing strict bridge. It returns that envelope at most once. A valid
native failure is diagnostic data, never authority to accept a command. No worker
thread accesses Blender or publishes a result.

`cancel`, `reap` and `cancel_all` revoke acceptance and retain the lease until the
actual owned child is reaped. Maintenance does not consume ready success. Stale
finalizers cannot release a newer lease. Bounded status/error records contain no
exception traceback, RNA reference or publication callback. Cancellation does
not queue a retry. A lifecycle coordinator must supervise incomplete cleanup.

The pure adapter has 118 focused tests and 382 adjacent regression tests, including
real repository solve/replay subprocesses and sleeping/ready cancellation. The
complete suite at integration passed 2,754 tests plus 19,484 text-buffer subtests.
Native lifecycle and actual editor event routing remain separate gates.

## One shared native cleanup coordinator

The existing `assembly_job_ui` coordinator now supervises both process adapters
with one persistent timer. It reaps only; successful sketch responses are consumed
only by their still-current owner. `ensure_supervisor()` covers an explicitly
started or cancelled request. No timer or lifecycle hook is registered per editor.

History, load and disable first suspend/retire the shared sketch owner, revoking
its input and publication capabilities, then cancel both adapters. Native exit
retires the input owner without checkpointing or editing scene data. Cancellation
uses one total five-second deadline; one cleanup failure cannot skip the other
adapter. Incomplete cleanup keeps supervision and the actual process lease.

The native `blender_sketch_job_lifecycle_smoke.py` gate passes 141 checks including
actual load, Undo/Redo, disable/reenable, invalid raw retention, delayed cleanup and
independent cleanup errors. The Linux exact-owned-child exit gate confirms a real
sleeping sidecar is reaped and an unrelated control process survives. Unchanged
assembly UI/load/Undo/exit, shared owner, rectangle, persistence and Part-publication
gates also pass. Cross-platform process exit remains unqualified.

## Reproduce the boundary checks

Use a separate QA checkout and the pinned development/sketch dependencies. The
verified runtime is CPython 3.12.14 with native Blender 5.2.2 LTS on Linux x86_64.
Set `BLENDER` to your actual standalone executable; a Python `bpy` wheel does not
replace the real-process exit tests.

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[dev,sketch]'
export MCAD_ROOT="$PWD"
export MCAD_PYTHON="$PWD/.venv/bin/python"
export BLENDER=/absolute/path/to/blender
export PYTHONDONTWRITEBYTECODE=1
mkdir -p evidence/async
.venv/bin/python -m ruff check .
.venv/bin/python -m pytest -q

for name in blender_part_publication_smoke \
  blender_sketch_job_lifecycle_smoke blender_assembly_job_ui_smoke \
  blender_assembly_job_load_smoke blender_assembly_job_undo_smoke \
  blender_shared_sketch_owner_smoke blender_viewport_sketch_smoke \
  blender_typed_sketch_display_smoke; do
  "$BLENDER" --background --factory-startup --python-exit-code 1 \
    --python "$MCAD_ROOT/tests/$name.py" > "evidence/async/$name.log" 2>&1 || exit 1
done

# These are CPython launchers that start and observe real Blender children.
# Do not run them through Blender's --python flag.
for name in blender_sketch_job_exit_smoke blender_assembly_job_exit_smoke; do
  "$MCAD_PYTHON" "$MCAD_ROOT/tests/$name.py" \
    > "evidence/async/$name.log" 2>&1 || exit 1
done
```

Inspect each explicit `*_SMOKE_OK` marker as well as the exit status. The typed
sketch display gate also runs a separate-process save/reopen check. The exit
launchers use Linux process-identity checks and qualify only that platform.
Generated test `.blend` files and logs belong in a disposable QA directory, not
an existing user's design folder.

An independent read-only audit of commit
`bea15777dadb7b4d8ac76ecddc750c9356883ad3` reran all of these gates, the complete
2,754-test suite and Ruff. Additional independent native probes passed 136
publication/staleness assertions and 39 actual running-child load/history/disable
assertions. No correctness blocker was found in that bounded adapter/publication/
cleanup scope. Later GeneralSession and viewport code require their own reviews.
