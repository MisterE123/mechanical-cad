# Proposed next slice: explicit sketch constraints and recovery

Status: the bounded slice shipped as the immutable 0.5 preview at `1a27e74`.
Core/action/UI commits and their tested boundaries are recorded in
[CONSTRAINT_VERIFICATION.md](CONSTRAINT_VERIFICATION.md). Independent reviews,
the full automation gate and exact installed native GUI/reopen checks passed.
See [the sealed release receipt](audits/constraint_installed_050.md).
The original proposal below retains the intended acceptance requirements.
This sequence is an engineering recommendation from the existing roadmap and
observed gaps. It does not reinterpret earlier dimension-interface feedback as a
user-directed priority change.

## Useful outcome

A user draws a four-line profile with the general tools, explicitly makes its
edges horizontal/vertical, anchors one corner at the origin, adds two existing
distance dimensions, sees the real remaining freedom, and extrudes it. Editing a
dimension updates the same Part. They can inspect which relations control an
entity, deliberately release one, and recover from a conflicting addition.
The circle workflow gains an explicit center anchor instead of relying only on
approximate pointer placement. Neither workflow requires hand-edited JSON.

The first milestone should expose the already supported constraint kinds rather
than add arcs, a new solver, a new workplane scheme or a broad shared-state rewrite.
General sketch coverage remains a longer-term goal.

## Bounded controls

- One selected line: explicit **Horizontal** / **Vertical** actions.
- One selected point: **Fix here** at its current validated solved coordinates;
  separately **Fix at origin**, whose shown target is sketch-plane (0, 0).
  The latter can move geometry and must say so before applying.
- Coincident creation is a gated extension within this plan, not required for
  the first H/V-and-anchor loop. It needs exactly two distinct explicitly picked
  points and a preview naming both. Reject direct or transitive coincidence that
  collapses a line. This adds a relation; it never merges or replaces entity IDs.
  Defer the button if these preflight and recovery gates are not yet ready.
- Selected entity: a compact list of its existing relations, with kind, value or
  fixed target, and related entities. Stable IDs remain available in details.
- Selected relation: **Remove relation**, without silently deleting its points,
  lines, circles or other relations. Release of a fixed point means removing the
  explicitly selected fixed relation, not every relation touching that point.
- Existing distance/radius drivers keep the compact field and their exact raw
  expression. No second driving constraint or diameter conversion is introduced.

Use contextual icon actions near the existing left tools, with readable hover
text and an optional learning label. Keep the right side focused on selected
relations/history and short current status. H/V/lock/coincident glyphs may be
shown near geometry, but the inspector is an unambiguous selection fallback.
Do not add a permanent dense wall of constraint buttons or require long menus.
Existing licensed icon sources can be reused; visibility at ordinary and enlarged
UI scales is an acceptance gate, not implied by asset availability.

## Reuse and exact gaps

### Reuse without a canonical schema change

`sketch_model.py` and `sketch_solver.py` already support horizontal, vertical,
coincident and fixed relations, alongside distance/radius. `AddRelation`,
`EditFixedTarget`, `DeletePreview` and `DeleteBatch` live in the pure command
module. Duplicate relations are compared conservatively and preserve the
existing ID. Formula strings are not algebraically equated.

`GeneralSketchDraft.execute` already journals current solved point/circle seeds
when deleting a relation. `GeneralSession.execute` prepares a detached candidate
and revalidates exact current evidence into it. Normal release therefore can
preserve placement, invalidate authority, and request a new solve without
rewriting the original canonical document until Finish.

The shared editor owner, exact scene/base revision checks, async execution lease,
publication transaction, local journal, draft persistence, compact field and
annotation store must remain the only implementations of those responsibilities.
No new background coordinator or parallel lifecycle handlers are needed.

### Missing before production UI

0. **Point picking needs an explicit route.** Current generic Select picks
   points and curves together, with no hidden priority. An endpoint ties with its
   incident line at the same screen position; zoom cannot resolve that tie. Add
   an explicit point-only picker/filter or a small stable-ID chooser before
   promising Fix/Coincident usability. Distinct overlapping points remain
   ambiguous. Selection/filter state is UI-only; any new persisted field needs
   explicit codec compatibility rather than silently expanding the old payload.
1. **Failure diagnostics need their own binding.** Current GeneralSession keeps
   a human error after failed Check but drops the validated failure report.
   Conflict IDs are currently rendered only in the current-solution branch.
   Store a bounded diagnostic snapshot separately from accepted solve evidence,
   bound to the exact request, session, command/input revision and source IDs.
   Clear it on any relevant change. Its IDs are diagnostic candidates, never
   proof of which relation should be deleted. It cannot provide current DoF,
   geometry, release seeds, Finish permission or export authority.
2. **Non-dimensional relation selection needs rendering support.** UI selection
   already permits constraint IDs, but viewport picking selects geometry and the
   overlay currently assumes selected constraints are dimensions. Generalize the
   relation descriptor/hit-test layer, or initially select them through explicit
   inspector rows, without falsely marking valid H/V/fixed/coincident IDs missing.
3. **Fix actions must expose existing intent.** Fix here requires current solve
   evidence. If a point already has a fixed relation, select it and offer explicit
   target editing/release; do not accidentally add another fixed target because
   rounded coordinates differ. Fix at origin is a distinct disclosed action.
4. **Conflict recovery cannot be silently weakened.** See the boundary below.
5. **No-op actions must stay no-ops at the owner boundary.** The reducer already
   returns an existing relation ID without a new journal entry, but current
   `GeneralSession.execute` still replaces state and starts Check. An unchanged
   relation action should preserve revision, allocation ledger, exact snapshot
   and current solve evidence. A UI-only placement/selection action is separate.
6. **Removed annotation binding stays explicit.** The annotation store already
   retains missing/changed bindings conservatively. Removing a driver must not
   silently reattach its label to another constraint with equal geometry/value.
   Undo restoring the same relation ID can restore its own placement.

## Conflict-removal boundary for review

The current safe release path requires a successful current solve. After an
inconsistent relation is added, that authority is intentionally gone. Existing
local Undo can reverse the latest addition and Check again, but arbitrary Remove
would currently be blocked. A restored inconsistent sketch may have no usable
local Undo history. Shipping an inspector that merely traps this case would leave
an important recovery gap.

Recommended implementation stages:

1. Land separately bound failure diagnostics and a visible **Undo last sketch
   action** recovery control first. Keep existing validated-release semantics
   unchanged while these controls are tested.
2. Before exposing unrestricted Remove, agree a distinct, explicit recovery
   action for a relation-only deletion with no successful current solve. Proposed
   wording: **Remove using authored positions**. Show the exact selected relation,
   disclose that no current solved placement exists, preserve the authored point
   and radius seeds exactly, and mark the result unverified until the next Check.
   It must never use a retained outline or stale solver coordinates as authority.
   This is a proposal requiring a reviewed typed command contract, not permission
   to bypass the existing DeleteBatch gate. If this contract is deferred, keep
   Remove disabled with a truthful reason and explicitly limit the slice's
   conflict recovery to available Undo/driver edits; do not claim imported
   inconsistent sketches are generally repairable.

The recovery action must delete only the named relation, preserve every surviving
entity/relation ID and source expression, and record the exact seeds/deletion in
one bounded journal operation. No implicit cascades or normalization are allowed.
Its persisted command must remain deterministic; if a new journal variant is
needed, add explicit version dispatch and preserve old 0.4 saved drafts and bytes.
A schema change must be justified by changed persisted meaning, not by UI labels.
Ordinary release from a valid sketch must continue to seed from the current
validated solution and preserve position across release/fix/Undo/reopen.

This boundary, especially the new recovery seed policy, should be reviewed before
production edits. It is distinct from relaxing solver/profile validity or
publishing a failed sketch. Failure remains a recoverable draft; canonical
publication still requires successful solve and all dependent features.

## Acceptance loop and regressions

### Human-verifiable loop

1. Draw a joined four-line profile in the general editor, not the Rectangle
   shortcut. Apply H/V explicitly; fix one corner at the origin with a visible
   target; add width/depth dimensions with the existing compact field.
2. Verify real 0 DoF and a closed profile, Finish and extrude. Change a driver and
   verify the same feature IDs, analytic volume and semantic side-face identities.
3. Release the anchor and show real 2 DoF without a positional jump; Fix here,
   Undo/Redo, suspend/resume, save/reopen, and recheck the same placement.
4. Add an incompatible relation, inspect exact-bound diagnostic candidates, then
   Undo it. Exercise the reviewed relation-removal recovery on a restored
   inconsistent draft as a separate gate, without manufacturing a passing result.
5. Anchor a manually drawn circle center at the origin, retain its radius formula
   and verify exact downstream disk geometry.

### Required automated and independent checks

- Duplicate H/V/coincident/fixed actions are idempotent, including reversed
  symmetric refs; no extra ID, journal entry or native geometry change.
- Distinct conflicting fixed targets are never silently collapsed or replaced.
- Releasing an anchor after dimension edits preserves current solved coordinates;
  operation order, far-origin coordinates and circle radii have explicit cases.
- Relation-only deletion has zero geometry cascade. Explicit recovery without a
  current solution uses only its disclosed seed policy and never current-DoF
  authority. Stale previews, IDs, revisions and resource overflows fail unchanged.
- Failed diagnostic IDs cannot survive a changed request, selection-bound source,
  Undo/Redo, raw input edit, source edit, scene/window replacement, load or disable
  as if they were current. Late native results cannot publish them.
- Surviving authored IDs and expressions remain exact through seed edits;
  reordered/reversed loop records retain the supported semantic face references.
- Annotation removal/Undo is bound by ID/kind/refs, not coincident screen position.
- Existing released schema/serialization/hash paths, Rectangle, assembly,
  lifecycle, busy/cancel/timeout and installed-package suites remain unchanged.
- Actual native GUI: contextual selection and icons, ordinary/enlarged UI scale,
  invalid selection, add/remove/Undo, conflict recovery, direct input and focus
  boundaries, viewport navigation, saved draft recovery, and downstream edits.

## Commit and review boundaries

1. Pure relation descriptors / diagnostics identity, explicit point selection,
   no-op preservation and tests.
2. Reviewed recovery command policy, old-draft compatibility and numerical tests.
3. Bounded owner integration using the existing async/publication path; independent
   transaction and stale-result review before exposing the new UI.
4. Contextual controls / relation rendering, native GUI review, then an exact
   clean installed-package gate and a downloadable example.

Point dragging, general coordinate expressions, inferred snapping constraints,
arcs, trim/extend, construction geometry, reference dimensions, arbitrary planes,
multiple profiles, new Part features and richer assembly solving remain outside
this proposed slice. They stay on the product roadmap rather than being hidden
behind unsupported controls.
