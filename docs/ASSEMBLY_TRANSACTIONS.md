# Blender assembly state transactions

This is the state/publication foundation for the assembly authoring slice. It is
not a claim of general constraint solving, continuous collision freedom, physical
fit, structural safety, or a finished GUI. Native CAD remains in the existing
bounded subprocess. `assembly_state.py` imports no core model, OCP, or solver.

## Separate ownership and persisted fields

Register `assembly_properties.CLASSES`, then install
`bpy.types.Scene.mechanical_cad_assembly = PointerProperty(type=MCAD_AssemblyState)`.
The existing `scene.mechanical_cad` remains the working Part and is never rewritten
by an assembly state operation. Assembly objects use only the separate assembly
ownership tags documented in ASSEMBLY_DISPLAY.md. Part regeneration cannot delete
assembly siblings.

The assembly property group persists:

- Independent `owner_id`, canonical `document_json`, `document_name`, and
  `document_path`.
- Attempt `status`, `error`, and `last_action_error`. A failed attempt remains
  visible while the previously accepted document and display remain intact.
- `display_status`, separately from `verification_status` and
  `verification_message`.
- `report_json`, the complete validated response envelope, including report,
  source diagnostics, and exact request fingerprints. This is historical evidence,
  not a persisted native B-rep or a trusted replacement for fresh replay.
- `report_document_json`, `report_request_json`, and `report_working_part_json`,
  binding exact accepted scene text, exact raw sidecar request, and exact working
  Part text. `report_preset_id` records the explicitly resolved preset or an empty
  string for unconfigured measurements.
- `selected_part_id`, `selected_instance_id`, `selected_joint_id` are UI selections
  only. They cannot change canonical definitions, instances, or joints.

A runtime-only accepted display response and evidence binding establish trust.
Persisted strings cannot reconstruct that runtime trust. Reopening a `.blend`,
Undo/Redo, add-on reload/rebind, and explicit invalidation all require a new check.
No geometry is inferred from Blender mesh indices, object names, transforms,
parenting, modifiers, or animation.

## Public API

- `read_assembly(state)` returns a detached strict JSON object. The sidecar is the
  complete schema/geometry authority; reading alone does not validate an assembly.
- `commit_candidate(context, candidate, expected_json=None)` freshly replays a
  dictionary or JSON candidate, stages every display resource, and publishes the
  complete accepted snapshot atomically. `expected_json` is the exact accepted text
  captured when a dialog opened, including whitespace; a mismatch rejects the edit.
- `replay(context)` uses the same transaction to rebuild accepted canonical data.
  It establishes a current display and clears prior verification trust.
- `check(context, preset_id=None)` stores evidence only. A supplied ID is explicit;
  otherwise only the canonical active preset is used. No automatic sole-preset
  selection is allowed. No configured preset means measurements with `passed=false`.
- `sample(context, joint_id, values)` stores evidence only and sends the entire
  authored base coordinate map, including fixed zeroes. Each listed sample changes
  only its named coordinate. Canonical pose and viewport objects remain unchanged.
- `display_is_current(context, update=False)` checks intact accepted geometric/pose
  caches. `report_is_current(context, update=False)` additionally requires an exact runtime evidence
  binding, canonical text, request, resolved preset, and working Part text. Both are
  read-only by default for Panel.draw. Action/depsgraph hooks use `update=True` to
  visibly revoke stale evidence; repeated stale checks avoid RNA/epoch churn.
- `source_updates(context, update=False)` returns update records with `source_document_id`,
  `accepted_digest`, `working_digest`, `working_digest_scope`, `part_ids`, and `instance_ids`.
  `working_digest` identifies raw editor JSON, not an authoritative source revision.
  A pure allowlisted canonical-equivalence check avoids false notices from serializer
  defaults, typed-sketch numeric conversion and stable-ID entity ordering. It never
  accepts an update. The read-only query is safe in Panel.draw. `update=True` also
  invalidates report trust; ordinary depsgraph hooks detect the changed working
  Part independently. The assembly continues using its explicitly accepted revision.
- `invalidate(scene, reason)` revokes verification trust and keeps persisted
  evidence, canonical data, and display resources for diagnosis.
- `require_idle(context)` rejects concurrent assembly operations and any active or
  suspended sketch draft. Use it before source-open/save operations.
- `validate_snapshot(context)` freshly replays accepted canonical data for an
  explicit save without publishing objects or changing report bindings. It returns
  a validated response. The caller must keep the remaining file write synchronous;
  this does not establish display trust or renew a check.

Replay, commit, check, sample, and validation return `AssemblyResponse`. Expected
validation/process errors use `BridgeError`; transaction cleanup also restores
state for unexpected exceptions and re-raises them. Existing add-on interpreter,
project-root, process timeout, and replay tessellation preferences are reused.
Preset checks use the preset's saved numerical policy; preferences cannot override
its engineering requirements or numerical tolerances.

All canonical mutations reject active or suspended sketch drafts, including a
modal session in another window and saved drafts in another scene. Check, sample,
and save validation conservatively use the same draft exclusion.

## Acceptance and rollback sequence

1. Reject an already running transaction, a sketch draft, or an expired dialog
   `expected_json`. Capture every owned state field, exact working Part bytes,
   original scene/window identity, scene scale, history invalidation epoch, and
   prior runtime trust. Scene-only contexts do not require a UI window.
2. Detach the candidate and request fresh isolated replay. The bridge validates
   complete protocol, document/source identities, poses, evidence, and fingerprints.
3. Reject a changed scene or window, then compare the original canonical text,
   owner, working Part, scene scale, and history epoch again. A late response cannot replace newer external edits.
4. Stage all meshes, instance objects, and literal frame objects while unlinked.
   Repeat freshness checks; publish the display reversibly; repeat checks again.
5. Write canonical/report state under the property callback lock and install the
   accepted runtime binding. Replay itself sets verification `UNCHECKED`.
6. Finalize old orphan cleanup only after successful acceptance. Cleanup warnings
   are visible in `last_action_error`; an orphan-cleanup failure does not roll back
   or misreport a successfully accepted canonical/display pair.

A native, staging, publication, or state-write failure leaves the previous accepted
canonical text and display identities intact. State-write failure restores every
owned field and runtime binding before attaching attempt diagnostics. Display
rollback restores original collection links; it does not reconstruct approximate
replacement objects. A late response detected before state writing never restores
an old snapshot over a newer external edit. The working Part is never written.

Recovery is independently guarded: even if display discard/orphan cleanup throws,
canonical fields and prior runtime state are restored in a guaranteed `finally`
path. If any recovery step remains incomplete, runtime capability is revoked and
state is explicitly `FAILED`, with stale display/evidence and both the primary and
recovery diagnostics. The raised error also retains both causes so operator error
reporting cannot hide the recovery failure. A cleanup-only failure may leave exact
old objects linked, but they remain conservatively untrusted until fresh replay.
Recovery always targets the original captured scene/state, even after the active
window switches to another scene. A matching cloned scene cannot authorize a late
response or receive the original target's failure diagnostics.

Report-only transactions perform the same exact-input and final-display guards.
Their write failure restores previous evidence. They never publish native result
meshes, change authored coordinates, or move the viewport to a sample. Incomplete
reports and known violations remain distinguishable from complete reports. A
current report means current evidence, not a pass verdict. Known interference,
clearance violations, threshold contacts, incomplete evidence, unconfigured intent,
and discrete-sampling limits have explicit status text.

## Lifecycle wiring owned by registration

The state module installs no global handlers and registers no classes itself.
Registration should call these hooks:

| Registration event | State hook |
| --- | --- |
| Successful scene property setup or deferred add-on rebind | `rebind_existing()` |
| `load_post` | `after_file_load()` |
| `undo_pre` and `redo_pre` | `before_history_change()` |
| `undo_post` and `redo_post` | `after_history_change()` |
| `save_pre` | `before_file_save()` |
| `depsgraph_update_post` | `depsgraph_update(scene, depsgraph)` |
| Add-on unregister / reload cleanup | `clear_runtime()` |

Registration supplies Blender's `persistent` wrappers and removes its own handlers
on unregister. `rebind_existing()` returns false under restricted startup access
so the existing deferred registration flow can retry. Hooks iterate scenes safely
without assuming that the current window displays the affected scene. No hook
launches native work. Publication ignores its own transient depsgraph activity.

Direct canonical RNA edits immediately revoke report/display currentness. A unit
change or manual display edit is caught by the depsgraph hook or a currentness
query with `update=True`. Read-only queries report stale without RNA writes.
Even restoring edited cache values cannot resurrect an already revoked
report. Geometric integrity and verification status remain separate: a restored
exact cache may be geometrically current while a fresh check is still required.

## Native evidence and remaining gates

`tests/blender_assembly_state_smoke.py` registers only required RNA classes and the
new property group, independent of main registration. It runs real sidecar geometry
under native Blender 5.2.2 LTS. Coverage includes:

- A newly authored schema-1 Part reused by three assembly instances; exact working
  Part bytes and embedded snapshots remain unchanged. Schema-2 capture is tested
  independently in another scene.
- Nonzero recentered origins and rotated placement, shared definition mesh,
  independent Part display ownership, explicit preset and no-preset evidence.
- Full-base-coordinate sampling without display/canonical mutation.
- Injected native, partial staging, partial publication, canonical field-write,
  evidence-write, and all-instance source-update publication failures, including
  compound canonical-write plus orphan-cleanup failure.
- Late assembly/working-Part revisions, real active-scene switching during Apply,
  check, and save validation, changed-window identity, saved/active drafts, source-update notices,
  all-instance acceptance, and unchanged literal datums.
- Manual transform/mesh corruption, units, lifecycle invalidation hooks, report
  binding tampering, and nonmutating save validation.
- Actual `.blend` save and a second native process reopening it, with byte-preserved
  Part/assembly/report/path data, stale initial state, fresh replay, and a new check
  resolving the saved verification preset.

Run with `--background --factory-startup --python-exit-code 1`; require the explicit
`ASSEMBLY_STATE_SMOKE_OK` marker. The second process separately requires
`ASSEMBLY_STATE_REOPEN_OK`. The architecture suite checks native-free and acyclic
imports. Lifecycle hook tests are not evidence of interactive Undo/Redo behavior,
GUI Apply/Cancel usability, installed-ZIP integration, or cross-platform support;
those remain separate integration gates.


## Authoritative Part capture boundary

Explicit New/Capture/Update operations request protocol-v1 `canonical_snapshot`
from the isolated core before constructing assembly candidates. The receipt binds
the exact raw request fingerprint, document/schema IDs, canonical document, exact
`Document.to_json()` bytes and their SHA-256 content hash. It performs no solve,
B-rep work or file writes. The Blender validator permits only the serializer’s
known defaults, sketch number normalization and stable-ID sorting; formulas,
feature order, entity IDs, references and numeric seeds cannot silently change.
Raw working Part JSON remains unchanged. The original scene/window and exact Part
and Assembly text are checked again after this extra process boundary.

`tests/blender_assembly_schema2_capture.py` retains the exact native viewport
regression that exposed raw-vs-canonical identity disagreement. It exercises
capture, two instances, fresh-process `.blend` reopen, ordinary formula editing,
all-instance update, uniform source/report hashes and pending-response rejection
after a late source edit. Hash comparisons are never weakened to repair input.

## Pending verification lifecycle

`sidecar_job.py` owns one detached JSON request and its process, temporary files,
stream caps, cancellation and cleanup. It never accesses Blender. `assembly_pending.py`
retains the original transaction and accepts evidence only from a main-thread poll
with matching scene/window/revision, draft, display and report bindings. Cancellation
invalidates even a ready but unpublished result. Busy ownership is retained until
process cleanup completes. `assembly_job_ui.py` owns modal input and a persistent
no-publication supervisor, which survives file loads solely to reap abandoned jobs.
An incomplete cleanup cannot be treated as a completed cancellation or release a
busy key. The native load regression separately verifies loaded-scene isolation. Before
load/history/unregister invalidates RNA, retained jobs shed all native references;
late cleanup is strictly process-only. On Blender 5.2 LTS, `exit_pre` cancels owned
children with a bounded total wait before interpreter shutdown. Interactive async
checks require this native exit hook; older Blender runtimes without it reject
starting such a job. OS-level uninterruptible cleanup is reported, not represented
as a successful reap.

## Asynchronous complete candidate creation

The gear configurator uses the existing assembly_pending registry, guarded native
job and exclusive execution lease with an explicit candidate purpose. Its
dialog-opening capture binds Assembly/report/source and working-Part bytes,
owners, original context, backend, units, history and live-admission revisions.
The shared assembly_state commit-from-evidence sink is also used by synchronous
edits; it accepts only the independently prepared full replay request and the
one-shot guarded evidence, never a saved result or transient preview. Native
work and cancellation leave accepted data/display unchanged. Complete success
publishes the candidate and clears the previous save path atomically, marks
checks UNCHECKED, then focuses the result. Cancel or stale results never accept
a candidate. Lifecycle invalidation detaches the same owner before RNA is freed.
The modal operator provides the normal single creation Undo boundary; no timer
or acceptance helper pushes an extra step. Headless modal-pump tests do not
claim interactive Undo/Redo qualification.
