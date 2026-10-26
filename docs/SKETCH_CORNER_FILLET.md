# Sketch Corner Fillet

Select two straight lines that share one authored corner (Shift-click the second),
then choose **Sketch Corner Fillet** in the contextual sketch tools or operator
search. The sketch must have a current successful Check. This is distinct from
solid Fillet.

The dialog has a positive Radius in millimetres, a purple geometric preview,
Apply and Cancel. It shows the radius ceiling and keeps detailed limits collapsed.
The preview is not native validation. Apply authors one command and checks it
natively; Finish still requires the normal successful complete Part replay.
Cancel allocates nothing and does not upgrade the sketch. Changing selection,
viewport, backend, saved draft or canonical Part invalidates the dialog. Repeated
Apply cannot reuse the original acceptance. A preview is transient, not restored
as active input after suspension or reopening.

## Explicit design intent

The original corner point remains as a **dimensionable intersection witness**.
Both original line IDs and both outer point IDs remain. Each line's corner end
is replaced by a new tangent point; one new center and a real directed minor arc
join them. Existing Horizontal/Vertical and supported point dimensions/anchors
are retained, not deleted or reinterpreted as new point identities.

Five explicit ordinary relations are added: arc radius, two arc/line tangencies,
and two witness-point-on-line relations. Point-on-line means each infinite
supporting line, not the finite trimmed segment. The witness is not part of the
profile boundary. A compact, double-clickable radius label uses the ordinary
Dimension editor; the sidebar also exposes the existing dimension controls.

Each isolated new arc also retains explicit version-1 `fillet_intent`: original witness,
ordered supporting line IDs, ordered outer point IDs and original corner turn.
The arc's own start/end identify the tangent points. This is bounded intent,
not a guessed naming repair. Native solve and Blender's independent result
boundary require both tangent points strictly inside their respective
witness-to-outer segments and the original directed minor branch. Oversized
edits fail with an explanation; they are never clamped or accepted as a flipped
corner. This guard applies to consumed replay and fresh export too. Unconstrained
outer geometry may still move under the solver: constrain dimensions you intend
to hold fixed.

## Supported scope

- Exactly two ordinary, non-collinear lines sharing one exact point ID.
  Coincident coordinates alone are not connectivity.
- H/V relations on the selected lines are preserved. Other selected-line
  relations must be released explicitly first. Corner coincidence relations,
  projected points (including coincidence aliases) and third curves at the
  original corner are refused.
- Radius must leave both trimmed segments and both witness-to-tangent distances
  at least 0.000001 mm. Zero, nonfinite, excessive and degenerate radii are refused.
- Construction conversion, Reverse Arc, required-relation removal and edits
  that change protected endpoint identities are refused, except for the explicit
  adjacent-fillet compound operation below. An isolated arc can be deleted with
  its intent through the checked deletion flow. Deleting an arc with a declared
  neighbor is refused rather than leaving or silently repairing dangling intent.
- No general sketch mirror/copy operation is introduced. Whole-sketch copies
  retain the scoped IDs and intent. Solid transforms/mirrors are downstream and
  do not rewrite local sketch intent. Existing projection does not project arcs.

## Adjacent corners (unreleased source development)

See [ADR 0010](adr/0010-explicit-adjacent-sketch-fillets.md) for the persistence decision.

All four corners of a constrained rectangle can now be filleted successively,
with unequal radii and either selection order. Select the next two straight
segments that still share an original corner, then use the same dialog and
radius editor. Width/height dimensions remain on the original witness points.
The preview ceiling accounts for the already-trimmed neighboring segment; a
successful native Check is still required, and combined radii must leave a gap.

Version-1 intent remains byte-for-byte unchanged for isolated corners. When a
new fillet shares a line with an existing one, both carry version-2 intent:
`neighbors` is an ordered two-element array of explicit arc IDs or null, aligned
with `lines` and `outer`. Original outer witness IDs never become tangent IDs.
The existing peer's intent is upgraded atomically with the new construction.

For every non-null role, structural validation requires the named peer to be
version 2, name the same line exactly once, reciprocally name this arc, and swap
its corner/outer witness IDs. The finite line endpoints must be exactly those
two arcs' corresponding tangent points. Every supporting line has exactly its
declared fillet owners; every v2 tangent endpoint belongs to only its declared
line and arc. Missing peers, ambiguous ownership, role rewrites, malformed
metadata, reversed branches and dangling deletion are refused. Four-corner
cycles are valid explicit relationships, not dependency cycles to recurse into.

Independent core and add-on numeric validation retain each tangent inside its
original witness span, preserve the original turn/minor branch, and additionally
require the two shared-line tangents to remain ordered with at least 0.000001 mm
separation along that span. Testing only each tangent's interior bound would
incorrectly admit overlapping large radii; it is not sufficient. Consumed replay
and fresh export use the same checks. No constraints are silently removed.

The new strict journal-3 `adjacent_corner_fillet` opcode retains the source
schema, exact support-position seeds, allocated geometry/relations, and one or
two complete before/after peer-intent replacements. Replay recomputes every
record and validates versions, role identity and allocation order. Undo restores
the exact prior state, including version 1 where applicable; Redo retains IDs.
Old journal readers reject the new opcode; old model readers reject version 2.
Recovery and save/reopen use the same strict draft/model codecs and never restore
native authority. No linked-chain deletion or general identity repair is added.

## Persistence and compatibility

The atomic journal-3 `corner_fillet` operation records the source schema, exact
line IDs, radius, three resolved support-position seeds, and all allocated
point/arc/relation records. Replay recomputes the construction and validates the
complete record and allocation sequence. Undo restores the exact previous sketch;
Redo restores the same IDs. Resume restores raw intent only, never native authority.

The optional self-versioned arc field is absent from legacy serialization.
Unknown fields/versions are rejected. Older installations cannot open these new
filleted sketches or resume their new command opcode; no silent downgrade is
provided. Recovery retains the same strict draft codec; a preview is not recovery
input. Required fillet bounds are canonical Part data after Finish.

## Development evidence

Focused pure and native tests cover acute/obtuse and CW/CCW geometry, exact
radius/tangency/minor sweep, retained point/line/constraint identities, compound
journal restore/Undo/Redo, invalid input, mutation refusal, protected dependencies
and strict metadata corruption. A constrained 20×10 rounded rectangle extrudes
to the exact expected volume at radii 2 and 3. Radii 10, 12, 25 and 100 fail closed;
the radius-100 case previously produced a valid but wrong flipped profile and
is now explicitly rejected before publication.

Blender 5.2.2 source-loaded background checks exercise the registered operator's
owner transaction, corrected oversized input, Cancel, stale/repeated Apply,
native validation, Undo/Redo, and failed radius-100 trial preserving accepted
sketch, raw input and canonical Part. A second Blender process resumes the saved
`.blend` without solve authority, retains the exact intent, and checks it afresh.
Actual cloud-desktop GUI observation in source-loaded Blender 5.2.2 covered
Shift-selection, contextual invocation, purple radius-1 to radius-4 preview,
Cancel unchanged, reopen/Apply, double-click radius label edit to 3, radius-100
refusal retaining 3, Cancel Input, fresh Check, Finish, a 10 mm Part extrusion,
and a successful Geometry Check. Both a suspended accepted draft and the final
rounded solid were saved as disposable `.blend` evidence. GUI testing exposed
and fixed a missing palette routing entry and Blender props-dialog re-poll;
the latter admits only the unchanged owning gesture and does not mutate state
when another editor polls it.

These are not installed-ZIP or full historical-suite qualification. No Windows
qualification or release update is claimed; frozen Linux1.24 remains unchanged.

### Adjacent-corner verification status

Focused pure tests cover two and all four corners, asymmetric radii, both
selection orientations, strict core round-trips, checkpoint Resume/Undo/Redo,
peer metadata tampering, dangling-peer deletion refusal, and the numeric overlap
case where each tangent individually remains inside the original span. The
bounded standalone native run passed 11 tests (including prior one-corner cases):
two adjacent and all-four asymmetric corners in both selection orientations
produce valid exact solids and the analytic rounded-rectangle volume at 20×10,
24×12 and 18×9 mm. Combined oversized radii refuse the dependent extrusion
without mutating input. Source-loaded Blender owner checks also pass all-four
Cancel/Apply/repeated-Apply refusal and exact Undo/Redo, valid radius editing,
and overlapping radius refusal preserving raw text, accepted geometry and canonical
Part. An independent Blender process restores the saved four-corner draft without
native authority and checks it afresh.

Actual cloud-desktop mouse work accepted four successive corners (radii 2, 3, 1,
2) on a script-seeded constrained rectangle and saved the accepted draft. The
same exact saved journal was reopened after the palette applicability fix;
sidebar Resume, palette Check, double-click radius editing from 2 to 3, and an
oversized radius-9 trial were exercised through mouse/keyboard controls. Radius
9 was refused with explicit shared-line overlap guidance; raw text 9 remained,
and accepted geometry exactly matched the radius-3 snapshot. Cancel Input,
fresh Check and Finish succeeded; the separate finished `.blend` was saved.
The profile was fully defined and closed, with all four radius labels visible.

Before the polling fix, timestamped presses on the same radius label reached
Python 4.24 seconds apart. Afterward, the two presses reached it 157 milliseconds
apart and opened the existing editor. These are bounded observed event timings,
not an overall FPS or general latency benchmark. A watchdog captured the prior
full constraint-transaction serialization in palette event hit-testing; the
strict execution binding remains unchanged. Original stack/event logs, full
saved draft, accepted/refused JSON observations, screenshots and both `.blend`
fixtures remain in the local engineering evidence directory.

This is not a release, installed-package, Windows, or full historical-suite
claim.

## Restore Sharp Corner (unreleased source development)

Select one explicit fillet arc, run **Restore Sharp Corner**, review the affected
geometry and choose **Restore Sharp Corner** or Cancel. This restores the original
sharp corner using its retained witness identity, unlike generic Delete. It
removes that arc, its three private points and its five required relations in
one Undo command. Adjacent corners remain rounded; reciprocal peer metadata is
updated explicitly. Original corner dimensions remain on their original points.

Extra constraints or curves attached to removed points, unsupported supporting-
line relations, projected geometry and arc reference labels prevent removal
instead of being silently deleted or reinterpreted. A retained line's read-only
reference length recomputes normally. The removed radius label's placement stays
visibly unavailable for exact Undo/Resume restoration. Apply validates a detached
candidate and refuses if any retained point moves more than 0.0000001 mm from the
current Check. Constrain drifting free geometry first. Consumed sketches also
need a successful full replay before removal is accepted. Cancel or failed checks
leave the original fillet unchanged; Finish still validates the full Part. See [ADR 0011](adr/0011-explicit-sketch-fillet-removal.md) for the
strict journal, metadata and verification boundaries.


Focused source verification includes 126 pure tests, six standalone native
removal cases, Blender 5.2.2 owner and fresh-process reopen checks, and actual
GUI Resume/Check/select/review/Cancel/Apply/Undo/Redo/Finish. The GUI Finish rebuilt
the consumed extrusion with the restored corner and other fillets intact.
Installed-package, Windows and broad historical-suite qualification remain outside
this verification; no release files were changed.
