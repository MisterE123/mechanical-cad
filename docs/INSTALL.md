# Current integrated build

The current source version is 0.9.0. Use the matching integrated installer, not an older backend with these tools. The native integration baseline is Blender 5.2.2 LTS on Linux. Windows remains deferred. A compact installer contains all runtime files and notices; corresponding sources may be a separately named companion in the same Library location, not an extra installation step. Read MATERIALS.md in the delivered package.

The historical instructions below describe previous releases and development setup.

# Installation: delivered 0.7.1 and the 0.8.0 development candidate

**0.7.1 is the delivered standalone preview**, including checked Assembly STEP.
Its bounded Linux install, export, joint-edit and save/reopen GUI workflow passed.
**0.8.0 adds visual fixed/slider connector placement**; its exact installer and
interactive qualification are pending. See [0.7.1 scope](RELEASE_071.md),
[0.8.0 status](RELEASE_080.md) and [distribution materials](STANDALONE_DISTRIBUTION_MATERIALS.md).

## Standalone: one offline Linux extension ZIP

The ordinary installation uses native **Blender 5.2.2 LTS on Linux x86_64** and
the complete platform-specific extension ZIP. These steps apply to delivered
0.7.1; the exact 0.8.0 candidate still requires its own qualification:

1. In Blender Preferences, use **Install from Disk** on the extension ZIP.
2. Enable **Mechanical CAD** and wait for automatic offline backend
   preparation to report Ready.
3. Open **CAD Workspaces**, create a document, then sketch and extrude a Part.
4. Follow [the box-and-sector project](BOX_SECTOR_PROJECT.md) for reusable Parts,
   explicit joint placement, pose checks, save/reopen and individual-Part export.
5. In 0.7.1, a complete passing current-pose check enables
   [Export Assembly STEP](ASSEMBLY_STEP_EXPORT.md), preserving reusable Part
   definitions and named placements. This action is absent from delivered 0.7.0.

The isolated Python/CAD backend is included. Do not extract another source tree,
install Python or dependencies, run a package manager, download a runtime, or set
manual backend paths for this standalone flow. Those steps below describe the
historical source-based installation only. Windows testing is deferred and its
public execution path remains disabled; no Windows qualification is claimed.

## Historical 0.6: Linux development preview only

The delivered 0.6 archive is a project package, **not a Blender installer**. Extract
the outer archive. The ZIP under `distribution/` ending in `-blender-addon.zip`
is the interface installer; keep that inner ZIP zipped when using Install from Disk.
It is a legacy add-on package and has no `blender_manifest.toml`.

That release requires both its matching source/environment and its interface ZIP.
The setup below documents the qualified Linux x86_64, Python 3.12, Blender 5.2.2 LTS
flow. **The delivered backend explicitly rejects Windows. Do not install its Python
dependencies expecting a Project Root correction to make it work on Windows.**
Windows qualification is deferred. Its public execution path stays disabled;
there is no Windows usability claim.

0.6 supports bounded arc build/edit/save, with arc Geometry Check/export/Assembly
capture blocked. See [its exact scope](RELEASE_060.md) and [verification](VERIFICATION.md).
These documentation corrections do not change previously delivered archive bytes.

After the Linux dependency installation below, run
`.venv/bin/python scripts/verify_sidecar_install.py --project-root "$PWD"`. Require
`ok: true`, core `0.6.0`, cyclic rejection `solver_dof_indeterminate`, and the
successful two-DoF acyclic control when using that release's matching source.
The current 0.8.0 source verifier instead requires core `0.8.0`; never mix
source, add-on or backend versions. The per-operation capability and evidence
checks still run; a setup verification cannot replace them.

## Historical 0.6 setup, step 1: restore source and history

Extract `source.zip` into a permanent folder. It has no enclosing directory: the
folder containing `pyproject.toml` and `src/mechanical_cad` is the Project Root.
Alternatively, clone the supplied full-history Git bundle:

```sh
git clone mechanical-cad-0.6.0-COMMIT-history.bundle mechanical-cad
cd mechanical-cad
```

Use the supplied file's actual commit suffix. A bundle clone records a local-file
origin; it does not publish a repository. Git is optional for an extracted source
checkout. Keep the earlier 0.1 archive if you want that exact historical version.

## Historical 0.6 setup, step 2: install the sidecar

From the source directory:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[dev,sketch]'
.venv/bin/python scripts/verify_sidecar_install.py --project-root "$PWD"
.venv/bin/python -m pytest -q
```

The `sketch` extra installs pinned `slvs==3.2`. It is required for the constrained viewport
sketch workflows, but not the older primitive-only documents. Native libraries
must stay in this environment, not Blender's Python.

Retain the Linux source and environment together when moving the project, and
update Blender's configured absolute paths. These legacy steps do not provide a
Windows installation route.

## Historical 0.6 setup, step 3: install the interface

In Blender Preferences → Add-ons, use **Install from Disk** for the supplied
`...-blender-addon.zip`, then enable **Mechanical CAD**. Expand its
preferences and set:

- **Python executable:** absolute path to the sidecar `.venv/bin/python`.
- **Project root:** absolute directory containing `pyproject.toml` and `src`.

These preferences select trusted local code to execute. There is no network
listener, automatic download or remote shell.

In a 3D Viewport, press **N**, select the **CAD** sidebar tab, and choose
**Open CAD Workspaces**. F3 → **Open CAD Workspaces** is an alternate route.
Setup creates owned Sketch, Part and Assembly tabs without replacing existing
user workspaces. The tabs share a scene; Part and Assembly keep separate canonical
documents, and assemblies embed explicit accepted Part revisions.

The add-on requires Blender 5.2 or newer. If installation reports an older
Blender version, use the qualified 5.2.2 LTS runtime. Do not bypass the version
check: cancellable checks depend on its native exit-cleanup handler. Later Blender
versions and non-Linux setup flows still need their own project qualification.

## Draw a circle and edit its radius directly

1. In Part, choose **New CAD Document** if no document is open.
2. Choose **New Sketch**, then **Circle** on the left. Click its centre and rim.
   The pointer outline is unverified; the accepted circle runs a native solve.
3. Choose **Dimension** or press **D**, select the circle, then place its label.
4. Double-click the radius label. Enter **10**, then press Enter. Wait for the
   checked acceptance; the label drives a 10 mm radius, not a 10 mm diameter.
5. Choose **Finish Sketch**. In Part choose **Extrude**, confirm the same profile,
   enter **10 mm**, and Apply. Expected volume is **1000π mm³**.
6. Select that sketch in history and **Edit Sketch**. Double-click its restored
   label, change radius to **15**, accept, then Finish. The same extrusion updates
   to **2250π mm³**; feature IDs remain unchanged.

Named parameter formulas work in the same compact field, for example `radius * 2`
when a project parameter named `radius` exists. Enter requests one acceptance;
invalid raw text stays editable. Esc cancels the field; clicking outside retains
it for **Reopen Input**. Dragging a label changes only its annotation position.
Saved `.blend` files retain placements; portable `.mcad.json` keeps design data.

The general editor temporarily hides mesh context in this viewport. Its prior
filter is restored on exit. **Check** shows current solver DoF. A successful open
connected line chain can Finish as editable data without an extrudable profile;
closed simple loops and single circles can supply profiles. Underconstraint is
shown explicitly and is not automatically a failure. See the complete bounded
[Line/Circle workflow](GENERAL_SKETCH_WORKFLOW.md), including unsupported regions,
constraint controls and text accessibility limits.

## Explicit relations on a drawn sketch

For a step-by-step constrained plate, see [the parameter-driven example](CONSTRAINT_EXAMPLE.md).
Select a line, then use the contextual **Horizontal** or **Vertical** action.
Choose **Points** to select an endpoint explicitly, or use the inspector's exact
Start/End/Center control. Distinct overlapping points remain ambiguous.

- **Fix here** requires a current successful Check and pins the solved position.
- **Fix at origin** explicitly confirms moving the selected point to (0, 0) mm.
- **Remove relation** requires a successful Check and keeps solved release seeds.
- **Remove using authored positions** is separately confirmed recovery when no
  current solution exists. It preserves authored seeds; solving may move geometry.

The right **Sketch relations** inspector shows named relation identities and
local Undo/Redo. Failed checks may list diagnostic candidates, never an automatic
choice of what to delete. A new Check retires prior solve authority; failure or
cancellation leaves a recoverable unverified draft. See [the precise policy](CONSTRAINT_INSPECTOR.md).
The bounded sector workflow and current limits are linked from
[the 0.7.1 candidate notes](RELEASE_071.md). The [0.6 notes](RELEASE_060.md) retain
that historical release's narrower scope.
General Coincident creation remains unavailable.

## Use the constrained Rectangle shortcut

1. In Part, choose **New CAD Document** if no document is open.
2. Choose **Rectangle Sketch** from the Sketch tools. Hover reveals tool descriptions.
3. In Sketch, click two opposite corners on global XY. This is an **unverified
   temporary preview**, not yet saved geometry.
4. Press **D** or choose **Dimensions**. Set width **40** and height **30** mm.
   Typed decimals and supported formulas remain full-precision text.
5. Leave **Fix rectangle position** enabled for a fixed lower-left corner. Turning
   it off removes the anchor relation and allows translation. The location readout
   identifies the corner being fixed; this need not be the first clicked corner.
6. **Apply Dimensions** validates the draft using the real solver. A successful
   fixed rectangle has **0 remaining DoF**; the free-position version has **2**.
   A changed/unverified preview never claims a current DoF count.
7. Press **Enter** or choose **Finish Sketch**. The validated feature is committed
   once, the document uses schema 2, and the Part workspace opens.
8. Choose **Extrude**, confirm the named sketch input, set **10 mm**, and Apply.
   The exact part volume is **12000 mm³**.

Leaving Sketch suspends an unfinished draft. Return to Sketch and choose **Resume**
or **Discard Draft**. Raw dimensions, including invalid text, are retained. A resumed
outline is unverified until Apply Dimensions or Finish runs a fresh check. Save the
`.blend` to preserve the draft across restarts; a `.mcad.json` saves committed design
history only. A changed base document blocks Resume rather than overwriting edits.
See [draft recovery](DRAFT_LIFECYCLE.md).

Viewport navigation remains available. If the view is edge-on to XY, use Numpad 7
for top view. Esc/Cancel discards the draft. Applying dimensions changes only the
draft; Finish changes saved design history. This shortcut is a constrained
rectangle tool; New Sketch opens the separate Line/Circle editor. Imported mirrored or
otherwise unsupported corner ordering is rejected rather than drawn incorrectly.

## Edit the same rectangle upstream

Select the rectangle in the right-hand feature history and choose **Edit Sketch**.
Change width to **60**, Apply Dimensions, then Finish. The existing extrusion
retains its feature ID and rebuilds to **18000 mm³**, rather than becoming a second
unrelated mesh. Dimensions and history remain editable.

Turning off Fix rectangle position on an unchanged, validated rectangle preserves
its current solved coordinates and changes only its remaining freedom. This
explicit edit reseeds the same corner IDs; Cancel preserves the original document.
A free rectangle's solve may change its position when dimensions change. Its
preview follows the actual solved coordinates. Re-enabling Fix rectangle position
pins the displayed current corner; it does not silently return to an old seed.

Invalid input keeps the committed model unchanged and retains your draft text for
correction. After an ordinary parameter edit outside a sketch, use Rebuild if the
status is Dirty. Blender Undo/Redo is session history; the feature list is saved
construction history. If Undo changes framing/isolation, use the visible **Focus Part**
button in Part. **Whole Scene** exits that viewport’s isolation without changing
other viewports or object hide flags. F3 did not find the CAD focus command in the
qualified 0.3 GUI; the visible buttons are the verified route. Consult the current
verification report for remaining UI limitations.

## Check, save and export

In delivered 0.7.0 and the 0.7.1 candidate, use **Check** in Part for supported
ordinary or bounded sector solids to obtain a fresh canonical geometry evaluation. The historical
0.6 release blocks arc/schema-3 checks and exports. The **Export**
menu provides **STEP** and **STL** file selectors, including normal overwrite
confirmation. Finish/cancel an active draft, or resolve a suspended draft first; exports never use a preview or
last-good stale mesh. If validation fails, an existing destination is preserved.
A lost subprocess reply is labeled an **unconfirmed export outcome**, because an
atomic file replacement may already have happened; inspect the file before retrying.

Use Tools & Document → **Save Document** for portable `.mcad.json` design
history. A `.blend` also stores that history and display cache; reopening marks
cached geometry unverified until regeneration. Keep JSON alongside the `.blend`.

STEP carries precise solids, not this application's feature history. STL carries
triangles without units/history; import it as **millimetres** elsewhere. Export
rejects invalid/multiple solids, non-watertight meshes and excessive binary32 STL
coordinate distortion. These checks do not certify manufacturing, fit, loads or
safety. See [geometry actions](GEOMETRY_ACTIONS.md) for tolerances and file guarantees.

CLI equivalents remain available from a separately restored matching source environment:

```sh
.venv/bin/python -m mechanical_cad.cli check-geometry examples/constrained_plate.mcad.json
.venv/bin/python -m mechanical_cad.cli export-step examples/constrained_plate.mcad.json plate.step
.venv/bin/python -m mechanical_cad.cli export-stl examples/constrained_plate.mcad.json plate.stl
```

## Reuse the Part in an assembly

For a supported ordinary or bounded sector Part in delivered 0.7.0 or the 0.7.1
candidate, choose **New Assembly from Part**, name the first instance, and
explicitly ground it.
Historical 0.6 arc/schema-3 capture and updates remain blocked. Add named
literal mate frames, then use **Insert Child
Instance** to reuse that Part with a fixed, revolute or slider relationship.
Choose a saved verification preset before interpreting a check as a pass. Without
a selected preset, results are measurements only.

In 0.7.1, Replay and Check Pose, then use [Export Assembly STEP](ASSEMBLY_STEP_EXPORT.md)
after a complete passing current-pose check. Export freshly rebuilds the accepted
Parts and repeats that check. The file preserves reusable definitions and
placements; Parts are not fused and no Assembly STL action is included.

Follow [the full bounded assembly walkthrough](ASSEMBLY_WORKFLOW.md) for explicit
source updates, named clearance requirements, listed-pose sampling, separate
assembly files and recovery. Sampling does not move the accepted design and does
not establish clearance between samples. The [clevis example](CLEVIS_EXAMPLE.md)
provides an editable benchmark with analytic expectations.

## Existing primitive workflow and recovery

The regular-Blender CAD panel retains Rectangle/Circle primitives,
Extrude and explicit Base/Tool Cut operations. **New Demo** creates the historical
40 × 30 × 10 mm drilled plate with a radius-4 mm bore, volume
11497.345175425633 mm³. The new viewport editor does not automatically convert
those primitives, arbitrary imported sketches, or the eight-endpoint backend
example into its own rectangle definition.

A failed direct regeneration retains the trusted previous display as a visibly
STALE wireframe cache, excluded from rendering. Correct dimensions/dependencies
and rebuild. Failed creation/load transactions preserve the accepted document.
Blender mesh edits, parents, deforming modifiers and transforms are not CAD edits;
regeneration restores authoritative geometry. Use a separate mesh copy for artwork.

For the historical source-based installation, if the backend cannot launch,
verify both absolute preference paths and run a CLI replay. The standalone
extension uses its included backend and automatic preparation instead. Part
solves and authoring commits currently block synchronously for their bounded
operation; a process timeout prevents indefinite waits. Mouse movement
performs no native solve. Assembly Check/Sample run cancellably after workload
confirmation on the qualified LTS runtime. Timeout/Cancel preserves accepted data
and exposes the outcome; it never publishes a partial successful report. General
background regeneration and broader sketch/assembly tools remain later work.
