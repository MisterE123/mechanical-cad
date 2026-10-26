# Explicit Line axis lock

In the general sketch editor, choose Line and click its first point. Hold Shift
while placing the second point to constrain the line along the nearest sketch-local
horizontal (U) or vertical (V) axis. The live hint names the actual constraint that
will be added on click. Release Shift to return to a free Line. The axis is chosen
from the larger local displacement; exact diagonal ties choose Horizontal.

This is a real, lasting Horizontal/Vertical relation, not merely aligned seed
coordinates. It is created with its line in one local Undo step, checked by the
existing native sidecar and retained in the saved sketch. It does not fix either
endpoint or constrain length. Existing points are reused only if they lie on the
chosen axis (1e-9 mm comparison tolerance); an off-axis point is refused with
instructions to release Shift or move away. No existing point is relocated to
satisfy a pointer snap. Preview and click each resolve current geometry and point
identity; hover is never acceptance authority.

The modifier applies only to a capturing Line's second endpoint. Arc, Circle,
Rectangle, Shift selection and dimension text input retain their own routes.
Escape cancels only the unfinished proposal. Recovered ordinary pointer proposals
do not restore held keys or gesture capture: Continue resumes input, and Shift
must be held anew. A separately captured [Driving length](PENDING_LINE_LENGTH.md)
field retains its explicit H/V intent as versioned data, not held-key authority.

## Persistence and verification boundary

The optional AddLine axis intent uses a bounded `add_axis_line` journal record
with exactly one new line, its endpoint allocations and one H/V constraint. The
existing draft codec, identity allocator, owner replacement and native Check
remain authoritative. The new record is accepted in current journal versions 2
and 3, matching existing additive compound records such as Rectangle; legacy
free-Line `add` records are unchanged. Older installers do not understand the new
opcode and cannot resume such draft journals. Use this source version to Resume;
this change does not update or qualify any frozen installer.

Focused pure tests cover atomic creation, journal reload followed by Undo/Redo,
legacy free-Line reload, invalid phase and axis, and local projection/rejection.
Native solver tests establish actual H/V relations with three remaining DoF for
one otherwise-free line. Blender adapter and owner smoke checks cover fresh
click resolution and off-axis rejection, independent of the visible preview.
Bounded source-loaded GUI observations are recorded separately; they are not a
full suite, packaged-install, Windows, exhaustive recovery or crash qualification.

## Bounded Linux observations (2026-10-24)

A single source-loaded Blender 5.2.2 GUI session accepted Horizontal and Vertical
Shift-click lines, displayed three DoF per unconstrained-position axis line, and
removed/restored a line and its constraint together using Ctrl-Z / Ctrl-Shift-Z.
An off-axis endpoint click was refused without adding geometry. Releasing Shift
then reused that exact point in a free diagonal line, without another relation.
Escape discarded the next unfinished proposal while preserving all three lines;
Cancel closed the draft without committing the Part. This bounded session exited
cleanly, but does not resolve the separately observed intermittent allocator crash.

The two focused Blender smoke scripts exited zero with LINE_AXIS_SMOKE_OK and
LINE_AXIS_OWNER_SMOKE_OK, including direct owner off-axis rejection, native Check,
Undo/Redo and discard. The GUI used the pre-final-label-exclusion source; subsequent
Shift-on-dimension-label exclusion received source review/background smoke, not a
second GUI qualification.

## Selected-line relation visibility (source development)

Select a line to see a small `H Horizontal · authored` or `V Vertical · authored`
badge beside it. The letters and full names describe sketch-local U/V intent,
not screen orientation. Only selected lines with explicit H/V records get badges:
a merely aligned free line does not. Multiple records on one selected line are
combined visually, not rewritten or duplicated. This is a read-only cue, not a
constraint editor or a solver-success indicator. Current/retained/unverified
geometry status continues to come from the existing owner/evidence contract.

Badges use the existing detached overlay, have no click targets, and avoid drawn
dimension hit boxes and earlier badge boxes (or omit themselves when no tested
placement fits the complete label). Omitted relations remain in the inspector.
They reserve the existing safe area; this is not general label collision avoidance.
The journal and frozen installers are unchanged, including the older-installer
`add_axis_line` Resume limitation above.

Focused verification adds five pure badge-contract tests alongside 137 existing
geometry/arc tests (142 passed). The dedicated Blender 5.2.2 native BLF/GPU smoke
passes for drawing, dimension-only hit bounds, safe-area clipping and GPU/object
preservation. The real owner/sidecar smoke also passes with the new detached
relation map checked against an actual successful native solve. Synthetic renderer
currency checks are not solver evidence.

One bounded source-loaded Linux GUI session showed compact H and V badges on
selected, natively checked lines. Clicking an aligned free line removed the badges
and showed no incident relations; selecting a constrained line restored its badge.
This is not packaged-install, Windows, exhaustive input/recovery, or crash
qualification. The intermittent allocator crash remains unresolved.
