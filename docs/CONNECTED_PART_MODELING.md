# Connected Part modeling

The current development implementation adds these replayable, editable features:

- Union adds touching or overlapping solids; Intersection keeps their overlap.
- Revolve sweeps a closed profile through a signed angle in degrees around an
  explicit world-space axis. Its origin is in millimetres. The axis direction
  must be nonzero. Profile geometry must yield a valid solid under the sweep.
- Fillet rounds all unique boundary edges at a common radius. Chamfer applies
  a symmetric distance to all unique edges. These are explicitly whole-boundary
  selectors: after an upstream change, **all edges of the new input** are selected.
  An impossible blend fails in full, never silently omits an edge.
- Move/Rotate makes a rigid transformed copy of a prior solid, with world X,
  then Y, then Z rotations in degrees, followed by translation in millimetres.
  Use this branch as a boolean tool or an independent output.
- Edit Feature changes the selected history feature's name, inputs and exact
  parameter expressions without replacing its ID or changing the final output.
  Constrained sketch geometry continues to use Edit Sketch. Changed documents
  invalidate open edit dialogs rather than overwriting newer edits.
- Editing an Add/Remove Boolean whose exact tool is an extrusion also exposes
  that tool's profile and signed depth in the same dialog. Both history nodes
  remain explicit and apply atomically. A shared tool lists its other direct
  consumers and requires an explicit opt-in before changing profile or depth.
  Depth edits replace only the tool's expression, never the named parameter's
  definition. Changing the selected tool requires Apply and reopening before
  editing the new tool's extrusion.

These features use the same canonical JSON, replay, undo/publication, check and
export boundaries as existing extrusions/cuts. Adding a feature creates named
project parameters. Editing an upstream feature regenerates all dependents.
All dimensions can refer to named parameters or arithmetic expressions.

## Whole-solid and topology limitations

A Part solid feature still requires exactly one connected solid. A disconnected
union or empty intersection fails visibly; no component is silently selected.
Separate reusable Parts/instances belong in Assembly. Multiple closed profile
regions can be displayed, but extrusion into multiple disconnected solids is
rejected by Part replay. Nested inner loops create actual holes, not overlapping
capped solids.

The new solid operations do **not** claim arbitrary persistent picked-edge or
picked-face naming. Whole-edge fillet/chamfer intent is durable because it does
not store transient OCCT enumeration IDs. Selected blends can instead persist
an explicit pair of stable semantic face IDs. Replay requires each face to resolve
uniquely and the two faces to share exactly one edge. Missing, split, merged,
nonadjacent, or ambiguous selections fail and require explicit repair.

Fillet, chamfer, and rigid transforms retain one-to-one stable face ancestry only
where exact native construction history proves it, using the same conservative
rules as existing cuts. A single selected edge may own one uniquely proven Generated blend surface;
all-edge and ambiguous generated surfaces remain unresolved. No nearest-face
guess is promoted into persistent identity. This supports chained selected
blends on still-resolvable faces. Boolean faces now retain exact one-to-one native ancestry from either operand;
merged or split faces remain unresolved. Patterns and closed-shell surfaces remain evaluation-snapshot-only. Open Shell
retains provably unchanged outer faces and uniquely proven feature-owned inner
walls and opening lips; ambiguous histories remain snapshots. Revolve uses explicit
construction provenance for generated profile-boundary faces and real sweep caps.

## Verification scope

Focused pinned-OCCT native tests cover exact union/intersection/revolve volume,
valid fillet/chamfer solids, impossible blends, transformed connected feature
chains, source round-trip, and downstream failure blocking. Pure history-edit
tests verify precision and snapshot preservation. See
`tests/integration/test_connected_solid_features.py` and
`tests/unit/test_solid_feature_edit.py`. Native Blender interaction and package
qualification must be reported separately, not inferred from those tests.

## Patterns and hollow parts

Linear Pattern includes the original plus count-minus-one translated copies at
an explicit XYZ spacing. Circular Pattern includes the original and distributes
copies over an explicit signed total angle around a world axis. A full 360-degree
pattern omits the duplicate endpoint; a partial sweep includes both endpoints.
Counts must be integers from 2 through 64. These are fused whole-source patterns,
not disconnected body collections or feature-selection patterns; copies must
join into one solid. Artificial coplanar boolean seams are simplified before
subsequent operations.

Shell now starts with a direct planar-face pick: click the lid to remove, enter
positive inward wall thickness, and Apply. The opening is saved as an explicit
stable face reference and remains editable along with thickness and the base in
Edit Feature. Shift-click can collect multiple openings before Enter, and the
dialog provides an explicit checked opening list. The supported scope is stable
planar openings, not arbitrary curved/unstable topology. Native
`MakeThickSolidByJoin` removes every explicitly resolved face; no mesh index or
nearest-face guess becomes persistent intent. See [multiple openings](MULTIPLE_SHELL_OPENINGS.md).

Choose **Closed cavity** in the same dialog to retain the previous closed inward
shell operation. Existing documents omit `opening_faces` and serialize/replay
through that unchanged operation. The open mode stores 1–64 distinct faces in that optional
list; existing singleton files remain unchanged. Missing, split, removed, ambiguous, or curved openings and impossible
thickness fail atomically, leaving the accepted Part unchanged. Open Shell retains an outside face only when native IsSame identity proves it
unchanged and one-to-one, allowing a subsequent face sketch or associative mate
on an enclosure side. Removed lids and ambiguous histories remain snapshot-only. Uniquely proven
inner offset walls and the opening lip expose feature-owned references as
described below. Closed Shell topology is unchanged.

Focused checks in `tests/integration/test_open_shell.py` exercise exact volume,
point classification through the opening, edited dimensions/thickness, real split
and deleted references, invalid thickness, and legacy closed mode. Native
Blender 5.2.2 operator and separate-process save/reopen checks live in
`tests/blender_open_shell_smoke.py`; these are not mouse-GUI/package qualification.

The native geometry check and STL encoding now omit OCCT's coincident-node,
zero-area UV-pole triangles on rounded surfaces. This does not relax closed
manifold checks, encoded-vs-source triangle equality, or export precision limits.
Fresh save/reopen → regenerate → check → STEP/STL is exercised for a filleted
block rather than assuming that a successful viewport replay implies export.


## Selected-edge interaction

Choose Fillet or Chamfer and click one supported edge in the viewport. The
single-edge picker records the two stable adjacent faces, never display indices.
“Pick Two Faces” and named-face dropdowns remain explicit fallbacks. A pair that
no longer shares exactly one edge fails rather than selecting a nearby edge.

The new-feature dialog shows an exact, cyan boundary preview after radius or
chamfer-distance changes settle. The original solid remains visible and unchanged;
the outline is not selectable, saved, or exported geometry. Invalid dimensions
clear the old outline and show the error. Apply runs fresh exact work and commits
the whole feature with its named dimension only on success. Cancel, Undo, document
replacement, or a lost window retire the preview and any pending native job.
Edit Feature retains the stored edge selection; live preview currently belongs to
the new-feature dialog, not history editing.
Edit Feature and Display now appear beside an explicit selected-feature label,
above the parameter and history lists in the standard CAD sidebar. The history
list also precedes named parameters, so large parameter sets do not bury feature
navigation. Dedicated Part/Sketch sidebars place their single Edit action row
above history too. When the selected sketch has projected construction, its single
Replace Reference launcher is beside these upper controls rather than beneath
history and support explanations. This keeps normal edit launch positions higher without cursor
relocation, duplicate buttons, changed formulas, or a second draft owner.

This is a bounded navigation improvement, not a general popup-position guarantee.
Blender's native dialog can still overlap the solid or extend beyond a small
window, especially with enlarged UI scale, long diagnostics, or other launch
routes. Drag its title to move it if needed. Automatic non-overlapping placement
and a persistent feature editor remain future UX work. The native draw/RNA probe
checks ordering, single action rows, visible errors and read-only rendering; it
does not establish actual GUI Apply/Cancel visibility at any window size.
Open `examples/connected_modeling/patterned_housing.mcad.json` for a connected
pattern → shell → opening-cut workflow, or `revolved_sleeve.mcad.json` for
revolve → chamfer → placement. Both pass fresh exact-solid/manifold checks.

## Loft and sweep

Loft joins two named closed single-wire profiles, or an explicitly ordered list
of 2–16 distinct profiles, into one solid. Choose **Ordered section list**, then
Add, Remove, Move up or Move down the selected row. Top-to-bottom traversal is
saved, never sorted by position. `ruled=0` requests smooth interpolation;
`ruled=1` joins successive sections by ruled spans. Place sections at their
intended positions first. Holes, multiple regions, guide curves and seam
correspondence controls are unsupported. See [multi-section contract and evidence](MULTI_SECTION_LOFT.md).

Sweep consumes a closed profile and a separately selected solved constrained
path. Draw an open connected line/arc chain, Check and Finish it, then select it
in Sweep's path dropdown. Open paths remain editable sketch data, not extrudable
regions. Branches, disconnected chains, crossings and overlapping curves reject;
shared endpoints are explicit identities or Coincident relations, not proximity.

New Sweep dialogs explicitly offer **Center at path start**, aligning the filled-area
centroid with the starting endpoint and section normal with the initial tangent.
Literal roll and **Start at other end (reverse path traversal)** are editable.
**Keep authored placement** leaves source section position and orientation unchanged,
and remains the behavior of older files without migration. The normal start is
the lexically first endpoint identity after explicit coincidence. This is a saved
construction rule, not inferred face identity; source sketches remain unchanged.
See [placement semantics and limits](SWEEP_PLACEMENT.md). Circular
arcs retain their authored clockwise/counterclockwise direction and are built as
exact native trimmed circles, not line approximations. Construction curves are
ignored. Closed curved paths, whole circles and 3D splines remain unsupported.
Self-intersecting or invalid swept solids fail visibly. Radius/constraint edits,
save/reopen and downstream replay preserve the original path records.

`scripts/blender_connected_parts_smoke.py` exercises actual native Blender RNA
operators against the isolated pinned backend, including selected-edge edits.
This is a background operator/publication test, not a mouse/keyboard UI test.

## Associative rectangle/circle on a face

Rectangle on Face and Circle on Face store a supporting solid feature dependency
and a stable semantic face ID, not a one-time copied world plane. Every replay
resolves that face again and constructs the profile on its current geometry.
Changing the supporting extrusion's height therefore moves the attached profile
and its downstream features automatically. Missing, split, ambiguous and
nonplanar faces fail explicitly instead of rebinding to a nearby surface.

The local frame origin is the current face area centroid. Its normal points
outward. Local X is projected world X, with world Y used when the face normal is
near world X; local Y completes the right-handed frame. Local XYZ offsets and an
in-plane angle are editable parameters. A circle is centered on that local
origin; a rectangle uses it as its lower-left corner. This centroid-based frame
is deliberate: reshaping the face can move its centroid and thus the sketch.

Ordinary extrusion now accepts either sign, with absolute length from 1e-6 to
1e6 mm and zero rejected. Negative length goes against the profile normal, so a
face circle can make an inward cut tool. The separately bounded certified sector
path still requires its existing positive 1–1000 mm extrusion range.

These two profile tools coexist with the drawn constrained support path below.
Independent sketch workplanes remain explicit, non-associative placements unless
a support face and solid dependency are authored.

## Drawn constrained sketches on faces

Constrained sketches can now retain a real planar-face support using the same
stable `support_face` reference and an explicit `inputs.support` dependency.
Their saved sketch plane is local to the supporting face, never a copied static
world plane. Replay composes that local placement onto the current exact face
and solves/builds a temporary world-plane sketch without changing the saved
feature, local coordinates, expressions, or canonical document hash.

The solve action replays only the supporting feature's transitive ancestry.
Unfinished downstream features therefore do not prevent working on a valid
support. Its response includes the exact canonical upstream subset, full replay
evidence, and resolved plane, allowing the client to bind the solved world plane
to the current authored source. Independent sketches retain kernel-free solve
behavior. Invalid support returns an explicit error before any fabricated solver
report; failed attached features block downstream solids normally.

This core path is covered with real fixed circles and four-line loops, upstream
height changes, local offsets/rotations, reopen, and inward cuts. The matching
viewport owner must render and unproject in the resolved world plane while keeping
its journal and canonical plane local; do not mistake core evidence tests for
verification of an unfinished UI owner.


## Boolean face ancestry

Union and Intersection use OCCT's exact modified/generated/deleted history from
both operands after coplanar simplification. Unique one-to-one operand faces can
support subsequent face sketches and selected-edge features. Faces formed from
multiple sources are marked merged, and source splits remain unresolved.

A transformed copy can inherit the same semantic names while having distinct
physical faces. Combining it with the original does not make those names unique:
aliased source identities remain unknown snapshot-only references. No branch is
chosen by list order or nearest geometry, even if one image disappears. Reusing
the exact same physical operand twice does not invent a second physical source.


Revolve retains generated profile-boundary face roles, and partial sweeps expose
start/end caps only where they are actual output faces. A full 360-degree turn
has no sweep caps. Planar end faces generated from section boundaries can support
subsequent sketches. Multiple images of one boundary remain split/unresolved.

### Associative construction projection

A constrained sketch can now reference one other constrained sketch through the
explicit `external` DAG input and a `projections` source/target entity list.
Authored line and circle IDs are persistent references. The targets are ordinary
construction entities with fixed-point drivers (and a radius driver for circles),
so normal sketch relations can constrain new geometry to them. Every replay and
solve recomputes those managed drivers from the upstream solved sketch, using the
target's current world plane, including an associative face attachment. Saved
placeholder coordinates are not treated as frozen imported geometry.

Lines use orthogonal projection and must remain nondegenerate. Circles require
parallel planes; tilted circles are rejected rather than approximated as circles.
Missing or changed entity types, missing managed constraints and failed upstream
solves stop the dependent sketch explicitly. This pass does not project arbitrary
solid edges, arcs or multiple source sketches. Solve responses include exact
ancestor replay evidence so the client can independently derive the projection.

### Repeated holes and pockets

Linear Hole Pattern and Circular Hole Pattern take separate base and tool solids.
They cut each placement directly from the base, so spaced hole tools do not need
to fuse into one connected body. Count includes the original placement; a full
360-degree circle omits the duplicate endpoint. Partial circles include both ends.
Intermediate placements outside the base are harmless, but the whole operation
must remove measurable material and leave one connected valid solid.

Upstream tool dimensions, base thickness, count, pitch and axis remain editable.
Exact composed OCCT cut history preserves unambiguous original base faces for
subsequent face sketches. Newly generated hole walls remain explicitly unresolved
instead of receiving guessed persistent names. Native checks cover three spaced
holes, a six-hole bolt circle, thickness edits and downstream face attachment.

### Imported single-solid STEP parts

`import_step` stores exact ISO-10303-21 bytes as canonical base64 with their SHA-256
checksum, not a mutable file path. Each import is limited to 512 KiB and the
existing 2 MiB document limit still applies. Save/reopen and replay therefore work
without the original source file. OCCT parsing and geometry validation occur only
in the isolated sidecar, using a temporary file that is removed after transfer.
Declared source length units are converted to the document's millimetres.

This bounded importer requires one transferable Part root and one valid, closed,
positive-volume solid occurrence. A single-component assembly wrapper is flattened with its occurrence placement
and units preserved. Multiple solid occurrences (even coincident repeated parts)
and loose surface/edge geometry are rejected rather than silently dropped.
Archives and XML STEP encodings are not accepted. Imported face identities are
explicitly snapshot-local, so ordinary whole-solid transforms, booleans, patterns
and all-edge blends work, but persistent face attachment or selected-edge naming
on the imported geometry is not invented. STEP export remains available after
normal geometry checks.

### Point, center and tangent relations

Four additional analytic sketch relations use authored stable entity IDs:
`point_on_line` and `midpoint` take a point followed by a line; `concentric` takes
two circles; `circle_line_tangent` takes a circle followed by a line. Point-on-line
and circle tangency refer to the infinite supporting line, not a segment-bound
contact. Midpoint means the exact average of the two segment endpoints.

The solver compiles circle tangency into native on-line, on-circle and perpendicular
radius equations with a temporary contact point. This is not a polygonal or frozen
coordinate approximation. Temporary points never enter saved sketches, meshes or
exported profiles. Native resource limits include them, and failure diagnostics
map back to the one authored tangent constraint. Independent analytic residuals
and the existing coordinate-cycle DoF guard continue to validate successful solves.
Existing shared-endpoint arc/line `tangent` semantics are unchanged.

### Direct sketch location dimensions

In an active sketch, choose **Dimension** (D), click a circle center or sketch
point, then a straight sketch/reference line. A construction preview shows the
perpendicular offset; click to place the label, type its value or a named
expression, and press Enter to check and accept. Offsets are unsigned: current
point placement seeds which side the solver starts on. To change sides, local
Undo until the new offset is removed, use Select to drag the center across the
reference, then dimension again. There is no signed-offset or Flip control.
Repeat against another edge to
locate the same center. Clicking two points instead measures their straight-line
distance, not a horizontal or vertical component. Click a curve perimeter for
radius or the interior of a line for length. Double-click a placed label to edit.

Point-to-line offsets use an ordinary construction foot and segment with native
point-on-line, perpendicular and distance relations. They never rewrite projected
reference anchors. The scaffold is one local Undo step; no new canonical
constraint type is introduced. Esc before placement cancels selection; Esc during
numeric editing retains the initial dimension, which local Ctrl-Z removes along
with its newly created helpers and annotation. Local Redo in the same editing
session restores that exact annotation placement with its construction geometry;
a divergent new command abandons the removed placement. Zero offsets use Point on line
instead. The reference's supporting straight line may extend beyond its endpoints.

### Reusing a selected bevel or fillet surface

For a single selected edge, a proven one-surface Chamfer/Fillet now owns a reusable
surface identity. Click a planar chamfer face to attach a sketch, or use supported
straight/full-circle boundary edges as sketch references. Curved fillet surfaces
are not planar sketch supports. Size edits preserve the feature's selected-edge
intent; Edit Feature changes the selection deliberately. The picker and Help
explain that dependency. All-edge, split or multiply generated faces still require
an explicit different modeling choice; proximity never picks a substitute.

### Sketching inside an open Shell

A uniquely proven native inner offset wall can now be selected for an attached
sketch when planar. Supported straight or full-circle boundaries can also become
associative sketch references. These follow the source wall and Shell thickness,
not an outer-face identity or mesh index. A unique lip follows the current authored
opening: deliberately changing the opening moves attached lip references with it,
while inner walls still follow their original source faces. Edit Shell to change thickness/opening; the picker and Help describe the
intent. Curved walls are not planar sketch supports, and split/competing ancestry
still fails closed. This applies to open Shell in typed replay; closed-cavity
shells and legacy replay do not acquire these new references.
