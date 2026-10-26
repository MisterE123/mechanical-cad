# Repair an unapplied upstream edit

An existing solid-feature edit, or Finish of an existing constrained sketch,
that rebuilds its own upstream geometry but breaks a downstream attached/projected
constrained sketch or an Up to Face extrusion end reference can be retained for review.
The failure notice says **Unapplied edit retained for repair; accepted model
unchanged**. Feature History shows the proposed upstream edit, its failed reference consumers,
and **Review Support** / **Replace Reference** / **Replace End Face** actions for that proposed graph.
The viewport and ordinary feature history remain the accepted model, not the
proposed geometry. No last-good shape is relabeled as successful proposed output.

Open the relevant review, choose an explicit source-bound repair and press
**Apply Repair**. The choices are freshly evaluated from the proposed edit's
real upstream geometry. Existing stable topology and construction intent rules
remain authoritative; there is no nearest-face/edge auto-match. A complete Part
replay must succeed before the upstream edit and the repair publish atomically.
If the selected reference is valid but supported reference failures remain, the
repair is kept only in the proposal. The accepted model, runtime and display stay
unchanged. **Undo Proposal Repair** reverses the last kept repair, including its
managed driver values, without altering ordinary Blender Undo. Each proposal
revision receives a fresh token, so old dialogs cannot modify or discard it.
The final successful operator is a normal Blender Undo step restoring the entire
accepted base, not an intermediate repair.

## Deliberately bounded transaction

- Exactly one rejected edit can be pending. Another candidate cannot silently
  replace it. Repair and accept, or explicitly discard it first. Named-parameter
  widgets are disabled while it is pending; direct numeric, formula and mode RNA
  changes restore accepted values and explain the same requirement.
- The live proposal is not canonical JSON, an export source or an active output.
  JSON Save and geometry exports always use the accepted model. Blender Save
  separately checkpoints pure repair intent, then suspends the live proposal only
  after a successful Save. **Resume Repair** freshly validates it; see below.
- **Cancel** in Review Support, Replace Reference or Replace End Face closes only that review and
  releases its read-only evidence. The exact live proposal, revision token,
  accumulated repairs, proposal Undo history and annotation intent remain. Choices
  not yet applied in the closed dialog are not kept. **Discard Proposed Edit** is
  the deliberate way to abandon the upstream edit and all its repairs, including
  its owned saved checkpoint. Accepted geometry/data need no rollback because they
  were never changed. Ordinary accepted-model review cancellation is unchanged.
- Base JSON/hash, scene owner, window/workspace/view layer, unit scale and backend
  selection bind the live proposal. Changed bindings invalidate it; successful
  save, load, history changes and add-on teardown retire live ownership. A saved
  checkpoint remains dormant and does not preserve native authority. An expired dialog cannot repair
  another/newer proposal.
  Sidebar drawing and polls only observe retained work; they never validate,
  retire it or write scene data. After a context switch a card may briefly remain
  until the lifecycle timer or an explicit action retires stale ownership.
  A workspace-only change can preserve strictly validated intent as described
  below. Actions still validate the original binding before use.
- Multiple reference repairs can accumulate, including two projections in the
  same sketch. Each Apply performs a fresh whole-Part replay. Partial progress
  requires the selected binding to be proven valid and every remaining failure
  to be a supported support/projection/end-face error, with blocked descendants only.
  An invalid repair or solver/kernel failure leaves the previous revision intact.
- When another projection in the same sketch prevents full sketch evaluation,
  a separate native validation-only probe enables just the selected projection.
  It preserves upstream geometry and the selected binding, but contains only
  that construction entity and its managed fixed/radius drivers. Dependent
  relations are not solved against other references’ stale drivers. The minimal
  probe sketch must succeed; all original constraints remain in the real candidate. The probe is never a publication/export source.
  Final constraint inconsistency fails closed. Support-only progress may use the fresh
  native resolved support plane when the next failure is a projection.
- Proposal repair Undo is an explicit transient control, not Blender Undo. Partial
  dialog execution returns CANCELLED after reporting “Repair kept in proposal”
  so it cannot add an empty canonical Undo step. That execution result means a
  repair was kept, not that the user cancelled. User Cancel also leaves existing
  progress intact but does not apply the current dialog choices. It never reads,
  replaces or reinstalls proposal ownership: a stale dialog cannot clear a newer
  revision, and an expired proposal cannot be revived. Lifecycle revocation still
  applies independently; closing a review does not extend a proposal's lifetime.
- This is not generic failed-document recovery. The accepted model must have a
  current successful native replay, the edited upstream feature must succeed, and
  a genuinely dependent attached/projected sketch or Up to Face end reference must fail. Kernel errors in the
  edited feature, malformed candidates and unrelated downstream failures are not
  silently retained as repairable proposals.

## Existing sketch Finish

The general sketch editor first requires its usual successful current Check and
complete supported geometry. Finish then performs the original exact whole-Part
replay. If the edited sketch succeeds but a downstream reference fails, the
complete candidate transfers into the unapplied proposal. This is **not** a
successful Finish or a partially accepted Part. Formula text, entity identities,
source data and dimension-label placement intent are retained together. Label
positions publish only with the eventual fully successful repair, inside the
same rollback boundary as canonical data and geometry.

The active editor and saved draft slot release only after the proposal has taken
ownership. A failed transfer retains the editable draft and its saved snapshot.
There is no simultaneous resumable draft/proposal copy. Another New/Edit/Resume
Sketch is blocked until full repair acceptance or Discard resolves the proposal.
Cancel in the repair dialog retains the proposed sketch edits and dimension-label
intent, but not unapplied choices made in that dialog. Reopen Review Support,
Replace Reference or Replace End Face to continue. **Discard Proposed Edit** abandons all proposed
sketch edits; it does not restore a second suspended draft.

Repair stays in the current Sketch workspace, where Feature History provides the
repair controls. A workspace change expires the live token. When only workspace
changed, the bounded recovery below preserves intent for explicit Resume, not
continued use of that token. Normal full-success Finish still returns to
Part. Unsolved or unfinished geometry, malformed/stale evidence, new sketches,
unrelated failures and downstream constraint/kernel failures retain their normal
failed-draft behavior; they do not become reference-repair proposals. Only a fully
successful Part replay can publish accumulated repairs; partial progress never
makes the proposed model current.

## Workspace-only recovery

If only the UI workspace changes within the same live scene/window/view layer,
the lifecycle timer, an explicit action or Blender Save can suspend the proposal
as ordinary v1 repair intent. Exact accepted JSON/hash, scene owner, units,
backend settings, tessellation tolerance and the runtime-captured accepted
annotation layout must still match. The existing strict codec validates the
original edit, every partial-repair/Undo transition and annotation intent before
writing. No publication binding is changed, no geometry is accepted and the old
token cannot revive when returning to the previous workspace. **Resume Repair**
still requires fresh native validation of the entire saved chain.

Recovery writes only an initially empty saved slot or the exact checkpoint owned
by this proposal. It never merges with or overwrites unrelated, malformed or
externally changed saved text. If that slot conflicts, codec validation fails or
the write fails, the stale token is retired and the latest proposal cannot be
retained in this single-slot design. An explicit **NOT saved** diagnostic reports
the loss; existing saved text and accepted data remain unchanged. A later Save
does not erase that warning or imply the lost proposal was included.

Successful workspace suspension first preserves intent in memory. Blender Save
is still required for disk persistence; a failed Save retains the dormant intent
and says it remains in memory only. There is no recovery across scene/document,
window/view-layer, units, backend, annotation or file-load/history changes, and
no second recovery slot or implicit history migration.

## Authority and verification

`staged_edit_store.py` owns detached proposal JSON and lifecycle below the
canonical coordinator. Its captured binding validator checks revocation and
workspace-only intent compatibility, never native replay or publication with a
changed binding.
`staged_edit.py` is the higher-level repair service; native validation and
publication remain in `document_state.py`. No import cycle or second publisher
is introduced.
Repair dialogs keep dynamic choices in hidden, non-saved RNA presentation fields
because Blender callback wrappers do not retain invoke-only Python attributes.
Apply revalidates the original guarded evidence and exact proposal token; editing
presentation fields cannot authorize geometry. The ordinary canonical publisher
and validators remain unchanged in their full-success requirement.

Targeted native-kernel and host tests cover both upstream failure fixtures,
source/target preservation, single-owner/stale binding rejection, explicit repair,
failed repair retention and UI routing. `tests/blender_staged_edit_repair_smoke.py`
uses real registered RNA callbacks and native geometry, exercises the actual solid
editor entry, both repair dialogs, failed complete replay, save/load retirement
accepted-only JSON save and STEP export, and background Undo/Redo with explicit
native history checkpoints. It checks that
accepted JSON, runtime and mesh datablocks remain unchanged before acceptance.
The 119 focused architecture/host/native-kernel tests and the existing native input-reselection
regression also pass.

Background native RNA dispatch is not real GUI interaction, popup legibility,
install qualification or interactive Undo/Redo evidence. No release/version change
is part of this work.

Proposal ownership is Python-only state, so each retain/retire transition explicitly
redraws open 3D View areas and regions. Cancelled edit operators need not produce
an RNA notifier; the proposal banner and disabled parameter controls must not wait
for reopening the sidebar. Redraw is presentation-only and cannot change model,
workspace or selection. Closed areas are skipped during teardown. Focused host
lifecycle tests and `tests/blender_staged_redraw_smoke.py` cover dispatch and native
region compatibility; actual immediate visual refresh is qualified separately.

`tests/blender_sketch_staged_edit_smoke.py` exercises the registered Edit Sketch,
actual editor owner/modal Finish dispatch and registered projection-repair RNA
callbacks with native sidecar results. Its circle replacement is produced through
real sketch commands, not document-service staging. It checks exact candidate and
formula preservation, unapplied annotation ownership, Cancel, full repair volume,
publication rollback, failed handoff recovery, competing-draft rejection,
unfinished/unsolved Finish rejection and unchanged full-success behavior.
This is source-loaded native evidence, not actual GUI or installer qualification.

Combined sketch-repair/automatic Undo replay is checked separately by
`tests/blender_history_sketch_integration_smoke.py`; see
[the bounded integration evidence](HISTORY_REBUILD.md#sketch-repair-integration-evidence).

The narrow-sidebar recovery card is placed immediately below the document name.
Review/Replace and Discard precede parameter diffs and error text. Excerpts are
bounded; **Full proposal details** opens the existing paginated diagnostic viewer
with every change, native error and recovery limitation intact. The .blend intent
checkpoint and accepted-only JSON/STEP notices remain visible. Only duplicate
retained-edit guidance is suppressed in the generic error box; unrelated action
errors are still shown. `tests/blender_staged_compact_draw_smoke.py` exercises both
panels at a simulated 240-pixel sidebar width with real native/RNA state and proves
draw leaves accepted data/evidence and proposal ownership unchanged. Actual popup
placement and default-width usability require GUI qualification separately.

Review Support reserves its orientation, reset, reset-warning and two-line
current-decision rows from the first draw. Strict disables irrelevant controls
without changing their values. Switching to plane preservation, Minimal twist,
World axes or explicit reset does not grow the dialog or require changing intent
to reach Apply. The full current decision and unchanged recovery limits are
available through the existing same-dialog, two-line paginated Help; no nested
modal is launched. Proposal/accepted-state, atomic replay, unapplied-state and Cancel
warnings remain visible. `blender_support_stable_draw_smoke.py` checks equal draw
row counts, all diagnostic pages, real RNA Next callbacks and read-only model/
proposal state across those policies. Actual default-window GUI remains separate
qualification.

## Multiple-reference verification

`tests/blender_multi_reference_repair_smoke.py` runs registered repair RNA with
native sidecar geometry for two dependent sketches and two references in one
sketch, including mutually equal references changing radius together. It checks
partial retention with unchanged accepted JSON/runtime/mesh,
revision-token rejection, explicit proposal repair Undo, complete atomic acceptance,
and full-model Undo/Redo with automatic native rebuild. Native checks also cover
two support repairs and a genuinely inconsistent final equal-radius relation.
Host tests reject remaining
solver/kernel/unknown failures and unrelated geometry/formula changes. Expected
reference validation errors keep their structured codes; unexpected runtime errors
are no longer mislabeled as repairable reference failures. No real GUI, installed
package or cross-platform qualification is claimed.

The coupled-reference native regression uses schema-3, the current authoring
format. Schema-1/2 redundant solves retain their existing stricter legacy evidence
restriction; this change does not normalize or discard solver diagnostic IDs.

Focused verification for this slice: 122 host/architecture/native-kernel tests;
63 native multiple-reference checks; the existing 150-check staged lifecycle
smoke and 55-check sketch/automatic-history integration smoke. Changed-module
Ruff and whitespace checks pass. The inherited full suite was not rerun.


## Save and explicitly resume repair intent

Blender **Save** stores a separate `repair_intent_json` scene property. Version 1
has exact fields `schema_version`, `kind` (`unapplied_repair_intent`), `base_json`,
`base_hash` (SHA-256 of those exact UTF-8 bytes), `owner_id`, `scale`, `feature_id`,
`states`, `annotation_before`, and `annotation_after`. `states` lists the original
rejected edit, each retained partial repair, and the latest candidate, in order.
Optional annotation before/after intent is paired and may alter only the edited
sketch's layout. No native receipts, failure reports, publication claims, owner
tokens, topology snapshots, meshes or backend authority are persisted.

The envelope is limited to 32 MiB of UTF-8 JSON and 32 proposal states. Each
complete document is limited to 2 MiB; annotation stores keep their 2 MiB limit.
Unknown fields/versions, duplicate keys, nonfinite or oversized numbers,
unsupported schemas, invalid Unicode and excess nesting are rejected, not
migrated or normalized. The initial proposal must change exactly its named
existing feature, retaining kind/order and the rest of the accepted model. Every
later transition must satisfy the same narrow one-reference repair scope used by
ordinary live repair. The bound permits at most 64 fresh native requests per
Resume (base, all states and any required selected-binding probes).

`save_pre` checkpoints without retiring the live owner. Only matching token and
checkpoint bytes at `save_post` suspend it. A failed Save retains the live owner
and in-memory checkpoint; this is not a claim that the file was written. Failed
checkpointing preserves the previous raw slot and live work, with a visible
warning that the file may not contain the latest repair. Correct the cause and
Save again before closing. An externally changed slot is never overwritten.

Loading a file merely restores dormant intent. **Resume Repair** requires the
exact accepted-base bytes/hash, owner ID, scene unit scale and relevant annotation
layout, with no competing sketch draft or live proposal. It captures the current
context/backend and freshly replays the accepted base and every retained state,
including all prior failure eligibility and selected-binding checks. Older backend
receipts/tokens are irrelevant. The sidebar button invokes a cancellable modal
runner: one guarded native job at a time, with a visible current phase, completed
check count and elapsed time. **Esc** or **Cancel Resume** stops pending work or
work between states. Cancellation/failure preserves the exact saved raw text;
there is no automatic retry. A process-wide input reservation blocks competing
Part edits, previews, replay/check/export work and sketch drafts even between
jobs, but is not native execution or publication authority. Only a running or
ready job owns the existing native execution lease until it is consumed or reaped.

Context/backend changes, Save, load, history or add-on disable retire the input
owner. The shared process-only supervisor also retires it if its window/editor
is lost, without ever accepting a result. Main-thread code alone touches Blender
RNA and validates result/schema data; native work uses the existing guarded
transport, never a parallel subprocess implementation. Bounded JSON parsing and
response validation still run on the main thread. The explicit Python/service
API and `EXEC_DEFAULT` keep synchronous behavior for scripts/tests; the sidebar
uses `INVOKE_DEFAULT`. Scripts that explicitly choose EXEC may still pause Blender
through the full history. Fresh retained failure diagnostics are capped at 16 MiB;
successful tessellations are not retained in proposal history.

Only complete validation creates one new live owner and new token, with freshly
reconstructed diagnostic/Undo history. Resume
never publishes geometry or adds a canonical Blender Undo step. After load a
separate, guarded automatic accepted-Part display rebuild may refresh the cache
when the backend is already ready; it never parses or resumes saved repair intent.
**Regenerate** remains the manual fallback (see HISTORY_REBUILD.md). After Resume, ordinary
repair-dialog **Cancel** keeps this exact new live proposal and reconstructed
history, including annotation intent and its saved checkpoint. **Cancel Resume**
stops validation before live ownership is installed and keeps dormant raw intent;
**Discard** on the saved-intent card removes dormant intent, while **Discard
Proposed Edit** abandons the resumed live proposal and its owned checkpoint.
Neither form of Cancel accepts geometry or abandons accumulated repairs.
Final complete repair
continues to use the existing atomic publication and ordinary Undo transaction.

Malformed, unsupported, changed-base/units or no-longer-repairable intent stays
byte-for-byte in the scene on failed Resume. A formerly failed state that now
succeeds is refused, not automatically accepted or removed from history. Such
intent can be saved again untouched or explicitly removed with **Discard**.
There is no automatic migration, merge, base rebinding or recovery from arbitrary
kernel/solver failures. Ordinary Blender history can restore dormant scene intent;
it cannot restore live ownership/evidence and must pass the same Resume guards.
Saved intent blocks new edits/drafts in its scene until Resume or Discard, while
JSON/STEP exports continue to use only accepted data. Explicit Discard requires
no parser and never changes the accepted Part.

`tests/unit/test_repair_intent.py` covers strict bounds, schemas, Unicode and
original/transition/annotation scope. `tests/blender_saved_repair_smoke.py` covers
native save hooks and actual failed Save, separate-process reopen, fresh replay,
partial-history Undo, stale backend/units, draft exclusion, corruption retention,
accepted-only exports and ordinary final Undo/Redo.
`tests/blender_modal_repair_resume_smoke.py` covers guarded multi-state/probe
execution, pending/between-state cancellation, stale ready responses, reservation
exclusion, lifecycle/context revocation, cleanup/setup/install failures and exact
proposal-local Undo. Background Blender dispatches EXEC, so its registered-RNA
trampoline explicitly calls the real Invoke method; it is not a GUI claim.
Headless checks do not qualify
real GUI legibility or installed-package behavior.

## Non-destructive review cancellation evidence

`tests/blender_repair_cancel_smoke.py` uses registered native RNA invoke/cancel
callbacks and fresh sidecar replay for both support and projection paths. It checks
ordinary accepted-model cancellation, partial Apply's `CANCELLED` result, Cancel
from the next review, exact proposal/token/history/annotation retention, stale
review rejection followed by Cancel, lifecycle-expired callbacks, fresh Resume
and explicit Discard of a resumed proposal and its checkpoint. Save lifecycle
hooks are exercised here; this focused check does not write/reopen a `.blend` file.
The existing sketch-Finish smoke checks that Cancel retains real transferred label
intent and explicit Discard abandons it. Host tests also ensure Cancel does not
inspect or mutate global proposal ownership under an old dialog's context.

This is a future-development usability change, not a requalification or version
change of the frozen 1.10 package. Native/background callback evidence is not real
GUI popup interaction, Esc event routing, visual legibility or installer evidence.


The saved-repair card places **Resume Repair** and **Discard** immediately below
its saved/not-applied state. One short sentence explains that Resume checks work
without applying it. **Repair details** opens the existing paginated viewer with
validation requirements, native-evidence limits, incompatibility handling,
Cancel-versus-Discard behavior and accepted-only export rules. Active validation
keeps its Cancel Resume control and phase visible. Real action errors, including
incompatible saved intent, remain visible with their full diagnostic viewer;
drawing never parses, normalizes or rewrites saved intent. The narrow draw tests
check ordering and unchanged state, not actual GUI legibility.


## Explicit Up to Face end-reference repair

A retained proposal may now include an `extrude_to_face` consumer. Only its
recognized missing/split/ambiguous, nonplanar, nonparallel or behind-direction
end-target failure is classified as `invalid_extrusion_end_face`. Unexpected
native errors, unsupported/invalid profiles and invalid direction/offset values
remain ordinary failures, not recovery permission.

Choose **Replace End Face** on the unapplied-edit card. The review identifies the
old solid and semantic face, shows the preserved direction and offset expression,
and offers an explicit **Earlier target solid** and **Replacement end face**.
Nothing is selected automatically. Choices come from a fresh proposed-graph
replay, not the accepted display. Only successful earlier solids outside the
consumer's descendant closure, with unique stable parallel planar faces ahead
in the saved direction and positive bounded offset travel, are offered. Identical
face IDs on different solids remain separately source-qualified. The chosen face
supplies an **infinite supporting plane**, not its finite boundary. Catalog reach
is informational; Apply still requires complete native replay.

Only `inputs.target` and `end_face` may change. Profile, direction, offset formula
and numeric types, feature identity and all unrelated intent remain unchanged.
The repaired extrusion itself must succeed before any partial progress is kept;
a support-plane record or sketch validation probe cannot substitute for it.
An explicit replacement may disconnect the repaired branch from the originally
edited source. The immutable initial proposal graph then bounds which newly
exposed downstream reference failures can join the repair chain. This graph is
eligibility only, never geometric evidence. Unrelated failures still reject the
attempt, and every accepted binding is proven again by current native replay.

The existing version-1 saved envelope retains the ordinary authored target/face
fields in each exact proposal state. Its bounds, original-edit and transition
checks remain in force; old sketch records are not migrated or reinterpreted.
Fresh Resume replays every state and proves each completed extrusion, preserving
partial repair order and Proposal Undo. Cancel keeps the chain; Discard abandons
it. No native tokens, failure records, face snapshots or geometry authority are
saved. No additional repair support for Fillet, Shell, mates, arbitrary kernel
errors, direct named-parameter envelope edits or changed feature graphs is claimed.

Native/source evidence and a prepared accepted model:
[MCAD-TNP-END-001](regressions/topology/end_face/MCAD-TNP-END-001.md).
Actual GUI and installed-package qualification remain separate.
