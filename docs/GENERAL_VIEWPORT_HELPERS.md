# General sketch viewport primitives

These pure helpers are development code. They are not registered viewport tools
and do not establish an installed GUI workflow. Owner lifetime, input routing,
async validation and canonical Finish remain separate integration gates.

## Geometry and selection proposals

`general_view_geometry.build_geometry` requires an explicit `source` choice:
`authored` seeds or `solved` geometry with the complete current solve request and
response. Solved input is revalidated at the strict native-free boundary. The
owner must still establish that the request belongs to its current revision.
There is no silent fallback from failed/missing evidence to authored seeds.

The result contains immutable stable-ID maps of points, lines, analytic circles
and driving distance/radius relations. Raw formula/literal values remain exact.
`Workplane.from_saved` normalizes a temporary WXYZ basis without rewriting saved
plane data. Its local/world mapping uses millimetres; `intersect_ray` rejects
parallel or backward rays instead of inventing a camera-plane location.

`pick_geometry` consumes an explicit world-mm-to-screen-pixel projection callback,
a pixel threshold and optional entity-kind selection. It returns candidate
identities, distances and unique/ambiguous/miss/incomplete state. Equal-distance
candidates are not resolved by enumeration, names or hidden point priority.
Picking proposes a visible choice; it never adds coincidence or binds topology.

Circle picks use bounded projected sampling (up to 2,048 segments per circle and
65,536 projection calls overall). Tested chord deviation is diagnostic evidence,
not a mathematical error guarantee for an arbitrary projection callback. Invisible
spans or exhausted sampling resources prevent a unique accepted proposal. Native
interaction latency has not yet been qualified at these caps.

`annotation_geometry` checks exact constraint kind/refs and creates presentation
anchors/leaders from a millimetre offset. It supports distance and radius only.
A zero radius offset chooses +U for the leader direction, not as a new persistent
reference. No formatting, rounding or diameter conversion changes source values.

## Inline raw text

`dimension_text_buffer.TextBuffer` provides Unicode-scalar caret/selection,
explicit insertion/deletion/navigation, selected-text access, escaped display
projection and local text Undo/Redo. It has no clipboard, Blender or evaluator
access. The caller reads/writes the Blender clipboard only after explicit user
copy/cut/paste input.

Raw strings are bounded by the existing 64 KiB UTF-8 draft budget; valid invalid
formulas stay exact. The evaluator's smaller formula limit is separate. Unknown
Unicode scalars and oversized construction reject. A rejected source must remain
available in its owning draft/recovery record. At most 128 combined history
records retain up to 8 MiB of raw UTF-8 payload plus bounded Python overhead.
Counter exhaustion and allocation failure occur before live buffer mutation.

Text Undo, accepted sketch-command Undo and committed Blender Undo are distinct.
This helper does not supply IME/composition, grapheme navigation, bidi shaping,
screen-reader or native-text-services parity. Production interaction needs a
stable ordinary native-panel fallback as well as tested inline event ownership.

## Verification

- `tests/unit/test_general_view_geometry.py`: 60 tests, including arbitrary
  planes, stable-ID reordering, exact evidence selection, ties, invisible spans,
  resource exhaustion and annotation bindings.
- `tests/unit/test_dimension_text_buffer.py`: 54 tests with 19,484 subtests,
  including randomized editing, Unicode retention, resource/overflow limits and
  injected allocation failures.

The assertions qualify these pure contracts only. They do not replace native
mouse/keyboard, camera navigation, accessibility or save/reopen workflow tests.

## Native drawing and transient input routing

`general_sketch_overlay` consumes detached geometry/UI observations and a caller's
world-mm projection. It draws bounded line/circle/point and annotation primitives
with an explicit current-solved fingerprint guard. It preserves exact input values
in metadata while presenting concise measured labels. Dimension hit bounds are the
actual clamped pixel boxes returned by the draw call, not guessed text extents.
Safe-area clamping reserves the owner's tool/history regions. GPU state is restored
even when batch creation, BLF or setup fails. This renderer owns no event, timer,
solver, canonical object or authoritative evidence.

`dimension_input` wraps the exact bounded TextBuffer in an immutable EditLease and
normalized event/result contract. Text changes are staged before the owner's atomic
raw-input approval. Enter requests validation once; acceptance is not inferred.
Esc cancels once, outside-click suspends exact text, and termination drains the
owned key releases without replaying them as sketch commands. Resume creates a
fresh controller/lease; no queued acceptance survives. Clipboard access occurs
only on explicit copy/cut/paste. An owner-rejected cut may leave copied clipboard
text but does not delete the original field. Local text Undo remains separate from
sketch-command and canonical Blender Undo.

The renderer passes 44 native Blender 5.2.2 offscreen checks, including real pixels,
fractional scale and injected cleanup failures. The input router passes 38 focused
tests with 113 subtests, 6,561 adversarial terminal sequences and 1,000 randomized
owner-approval/history transitions. These do not qualify actual GUI autorepeat,
focus, platform clipboard behavior, IME, bidi, accessibility, or the full viewport
adapter. An ordinary native-panel field fallback remains required for release.
