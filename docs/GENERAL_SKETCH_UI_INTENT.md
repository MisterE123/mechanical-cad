# General sketch UI intent (development)

This pure, native-free authoring wrapper is implemented and unit-tested. It is
connected to explicit shared codec dispatch and the shared owner lifecycle. It is
not yet registered as a Blender viewport editor or qualified through an interactive
viewport workflow. The audited command draft, journal, version-1 codec and released
rectangle workflow remain unchanged.

## Two independent kinds of intent

`general_authoring.GeneralSketchAuthoringState` owns a `GeneralSketchDraft` plus a
small, independently versioned UI value. Construction validates and snapshots the
supplied draft, retaining its checkpoint exactly while dropping transient solver
evidence. The caller's original draft and supplied UI dictionaries are not aliases.
The wrapper's explicit `command_draft` property is its live, owned command API;
adapters use that existing audited API for commands, Undo/Redo, pending raw fields
and validated solver responses. UI properties and payloads return detached copies.

`document_json`, `feature_id`, `is_edit`, `base_hash`, `require_current`, `candidate`
and the command `revision` delegate to the owned draft for later shared-owner
integration. The separate `ui_revision` advances only for an actual UI change.
There is no new command reducer or modeling authority.

UI schema 1 has exactly these fields:

- `schema_version`: integer 1
- `revision`: nonnegative integer up to `2**53 - 1`
- `tool`: `Select`, `Line`, `Circle` or `Dimension`
- `selection`: up to 32 distinct `{kind, id}` stable-identity bindings; kinds are
  `point`, `line`, `circle` or `constraint`
- `proposal`: null, or one unfinished line/circle observation
- `annotations`: up to 512 placements keyed by stable constraint ID

A line proposal has `kind: line`, an `anchor`, and a nullable `endpoint` XY
coordinate. A circle proposal has `kind: circle`, an `anchor`, and a nullable
observed `radius`. An anchor is exactly `{kind: existing, point_id}` or
`{kind: new, position: [u, v]}`. Existing IDs never become coordinate seeds on
failure. New coordinates do not allocate point IDs or imply coincidence.

Each annotation is exactly `{kind, refs, display, offset}`. `kind` and `display`
are `distance` or `radius`, and must agree. The ordered refs must exactly match an
observed relation of that stable ID; placement does not rewrite reference order.
Offsets are sketch-local XY coordinates in millimetres. A changed scalar/formula
does not change the annotation's identity. This slice supports radius display and
editing only. Diameter presentation/editing is deferred; raw formulas are never
halved or otherwise converted. There is no second circle driver.

## Explicit pure authoring operations

- `select_tool(tool)` changes only palette intent. Changing tool does not silently
  cancel a proposal; its separate Continue/Cancel choice remains available.
- `select([(kind, id), ...])` replaces selection with currently existing exact
  bindings. Persisted selections that later disappear remain visible as conflicts.
- `begin_line(PointRef(id) | PointSeed(u, v), endpoint=None)` and
  `begin_circle(anchor, radius=None)` begin one proposal and select the matching
  tool. They reject an existing unfinished proposal or pending driver edit.
- `update_line(endpoint)` and `update_circle(radius)` retain the last observation.
  They require the anchor to remain available, and reject a pending driver edit.
- `resume_proposal()` returns detached Continue intent after rechecking the
  current anchor. It changes no revision or geometry, captures no input, invokes
  no solve and replays no click. Repeated calls are equally noncapturing.
- `cancel_proposal()` changes only the proposal to null. All earlier accepted
  segments, other geometry, journal entries and pending driver text remain intact.
- `place_annotation(constraint_id, offset)` explicitly binds a placement to the
  existing distance/radius relation; `move_annotation` requires the exact binding
  to remain available; `remove_annotation` removes only presentation intent.

All coordinates and offsets are finite numbers within ±1,000,000 mm. Booleans
are not numbers. An observed radius is finite and between 0 and 1,000,000 mm;
zero is a legitimate unfinished pointer observation. Likewise an unfinished line
may observe its own start coordinate. Neither case is an accepted geometric
command: actual commands retain the audited minimum line length/circle radius
of 0.000001 mm. This module does not commit proposals. The separate pure `general_proposals`
adapter stages one audited command and proposal removal on a detached candidate;
its exact-source replacement guard is described below. Native owner/context and
canonical publication remain separate integration responsibilities.

All updates validate a detached replacement and reserve a bounded UI revision
before replacing live UI intent. Invalid coordinates, identity, counts, versions
or exhausted counters leave both UI and command state unchanged. Checked no-op
updates, status inspection and Continue still work at the revision limit. UI-only
operations never advance the command revision, change its journal or candidate
hash, invalidate its solver evidence, solve, or change manufacturing meaning.

## Atomic proposal preparation

`general_proposals.prepare_proposal(state, endpoint=None)` snapshots and restores
a detached wrapper, validates its current stable-ID anchor, executes exactly one
`AddLine` or `AddCircle`, clears only that proposal and validates the combined
persistable result. It returns a `ProposedCommand` with exact source/candidate
snapshots and allocated entity IDs. Nothing is published or solved.

A line may receive an explicit `PointRef` or `PointSeed` endpoint from the click
adapter. Without one, the last observed coordinates create a new point. No
proximity matching, implicit coincidence, fixed corner, axis constraint or next
chained gesture is inferred. A circle uses its retained observed radius. Zero or
missing geometry observations remain recoverable proposals and cannot commit.

`receipt.replacement(current)` requires the current whole wrapper to match the
captured source before restoring the detached candidate. The native owner must
also check the original scene/base/session and swap its wrapper only after that
guard succeeds. Command/UI counter exhaustion, missing anchors, invalid geometry
or persistence failure leaves original intent and its current solver evidence
unchanged. A successful candidate carries no solver authority; its explicit
command must receive fresh validation. This helper does not authorize Finish.

## Missing identity and bounded provenance

`status` is a fresh, deterministic `AuthoringStatus` containing separate proposal,
selection and sorted annotation `BindingStatus` values. Each has a scope, stable
identifier (null for a new-coordinate anchor), and `available`, `missing`,
`changed` or `unverified` state. `conflicts` contains the unavailable bindings.
Availability describes binding identity only, never valid geometry, DoF, solver
success or manufacturing readiness.

Existing-point proposals are checked against the current accepted sketch on every
Continue/update and status read. Deletion, Undo of point creation, or an abandoned
branch preserves the exact binding as `missing`. Undo/Redo can restore the original
ID; a different point at the same position cannot. There is no nearest-point
lookup, fallback coordinate, replacement ID or implicit command.

For annotation validation, the unchanged original sketch, retained journal anchor,
retained before/after records and accepted sketch establish observed kind/refs.
An annotation is `missing` when its observed relation is absent, and `changed`
when the same ID currently has different kind/refs. Exact Undo can make it
available again. A real ID with a fabricated signature contradicted by its
retained records is rejected. Unknown/unreserved IDs, wrong entity kinds and
invented references are rejected rather than displayed as ordinary stale intent.

The journal is bounded and can drop an old branch or prune its oldest records.
Its permanent reservation ledger can establish a generated identity's entity kind
from its typed allocation prefix, but cannot reconstruct a removed relation's
historic kind/refs. If no record of that constraint remains, its well-formed
placement and reserved references are retained as `unverified`; they cannot be
moved or used as an available annotation. The user can remove the placement.
This is quarantine of unprovable presentation intent, not proof that its signature
was ever authentic. Arbitrary changes to an unobserved tombstone's signature cannot
be distinguished from genuine old UI intent in this bounded format. No invented
history or silently rebuilt driver fills that gap. Original imported IDs retain
kind provenance from the exact base even when absent from retained history.

The mutable command draft remains the audited API boundary. Commands do not
silently mutate UI selection, placements or proposals; status reflects their
consequences. A future adapter must display these unavailable states and offer
explicit repair/cancel instead of interpreting them as actionable geometry.

## Explicit envelope version 2

`general_authoring_store` owns a new envelope with exactly `schema_version: 2`,
`kind: general_sketch_ui_draft`, `base_sha256`, the unchanged nested `draft`
checkpoint, and the separate `ui` schema-1 value. Its total serialized input/output
budget is 8 MiB, including UTF-8 bytes for both payloads. Existing document, raw
field, journal and identity budgets remain those of the audited command codec.

Unknown envelope/UI versions and fields, duplicate keys, nonfinite numbers,
malformed Unicode (including escaped lone surrogates), excessive nesting and byte
limits fail closed as public `SnapshotError`. Failed snapshot text must be retained
by the caller for explicit recovery/Discard. Restore requires byte-identical base
JSON, including whitespace. Restored raw invalid text, source scalar types,
formulas, IDs, accepted candidate and retained local journal remain exact.

The version-1 codec remains unchanged and rejects v2, while this v2 codec rejects
v1. Only after an editor is explicitly selected may
`GeneralSketchAuthoringState.from_v1_draft(v1.restore(...))` create empty UI defaults:
Select tool, UI revision zero, no selection, proposal or annotation placement. It
does not alter the command checkpoint or solve. A subsequent explicitly chosen
v2 encoder writes the new envelope. Shared dispatch selects the named codec by
exact kind/version; it does not migrate or reinterpret either payload.

No snapshot or UI value contains solver evidence, native handles, process tokens,
mouse grab/capture, annotation-drag capture, queued Enter/accept intent or input
lease. Pending driver raw text stays solely in the nested audited command draft.
Reopening restores a noncapturing Continue/Cancel proposal and observed placement,
not a running gesture or text-field focus.

## Verification and remaining integration

`tests/unit/test_general_authoring.py` and
`tests/unit/test_general_authoring_store.py` cover explicit v1 defaults, exact
nested checkpoint/base/raw input round trips, line/circle observations, annotation
radius-only identity, delete/Undo/Redo binding recovery, pruning/branch quarantine,
changed relation signatures, no replay/capture, immutable caller boundaries,
unchanged hashes/journals/evidence during layout edits, strict adversarial JSON,
combined byte limits and preflight counter/count failures. Native-free import is
checked in a fresh process. Synthetic pure-state fixtures do not claim a native
solve or viewport interaction.

The proposal helper has 22 pure tests plus two real-solver evidence-retention
cases in `test_general_proposals_native.py`. Shared dispatch has 57 unit tests,
and `tests/blender_general_authoring_owner_smoke.py` exercises 161 native lifecycle
checks plus 37 separate-process reopen checks. Exact base bytes, invalid raw text,
UI proposals, annotations and report labels survive the tested interruptions.
Actual picking, event routing, compact field focus and full async publication
remain separate integration gates. These checks do not qualify the full general
sketch editor.
