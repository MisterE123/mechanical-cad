# Fresh accepted-Part display after Undo/Redo and file open

Undo/Redo still restores canonical scene JSON, not trusted mesh evidence. After
history restoration, one nonpersistent app timer now attempts a fresh Part replay
for the active window's dirty CAD document. The default removes the separate
manual Rebuild click for ordinary supported Object Mode history navigation.

The handler does not launch a native process or perform a synchronous replay.
The timer debounces rapid history navigation for 250 ms. It waits at most two
seconds for the shared execution lease to become available, launches at most one
guarded async sidecar, and never retries failed or cancelled work automatically.
Transport retains the configured bounded timeout and process cleanup policy.
No backend setup, install, network operation or assembly replay is started.

Publication uses the existing fresh regeneration sink after transport cleanup,
under the shared execution lease. It does not write or reserialize canonical
JSON, create an edit candidate, consume an Undo step, restore unverified meshes,
or change unrelated objects/scenes. Last-good geometry remains hidden or visibly
stale until exact fresh evidence passes. Failed model replay retains its normal
visible feature diagnostics. Manual Rebuild remains the recovery path.

Bindings cover the original window, scene, view layer, workspace, exact canonical
bytes, ownership, unit scale, backend generation/lifetime/selection and mesh
tolerance. Active/saved sketch drafts and retained repair proposals block the
automatic attempt rather than being silently displaced. Switching context,
editing the model or changing these bindings cancels pending work. Another
history operation, file load, add-on disable or backend invalidation retires the
RNA-bearing publication capability before existing process-only cleanup runs.
A completed manual rebuild before the timer fires suppresses duplicate work.

The Part history panel and normal CAD sidebar show Cancel Rebuild while queued
or running. Cancellation has no Undo flag, does not change restored canonical
data, and does not restart the job. Rebuild returns after cancellation/failure;
cleanup may briefly retain the process-wide lease until the child exits.

## Qualification

- `tests/unit/test_history_rebuild.py`: bounded scheduling, coalescing, blocked
  contexts, busy expiry, revocation, single publication/failure and cancel UI.
- `tests/blender_history_rebuild_smoke.py`: native Blender Undo/Redo and real
  guarded sidecar replay, exact JSON and expected native volume, visible fresh
  display, preserved Redo, rapid repetition, in-flight history/context/backend
  interruption, explicit cancellation, load/disable, manual recovery and
  unrelated object/scene preservation.
- The native background test pumps the registered timer callback on Blender's
  main thread. It is not real desktop event-loop or installed-package GUI
  qualification. Those remain separate release gates.

History/Undo scope is intentionally the restored active Part only. Other scenes
and assemblies are not automatically replayed by history restoration. Missing backend, unsupported context, active or
saved draft, blocked lease and model failure remain explicit manual-retry states
for history restoration.

## Accepted display after opening or reverting a file

Open/Revert uses an explicit load-origin ticket in the same owner, after load
invalidation. With an already configured/ready backend, the active Part is freshly
replayed asynchronously and its disposable display cache becomes visible. An
Assembly workspace instead schedules one accepted-Assembly display replay, even
when there is no working Part. The same single restoration owner and native
lease prevent competing Part/Assembly jobs. Only the active workspace role is
rebuilt; an Assembly tab never unexpectedly shows its inactive stored Part.

Unlike history restoration, the load-origin attempt can coexist with dormant
saved sketch drafts and saved repair intent, including unknown/malformed records.
It treats those records and saved annotations as opaque exact text. It neither
parses nor validates them, changes their base, consumes them, starts Resume Repair,
nor accepts a proposed edit. The requested native document is only accepted Part JSON, or the accepted
Assembly with its embedded source snapshots. No source Part is refreshed. Resume remains an explicit separately guarded operation.

The load ticket additionally binds the exact saved draft/repair/annotation bytes
and runtime sketch/repair admission revisions. Starting a live sketch or Resume,
even if cancelled before the next timer tick, retires the attempt. New input,
context, units, backend or history changes also reject running/ready results at
publication. While native work owns the shared lease, use **Cancel Rebuild** and
allow cleanup before starting Resume/editing; the lease is never bypassed.

No setup/install/network action, backend-readiness wait or hidden retry is added.
A not-ready backend, unsupported context, cancellation or failure leaves a visible
manual **Regenerate** fallback. Cache rebuilding does not rewrite saved intent.
Neither successful cache publication nor cancellation creates a canonical Undo
step. The existing stricter history-origin draft/proposal policy is unchanged.

`tests/blender_load_rebuild_smoke.py` writes real plain, repair, draft and unknown
intent files, then opens them in a separate native Blender process. It checks
accepted native geometry, unchanged source/intent/annotation bytes, dormant
ownership, actual Revert, load over an in-flight job, real intervening Resume and
draft ownership, stale ready responses, backend-not-ready/manual recovery,
cancellation, Assembly-workspace exclusion, unrelated scene/object isolation and
zero extra Undo/Redo step. The focused source check passes 170 host tests, native
load/reopen checks (5 writer and 153 reader assertions), the existing native
history check (69 assertions), saved-repair writer/reopen regression, and native
narrow panel drawing with both dormant cards and one Cancel Rebuild control.
The background harness pumps the existing registered timer on the main thread;
it does not qualify real GUI event-loop behavior or an installed release.

### Assembly display-only restoration

The Assembly path uses the existing guarded asynchronous assembly job owner and
reversible cache staging transaction. It preserves exact canonical Assembly
text, embedded source digests, ownership and saved report bytes. Only fresh replay
geometry gains current display authority. A saved Check or Sample remains visibly
**historical / not current**: its runtime report binding is explicitly absent.
No interference, clearance, verification preset or dynamics is evaluated by
replay. **Check** stays explicit.

Missing ownership, unsupported models, a non-ready backend or failures leave
**Replay** as the manual fallback. No setup/network action, deferred readiness
retry, source refresh or automatic acceptance of transient edits occurs.
**Cancel Rebuild** is available while queued or running. Assembly dialogs/edits,
live sketch/repair admissions, changed report text, workspace/view layer, scene
units, backend, history or newer loads revoke the old ticket. Dormant Part intent
is neither inspected nor consumed. Cache publication does not push model Undo.

Focused gates: `tests/unit/test_assembly_load_rebuild.py` covers role dispatch,
opaque intent, stale results and cache-only rollback. The two-process
`tests/blender_assembly_load_rebuild_smoke.py` covers Open/Revert, Assembly-only
files, exact source/report/intent retention, historical report authority,
queued/running/ready cancellation, newer loads and native owner isolation.
This is native background qualification, not a new GUI or package claim.

## Sketch-repair integration evidence

`tests/blender_history_sketch_integration_smoke.py` combines registered existing
Sketch Edit/Finish, a retained failed projection proposal, and registered explicit
reference repair with automatic history replay. The source-loaded native Blender
5.2.2 check passes 55 assertions: exact old/repaired canonical JSON and annotation
layout return together, repeated Undo/Redo produces freshly replayed 45π/80π mm³
solids, no proposal or duplicate draft survives, and Redo remains available after
cache publication. No OCP module is imported into Blender.

This bounded background harness uses explicit native Undo checkpoints and pumps
the registered timer on the main thread. It does not establish GUI event-loop,
interactive checkpoint placement, installer qualification or release readiness.
The integrated focused architecture, history ownership, proposal ownership and
proposal UI host scope passes 97 tests; the individual feature suites were not
repeated. Proposal retention preserves the shared immediate redraw hook only
after successful timer registration; registration failure removes the pending
owner without announcing a retained proposal.

After integrating the compact proposal card, the narrow native draw check also
verifies exactly one Cancel Rebuild control and no competing Rebuild launcher in
both panels while automatic history replay is queued. Proposal controls remain
above history, and ordinary accepted-model projection actions stay suppressed
while a proposal owns the repair. The final narrow architecture/history/UI scope
passes 50 host tests plus `STAGED_COMPACT_DRAW_NATIVE_OK` in native background
Blender; this still does not substitute for GUI qualification.
