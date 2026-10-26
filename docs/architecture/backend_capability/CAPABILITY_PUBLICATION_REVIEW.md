# Independent capability-boundary review: publication and lifetime

Date: 2026-10-17. Design review only; no production or proposal files changed.
Inspected `cad_arc_core` at base commit
`d6f13afbda1dbae5516e5fe53cda533902c595b2` with the unreleased arc core edits
present. References below are relative to that checkout. Line numbers describe
the inspected source and will move during implementation.

## Decision

The per-operation, same-process gate is the right boundary. I support staged
implementation, subject to the concrete acceptance conditions below. A transport
wrapper alone is not an acceptable cutover. Production remains unqualified until
every publication and current-evidence sink is converted and independently tested.

The corrected pure-snapshot exception is coherent: contract capability required,
no solver capability/import, no solve authority. All potentially solving actions
must require the actual imported solver's guard marker, even on primitive-only
input. No capability cache, version string, old result, or automatic downgrade
can authorize a production operation.

Wire fields, resource accounting, ordinary early-failure projection, and path
identity were assigned to the separate pure-contract reviewer. This review does
not duplicate that approval. In agreement with that reviewer, the smallest safe
production client uses **explicit result 2 for all schema-1/2 potentially solving
actions**, result 3 only for reviewed explicit arc intent. Preserve legacy v1
tooling APIs separately; do not promote their permissive validation to guarded
publication authority. Snapshot keeps its separate result contract.

## Implementation blockers to close before cutover

### 1. Preserve guarded evidence beyond the transport

`bridge.replay()` currently returns only `response['result']`. Synchronous Part
publication, rectangle acceptance, geometry display, and general solved-seed
consumers subsequently accept bare dictionaries. Adding the contract only to
`_exchange_raw` and `SidecarJob` would lose the required evidence before the most
important mutation sites.

Create an immutable, native-free guarded-evidence value containing exact G,
projected O, the original guarded response, validated projected operation
evidence, and captured backend selection/lifetime identity. Accessors return
detached projections. A caller cannot turn arbitrary legacy dictionaries into
production authority by invoking a legacy validator or setting a flag.

Keep **retained evidence** distinct from **one-shot acceptance/publication**.
Current same-session solve evidence is legitimately read again for drawing,
seed-dependent edits, and detached command-candidate cloning. Making the entire
evidence object consume-on-read conflicts with those existing workflows. Consume
the operation completion and publication intent once; allow bounded re-reading
of immutable evidence while its owner/revision/generation remains current.

Do not duplicate the typed action validators. The guarded facade validates the
receipt and selection, then explicitly projects into existing strict result-2
validators. Pure legacy helpers may remain test/tooling APIs, but production
sinks must require the guarded object or an owner-bound projection they cannot
manufacture from saved JSON. A dict subclass alone is insufficient: current
validators often require `type(value) is dict`, and `AssemblyResponse` can be
created through the legacy acceptance path.

### 2. Invalidate completed evidence, not only late jobs

`MCAD_Preferences` has no update callbacks. General pending identity and
`PartPublicationIntent` compare effective settings, but the general command
solution, rectangle cached report, Part CURRENT labels, assembly display and
assembly report remain current after a settings change unless explicitly revoked.

Add one main-thread configuration/lifetime authority shared by all production
entry points. RNA updates increment its generation even for A→B→A, revoke live
accepted evidence, and mark retained CAD display/reports stale across relevant
CAD scenes. Do not mutate authored canonical/draft/annotation bytes, remove
relations, change seeds, or touch unrelated Blender objects. Pending jobs are
retired through the existing supervisor; cleanup still owns its lease.

Capture selection once per operation and pass that exact selection into launch
and later checks. Do not independently resolve settings in the request builder,
owner identity, and worker constructor. Deflection/policy stays in the exact
request; the selected timeout/environment/interpreter must not be recaptured
later. Compare generation plus effective settings at the named boundaries.

Bound the environment claim precisely: a changed effective `MCAD_ROOT` or
`MCAD_PYTHON` observed at launch/poll/consume/publication revokes evidence.
Arbitrary `os.environ` A→B→A mutations entirely between observations cannot be
detected by polling. Do not claim otherwise. Supported preference changes have
callbacks and therefore can guarantee ABA detection. No monkey-patching of the
whole process environment is needed.

### 3. Rollback and re-enable cannot restore authority

`document_state._publish_candidate_locked` restores captured RNA fields after
failure. `assembly_state._recover_failure` can restore the old runtime record.
If configuration changes inside publication, restoration can resurrect old
READY/CURRENT flags or a report binding. Revalidate the live generation after
rollback and restore only authored state plus stale display when the captured
authority has expired. Never roll back the global configuration generation or
revocation state.

`registration._rebind_existing_documents()` currently restores Part status,
geometry status, and feature solve statuses verbatim. This is unlike assembly
rebind, which drops runtime authority. Re-enable/rebind must clear live Part and
sketch authority and mark saved reports historical. A saved receipt or restored
status string is never sufficient. Lifecycle epoch identity must not accidentally
repeat if a counter is reset on module reload. Existing load/history/disable
ordering remains: retire RNA-bearing publication intents first, then cancel/reap
detached processes, retaining opaque ownership until cleanup finishes.

### 4. Keep file outcome separate from display acceptance

Every new contract/identity/projection error after a launched export needs the
same conservative treatment as an existing lost transport reply. A generic new
`BridgeError` must not silently drop `outcome_unknown`. A valid pre-dispatch
rejection and a local before-launch rejection are definite no-write cases.

A valid typed export receipt followed by a stale scene/configuration or display
failure is historical evidence that the earlier request wrote its destination;
it does not make the current scene verified. Keep that distinction in the report.
Missing or malformed post-launch evidence is unknown outcome. Never retry an
export automatically and never claim cancellation/Undo restored the file.

The synchronous transport currently captures stdout/stderr in memory with
`subprocess.run(capture_output=True)` and checks stdout only afterward; only
`SidecarJob` has file-backed live stream bounds. A new guarded synchronous path
can reuse the bounded exchange mechanism rather than duplicating it. Do not
describe the current synchronous path as already memory-bounded or a sandbox.

## Explicit production sink inventory

Paths in this section are under `blender_addon/mechanical_cad_blender/`.

| Source seam | Existing behavior / required change |
| --- | --- |
| `bridge.py:239 _exchange_raw` | Resolves settings and transports a dict. Add a guarded transport path taking an already captured selection. Legacy adapter remains explicit. |
| `bridge.py:306 _exchange`, `:349 replay` | v1 is permissive and replay discards the envelope. Production requires typed guarded evidence and must not return a naked authoritative result. |
| `bridge.py:381 geometry_action` | Returns a full ordinary dict after validation. Preserve guarded envelope/selection through the geometry owner; wrap post-launch failures with export uncertainty. |
| `sidecar_job.py:64 SidecarJob` | Captures its own configuration and returns raw response once. Accept the captured selection; transport-ready is not accepted evidence. Request snapshot must preserve G exactly. |
| `sketch_pending.py:74 _request_snapshot`, `:217 prepare`, `:255 poll` | Existing allowlist rejects a new field; polling validates O and returns a bare accepted dict. Introduce explicit G/O projections and retain guarded evidence. Cancel ready results on stale generation before consuming. |
| `assembly_pending.py:108 prepare`, `:175 _assert_inputs`, `:264 poll` | Creates a second settings snapshot and checks scene/data, not backend. Bind one selection into transaction and use guarded assembly acceptance on both sync/async paths. |
| `document_state.py:254 _run_sidecar`, `:446 _regenerate_locked` | Regeneration receives a result-only dict and `_capture_binding` lacks settings. Capture selection with the main-thread transaction and keep evidence to `_apply_result`. |
| `document_state.py:266 _apply_result` | Writes resolved parameter values, CURRENT sketch reports, READY status, current mesh and volume from a dict. This is a primary authority sink, including partial/failing geometry paths. Require owner/current guarded evidence before writes. |
| `document_state.py:472 _commit_candidate_locked`, `:498 _publish_candidate_locked` | Canonical/display publication accepts a bare result. Share the guarded sink with async Finish, revalidate before/after mutation, and make rollback generation-aware. |
| `document_state.py:152 _parameter_mode_changed` | Converts formulas using retained resolved values when state is READY. Backend invalidation must remove that READY-derived authority; keep the authored expression until a fresh guarded regeneration. |
| `part_publication.py:29 _configuration`, `PartPublicationIntent.publish/prepare` | Existing async Finish checks settings but accepts raw response through the legacy typed validator. Capture one shared selection/generation, require guarded evidence and retain final editor/layout rollback checks. |
| `viewport_sketch.py:121 initialize_preview` | Synthesizes a replay result from saved `sketch_report_json` and CURRENT flags. Require a live matching guarded runtime association or run a fresh guarded operation. Never reconstruct authority from the saved report. |
| `viewport_sketch.py:147 solve`, `:165 finish` | Feeds bare Part results into rectangle draft acceptance. Bind current selection and guarded typed Part evidence. Fresh Finish remains independent from preview authority. |
| `sketch_draft.py:318 accept_replay` | Retains `solver_report`, `validated_json`, dimensions/anchor and solved points. Production needs guarded owner-bound evidence; historical outline/seed data must not confer current DoF. Do not change existing draft serialization bytes. |
| `general_session.py:233 identity`, `_start_job`, `tick` | Identity rereads config separately from launch. Capture once; preserve guarded evidence through solve, trial, downstream and Finish. Trial and downstream evidence must both remain current at acceptance. |
| `general_session.py:449 _accepted_driver`, `:549 execute` | Restores a detached command wrapper and replays the saved response into it. Permit guarded same-owner/revision transfer, never a legacy JSON rehydration shortcut. |
| `general_sketch_draft.py:186 has_current_solution`, `:421 record_validated_solution`, `:495 accept_edit` | `_Solution` stores revision/candidate/points/radii, with no runtime backend identity. The owner must actively revoke it; production acceptance/replay validation must be through guarded evidence, including downstream success. Pure legacy tests can retain isolated APIs. |
| `constraint_actions.py:130 _binding`, `:162 _solved` | Binds command/evidence identities but no backend generation, and revalidates raw dictionaries before fixing/releasing/recovering relations. Bind live evidence generation and reject stale prepared intents before authored edits. |
| `constraint_diagnostics.py`, `GeneralSession.current_diagnostics` | Failed-solve recovery candidates are also backend-bound evidence. Revoke them on setting changes; do not retain failed relation IDs as current recovery authority. |
| `general_view_geometry.py:163 build_geometry`, `general_session.py:471 geometry` | A legacy-valid solve becomes `source='solved'`. Production must only call it from current guarded ownership. Retained outline may remain visible as `source='retained'` with no solver fingerprint. |
| `workspace_ui.py:672 _draw_general_status`, `:766 committed report section`, `constraint_ui.py` | CURRENT DoF labels/tool availability consume owner flags and persisted JSON. Read current runtime predicates; stale strings alone cannot keep labels or operations enabled. No native work from drawing callbacks. |
| `geometry_operations.py:80 run_geometry_action`, `:26 _record_report` | Unwraps the response with `{**response, ...}`, publishes `response['result']`, and persists stripped report metadata. Retain evidence separately until publication; projection is for historical report serialization only. Extend binding with selection/generation and distinguish stale written-file evidence from current checks. |
| `part_snapshot_bridge.py:140 canonical_snapshot`, `:57 validate_response` | Returns stripped canonical receipt data. Guarded production entry must retain its contract evidence through capture acceptance; pure snapshot evidence can never be used as a solve/solid authority. |
| `assembly_operator_helpers.py:38 canonical_working_part` | Unwraps the canonical document after scene/window/data checks, with no settings check. Validate captured selection at this boundary; subsequent assembly replay independently gets a new guarded operation. Canonical data itself remains ordinary data. |
| `assembly_bridge.py:74 AssemblyResponse`, `:440 accept_response`, `:458 assembly_action` | Legacy validator can create a display-capable `AssemblyResponse`; mutation check binds response only, not live generation or its private request. Guarded production response must preserve and revalidate G/O/receipt/selection, not merely be an instance of the old class. |
| `assembly_display.py:132 _validated`, staging and trusted-display checks | Class identity plus `assert_unchanged()` currently suffices. Require guarded assembly authority before staging; later currency also requires the accepted generation. |
| `assembly_state.py:161 _capture`, `:176 _assert_current` | No backend configuration today. Extend the existing shared transaction snapshot; do not invent a separate assembly capability owner. |
| `assembly_state.py:278 commit_candidate`, `:364 validate_snapshot` | Candidate/source updates, replay and explicit portable save all call the sidecar. Require guarded response; final save validation is not renewed display authority. |
| `assembly_state.py:541 _publish_report`, `:588 _report_only` | Both synchronous and asynchronous Check/Sample converge here. Guard complete and partial reports, then recheck generation after RNA writes before establishing current runtime binding. |
| `assembly_state.py:267 _evidence_fields`, `_RUNTIME`, `display_is_current`, `report_is_current` | Saves response and request JSON but current authority lives in runtime. Add live generation association and never restore it from saved receipt bytes. `dict(response)` must be a historical projection only. |
| `assembly_state.py:210 _recover_failure` | Restores prior runtime after rollback. Keep revoked evidence revoked even when canonical/display restoration succeeds. |
| `properties.py:91 MCAD_Preferences` | No backend settings callbacks. Shared generation/revocation hook must cover root, Python, timeout and relevant tolerance/policy settings with no solving or process waits. |
| `registration.py:48 _on_blend_load`, `:136 _retire_native_jobs`, `:191 _rebind_existing_documents`, register/unregister/history | Clear runtime capability on lifecycle changes and do not restore CURRENT from persisted fields. Retain existing before-RNA-invalidation ordering and single cleanup supervisor. |

Other UI readers of saved assembly report JSON (`assembly_ui` and
`assembly_verification_ui`) may continue displaying historical details, but
their current-verification affordances must use the generation-bound runtime
predicate. `draft_store` deliberately strips `solver_report` and `validated_json`;
preserve that behavior and its seed/draft bytes. Do not serialize the new runtime
selection, nonce, generation, authority token, or Python objects into canonical
documents, existing draft codecs, annotations, or journals.

## Required targeted tests beyond generic contract tests

1. Instrument all nine production action families and their sync/async entry
   points: exactly one G is transported; minimum requirements cannot be removed;
   all current-evidence sinks reject a matching legacy success dictionary.
2. Use original schema-1/2 and primitive-only documents with explicit result 2.
   Rectangle, formula conversion, full Part, geometry, and assembly native
   controls must keep their meanings and stable canonical hashes.
3. Complete a good Check, change settings, then restore A before polling or
   performing any native action. General DoF/Finish, constraint seed actions,
   rectangle cached-preview opening, Part resolved values/CURRENT reports and
   assembly display/report currency must all remain stale until fresh work.
4. Capture a constraint intent under A, perform A→B→A, then apply it. Reject
   before changing authored relations, seeds, dimensions, or journal history.
5. Complete a trial solve under A, then change generation before downstream
   replay or final driver acceptance. Reject combining old solve authority with
   a new backend's downstream result. Preserve raw trial input for retry.
6. Change settings in injected callbacks at `_apply_result`, `_publish_layout`,
   assembly `_write_fields`, and final publication validation; throw afterward.
   Roll back authored changes but never restore old runtime/CURRENT authority.
7. Disable/re-enable, restricted-data deferred rebind, file load, Undo/Redo, and
   owner retirement with ready results. Saved reports remain historical; old
   detached cleanup cannot release a newer job's lease or revive an old epoch.
8. Inject malformed receipt, wrong nonce, identity mismatch and stale selection
   after export launch and after atomic replacement. Preserve destination,
   explicit uncertainty/historical-write reporting, and zero automatic retries.
   Before-launch and valid pre-dispatch failures must create no export tempfile.
9. Revalidate G, O and ordinary response after acceptance, including mutations to
   nested objects, public projections and an assembly response's private request.
   Guarded validation must not be a one-time mutation-blind flag.
10. Snapshot capability evidence cannot enter any solve/display/Finish sink.
    Its canonical document can be reused only as data for a separate fresh,
    guarded replay. No engine/solver/native imports are added to snapshot.
11. Check callbacks and runtime invalidation across multiple CAD scenes/windows;
    do not overwrite canonical/draft data or touch unrelated objects. Ensure
    draw/predicate calls never start native work or block on cleanup.
12. Test effective environment-default changes at every named observation
    boundary; distinguish that guarantee from unsupported invisible environment
    ABA. Test a new lifecycle epoch with an old retained evidence object.

## Smallest coherent implementation split

1. **Freeze pure contracts and fixtures.** ADR, strict guarded request/receipt
   leaves, explicit production result-2 policy, original mismatch witness and
   legacy byte fixtures. No UI switch and no canonical migration.
2. **Core same-process admission.** Own the marker in the actual solver module;
   gate each action before native/model side effects; preserve unguarded paths
   and snapshot import isolation. Pure server tests and all-action old-core
   rejection can land independently of Blender integration.
3. **Client selection/evidence and both transport adapters.** One captured
   selection, guarded facade, strict projected validation, export uncertainty,
   and immutable evidence with separate one-shot consumption. Reuse a bounded
   subprocess primitive. Keep production disabled while sinks are being moved.
4. **Convert production owners/sinks plus lifetime in one cutover milestone.**
   Part + geometry + rectangle, general solve/trial/seed/Finish, snapshot +
   assembly, preference callbacks, runtime predicates, rebind and rollback.
   These may be reviewable internal commits, but do not enable a partially
   guarded add-on. Gate completion on the explicit sink inventory above.
5. **Independent qualification and exact package.** Full Ruff/pytest plus native
   acyclic controls, deliberately mismatched old cores, real installed ZIP/GUI,
   corrected-settings recovery, two-process persistence and lifecycle/export
   tests against the final source/package hashes. Arc result-3 support remains a
   separate later milestone and is advertised only when its contracts pass.

No second lifecycle supervisor, background handshake process, replacement
solver, schema migration, or hash-based attestation layer is needed. The
engineering cost is concentrated in carrying authority through existing seams
and making their already present stale-state behavior complete.

## Revised-proposal disposition

Re-read the revised proposal at 01:37 UTC. Its production result-2 minimum,
explicit publication seams, immutable retained evidence/separate one-shot token,
bounded managed synchronous transport, immediate completed-evidence invalidation,
observable environment semantics, rectangle saved-report rejection, and
generation-aware rollback requirements address the architecture blockers above.
**Bounded approval for implementation from this review's scope.** The inventory
and targeted tests remain acceptance requirements; this is not approval to ship a
partially converted add-on or a claim of runtime qualification.

Two small documentation refinements were sent to the designer: explicitly name
Part rebind's saved-status restoration, and refer to the rectangle workflow's
existing Apply Dimensions/Finish validation actions rather than implying a new
General-style Check control is required. Neither requires a new architecture.

### Final frozen-design signoff

At 01:40 UTC, verified the amended `CAPABILITY_PROPOSAL.md` SHA-256:
`bd5c5faf0d0c297491bc1b360fffacdc802b15cf26eb563d734b125632e24c2d`.
It applies both refinements, incorporates this review's sink inventory and tests
as mandatory cutover requirements, and explicitly covers formula conversion,
prepared constraint intents, trial/downstream generation consistency,
nonrepeating runtime lifetime identity, rollback revocation, and historical
confirmed export outcomes. The frozen names, metadata overhead, and Linux-only
identity policy do not reopen a blocker in this review's assigned scope.

All publication/configuration/lifecycle **design blockers are addressed**.
Approved as a design for staged implementation, with no remaining design blocker
in this scope. Production conversion, independent tests, native/installed GUI
qualification, and final-package review remain required before release. This
signoff made no production changes and ran no runtime qualification tests.

## Verification limits

This review was source inspection and design analysis. I did not modify
production code, run native CAD/Blender, qualify an archive, or claim the proposal
has passed implementation tests. All findings were reported to the parent and
designer during review. The pure wire/path review remains separate.
