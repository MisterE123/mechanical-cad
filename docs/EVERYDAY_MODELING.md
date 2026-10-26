# Everyday modeling inside Blender

This walkthrough describes the current development source, not a newly delivered
or qualified installer. See [current capabilities and limits](INTEGRATED_MODELING.md)
and consult your package's evidence for its exact scope. Millimetres are the
CAD document's length units; the Blender display converts them to metres.

## A plate with an editable face-mounted hole

1. Create a **New Document**, then use **Rectangle Sketch** for a 40 × 30 mm
   footprint. Finish the sketch and **Extrude** it 10 mm.
2. In the Part workspace choose **Sketch on Face**. Hover the current solid and click its highlighted
   stable planar end cap. Esc cancels; the advanced face list remains available. The sketch uses that face's centre and outward normal,
   not the world XY plane. Keep the current geometry rebuilt before selecting a
   support.
3. Draw a **Circle**. Add a radius/diameter dimension and position constraints
   as required. **Check** and **Finish** the sketch. An underconstrained sketch
   can be useful while exploring, but its reported degrees of freedom explain
   what remains free; it is not automatically fully dimensioned.
4. Use **Extrude Remove**, choose the plate as base and the new sketch as profile,
   then choose **Through All** and **Reverse** to cut into this outward face.
   Remove defaults inward for a standard zero-offset face sketch on the selected
   base; other planes are not guessed. Through All stores direction and the
   target body, not an oversized fixed depth. It is directional from the sketch
   plane, not automatically both sides.
5. Select the original extrusion in history and **Edit Feature** its length.
   The face sketch follows the moved cap, and Through All rebuilds through the
   changed plate. Choose **Blind** instead when the hole should keep a fixed
   depth. **Symmetric / Mid-plane** uses a positive total depth, half on each
   side of the sketch plane.
6. **Check Geometry**, save the CAD document and Blender scene as appropriate,
   then use **Export** for exact STEP or a tessellated STL.

**Extrude Add** works the same way for a boss that touches the existing body.
A disconnected boss is rejected rather than silently turning one Part into a
multi-body document. The individual extrusion and Boolean remain in history
so their dimensions and operands can be edited later. Selecting the Add/Remove
operation and **Edit Feature** exposes its linked extrusion profile and end
condition in the same dialog. Blind has signed depth; Symmetric has positive
total depth; Through All has direction and target rather than a fake depth. A tool shared by other operations lists those consumers
and requires explicit opt-in before changing them.

## Draw and dimension without leaving the sketch

Use **Rectangle** (or R) inside a drawn sketch and click two opposite corners.
It creates four editable lines with horizontal/vertical relations, on the current
datum or attached face plane. Use **Dimension**, choose a side, and place its
label: the value field opens immediately with the measured value selected. Type
a value or expression and press Enter. Double-click an existing dimension to
change it later. Esc cancels numeric entry without removing the placed dimension.

## Preview before accepting an extrusion

Extrude and Add/Remove dialogs prepare a debounced exact result in the sidecar.
Cyan boundary outlines show proposed geometry while the original solid remains
visible. They are a preview, not accepted geometry or selectable CAD identity.
Changing an input invalidates the old outline. Cancel leaves history unchanged;
Apply validates the current intent again before atomic publication.

## Make design changes deliberately

- Click a history row's pencil to open its matching editor directly, without
  changing the part's active output. Cancel leaves the model unchanged; unsupported
  and imported feature types have a disabled pencil. The named actions remain:
  **Edit Sketch** for drawn geometry and constraints, and
  **Edit Feature** for primitive sketch dimensions and solid parameters/inputs.
  The selected-feature controls above history show only the matching editor;
  both named routes remain in **Tools & Document** in Sketch and Part. These
  edit the canonical CAD model, unlike Blender Edit Mode on its disposable mesh.
- **Offset Fixed Sketch Plane** appears directly only for constrained sketches.
  Attached sketches and linked projections retain the disabled action with its
  guarded explanation; primitive sketches use their dimension editor instead.
  The named offset route remains in **Tools & Document** for discoverability.
  Busy or stale state does not remove a family-applicable direct action.
- Named parameters accept expressions. Feature dimensions can refer to those
  names; changing a parameter rebuilds dependent features.
- Stable face references are associative. New drawn face sketches expose
  **Preserve logical plane** intent: proven coplanar Cut fragments can retain
  the saved source-relative workplane without pretending that one fragment is
  the original face. **Review Support** explains the assumption and lets you
  choose Strict or change the support. Legacy sketches without saved intent
  remain Strict; missing or ambiguous ancestry is not guessed by proximity.
- Fillet/chamfer starts with a direct edge pick. Its stable adjacent face pair
  identifies exactly one native edge; triangulation diagonals are never offered.
  The creation dialog previews the proposed exact boundary in cyan. Two-face
  picking, all-edge and named-face options remain explicit alternatives. An
  impossible radius fails visibly; reduce it or change the selection.
- Reopening a scene does not certify its cached mesh. Rebuild before resuming
  a supported sketch or selecting current exact geometry.
- A failed operation retains the preceding valid document. Read the exact
  diagnostic and the suggested remedy; do not treat an old visible mesh as a
  successful result of the rejected operation.

## Position new geometry against an earlier sketch

During a drawn sketch choose **Project Geometry**, then select the earlier
constrained sketch and its line or circle. The reference is construction
geometry, not an added profile boundary. Constrain your ordinary geometry to
its projected points or use an equal relation to its circle, for example.

Changing the earlier sketch recomputes the projected reference. Save/reopen and
sketch Undo/Redo retain the dependency, not a detached copy of its coordinates.
Repeat Project Geometry to add references from different earlier sketches.
Each reference retains its explicitly chosen source, within the shared limit of
64 references. Lines must not collapse in projection; circles require
parallel sketch planes. Oblique circles are not silently approximated by circles.
For a solid edge, choose **Use Solid Edge** while editing the sketch, choose an
eligible earlier **Source solid**, then **Pick Edge**. Click a highlighted straight
native edge or full circle away from a corner. The temporary picking body belongs
to that source; it does not change active output or accepted Part geometry.
It creates construction geometry, not an extra profile boundary. Use
ordinary point, line, circle and dimension selection on that reference. For
example, draw a construction segment from a point constrained onto the reference to the hole centre, make it
perpendicular, and dimension its length to control the hole's edge offset.
A second endpoint distance can locate the foot along the edge.

For a circular rim, place the sketch on a parallel plane or planar end face,
then Use Solid Edge on the rim. Its exact centre and radius follow the source.
Use its centre to locate a concentric hole, or an equal relation to follow its
radius. The reference radius and centre cannot be edited independently.

The reference follows the upstream solid on Check/rebuild. A straight edge's two
endpoints are identified by additional incident stable faces, not by nearest
position or native enumeration. A full circle uses its unique stable face pair
and native analytic centre, normal and radius, never an approximation of its
viewport segments. Unsupported endpoint identity, split/removed faces, partial
arcs, other curves, oblique circles or a collapsed line produce a diagnostic.
One sketch can mix straight and circular references from several earlier solids
and sketches. Repeat the source chooser without Finish or reopening the sketch.
Finish, save and reopen preserve each source dependency and its dimensions.
Replacement never silently moves a reference to another source, even when face
labels match. See [multi-source authoring and repair](MULTI_SOURCE_PROJECTION.md)
for cancellation, supported repair and source-identity limits.

## Reuse the Part in an assembly

Switch to Assembly and create an assembly from the current Part. Create named
mate frames and insert instances using fixed, revolute, slider, cylindrical, planar or ball joints. Cylindrical joints have
independent axial translation and rotation, with separate limits. Use
an associative planar-face frame when its origin/normal must follow a source
face; ordinary surface-picked coordinates remain literal.

To remove a mistaken component, select it and choose **Remove Component**.
The confirmation lists its descendants, connecting joints and affected
clearance requirements. Removing a branch keeps reusable Part definitions.
The grounded root cannot be removed this way. An emptied active requirement
preset is explicitly cleared to measurements-only, not silently treated as a
passing safety policy. The preview must still match the current assembly.

Source changes are explicit: update the assembly's captured Part definition,
then evaluate its joints and check the relevant saved/listed poses. Assemblies
support up to 64 instances in a rooted joint tree. They do not yet solve general
closed-loop mechanisms. Clearance at listed poses is not proof of collision
freedom over every intermediate motion or of structural strength.

## Other connected solid tools

- Revolve uses a world-space axis and an angle in degrees.
- Loft joins two compatible closed sections. Sweep follows a solved planar line/arc
  chain, with explicit automatic section centering at path start, roll and reversed
  traversal, or Keep authored placement. See [Sweep placement](SWEEP_PLACEMENT.md).
- Solid patterns join repeated copies into a single body. For separated holes,
  use **Linear Hole Pattern** or **Circular Hole Pattern** with a base and one
  cutting solid. Count includes the original tool. A full 360° circular pattern
  does not duplicate the start; a partial sweep includes both ends. The final
  Part must remain one solid. Generated hole walls may need explicit reference
  repair rather than offering stable associative support.
- Shell: click the planar lid to remove, enter wall thickness, and Apply to make
  an open enclosure. Shift-click additional planar faces to create multiple
  openings, then review the checked list. Edit Feature changes the openings and
  thickness or selects Closed cavity. Split/missing references fail safely instead
  of silently selecting another face. See [multiple Shell openings](MULTIPLE_SHELL_OPENINGS.md).

See [current limits](INTEGRATED_MODELING.md) before relying on a workflow that is
not demonstrated here. Drawing sheets and load certification are outside this
project's current requested output.

## Bring in a standard mechanical part

Choose **Import STEP Solid** from Tools & Document or the empty Part panel.
The file selector accepts one valid closed solid, at most 512 KiB. Supported
single-component wrappers preserve placement and units; true repeated
occurrences, loose surfaces and multi-solid assemblies are rejected.

The exact STEP bytes are embedded in the saved CAD history. You can move,
blend, combine or capture that imported solid as an assembly source without
keeping the original file on disk. Imported face handles are snapshot-only,
not persistent semantic sketch supports. Use explicit datum sketches and
named/literal mate frames rather than assuming an imported face survives an
unrelated geometry replacement.


## Find in-app explanations

Open **CAD → Search CAD Help** in Sketch, Part or Assembly (also available in the
ordinary CAD sidebar). Choose a category, or search across all categories by tool,
action or error words, such as `solid edge`, `facing normals`, `through all` or
`blocked timeout`. Choose a matching Topic, then **Read topic**. **Previous/Next**
reads bounded pages; **Back to results** keeps the search and category. Esc or a
click outside closes Help without editing the model. No-match searches suggest
clearing the search or choosing All categories.

Existing contextual question buttons and in-dialog Help remain available; those
continue to preserve authoring fields. The browser reuses their topic text rather
than a separate copied manual. Chapters explicitly distinguish suggested inputs
from accepted geometry, explain how to correct face-mate defaults and extrusion
choices, and describe when a fresh geometry or pose check is needed. Source docs
remain the detailed specification, not a certification promise.

Focused verification: `tests/unit/test_help_catalog.py` covers hierarchy, common
searches, text pagination and registration/menu wiring;
`tests/blender_help_browser_smoke.py` exercises real Blender RNA callbacks,
empty results, category changes, Back/paging and all draw branches in background.
This is not manual popup layout/usability or ZIP-install qualification.

## Geometry check confirmations

Successful current Part geometry checks and STEP/STL exports use a brief status
confirmation without a dismissible help popup. Expand **Part details** to read
the complete report, numeric checks, export destination and caveats. STL exports
still require millimetres in the receiving application. Failed, unknown or
outdated outcomes retain their detailed warning popup, including confirmed files
written for an earlier request; they are not reported as current success.

## Turn a saved sketch into a solid

With a saved sketch selected in Feature History, **Extrude Selected Sketch**
opens the existing extrusion dialog directly in either Sketch or Part. The
selected profile is already filled in; enter the depth and Apply, or Cancel to
leave the saved design unchanged. This creates a separate extrusion feature,
not a replacement sketch or an automatic Add/Remove operation.
When launched from Sketch, successful Apply opens Part and focuses the solid.
Cancel or failed Apply stays in the original Sketch view. This handoff belongs
only to this shortcut; the ordinary Extrude command keeps its existing behavior.

The shortcut requires a closed profile in the current replay and the existing
supported-operation policy. An open or unsupported boundary shows its reason;
an unverified or stale result asks for Rebuild instead of claiming readiness.
A fully defined sketch is not necessarily a closed profile. Finish or cancel an
active/suspended draft or staged repair before this saved-sketch shortcut appears.
This is a source-development usability change, not a new qualified installer.

### Name a feature for its purpose

Select a feature in Feature History, then use the small text icon beside
**Selected:** to open **Rename Feature**. Enter a name and choose **Rename**;
**Cancel** leaves the model unchanged. Names may contain Unicode and spaces and
must be nonempty, at most 256 characters (the existing model-label contract).
Names are not unique identifiers: changing a label does not change its stable ID,
formulas, dependencies, dimensions, or the active output. The renamed feature
stays selected. Blender Undo/Redo restores/reapplies the label.

Finish any sketch draft or proposed edit before renaming. If the document,
selected feature, scene, runtime, or units change while the dialog is open,
reopen it. Rename uses the existing canonical replay/publication transaction,
not direct edits to cached history rows. It therefore currently replays the
model, even though the authored change is only a label; unchanged names are a
no-op. Focused source-loaded Linux checks cover label-contract tests, native
Cancel/no-op/stale guards/publication rollback/geometry preservation/Undo/Redo,
and actual GUI Cancel, Rename, Undo/Redo and the unclipped dialog. These bounded
checks do not establish installed-package, two-process persistence, full-suite
or Windows qualification.
