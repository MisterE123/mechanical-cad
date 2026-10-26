# Drawn sketch workflow: lines, circles, arcs and dimensions

This guide describes current source behavior, not a delivered-package or GUI
qualification claim. Start with [current capabilities and limits](INTEGRATED_MODELING.md).

The normal add-on registers this workflow. Importing the add-on or its viewport
modules does not register classes, acquire an execution lease, or start native
work. The existing shared owner, scene draft slot, exact-version codecs and
lifecycle handlers remain the only ownership and recovery mechanisms.

## Analytic geometry and arc boundaries

Center Arc uses three inputs: center, start and end. Use Existing Point chooses
exact shared point identities; coincident screen positions alone do not connect
curves. Check may move unconstrained points. Reverse changes the directed sweep
to the complementary arc without swapping endpoint identities. Radius editing,
local Undo/Redo and supported saved drafts retain those identities.

Current profiles include closed mixed line/arc contours and analytic circles,
with supported non-touching holes. A connected nonbranching open line/arc chain
can instead be saved for Sweep. Crossing, overlapping, touching or branched
boundaries are not guessed into a region. A checked sketch is not automatically
an extrudable profile, and a profile is not a solid. Only valid solid output can
be checked/exported as STEP/STL or captured as an Assembly Part.

See [closed regions and analytic curves](MULTI_LOOP_PROFILES.md). The specialized
single-sector path remains separately bounded for its original source form;
it is not the limit of the general arc editor. In particular, the sector-form
profile is excluded from Symmetric, Through All and Up to planar face extrusion;
see [end conditions](EXTRUSION_END_CONDITIONS.md).
The earlier [arc milestone](NEXT_SKETCH_ARCS.md) records historical checkpoint
scope and evidence, not current availability or blanket export restrictions.

While drawing Line or Center Arc point inputs, or choosing a Circle center,
hovering a uniquely picked existing point shows a small ring and “Reuse point”.
Click rechecks the same point picker and reuses its identity; the hint adds no
constraint or origin snapping. Ambiguous/hidden targets have no unique hint.
Rectangle corners and Circle radius input do not use this preview. Retained
proposals must be continued first; navigation or draft changes clear the hint.

## Entry and editing

- **New Sketch** in the Sketch or Part CAD tools opens the general editor in
  the Sketch workspace. Choose XY, XZ or YZ with an offset; **Sketch on Face**
  starts a drawn sketch on a supported stable planar face.
- **Rectangle Sketch** remains an explicit shortcut in the Sketch palette and
  CAD menu. It retains the two-corner, named width/height editor.
- **Edit Sketch** validates the selected canonical constrained sketch first. The
  supported legacy rectangle definition opens its rectangle editor; other
  supported line/circle/arc definitions open the general editor on their saved
  datum or associative support plane. Unsupported
  feature types, planes, schemas or fields are refused without rewriting them.
- General sketch view isolates mesh context only in its owning viewport. The
  previous viewport mesh setting is restored on exit. Other viewports and scene
  objects are not hidden globally. Visible solid context is not an automatic
  projection: use the explicit reference tools described below.

## Left tools and right status

The left native CAD palette includes Select, Points, Line, Circle, Center Arc,
Rectangle, Dimension and contextual relations, with matching icons and hover
explanations. Check, Finish and Cancel retain explicit controls. While a
check is running, Cancel Check replaces Check. The CAD menu exposes the same
capability-gated actions when gizmos are hidden. Shared Finish and Cancel also
remain in the header and right-side history panel. The general palette reserves
its contextual slots so Check, Finish and Cancel never exchange positions when
selection changes. The responsive palette can use two columns, keeping Check
above a final Finish/Cancel row. If the available viewport cannot fit the palette,
the header menu is labeled **CAD · Sketch · Tools** and retains all
named actions, with Finish and Cancel also available in the header. Hiding gizmos
or showing Blender's stock toolbar likewise keeps the named menu available.

The right side gives a concise current draft status, real current-solve DoF,
validated check errors, pending input/proposal recovery controls and a `?` help
button. Committed Part status is labeled separately. An unverified or pending
field never claims a current DoF count. No constraint count is guessed locally;
failed checks retain their validated error rather than reusing older evidence.

- **Line:** click two points. Choosing an existing endpoint explicitly reuses
  its stable point identity.
- **Select / Points:** ordinary Select keeps curve/endpoint ties explicit. Points
  restricts picking to endpoints and circle centers, without choosing between
  distinct overlapping point IDs. The right inspector also has exact Start,
  End and Center buttons.
- **Horizontal / Vertical:** select one line and apply the contextual relation.
  Reapplying an existing relation selects it without adding a duplicate.
- **Fix here / Fix at origin:** select one point explicitly. Fix here uses the
  current solved location. Fix at origin asks for confirmation and can move the
  connected sketch. A current successful Check is required for Fix here.
- **Circle:** click the center, then a radius point.
- **Center Arc:** click center, start and end; use Reverse for the complementary
  sweep. Keep endpoint identities connected explicitly when forming a profile.
- **Dimension:** choose a line for length, a circle/arc perimeter for radius,
  two points for straight-line distance, or a point then a straight line for
  perpendicular offset. Place the label to open its value/formula field.
  Point distances are not horizontal/vertical dimensions. Offsets are unsigned;
  the existing point placement seeds the side. To change sides, Undo the new
  offset, drag the point across the line, then dimension again.
- **Set Diameter:** select a circle or arc and enter a diameter; the saved driving
  value is radius = diameter / 2, not a separate diameter constraint. Select two
  lines for a driving angle in degrees. Double-click an existing label to edit its
  value or named formula; drag labels to adjust annotation placement only.
- Bare length input uses millimetres and angles use degrees. Explicit literals
  such as `10 mm`, `1 in` or `1 rad` normalize to those units; unit suffixes
  inside formulas remain unsupported. See [typed unit input](UNIT_INPUT.md).
  Arbitrary relation-target editing remains unavailable. See
  [supported relations](SKETCH_RELATIONS.md) for selection and correction rules.
- **Reference measurements:** select a line, circle or arc, then choose the inspector
  Length/Radius/Diameter **(REF)** action. Labels are read-only and do not add
  solver constraints. Use the inspector X to remove a label; local Undo edits
  geometry, not label placement. See [reference dimensions](REFERENCE_DIMENSIONS.md).
- **Enter in a field:** request one asynchronous checked acceptance. A consumed
  profile also needs successful downstream replay before its driver is accepted.
- **Esc in a field / Cancel Input:** discard that pending driver edit. Previously
  accepted geometry stays unchanged and needs a fresh Check.
- **Outside click:** close the field and retain its exact raw text. That first
  click and its release belong to the field, so they cannot also activate a
  native palette button or create geometry. Choose Reopen Input to continue, or
  Cancel Input to discard the pending edit.
- Pointer orbit/pan/zoom pass through the modal editor, including during field
  editing. Numeric and other typing keys remain field-owned while it is focused.
- **Check:** explicitly run a real solve. **Cancel Check** cancels its native work
  without accepting input; raw text is retained for an explicit retry. Shared
  execution-busy rejection never schedules an automatic retry. Beginning a new
  Check retires previous solve authority; cancellation or launch failure leaves
  the sketch explicitly unverified. Authored geometry and its local history stay
  available for correction, recovery or an explicit retry.
- **Finish:** requires a current successful check and no unfinished input or
  proposal. It replays and publishes one canonical transaction, including the
  accepted annotation layout, then returns to Part. If editing an existing sketch
  produces an eligible downstream support/projection failure, its unapplied edit
  can instead transfer to [staged repair](STAGED_EDIT_REPAIR.md). This is not a
  successful Finish or partially accepted Part; other failures retain the draft.
- **Cancel Sketch:** discard the draft without changing committed Part history.
  **Esc outside a field** cancels a pending check or unfinished proposal first;
  otherwise it suspends the draft. Local Ctrl-Z is sketch journal history,
  separate from Blender canonical Undo/Redo.

A connected nonbranching open line/arc chain is not a closed extrusion profile.
Unavailable consumed profiles remain drafts. Constraint editing remains limited
to the exposed relations and driving dimensions. See
[relation inspection and recovery](CONSTRAINT_INSPECTOR.md)
for exact-ID selection, local Undo/Redo, normal solved-position release and the
separately confirmed authored-position recovery policy. These geometric relations
do not model physics or establish mechanical safety.

## Exact saved-draft dispatch

Resume validates the original document bytes and named codec before opening any
owner. Rectangle UI draft version 1 uses the rectangle editor. General sketch UI
draft versions 1, 2 and 3 use their explicit codecs; version 1 receives empty
UI defaults while preserving its command intent. Version 2 retains selection,
annotation placement, tool and unfinished proposal/input state. Version 3 carries
the explicitly arc-capable authoring state. Unknown versions are not migrated.

Resume starts no solve and captures no retained field/proposal automatically.
Evidence and DoF remain unverified. Unknown, newer, corrupt or stale snapshots
are not guessed, migrated or silently redirected. Their exact raw slot text stays
available until the user explicitly discards it. A staged workspace transition
also checks that the canonical document and saved slot have not changed before
it launches the selected editor.

## Verification and QA launcher

`tests/blender_general_dispatch_smoke.py` exercises the registered New, Rectangle,
Edit and exact-version Resume routes in native Blender background mode. It also
checks atomic failed registration, idempotent registration/cleanup, unknown raw
preservation, execution-busy entry, left palette capabilities, field outside-click
ownership, navigation and ordinary QA-launcher compatibility. All native tests
must use `--background --factory-startup --python-exit-code 1` and verify their
explicit completion marker.

`scripts/blender_general_viewport_dev.py` now relies only on normal production
registration and its registered general viewport operator. It remains an isolated
QA launcher: it opens a blank
QA document/workspace and writes a test state receipt, without scripting geometry.
No duplicate experimental class registration remains. Use a distinct QA profile.

Headless dispatch is not native GUI usability evidence. Real left-palette hover,
click targets, keyboard focus, visual hierarchy, workspace transitions and
Finish/Cancel/Undo/Redo still need GUI review on the installed build.

## Use Solid Edge

With an active sketch, choose Use Solid Edge, select an eligible earlier Source
solid, then Pick Edge. Click a supported straight edge or full circle on that
source's temporary picking body. The orange highlight identifies the
native edge, not a triangulation diagonal. Esc cancels without adding geometry. A successful pick
adds a source-linked construction line or circle and starts Check. Its geometry
remains selectable for ordinary dimensions and relations; source-driven points
and circle radii cannot be independently edited or lose their managed drivers.
For a concentric hole, use the projected circle centre when drawing the hole.
Place the sketch parallel to the circular edge's plane, for example on its planar
end face. Oblique circle projection would create an ellipse and is rejected.

Every saved reference contains a unique pair of stable faces. Straight edges also
retain the two endpoints' additional incident stable-face signatures. Native
replay recomputes their endpoints or the full circle's analytic centre, normal
and radius, then projects into the current sketch plane. Unsupported or changed
identity requires explicit reference repair, not a guessed substitute.
Straight edges and circles may share one solid source, and the same sketch can
mix several explicitly chosen earlier solids and sketches. Use Project Geometry
for earlier sketch lines/circles; repeat either chooser without finishing the
draft. Each reference keeps its own source, even if face labels match elsewhere.
Partial arcs, other curves, oblique circles, ambiguous face pairs and collapsed
lines remain unsupported. See [multi-source projection](MULTI_SOURCE_PROJECTION.md)
for source switching, cancellation and same-source repair. An unfinished restored draft may display authored
seeds until Check, but those seeds never authorize Finish or native geometry.
