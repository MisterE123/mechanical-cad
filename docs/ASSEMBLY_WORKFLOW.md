# Bounded assembly authoring workflow

This development slice authors rooted fixed/revolute/slider trees from ordinary
user-created Parts. It is separate from the immutable 0.2 Part preview. The Part
feature graph remains canonical for each solid; the assembly has its own canonical
embedded-source snapshot. Blender meshes and object transforms are display caches.

## Create, reuse and mate

1. In **Part**, create a document, draw a rectangle (or another supported profile),
   and extrude it. Select the intended solid output. Give the Part a useful name.
2. In **Assembly**, choose **New Assembly from Part**. Name the assembly and first
   instance, then explicitly check **Ground first instance at world origin**.
   Apply captures the core serializer’s canonical Part snapshot without rewriting
   the working editor JSON. Existing assembly content
   is replaced only when Apply succeeds; save it first if it is needed.
3. Under **Reusable parts**, add named **Mate Frames**. Enter three comma-separated
   XYZ values in millimetres and three XYZ rotation values in degrees (X then Y
   then Z, right-hand rotations). Advanced mode accepts an already unit WXYZ
   quaternion. Unchanged orientation retains its exact saved quaternion and sign.
   Leave **Attach to stable planar face** off for literal part-local coordinates,
   or enable it and choose a named stable planar source face. In face mode XYZ and
   rotation are explicit face-local offsets: origin is the current face centroid,
   +Z its outward normal, and X the projected Part X (Part Y for near-X normals).
   Explicit **Update All Instances** resolves the current exact source face and
   moves the mate with it. Deleted, split, ambiguous or nonplanar support requires
   explicit reference repair; the last accepted assembly is retained on failure.
   Frames are shown as axes on every instance. Editing a
   reusable frame affects every instance of its definition.
4. Choose **Insert Child Instance**. Select a reusable definition, or explicitly
   choose **Capture working Part**. Choose the named parent instance, its named
   frame, the child's named frame, and a fixed, revolute or slider joint. Name the
   instance and joint. The child and incoming joint are committed together; an
   orphan child is never saved.
5. For moving joints, enter a coordinate and optionally strictly increasing
   limits. Revolute UI values are **degrees**; storage is **radians**. Slider values
   are **millimetres**. Motion uses the mate frame's right-hand local **+Z** axis;
   its XY axes determine zero rotation. No coordinate is silently clamped.
6. Use a joint's pencil button to edit its coordinate or limits. Use a named frame
   button to edit its coordinates or quaternion. Text-based numbers preserve
   untouched saved doubles; no mesh movement is interpreted as a canonical edit.

**Focus Assembly** frames all assembly instances and axes, including when a prior
Part local view hid them. **Whole Scene** leaves local view. New/Load enter the
Assembly workspace; opening an embedded source enters Part. These view changes
do not change unrelated object hide flags.

The first root is grounded at the identity world frame. This slice does not edit
root placement in the UI. Imported explicit ground placements remain intact.
Definitions can be reused across multiple instances. Different revisions of the
same source identity cannot coexist in this slice; create a separate new Part
identity for an independent design.

Every Apply submits a complete candidate to the isolated sidecar, validates its
response, stages every display object, then publishes the model and display in a
single reversible transaction. A failure leaves accepted model/display data
intact and shows the error. Dialog Cancel changes no canonical data. Open dialogs bind their originating
scene/window and exact Part/Assembly snapshots; switching to another scene or
changing those inputs requires reopening the dialog. Named history selections
highlight the corresponding owned instances and datum axes in the viewport. Any active
or suspended sketch draft blocks assembly editing, checking and saving until it
is explicitly finished, cancelled or discarded.

## Visual connector placement

The visual joint tool is the next development increment; its installed GUI
qualification is pending. The delivered 0.7.1 installer remains unchanged.

1. Replay the Assembly, then choose **Place Joint in Viewport**. Click the parent
   instance and then the child. The panel names the existing incoming joint that
   **Apply will replace**. The grounded root cannot be the child, and choosing a
   descendant as its parent is rejected.
2. Select **Parent handle** or **Child handle**. Drag its red, green or blue axis,
   or press **X**, **Y** or **Z** and type a distance in millimetres. The connectors
   are literal positions in the existing Part definitions. They are not attached
   to a picked face, mesh vertex or changing surface. **Pick surface** samples a
   visible point and tessellated normal on the selected instance as a literal
   connector suggestion. Local XYZ stays visible; subsequent Part edits do not
   make it follow the face. **Origin** resets the selected connector to Part origin.
3. Choose **Fixed** to align the connectors rigidly, or **Slider** to move the
   child along the parent connector's positive blue **+Z** axis. Enter a slide
   distance in millimetres. **Revolute** instead rotates about parent **+Z**; enter
   degrees in the Angle field or use the one-degree step buttons to preview motion.
   Canonical revolute coordinates remain radians. Changing joint kind resets its
   coordinate and limits rather than reinterpreting millimetres as radians.
   Direction buttons, **Flip** and **Roll 90°** orient the
   selected connector without quaternion entry.
4. The gold wireframe previews the child and its descendants. The accepted solids
   stay where they were until **Apply joint** finishes a fresh guarded replay.
   Editing one connector creates a separate literal frame when its original is
   shared, so another instance of the same Part does not move accidentally.
5. **Cancel / Esc** discards the whole preview. **Apply** creates one ordinary
   Blender Undo step. Use **Edit Connectors in Viewport** on a fixed, slider or revolute
   joint to change it later. A successful Apply provides a current display;
   **Check Current Pose** is still required before **Export Assembly STEP**.

Picking selects accepted meshes visible in this viewport and respects nearer
visible mesh occluders. Visible unsupported generated instances or non-mesh
surfaces ask you to use **Focus Assembly**; this is a display-interaction limit.

Middle-mouse navigation and the wheel remain available. An unfinished visual
preview is not saved as Assembly data. Loading, Undo/Redo, changing the original
scene/view layer, closing its viewport, or disabling the add-on ends that preview.
After reopening a saved project, Replay and Check explicitly restore current
evidence before export. Selecting an instance in history exposes **Place / Edit
Component**, which opens its incoming joint directly. Moving the parent connector
places the component and its descendants; the grounded root remains fixed.
Advanced literal-frame and motion-limit controls remain available separately.

## Working Part edits and all-instance updates

The working Part and assembly are deliberately separate. Editing Part does not
silently change assembly geometry. An **Update available** notice identifies
when that working Part differs from an accepted embedded source.

- A reusable Part's pencil button opens **Open Embedded Source as Working Part**.
  The dialog names the target source and current working Part. Save any working
  Part you need to retain, then explicitly confirm its replacement. Opening the
  source does not change the assembly snapshot.
- Edit source dimensions using ordinary Part tools. Return to Assembly and choose
  **Update All Instances**. The dialog lists the accepted source revision, the
  current raw working-draft fingerprint, and every affected named instance. Apply validates and replaces all affected
  instances transactionally. Cancel keeps the old accepted source.
- Literal frames keep their authored local coordinates. A numeric datum at
  Z=4 mm stays at Z=4 mm after changing a Part's thickness. No face attachment,
  midplane following, automatic datum repair or nearest-face guess is implied.
- Accepted source updates invalidate earlier verification. Inspect the new shape
  and literal axes, then explicitly check again.

## Saved verification intent

A saved **Verification Preset** is distinct from an active selected preset and
from the result of a check. Creating a custom preset does not automatically select it;
check **Make this the active verification preset** or use **Select Active
Verification Preset** explicitly. Saving/selecting never runs a check.

A clearance preset stores named instance-pair requirements with an engineering
minimum separation in **mm**. Editing a pair preserves its stable requirement ID
and all other pairs. Use an existing pair's button to edit it, or change its two
instance choices to add/update another pair. The explicit **Interference only**
alternative stores no clearance allowances; changing an existing preset to that
kind removes that preset's clearance pairs, as stated in the Apply dialog.

**Advanced numerical policy** is separate:

- Linear query tolerance: mm, default 1e-6
- Common-volume threshold: mm³, default 1e-9
- Tessellation deflection: mm, default 0.1

These finite-resolution query parameters are not engineering fit allowances.
Only the saved selected policy is used; no hidden ad-hoc override is added.
Without an explicit active preset, Check produces measurements and known
violations but cannot report a pass.

**Check Current Pose** freshly replays exact solids at saved joint coordinates.
For a new assembly without saved presets, **Set up standard checks** saves and
selects a strict interference-only preset (linear tolerance 1e-6 mm, volume
threshold 1e-9 mm³, tessellation 0.1 mm), using the existing cancellable replay
transaction. It does not check geometry, add contact exceptions, change replay
precision, or infer engineering clearance. Existing saved settings are never
overwritten or automatically selected. Custom clearance/contact requirements
remain optional in the collapsed check details.

Then **Check current pose** starts the asynchronous check directly, without a
second confirmation. Workload and scope remain available in status details;
Sample retains its explicit coordinate dialog. First-use standard checking is
two deliberate UI actions (setup, then Check), rather than the previous seven
(create preset, open kind menu, choose interference, activate, Apply, Check,
confirm). This is code-derived click counting, not measured user timing.
Setup and Check remain separate transactions; a cancelled Check retains saved
settings, while a cancelled/failed setup retains the original assembly.
On Blender 5.2 LTS, interactive Check and Sample run in an isolated cancellable
process while viewport navigation remains available. Use **Esc** or **Cancel Check**; a timeout or failed request stays explicit.
No partial response is published. The previous evidence remains historical and can
only stay current if its original input binding is still unchanged. Loading a file,
history changes, closing the originating window, or disabling the add-on cancels
pending work and retains cleanup supervision until its process is reaped. These
resource caps are not a claim that maximum-size models finish interactively.
The history pane separately reports whether evidence is current, whether it
passed, computational completeness, known interference, known clearance
violations and threshold contact. Known violations remain visible even when
other measurements are incomplete. Historical/stale evidence is labeled as such.
**Inspect Poses and Pair Measurements** uses Summary, Coordinates, Pairs and
Diagnostics sections in one read-only 600-pixel dialog. Choose a zero-based pose
and page. Each page has at most eight wrapped content lines (13 rows including
controls); long names and complete correction messages continue onto later pages.
The coordinate section separates requested/effective values. Pairs include named
distances (mm), common volume (mm³) and requirements. Display numbers are concise;
canonical report values remain unchanged. Changing section or pose resets only
the dialog's page number.

**Check Listed Joint Poses** takes 1–32 explicit comma-separated coordinates for
one moving joint, in the same mm/degrees UI units. Every sample preserves the
complete saved coordinate map for all other joints, including fixed zeroes. The
report retains requested/effective coordinates and each listed pose's result.
Sampling does not move the accepted display or change saved joint coordinates.
Out-of-limit samples are blocked, never clamped. Clear samples do not prove
clearance between them.

No check in this slice establishes continuous collision freedom, structural/load
capacity, physical fit or manufacturing certification. General closed-loop mate
solving, arbitrary mechanisms and swept-volume collision are outside scope.

## Portable files and recovery

**Save Assembly** writes a separate `.mcad-assembly.json` containing explicit
instances, joints, literal frames, presets and embedded unchanged Part snapshots.
No filesystem path in model JSON can cause hidden input or output. Save freshly
validates the snapshot, writes a temporary file in the selected directory, flushes
it and atomically replaces the destination. Failed validation or failed replacement
keeps the destination unchanged. Load validates and replays before acceptance;
a failed Load preserves the current assembly. Part `.mcad.json` files and Part
Save/Load remain separate.

After `.blend` reload, history changes or edited display caches, **Replay Assembly**
restores the disposable mesh/axes from accepted canonical data. Replay is not a
verification pass. Run an explicit Check to establish current evidence. Manually
moving, parenting, scaling or modifying instance meshes cannot alter the assembly
and makes their display untrusted. Unrelated scene objects remain untouched.

## Verification evidence

`tests/blender_assembly_authoring_smoke.py` uses native Blender 5.2.2 and the real
sidecar, creating an ordinary rectangle/extrusion through Part operators. It
exercises grounded capture, reuse, literal frames, slider/revolute authoring,
explicit preset selection, named-pair preservation, exact checks, whole-map
samples, source-open confirmation, all-instance updates, Cancel callbacks,
portable files, rejection preservation, draft blocking and the native-import
boundary. Require its `ASSEMBLY_AUTHORING_SMOKE_OK` marker with
`--python-exit-code 1`.

Headless operator and Cancel-callback tests do not establish interactive popup
usability, actual mouse Cancel/Escape, installed-ZIP integration or GUI Undo/Redo.
Those are independent review gates, as are platform qualification and broader
mechanism/geometry coverage.

`tests/blender_assembly_report_smoke.py` calls the actual report draw method with
a fake native-Blender layout: 16 instances, 15 joints, 120 pairs, 32 poses and long
full diagnostics. It checks all pages of every section for a maximum of 13 rows,
complete accessible text and zero report mutations. This is a draw-boundary test;
it does not claim a visual GUI review. Require `ASSEMBLY_REPORT_SMOKE_OK`.

## Associative face mate frames

Named frame authoring now supports stable planar face attachment independently
of the visual surface-snapshot picker. The optional canonical `support_face` is
a semantic identity on the definition's output solid; `placement` is its explicit
local offset. Old literal records retain their bytes and hashes. Assembly result3
replays source geometry, resolves the exact face, and supplies checked resolved
frames separately from canonical intent. No Blender display mesh can supply this
attachment. The visual surface-picker refuses editing an attached joint; use the
named Mate Frame dialog for its offset, or the joint-coordinate dialog for motion.

Focused checks: `tests/integration/test_assembly_face_frames.py` verifies native
source-height updates and unresolved-face repair;
`tests/blender_assembly_face_frame_smoke.py` exercises the actual Blender dialog
operator, fixed instance insertion, and explicit source update through the sidecar.

## Mate by Faces (development)

With a current assembly display, choose **Mate by Faces** under Tree joints.
Click a stable planar face on the parent component, then one on the child.
The child must be an existing non-grounded component; Apply replaces its existing
incoming joint (including explicit reparenting), never adds a second constraint.
Choose Fixed, Slider, Revolute, Cylindrical, Planar or Ball in the viewport.
Named motion axes and their limits remain unchanged while connectors move; use
the existing joint **Edit** dialog after Apply to edit those values. Scalar slide
and revolute motion also remain adjustable in the viewport. Kind changes that
would discard motion or limits are rejected. **Reset motion** explicitly zeros
all motion axes and removes all limits if that is the intended new setup.
Reparenting preserves the existing joint kind and motion, with an initial
connector offset that avoids moving the component before new face picks.

Each new pair starts at exact face centroids with deterministic in-plane axes:
parent +Z follows its normal, while the child connector is flipped to face it.
These are disclosed defaults, not inferred hole
centers or intended attachment points. Flip reverses +Z, Roll turns 90 degrees,
and dragging an RGB handle (or X/Y/Z followed by a number) authors an offset in mm.
Choose Parent/Child handle to edit either end; Pick face replaces that end's support.
Preview is unchecked; Apply freshly replays and atomically publishes the candidate.
Cancel or a stale binding leaves the accepted assembly untouched.

Semantic face IDs and face-local offsets persist, not mesh triangle numbers.
Reopening **Edit Connectors in Viewport** retains these attachments and offsets;
shared named frames are copied on write so reused siblings do not move. Supported
upstream changes move attached connectors with their faces. Missing, ambiguous or
nonplanar support fails visibly; there is no guessed or literal fallback. The
original literal **Place Joint in Viewport** workflow remains available.

Focused evidence: native replay tests in `test_face_mating_draft.py`, plus
`blender_face_mating_smoke.py` for actual accepted-mesh ray casts, preview/Apply,
Cancel/stale rejection and a separate-process save/reopen/edit. Headless adapter
checks do not establish manual mouse/GUI usability.

### Picking coincident components

Mate by Faces temporarily shows one named Assembly component at a time while
picking. The HUD states **Parent/Child: name (isolated)**; **Previous** and
**Next target** switch components without moving them. The first parent target
is the grounded root; the next step offers eligible children, excluding the root,
parent and any candidate that would form a cycle. Pick a face on each displayed
target, then all original per-view-layer visibility is restored for preview.
The same isolation applies when replacing a selected connector's support face.

This handles ordinary Fixed origin/origin inserts that occupy the same location.
No extra placement, coordinate or constraint is inferred. Cancel, rejected picks,
stale bindings and owner cleanup restore the original visibility, including
components that were hidden before the tool. Non-Assembly objects and collection
visibility are not changed. If a target is excluded by local view or a hidden
collection, the tool asks for Focus Assembly rather than overriding that state.

### Development contact defaults and preview outlines

Completing a new face pair starts both connectors at their face centroids and
flips the child connector 180° about its local X axis. Before existing authored
joint motion, this makes outward surface normals face one another rather than
point the same way. Flip reverses that default; Roll and offsets remain explicit.
No existing saved joint is automatically flipped on reopen. Replacing an already
attached connector's support retains its face-local offset and orientation.

The unchecked preview draws face boundaries/seams rather than same-face
tessellation diagonals, using the same outline helper as extrusion previews.
Unknown face IDs retain edges conservatively, and very large previews remain
sampled to the existing display budget. This is a placement preview, not a
collision/contact/clearance test; arbitrary faces, offsets or existing motion
can still produce intersecting bodies. Run the existing explicit pose checks.

## Gear coordinate relations (development)

Use **Gear coordinate relations → Add Gear Relation** to explicitly couple two
existing revolute joints. Choose the driver/driven joints, signed ratio and phase
in degrees; **Keep current alignment** calculates phase only when requested.
Driven angles are visibly read-only, while their limits stay editable. Edit or
sample the independent driver to move followers on all assembly branches.
Remove releases the follower at its current angle without a pose jump.

Geared assemblies currently use named Mate Frame edits, not viewport connector
or motion preview. This is a coordinate relation, not tooth contact or closed-loop
solving. See [full bounded workflow and persistence contract](ASSEMBLY_GEAR_RELATIONS.md).

### Responsive explicit Replay (development)

Replay now starts a cancellable native sidecar job instead of blocking Blender
while rebuilding the accepted Assembly. Navigate while waiting; the panel shows
elapsed time and **Cancel Replay**, and Escape cancels. No collision/interference
check runs automatically. Successful Replay refreshes the geometry and marks it
unchecked, retaining the existing save path.

Pending work changes neither accepted canonical data nor display/check authority.
Cancellation, history or context changes reject late results. Replay after
Undo/Redo captures the exact currently accepted Assembly; repeated clicks cannot
launch a second owner or invalidate the running one. This uses the existing
execution lease, candidate publication guards and lifecycle cleanup supervisor.
Internal synchronous authoring helpers are unchanged; other assembly edits and
exports are not made asynchronous by this change.

Focused evidence: `tests/blender_assembly_replay_async_smoke.py` exercises native
sidecar completion, running cancellation, ready-result rejection, repeated clicks,
real Undo/Redo and default gear replay. Its background modal pumping is not a
claim of real GUI redraw, ZIP installation or Windows qualification.

Invocation timing measures only return to the modal event loop, not complete
native replay or final mesh publication. The new path does not automatically
rebuild after Undo/Redo: the user explicitly presses Replay. Native geometry
runs in the sidecar; final Blender display publication still runs on the main
thread and may take time for large meshes.

### Standard first-check validation

The bounded first-check pass covers 109 focused unit tests (candidate editing,
primary actions, invocation, busy admission, cancellation/stale candidate guards
and publication binding). `tests/blender_assembly_standard_check_smoke.py` passed
in native Blender 5.2.2 background mode, including cancelled/stale setup,
repeated setup/check actions, exact saved preset/report binding and retained
save path. Background Blender bypasses normal invoke dispatch, so that smoke
uses a registered probe entering the production invoke method explicitly.
This does not establish interactive GUI, Undo/Redo, fresh-process persistence,
ZIP installation, Windows compatibility, a full regression pass, or latency.
