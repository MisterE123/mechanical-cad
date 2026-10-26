# Mechanical CAD for Blender

An ongoing GPL-3.0-or-later project for parametric mechanical CAD inside Blender.
**1.0.0 is the first packaged usable-workflow release.** It provides
editable constrained sketches, exact solid modeling and mechanical assemblies
inside Blender. It does not claim complete Onshape feature parity. The earlier
frozen 0.9.x packages remain unchanged. See [1.0 scope and evidence](docs/RELEASE_100.md)
and [current limitations](docs/INTEGRATED_MODELING.md).

Release infrastructure now includes [checksum-locked Linux runtime acquisition](docs/RUNTIME_ACQUISITION.md),
an [offline tag-bound candidate builder](docs/RELEASE_CANDIDATE_BUILDER.md)
and [exact-installed standalone smoke harness](docs/STANDALONE_QUALIFICATION.md).
The read-only release-readiness workflow runs regressions; it does **not** publish
releases. Complete-source, runtime/material, and native-platform admission gates
remain required before a tagged-main candidate can become a release.

Development also adds [contextual arc captions](docs/QUIET_SOLVED_ARCS.md):
current solved arcs stay compact until selected, with dimensions and actionable
unverified/discrepancy guidance retained. GUI qualification is pending.

Post-1.29 development adds [whole-Assembly source-update preview](docs/ASSEMBLY_SOURCE_UPDATE_PREVIEW.md):
review changed reused-Part geometry and mate placement before one atomic Apply.

Post-1.29 development also fixes [Assembly component selection context](docs/ASSEMBLY_COMPONENT_CONTEXT.md):
viewport selection now determines contextual actions and insertion parent without
changing model data.

Post-1.29 development adds [independent slider motion preview](docs/SLIDER_MOTION_PREVIEW.md)
with explicit millimetres, full-assembly ghosts and authored limits. Native checks
pass; GUI Apply/Undo verification is pending specific QA approval.

The **1.29.0 Linux editing-flow checkpoint** is in preparation. It adds stable
Edit Feature history selection, safely attributed primitive-circle expression
draft recovery, stored parameter context, explicit Focus Preview, and direct
initial depth entry from a selected sketch. See [scope and qualification limits](docs/RELEASE_129.md).

The frozen **1.28.0 Linux editing-usability checkpoint** has bounded exact-installed
radius/shared-tool, Undo/Redo and saved-model verification. It is not a full-suite
pass or Windows qualification. See [1.28 scope](docs/RELEASE_128.md); its archive
remains unchanged.

The **1.27.0 Linux reference/usability checkpoint** is in preparation. It adds
explicit fractional quantities with units, stable circular-arc solid-edge
projection, and intentional retired radius-label presentation after Restore.
See [1.27 scope and evidence boundaries](docs/RELEASE_127.md). Qualification is
pending until exact-installed native and actual GUI checks complete. Previous
archives remain unchanged. Recovery remains OFF by default; the intermittent
native allocator crash remains unresolved.

The **1.26.0 Linux feature checkpoint** adds adjacent sketch fillets and
Restore Sharp Corner. Explicit reciprocal intent supports all four corners;
restoration preserves original witnesses, dimensions and retained placement.
See [1.26 scope and evidence boundaries](docs/RELEASE_126.md). Older readers
reject new metadata/opcodes. Recovery remains OFF by default; the intermittent
native allocator crash remains unresolved.

The **1.25.0 Linux feature checkpoint** adds direct Sketch Corner Fillet with
persistent explicit corner intent and guarded radius editing. Gear-pair Edit and
source-Part actions are promoted to primary Assembly controls. See
[1.25 scope and evidence boundaries](docs/RELEASE_125.md). Older strict readers
cannot open the new fillet metadata. Recovery remains OFF by default; the
intermittent native allocator crash remains unresolved.

The **1.24.0 Linux usability checkpoint** adds Circle center → Tab literal
Diameter creation, explicit diameter annotation editing with canonical radius
preserved, and compact optional recovery details. See
[1.24 scope and evidence boundaries](docs/RELEASE_124.md). Recovery remains OFF
by default; the intermittent native allocator crash remains unresolved.

The **1.23.1 Linux development checkpoint** adds [optional local recovery](docs/LOCAL_RECOVERY.md)
for unsaved Part data and supported raw sketch intent. It defaults off, stores
unencrypted bounded local copies only after opt-in, and restores explicitly into
a new unsaved Scene. This best-effort feature does not fix the unresolved native
allocator crash or guarantee zero loss. See [1.23.1 scope and evidence boundaries](docs/RELEASE_1231.md).

The **1.22.0 Linux development checkpoint** improves sketch input: corrected
first Hole face guidance, explicit Shift H/V Line constraints and selected
read-only badges, and Tab-driven positive literal/unit Line length with an
editable distance dimension in one atomic command. Pending raw length intent
survives save/reopen; verified open sketches receive informational guidance.
See [1.22 scope and evidence boundaries](docs/RELEASE_122.md).
Creation formulas are not supported; use the existing Dimension editor afterward.
Older installers cannot Resume the new pending intents or journal opcodes.
The intermittent native allocator crash remains unresolved.

The **1.21.0 Linux development checkpoint** adds a saved-sketch Extrude
shortcut with profile guidance and successful transition to Part, contextual
history controls, visible-label/ID history search and guarded label-only Rename.
An imported mounting-adapter example and presentation scripts are also included.
See [1.21 scope and evidence boundaries](docs/RELEASE_121.md).
Exact installed background smoke is distinct from source-loaded GUI observations;
no full historical-suite, exhaustive GUI or Windows qualification is claimed.

The **1.20.0 Linux development checkpoint** adds sketch-point reuse hover,
compact successful geometry reports, named fresh-Part starts and clearer status
copy, guarded Assembly source-Part editing, explicitly unlinked copied-face
sketch planes and a one-time normal offset for fixed sketch planes.
See [1.20 scope and evidence boundaries](docs/RELEASE_120.md).
Source-loaded GUI observations and exact installed-archive checks are separate;
this is not exhaustive GUI, Windows, or full historical-suite qualification.

The **1.19.0 Linux development checkpoint** adds direct history-row editing,
compact support explanations and empty-document starters, clearer Assembly copy,
and a focused three-tool empty Part palette with the full menu retained.
Call-local presentation work and receipt validation avoid duplicate processing;
this is not a measured end-to-end speedup claim or a geometry feature expansion.
See [1.19 scope and evidence boundaries](docs/RELEASE_119.md).
This is a bounded checkpoint reconstructed from retained source patches after a
workspace refresh, not a full historical-suite release. Previous delivered
artifacts, including Linux 1.18 and Windows 1.16, remain unchanged. Windows 1.19
and exhaustive interactive GUI/Undo qualification are not established.

The previously delivered **1.15.0 Windows development build** integrates guarded bundled Windows runtime
support with the existing responsive Replay and editable gear-pair workflows.
Fresh bundled Windows preferences use a finite 240-second operation deadline;
Linux retains 60 seconds and saved user choices are not overwritten.

The previously delivered Linux checkpoint was **1.16.0**. The exact Windows
1.15 installer passed bounded native Blender creation, cancellation, Replay,
gear-pair editing, export and independent reopening checks on Techbox.
Windows interactive GUI and Undo testing are not established. See
[1.15 scope](docs/RELEASE_115.md) and [Windows delivery evidence](docs/RELEASE_115_WINDOWS.md).

Source development also adds [Sketch Corner Fillet](docs/SKETCH_CORNER_FILLET.md):
select two shared-corner lines, preview a radius, then Apply one tangent-arc edit.
The original dimensionable corner is retained, and persistent bounds reject flipped
or excessive radius edits. This is a separate unreleased development feature.

Source development also adds [explicit Line axis lock](docs/LINE_AXIS_LOCK.md):
hold Shift for the second endpoint to create a lasting Horizontal/Vertical
constraint in one Undo step, or release Shift for a free line.
Press Tab after the first Line point for a [driving literal length](docs/PENDING_LINE_LENGTH.md),
created with its editable dimension in one guarded Undo step.
After choosing a Circle center, press Tab for a [driving literal diameter](docs/PENDING_CIRCLE_DIAMETER.md),
with its canonical radius driver created in one guarded Undo step.

Post-1.19 source development also offers an explicit
[unlinked copied face plane](docs/COPIED_FACE_PLANE.md) for a new sketch.
It does not establish stable imported-face identity or change the frozen release.

See [simple and counterbored round holes](docs/ROUND_HOLES.md),
[ordered multi-section Loft](docs/MULTI_SECTION_LOFT.md),
[explicit multiple-edge blends](docs/MULTIPLE_EDGE_BLENDS.md),
[reference dimensions](docs/REFERENCE_DIMENSIONS.md) and
[staged edit recovery](docs/STAGED_EDIT_REPAIR.md).

See [printable spur gear pair configurator](docs/GEAR_PAIR_CONFIGURATOR.md),
[typed unit input](docs/UNIT_INPUT.md) and
[successive-Cut support](docs/regressions/topology/support/MCAD-TNP-SUPPORT-003.md).

See [extrusion end conditions](docs/EXTRUSION_END_CONDITIONS.md),
[gear relations](docs/ASSEMBLY_GEAR_RELATIONS.md), and
[multi-source projection](docs/MULTI_SOURCE_PROJECTION.md),
[Sweep placement](docs/SWEEP_PLACEMENT.md) and
[history rebuilding](docs/HISTORY_REBUILD.md),
[unapplied edit repair](docs/STAGED_EDIT_REPAIR.md),
[visual reselection](docs/VISUAL_FEATURE_RESELECTION.md), and
[projection reference repair](docs/PROJECTION_REFERENCE_REPAIR.md).

The source package dependency pin now matches the bundled OCCT version
`cadquery-ocp-novtk==8.0.1.1.0`. Earlier 1.2/1.3 source metadata accidentally
changed this dependency with the application version; their self-contained
installers retained the correct bundled runtime and are unaffected.

## Current workflow

Use Sketch → Part → Assembly to create your own designs, revise upstream
parameters, rebuild, check exact geometry, save/reopen and export STEP/STL.
The feature graph is canonical; Blender meshes are display caches. Native OCCT
and SolveSpace execute in an isolated bundled Python sidecar, never in Blender.

The current feature set includes analytic sketches with holes, datum planes,
construction and driving dimensions/relations, freely drawn associative
planar-face sketches, booleans, revolve, selected-edge blends, patterns, shell,
loft and planar line/arc-path sweep. Self-contained single-solid STEP import preserves the
source bytes within the document. Reusable Parts feed fixed/revolute/slider/cylindrical/planar/ball assemblies
with visual and associative planar-face connectors, pose checks and named-instance STEP export.

Start with [everyday modeling](docs/EVERYDAY_MODELING.md).
See [scope and remaining limitations](docs/INTEGRATED_MODELING.md),
[solid features](docs/CONNECTED_PART_MODELING.md),
[sketch relations](docs/SKETCH_RELATIONS.md),
[trim/extend](docs/SKETCH_TRIM_EXTEND.md), and
[assembly workflow](docs/ASSEMBLY_WORKFLOW.md).

## Installation and verification

The distribution target remains one offline Install from Disk extension ZIP for
Linux x86_64 and Blender 5.2.2 LTS, with automatic backend setup. A compact
installer may provide corresponding sources in a same-location companion archive;
the companion is not an additional installation step. Consult MATERIALS.md in
the actual package. Windows 1.16 has a separate offline installer with bounded
background qualification under the registered Techbox launcher. Ordinary Windows
launchers and interactive GUI remain unqualified; see the Windows delivery receipt.

Development feature tests and native Blender operators have been exercised;
current GUI and broader regression results are reported separately. Never infer
an untested platform or manufacturing certification from successful tessellation.
Local Git tracks this project's source. There is no telemetry or automatic
publication of user model history, and no GitHub publication is configured.

## Try it

Use **Blender 5.2 or newer**; the qualified runtime is native **5.2.2 LTS** on
Linux x86_64. Earlier Blender versions are rejected by the add-on metadata;
they lack the native exit-cleanup hook required by cancellable checks.
Follow [installation and the first-part walkthrough](docs/INSTALL.md), then
[draw and directly dimension a sketch](docs/GENERAL_SKETCH_WORKFLOW.md), then
[create and verify an assembly](docs/ASSEMBLY_WORKFLOW.md).

From the separately restored source:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[dev,sketch]'
.venv/bin/python -m pytest -q tests/integration tests/unit/test_assembly*.py \
  tests/unit/test_solid_feature_edit.py tests/unit/test_history_edit.py \
  tests/unit/test_document_paths.py tests/unit/test_position_relation_selection.py \
  tests/unit/test_addon_architecture.py
.venv/bin/python -m mechanical_cad.cli replay examples/viewport_rectangle.mcad.json
```

This is the current modeling/assembly behavioral-check scope, not the entire
inherited regression suite. Actual Blender installer, UI and save/reopen
qualification are separate. Historical hash-bound source-audit expectations
remain interleaved with older meaningful tests; they are not silently excluded
and should not be interpreted as qualification of a different source revision.

`examples/circle_sketch_part.mcad.json` is a radius-driven exact disk.
`examples/open_line_sketch.mcad.json` is a saved open chain with no solid.
`examples/viewport_rectangle.mcad.json` is the editable rectangle example.
`examples/drilled_plate.mcad.json` retains the primitive-and-bore example.
The [clevis hinge benchmark](docs/CLEVIS_EXAMPLE.md) provides three editable Parts,
explicit mate frames, saved clearance requirements and seven named sample poses.
It is a reproducible canonical example, not a claim that every feature was drawn
through the current viewport sketch tool.

## Verification and documentation

The integrated candidate retains the bounded
[directed-arc core](docs/ARC_CORE_MILESTONE.md), native sector construction,
[data-only solve/replay service](docs/ARC_SECTOR_DATA_SERVICE.md), and reviewed
[live-owner boundary](docs/ARC_AUTHORING_OWNER_MILESTONE.md). The
[0.7.1 release notes](docs/RELEASE_071.md) describe checked Assembly STEP and
distinguish source-loaded checks from pending exact successor installer/manual-GUI
qualification and distribution clearance. The delivered 0.7 archive remains
unchanged.
Historical [0.6.0 notes](docs/RELEASE_060.md) describe its narrower build/edit/save
scope; they do not define the successor's current capability set.
The [backend capability boundary](docs/BACKEND_CAPABILITY_MILESTONE.md) carries
per-operation evidence through every production Blender owner. The exact 0.5.2
package completed its bounded installed-GUI mismatch/recovery review; its
immutable qualification record is separate from this new authoring work.

The pinned sidecar uses CPython 3.12, `cadquery-ocp-novtk==8.0.1.1.0` and optional
`slvs==3.2`. Current 1.18 Windows/macOS installation and later Blender releases are unqualified;
earlier Windows 1.16 has separate bounded evidence described above.
[Verification](docs/VERIFICATION.md) separates automated native tests, actual
source-loaded GUI review and exact installed-package evidence. Tests establish
bounded cases, not all possible mechanical designs or manufacturing safety.

- [Architecture and invariants](docs/ARCHITECTURE.md)
- [Assembly authoring and source updates](docs/ASSEMBLY_WORKFLOW.md)
- [Part format and process protocol](docs/FILE_FORMAT.md) · [Assembly format](docs/ASSEMBLY_FORMAT.md)
- [Geometry checks and Part export](docs/GEOMETRY_ACTIONS.md)
- [Sketch workflow](docs/GENERAL_SKETCH_WORKFLOW.md) · [Sketch solver](docs/SKETCH_SOLVER.md)
- [Draft recovery](docs/DRAFT_LIFECYCLE.md) · [Annotation layout](docs/SKETCH_ANNOTATION_LAYOUT.md)
- [Interaction contract](docs/UX.md) · [Roadmap](docs/ROADMAP.md)
- [Regression catalog](docs/regressions/README.md)
