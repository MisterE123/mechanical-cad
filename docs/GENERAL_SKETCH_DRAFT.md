# General sketch draft transactions (development)

This pure authoring layer is implemented and tested. It is not yet connected to a
qualified Blender viewport tool. The released 0.3 rectangle tools remain separate.

## Intent, evidence and publication

`GeneralSketchDraft` captures exact base Part JSON, a target feature ID and a
monotonic live revision. Commands change detached local sketch intent. They never
write the scene's canonical Part document or invoke the solver. Candidate creation
preserves unrelated parameters, features, IDs, formulas and the active Part output.
Creating a new constrained sketch explicitly produces a Part-schema-2 candidate;
opening an existing sketch preserves its embedded version until a command requires
an explicit version migration.

The bounded current authoring domain is the global XY plane, points, straight
lines and circles, with horizontal, vertical, coincident, fixed, distance and
radius relations. The core can evaluate more workplanes; this editor must not
silently reinterpret an unsupported one. Shared endpoint IDs explicitly join
line segments. Equal coordinates alone do not create a persistent relation.
An already-identical relation is idempotent and keeps its original ID/value type.

A successful solve is revision-bound evidence, not saved intent. It contains
actual native-solved seeds. Releasing a constraint requires that exact current
solution and copies those coordinates into the explicit edit so the profile does
not jump back to creation seeds. Resume never restores trusted solve evidence.

## Local journal and identity

`general_sketch_commands.py` holds typed commands and the deterministic reducer.
`general_sketch_journal.py` holds bounded history and strict restore validation.
`general_sketch_draft.py` orchestrates candidates, pending edits and evidence.
`general_draft_store.py` owns an independent versioned UI snapshot codec.

The local journal retains at most 64 edits and 2 MiB, pruning only the oldest
entries into a checkpoint. IDs allocated by discarded/undone branches remain
reserved and are not reused. Restore replays retained commands, checks exact
before/after continuity, validates the accepted cursor state and rejects invented
IDs or malformed entries. Journal schema 2 also records an allocation watermark
at the retained checkpoint and exact allocation ranges for each command. Restore
replays allocation in order, including collisions with permanently reserved
original IDs. A deleted pre-checkpoint ID cannot be introduced again; legitimate
gaps from abandoned branches and retained Redo remain supported. Journal schema 1
is rejected explicitly rather than guessed or silently upgraded.

This is sketch-local Undo/Redo. It does not replace committed feature history,
Blender Undo or source Git.

## Driving-field lease

`begin_edit` captures constraint identity, kind, references and original scalar.
`update_edit` keeps raw text exactly, including invalid text and whitespace, while
advancing a separate input revision. A trial candidate may trim edited outer
whitespace for expression parsing; the raw pending buffer remains unchanged.
No accepted intent is changed until explicit successful acceptance.

`record_validated_solution` uses the shared strict solve-only response validator
and requires the exact candidate and current revision. For a sketch consumed by
downstream features, driver acceptance additionally requires a successful full
Part replay for that exact trial. A valid local solve cannot approve a broken
extrusion. Failed, missing or stale evidence retains the pending input for repair.

Whole-sketch Finish remains the owner adapter's responsibility: run a fresh full
replay and atomically publish only while scene/window, exact canonical base,
draft-slot revision, backend configuration and cancellation guards still match.
This pure layer does not implement those Blender ownership resources.

## Persistence and recovery

The independently versioned `general_sketch_ui_draft` snapshot contains exact
base JSON, accepted intent, local journal, reserved IDs and observed pending raw
input. It contains no native handles, process tokens, modal ownership, queued
accept intent or trusted solver results. Restore requires identical base bytes.
A stale or corrupt snapshot is retained for explicit recovery or Discard; it is
never silently merged, rebased or replaced.

Snapshots are bounded to 8 MiB, raw field input to 64 KiB, and allocation ledgers
to 8,192 IDs. Actual numeric/formula acceptance still obeys the stricter core
limits. Revision, input, allocation and journal counters are bounded to
`2**53 - 1`. Every increment reserves a valid successor before changing live
intent, history, raw text or evidence. Exhaustion is a recoverable unchanged-draft
error; genuinely unchanged commands and checked no-op driver acceptance still
work at the limit.

Open connected line chains may solve and persist without a profile;
unsupported regions and conflicting solves remain recoverable drafts. Presence
of a sketch or successful constraint solve never implies a manufactured solid.

## Verification

Pure tests cover commands, dependency deletion previews, no-reuse IDs, local
Undo/Redo, malformed journals, stale exact bases, raw invalid restoration and
strict current-evidence acceptance. Adversarial tests also cover pruned-history
ID reintroduction, allocation provenance, imported high-numbered IDs, branch gaps,
Redo, and atomic counter-limit failures. `test_general_sketch_draft_native.py` adds
real libslvs/OCCT circle release continuity, consumed formula edits, invalid-trial
recovery, and open chain → triangle → extrusion with stable line provenance.
These tests do not establish GUI keyboard, focus, lifecycle or accessibility.
