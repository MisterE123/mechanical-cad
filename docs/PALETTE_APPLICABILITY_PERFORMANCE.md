# Sketch relation palette applicability

Contextual relation visibility is a presentation hint, not a prepared constraint
transaction. Pointer-event palette bounds previously ran `prepare` for all nine
pair relations. Each preparation captured the full draft journal, exact saved
snapshot, canonical data and execution evidence, even for inapplicable actions.
The captured result was immediately discarded.

The UI now checks the same pure selection contract without capturing a
transaction. Original-owner/context, busy, unfinished-input and gesture checks
remain. Fix here/removal retain their current-solution prerequisite; authored
recovery requires absent current/retained evidence. Deeper evidence validation or
protected-removal rules can still reject a displayed action on invocation. Hints
are booleans only, never disclosures, native authority or execution capabilities.
The registered operator still prepares a fresh exact-bound intent; Apply still
prepares again and compares the full binding before executing. No prepared
intent, layout or geometry cache was introduced. Native gizmos retain their
fixed action identities; no click is remapped through a newly computed list.

## Bounded measurement, 2026-10-25

On the saved four-corner GUI draft (33,977-byte snapshot SHA-256
`159d30b00842ec9fbfbb11e2ad1331c82374bac7014f99734d695af54060ae64`),
the nine pair-relation probes took a median 0.903128 seconds before and
0.011057 seconds after over seven repetitions in the pinned Linux development
Python. All nine eligibility results matched. Before range: 0.885399–0.935979 s;
after range: 0.010623–0.019001 s. The selected authored lines were l_d8 and l_d5.

`tests/profile_constraint_palette.py SNAPSHOT_JSON CANONICAL_JSON` reproduces this
bounded measurement with real restored draft/codec/preparation and runtime host
stand-ins. Restored drafts intentionally have no native solution authority.
It does not time Blender dispatch, drawing, native evidence validation, or the
whole interaction. Watchdog traces establish this as an observed hot path, not
proof that it explains all reported tens-of-seconds delays. The exact raw timing
record and saved fixture are retained with the local adjacent-fillet GUI evidence.

79 focused pure tests passed, including non-mutating selection equivalence,
fresh selection/context checks, no preparation on a UI probe, and the actual
prepare/Apply binding rejecting changed selection, revision, backend, context,
and source, as well as rejecting a boolean hint as an intent. These tests use
native-free hosts. Native Blender smoke, interactive latency, full-suite and
installed-archive qualification remain separate; none is claimed here.

An expanded pure run also passed all 46 general-authoring tests. The existing
`test_arc_ui_availability.py` suite reported 31 failures and 32 passes both on
unchanged adjacent base 3d5d338 and on this patch, with identical failing test IDs.
Those inherited failures are not silently excluded or represented as passing.

## Same-fixture actual GUI observation

Source-loaded Blender 5.2.2 reopened the exact preserved four-corner journal
(33,977-character saved-draft envelope). Sidebar Resume followed by palette
Check succeeded. Two actual presses on the existing radius annotation reached
Python 157 ms apart and opened the radius editor; before the fix, the same
fixture's two presses reached Python 4.24 s apart and were treated separately.
These are bounded event-processing observations, not an overall FPS or general
latency benchmark. The prior watchdog log shows full constraint-transaction
capture during palette hit-testing.

Actual keyboard radius change 2 → 3 was accepted. A radius-9 trial was refused
for adjacent overlap while retaining raw 9 and exactly preserving accepted
geometry. Explicit Cancel Input, fresh Check and Finish succeeded; the separate
finished fixture was saved. Full action preparation and Apply guards were not
changed or bypassed. Both original timing/stack logs and patched event evidence
are retained alongside the original saved fixture.
