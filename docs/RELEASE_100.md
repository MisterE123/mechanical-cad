# Mechanical CAD 1.0.0

## What is included

- Sketch, Part and Assembly workspaces; contextual icon tools, hover explanations,
  editable history and paged in-dialog help. The full palette adapts to shorter
  viewports without reducing its click targets.
- Lines, circles and analytic arcs; driving dimensions and formulas; common
  positional, equal, parallel/perpendicular, concentric and tangency relations;
  construction geometry, basic line trim/extend and local Undo/Redo.
- Datum-plane and freely drawn associative planar-face sketches. Projected
  construction references follow earlier sketch geometry rather than freezing it.
- Extrusion, one-step Add/Remove extrusion, Boolean tools, revolve, selected-edge
  fillet/chamfer, transforms, solid patterns, repeated-hole patterns, shell,
  two-section loft and line-path sweep.
- Embedded single-solid STEP import, exact geometry checks, STEP/STL export,
  upstream edits and save/reopen without the original imported source file.
- Reusable Parts and fixed, revolute, slider, cylindrical, planar and ball joints;
  named frames, associative planar-face connectors, independent coordinates and
  limits, discrete pose checks, named-instance STEP export and explicit
  component-branch removal with verification-policy impact preview.
- One offline Linux extension ZIP with automatically prepared bundled backend.
  A corresponding-source companion is available; it is not an installation step.

## Honest operating limits

The target checked here is Blender 5.2.2 LTS on Linux x86_64. Windows execution
remains deferred at the user's direction; later patch releases are not claimed
qualified by these checks.

Parts produce one connected solid. Assemblies are rooted trees, not general
closed-loop solvers. Listed-pose clearance/interference reports are not continuous
collision, dynamics, structural strength or manufacturing certification. Ball
limits bound XYZ Euler components rather than a cone angle.

STEP import is limited to 512 KiB and one valid closed solid. Imported faces are
snapshot handles, not invented persistent semantic supports. General spline
sketching, arbitrary solid-edge projection, general constrained trim, curved sweep
paths, multi-section lofts and drawing sheets are not part of this release.

## Verification evidence and its scope

The combined current-modeling/assembly behavioral command documented in README
passed **2,035 tests** on the integrated feature code after the canonical snapshot
fix. Whole-tree Ruff checks also passed. This is not a claim that the entire
inherited historical source-audit suite is green. Legacy audit expectations are
retained rather than hidden or misrepresented.

Native Blender processes exercised face attachment, projected references,
constraint Apply/Remove/Undo/Redo, Add/Remove extrusion, repeated holes, STEP
import without its original file, all new joint coordinates, component removal,
and fresh-process persistence. Exact bundled-backend checks are separate from
source-environment tests.

Ordinary installed 0.9.2 UI exercised the mouse-authored face-hole Part, source
thickness editing, assembly capture/reuse, cylindrical motion editing, component
removal, explicit current-pose measurement and portable assembly save/reopen.
That package contains the same modeling features. The successor additionally
fixes data-only snapshot validation and broadens the assembly JSON browser filter.
Package-specific identity and installation evidence is delivered separately
with the artifact, rather than inferred from these source-contained notes.

Use [Everyday modeling](EVERYDAY_MODELING.md) for the normal workflow and
[Joint types](ASSEMBLY_JOINT_TYPES.md) for coordinate conventions. Source history
is maintained in Git. No GitHub publication or telemetry is configured.
