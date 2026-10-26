# Explicit authored-position relation recovery

Status: pure command/draft implementation after immutable release 0.4 (`4b53129`).
This contract does not expose a production control, change canonical publication,
or establish native Blender GUI acceptance. The planned owner and UI gates remain
in [NEXT_SKETCH_CONSTRAINTS.md](NEXT_SKETCH_CONSTRAINTS.md).

## Two distinct actions

`DeleteBatch(preview)` keeps its released contract. If its exact announced cascade
contains a constraint, it requires successful, validated **current** solve evidence
and records all current solved point coordinates and circle radii as release seeds.
An old successful result, restored snapshot, failed Check, or retained outline is
insufficient. Geometry-only deletion without a constraint retains its existing
behavior. This implementation does not weaken or redirect any of these paths.

`RecoverRemoveRelation(preview)` is a separately named, frozen typed command,
accepted by `GeneralSketchDraft.execute` only when no successful current solution
exists. Its intended control is **Remove using authored positions**. An adapter
must disclose the exact selected relation and that there is no current solved
placement; authored seeds will be retained, and the result needs another Check.
It must not silently substitute this command after a failed `DeleteBatch`.

Absence of current evidence is the gate; a failed diagnostic report is not needed
and does not authorize choosing a relation for the user. A never-checked or
restored inconsistent source can therefore recover even with no retained Undo.
Removing a relation does not guarantee the remaining sketch will solve.

## Admission and atomic result

Recovery requires all of the following:

1. No pending dimension input, including invalid raw text or a verified trial.
2. No current successful solve. If one exists, reject without losing that
   evidence; ordinary validated release is the applicable action.
3. A typed `DeletePreview` with an integer revision exactly equal to the current
   draft revision, exactly one explicit constraint target, exactly that constraint
   in its removal set, and empty point/line/circle removal sets. Targets use typed
   tuples; absent targets, multiple targets, geometry targets, stale revisions,
   altered cascades, and forged previews are rejected.
4. The preview must equal a freshly derived preview against current accepted
   intent. No inferred cascade, entity merge, target replacement, or automatic
   selection of a diagnostic candidate is permitted.
5. The normal candidate validation, revision counter, journal sequence, and
   bounded history checks must all succeed before any accepted state changes.

Preparation derives complete seed records directly from current authored
`points` (`id`, `u`, `v`) and `circles` (`id`, `radius`). It accepts no external
release seeds. Coordinates and radii preserve their exact numeric types, signed
zero, values, and record order. No solve, evaluation, rounding, normalization,
previous journal seed, last-good display, or old `_Solution` coordinates are used.
“Current authored” means the accepted sketch immediately before this command,
including any explicit seed changes already accepted earlier in local history.

The result removes only the named constraint. Every geometry record, surviving
relation ID, reference, fixed target, and exact dimension expression is retained.
No identity is allocated or reused. The draft revision advances once, and one
detached journal entry captures the before/after transition. Returned payloads
cannot mutate the retained entry. All evidence is cleared; no DoF, profile,
Finish/export permission, or canonical document modification is implied.

Local Undo restores the exact prior inconsistent authored intent; Redo restores
the exact recovered intent. Both revoke solve evidence. Snapshot/reopen retains
that history and its stable identities, with no native authority restored.
Allocation exhaustion alone does not prevent removal because it allocates no IDs;
revision and history/document capacity failures leave the whole draft unchanged.

## Why the saved schema is unchanged

The existing journal-v2 `delete` record already has this complete meaning:

- `targets`: the explicitly selected stable identities;
- `removed`: the exact deterministic removal sets;
- `seeds`: complete explicit point/radius intent applied before the removal.

Its replay reducer has always treated stored seeds as ordinary authored intent,
never as a saved certificate of a successful solve or an instruction to solve.
The new action records that same operation with seed values equal to the current
authored values. Its seed transition is therefore an exact identity operation,
followed by one relation removal. No field gains a new interpretation, no operation
is added to the reducer, and no restored entry grants current-solve authority.

The live command type records which admission/seed policy the caller requested;
the persisted record records the complete resulting intent transition. There is
no historical claim that a saved `delete` was validated release rather than
recovery. If future UI requires persisted action-provenance labels, that is a new
requirement needing explicit versioning; it must not be inferred from equal seeds.

Consequently the general snapshot remains kind `general_sketch_ui_draft`, envelope
version 1, journal version 2, with unchanged keys, codec, reducer, and allocation
replay. Embedded sketch versions 1 and 2 are preserved, including absence of a
`circles` field in version 1. The old reader can deterministically restore the new
record as intent using its existing contract. Released operations serialize to the
same exact bytes; no release archive, runtime version, Part schema, or model hash
path is changed.

## Verification and integration boundaries

Unit tests cover exact authored numeric seeds versus far-away stale solved seeds,
circle radii and raw expressions, no geometry deletion, immutable command/preview
and detached journal copies, snapshot roundtrip, Undo/Redo, stale or malformed
previews, pending input, current-solve rejection, injected seed rejection, resource
failure atomicity, exhausted allocation counters, and embedded schema-1 retention.
Four golden SHA-256 snapshot checks were captured against the unchanged released
path before these edits: current solve, validated release, Undo, and Redo. The
released implementation files were identical at `4b53129` and `925f32f`.
The unchanged `4b53129` codec/reducer was also loaded separately and verified to
read a newly generated recovery snapshot byte-exactly and retain Undo/Redo.

Real libslvs tests cover conflicting Horizontal, Vertical, and Fixed additions,
explicit recovery after failed Check, and restored inconsistent sources with no
local Undo. They also retain the current-solved release after a far-origin driver
edit, subsequent Fix, Undo/Redo, and reopen. Authored seed copies are exact;
independently repeated native solves are compared with absolute tolerance `1e-8`
mm, rather than pretending floating-point native replay is byte-identical.

Exact duplicate relation additions remain pure no-ops, preserving the existing
ID, revision, ledger, snapshot bytes, and current evidence, including reversed
symmetric references. The pre-existing owner no-op gap was repaired separately in
`3bb0cbe`: `GeneralSession.execute` retains state/evidence and does not start Check
after an unchanged action. The pure recovery change itself does not edit the owner, UI, registration,
diagnostics, selection, or publication layers. Their later integration and
qualification are recorded separately in [constraint actions](CONSTRAINT_ACTIONS.md)
and [development verification](CONSTRAINT_VERIFICATION.md). Failed sketches remain
recoverable drafts, never published geometry.
