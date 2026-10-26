# ADR 0011: explicit sketch-fillet removal

Status: unreleased source implementation; focused pure and standalone native
geometry verified. Blender/GUI and installed-package checks pending.

## Decision

Restore Sharp Corner (internally Remove Sketch Fillet) is distinct from generic Delete. It operates only on a
selected arc carrying valid version-1 or version-2 fillet intent. Both supporting
line IDs retain their original orientation and outer endpoints: only the named
tangent endpoint returns to the existing original corner witness. No point
identity is inferred from coordinates, and the witness is never deleted.

The command removes the selected arc, its three private center/tangent points,
and its five unique required semantic relation roles (radius, two tangencies,
two witness-on-line relations). Current fillet metadata owns these unique roles,
not historical allocation IDs; the journal retains each complete current record.
All extra relations referencing removed entities, third curves using private
points, other fillet witness attachments, projected geometry, and changed-line
relations other than H/V or declared peer-required roles refuse without mutation.
Original point dimensions and all unrelated records remain unchanged.

Exact reciprocal peer roles are set to null in the same command. A peer stays
version 2 even if both roles become null: there is no guessed historical-version
rollback. Existing canonical validators apply before and after the edit. Generic
Delete keeps its previous separate behavior and does not restore corners.

## Transaction and metadata

The strict journal-3 `remove_corner_fillet` opcode stores the complete removed
records, complete before/after line records, complete before/after peer intents,
arc ID and exact source schema. Bounded JSON preflight rejects non-JSON values,
then explicit version/intent validation and a recursive exact-type/shape check
precede exact comparison against a recomputed record. No allocation occurs.
Undo restores the complete previous sketch; Redo restores the same sharp corner.
Unknown opcodes still fail closed in older readers. No new canonical intent
version or general model-schema migration is needed.

The review dialog is bound to the owner, original selected arc, draft snapshot,
saved slot, viewport and backend. Current successful Check is required, including
at Apply. Cancel allocates or changes nothing, and acceptance is one-use. Apply
builds a detached candidate: no original sketch, history or layout changes until
its fresh guarded solve preserves every retained point against the original
successful Check within 1e-7 mm. Both witness and unrelated points are checked.
A drifting free case is refused with a request to constrain placement first,
without rewriting seeds/expressions or adding hidden fixed constraints.

For an already-consumed sketch, a bounded full canonical replay also has to
succeed and preserve these positions before acceptance. Every result binds the
exact candidate, parameters, backend and owner; the normal guarded solve/replay
evidence chain is retained. Cancel/failure/stale results retire the detached
attempt with the original draft intact. Pending attempts never enter recovery.
Successful acceptance appends one command. Later Finish still requires fresh
full replay. This is placement preservation for this removal, not a permanent
freeze against future intentional edits.

A required radius annotation is retained with explicit, versioned UI-only
retirement metadata rather than presented as an accidental missing binding. Its
exact placement and radius/diameter display recover on Undo and after save/Resume.
Redo does not silently discard it. See the annotation-layout retirement contract. A user-added reference annotation on the removed arc refuses
until explicitly removed. Reference measurements on retained lines remain bound
to those lines and recompute their changed length. The bounded annotation binding extension is stored in draft UI2 and scene layout
version2; the command journal and canonical geometry schema are unchanged. Normal recovery saves raw intent and never revives solve authority.

## Observed verification and remaining boundaries

Focused pure tests cover isolated acute/obtuse/CW/CCW corners, four-corner cycles,
retained dimensions, exact counters and records, Resume/Undo/Redo, re-fillet,
strict nested mutations and unsupported attachments. Pure owner-port tests cover
Apply/Cancel/repeated acceptance, stale target/selection/slot/backend/Check/viewport,
and annotation retirement/restoration. Mocked owner ports are not native evidence.

Six standalone native cases cover both selection orientations with one or all
four corners removed. Remaining unequal-radius fillets preserve valid exact
profiles and analytic extrusion volumes at 20×10 and 24×12 mm, with untouched
canonical input. A free H/V corner preserves all retained coordinates through
fresh serialization/rebuild; an unrestricted free corner demonstrably drifts
and is refused by the same placement guard.

The pre-existing broad owner-authority inventory currently has two stale
allowlists (nine prior sink entries and two prior read wrappers absent). The new
removal sink/read entries are added without weakening those assertions, and a
scoped removal authority-inventory test passes. This historical inventory is not
reported as a green aggregate check. The focused final pure run is 126 passed;
17 native cases were excluded there. The separate removal-only standalone native
run is six passed. Touched-file Ruff passes.

Restore Sharp Corner availability is deliberately a fresh, non-authoritative
selection/context/busy hint. Palette polling does not request solve evidence,
serialize the journal, capture a gesture, or clone a candidate. The props-dialog
redraw uses only the invocation's read-only summary. Invoke and Apply retain full
validation and exact one-use transaction checks; an enabled hint is not approval.
A pure hot-path regression forbids those expensive calls across repeated ordinary
and live-dialog polling/redraw. This is not a general UI latency benchmark.


Source-loaded Blender 5.2.2 owner and second-process reopen harnesses passed.
The owner harness checks native free-placement refusal/acceptance, consumed
replay failure without source mutation, successful removal, cancellation,
Undo/Redo and retired annotation recovery. Zero-length extrusion is the deliberate
downstream failure fixture; negative extrusion is valid and is not used as a
failure assumption. A saved suspended draft resumes without solve authority and
checks afresh. Native OCP/slvs modules remain outside Blender.

Actual cloud-desktop GUI input separately verified Resume, Check, selecting the
remaining radius-3 arc, the Restore Sharp Corner review, Cancel unchanged, fresh
review/Apply, local Undo and Redo, and Finish rebuilding the consumed extrusion.
Read-only snapshots confirmed exact sketch/annotation equality after Cancel and
Undo, and exact candidate equality after Redo. The selected corner visibly became
sharp while the remaining two fillets stayed rounded. The unavailable historical
radius binding stayed visibly listed. The final current Part and original
suspended fixture were saved separately before clean Blender exit. Scripted
fixture setup is not represented as interactive authoring. These checks are not
installed-ZIP, Windows, release or full historical-suite qualification.
