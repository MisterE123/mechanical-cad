# ADR 0001: Geometry, constraints, and document ownership

Date: 2026-10-16  
Status: OCCT/OCP selected and exercised; sketch solver proposed, not integrated.

## Decision

Use **Open CASCADE Technology (OCCT), through the thin OCP Python bindings**, in
an isolated CPython worker. The initial dependency is
`cadquery-ocp-novtk==8.0.1.1.0`. Keep our feature document, parameter expressions,
transactions, replay, semantic references, and Blender interaction in small
application-owned modules. Blender meshes are disposable views of the B-rep.

This is a pragmatic complexity boundary, not a claim that OCCT is a small or
simple library. Its substantial C++ geometry algorithms can be modified under
their license, but debugging a difficult Boolean or fillet can require specialist
kernel knowledge. A narrow, tested adapter keeps that complexity out of ordinary
feature and interaction code. OCP deliberately supplies bindings rather than an
additional modeling framework. See [OCP's stated scope](https://github.com/CadQuery/OCP).

The isolated worker avoids coupling native CAD dependencies to Blender's embedded
Python ABI and reduces the consequences of native crashes. It adds a process,
serialization, cancellation, and packaging boundary that must be tested. It does
not establish a legal exemption or automatically guarantee thread safety.

The user target is the latest Blender LTS. Official search-index results inspected
on this date identify **5.2.2 LTS**, dated September 15, 2026. Direct reads of the
[official LTS page](https://www.blender.org/download/lts/) and
[download page](https://www.blender.org/download/) returned HTTP 402 during this
research. No exact official binary URL was verified. Treat this as a
source-reported target, not evidence of successful Blender 5.2 runtime testing.
The accessible official [`bpy` 5.2.2 PyPI release](https://pypi.org/project/bpy/5.2.2/)
independently confirms that version and provides a Linux x86-64 wheel requiring
CPython 3.13. Blender's [release checklist](https://developer.blender.org/docs/handbook/release_process/release_checklist/)
documents this PyPI publishing path. A separate 3.13 environment can test headless
registration/replay/save/reopen; it cannot establish GUI interaction correctness.

## Why this stack rather than the alternatives?

- **Direct OCP:** selected. Gives access to exact analytic/NURBS B-reps, operation
  builders and their history, validation, meshing, and STEP exchange. More verbose
  than a modeling DSL, but the actual algorithms and failure reports remain
  accessible. Our current operations do not need a second abstraction layer.
- **build123d:** a useful optional helper and reference implementation. Its Python
  object/algebra APIs make construction easier to read. It still runs on OCP/OCCT
  and adds dependencies and conventions. Our application needs persistent feature
  IDs, graph editing, constraints, rollback and repair semantics regardless of the
  chosen construction API; a script or builder context should not own that
  document. Its development branch currently uses the no-VTK OCP variant. See
  [project](https://github.com/gumyr/build123d) and
  [dependency manifest](https://github.com/gumyr/build123d/blob/dev/pyproject.toml).
- **CadQuery:** mature scripted construction, selectors and useful examples.
  Version 2.8 added topology-operation history to its free-function API; saying it
  has no history would be outdated. This is not a replacement for our editable
  document model. Its current shape module imports VTK, making it a heavier
  dependency for a Blender worker that already has a viewer. See
  [2.8 changes](https://github.com/CadQuery/cadquery/blob/master/changes.md),
  [maintainer's experimental-history description](https://github.com/CadQuery/cadquery/discussions/2051),
  and [shape implementation](https://github.com/CadQuery/cadquery/blob/master/cadquery/occ_impl/shapes.py).
- **FreeCAD as backend:** the most substantial reuse option when its document,
  Sketcher and Part features match the product. It means adopting or bridging an
  existing application model and dependencies instead of maintaining our narrow
  engine. Worth a separate spike before implementing many advanced workbenches;
  not a lightweight replacement for this adapter. [FreeCAD source](https://github.com/FreeCAD/FreeCAD).
- **Truck:** genuinely modular Rust B-rep/NURBS geometry and solid Booleans under
  Apache-2.0. Attractive if developing the kernel itself is a project goal. Its
  coverage and interoperability would need evaluation against the same difficult
  part corpus; the modular design alone does not establish production robustness.
  [Truck architecture](https://github.com/ricosjp/truck).
- **Manifold:** focused, readable, Apache-2.0 triangle-mesh Boolean library with
  explicit manifoldness goals and provenance support. Useful for mesh workflows;
  it is not a substitute for analytic CAD faces, precise curved B-rep operations,
  and STEP solids. [Manifold](https://github.com/elalish/manifold).

### Existing Blender projects

[CAD Sketcher](https://github.com/hlorus/CAD_Sketcher) is the most relevant sketch
interaction and solver-integration reference. Its current code documents editable
native curves and constraints, with geometry realized through a mesh/Geometry
Nodes body; that is a different representation boundary from an authoritative
OCCT solid. Reuse ideas and possibly compatible components, not a claim that it
already supplies our required B-rep history. See its
[data model](https://hlorus.github.io/CAD_Sketcher/code_docs/).

[Sverchok](https://github.com/nortikin/sverchok) provides extensive procedural
geometry nodes; its solid objects use FreeCAD. It is useful precedent for Blender
plus CAD-library integration, but the node paradigm does not supply our intended
direct feature-editing interaction. [BlendQuery](https://github.com/uki-dev/blendquery)
connects CadQuery/build123d scripts to Blender scenes. Its repository did not show
a license file in the inspected root, so do not copy its implementation without
resolving reuse permission.

## Sketch constraints: next decision

Evaluate **SolveSpace's libslvs**, with a small versioned adapter, before writing a
new nonlinear solver. Its C interface exposes geometry/constraints, degrees of
freedom, solve status, dragged parameters, and optional failing-constraint
diagnostics. Computing conflict diagnostics can be more expensive than solving;
reserve the expensive pass for errors rather than every drag frame. See the
[actual API](https://github.com/solvespace/solvespace/blob/master/include/slvs.h).

The official [`slvs` 3.2 package](https://pypi.org/project/slvs/) has CPython-specific
wheels, including 3.12 and 3.13 across several platforms. CAD Sketcher's
[extension manifest](https://github.com/hlorus/CAD_Sketcher/blob/main/blender_manifest.toml)
illustrates platform-split bundling. Before selection, pin and test the actual
wheel, API result structures, solver state isolation, underconstraint, redundant
and conflicting constraints, near-degenerate geometry, and drag continuity. This
prototype has not installed or tested that solver.

Alternative: FreeCAD's **PlaneGCS**, particularly if the sketch roadmap needs its
broader curve/constraint model. Its [source](https://github.com/FreeCAD/FreeCAD/blob/main/src/Mod/Sketcher/App/planegcs/GCS.h)
is LGPL-2.1-or-later; an independent [WebAssembly wrapper](https://github.com/Salusoft89/planegcs)
exists, but that is not a ready-made native Python integration. CadQuery's own
[sketch constraint solver remains documented as experimental](https://cadquery.readthedocs.io/en/latest/sketch.html).

Intent inference belongs above the solver: show proposed coincidence, horizontal,
vertical, equal-radius and symmetry constraints before/while they are accepted;
retain their source and allow removal. Report remaining freedom and conflicts.
A numerically solvable constraint set is not proof of the user's intended design.

## Provenance and persistent naming

OCCT provides `Generated`, `Modified`, `IsDeleted`, and composable
`BRepTools_History`. These track actual operation lineage, not arbitrary semantic
identity across document edits. See [kernel history documentation](https://github.com/Open-Cascade-SAS/OCCT/blob/master/dox/user_guides/modeling_algos/modeling_algos.md).
OCAF also provides [TNaming selectors](https://www.occt3d.com/dev/doc/refman/html/class_t_naming___selector.html),
which require correctly maintained document labels and evolution data.

OCCT 8 introduces **BRepGraph**, including stable graph UIDs and history-aware
ingestion. It deserves an isolated experiment, not a claim that naming is solved:
the maintainer explicitly warns of interface changes in 8.1/development. Graph
identity and preserving design intent through a face split are distinct problems.
See [BRepGraph scope](https://github.com/Open-Cascade-SAS/OCCT/discussions/1170) and
[compatibility note](https://github.com/Open-Cascade-SAS/OCCT/discussions/1291).

Our implemented, deliberately bounded contract:

1. Rectangle/circle profile edges have construction roles. Extrude caps come from
   `FirstShape`/`LastShape`, and side faces from `Generated(profile edge)`. Retain
   `MakeWire.Edge()` after insertion because the builder may replace input edges.
2. Boolean cuts preserve an existing role only for uniquely supported unchanged
   or one-to-one modified lineage. Reverse ancestry is checked; splits and merges
   do not silently choose a descendant.
3. New tool-derived walls and untracked/imported faces remain non-stable. Geometry
   ranks visible repair suggestions; it never proves identity.
4. Deterministic `snapshot:...` IDs are temporary picking handles. Saved references
   use semantic feature/role data, never an OCCT traversal index or mesh index.

Real tests in [test_kernel.py](../../tests/integration/test_kernel.py) exercise
dimension changes, bore relocation/resizing, split faces, deleted faces, resolver
behavior, replay determinism, positive volume, STEP roundtrip and STL topology.
These do **not** prove naming for fillets, shelling, patterns, arbitrary sketch
edits, imported parts, multi-body/assembly references, or a kernel upgrade.

## Packaging and license boundaries

- OCP's wrapper is Apache-2.0; OCCT itself remains **LGPL-2.1 with its additional
  exception**. Preserve both sets of notices, and provide the source/relinking
  arrangements required for the actual distribution. See
  [OCCT license](https://occt3d.com/dev/doc/overview/html/occt_public_license.html).
- build123d, CadQuery and Truck use Apache-2.0. Apache-2.0 is compatible with GPLv3,
  not GPLv2-only; this project chooses GPL-3.0-or-later. See
  [Apache's compatibility guidance](https://www.apache.org/licenses/GPL-compatibility).
- SolveSpace's upstream [library guidance](https://solvespace.com/library.pl)
  and package description specify GPLv3. PyPI's `slvs` metadata instead labels
  the package MIT. Do not infer that the linked solver became MIT; audit bundled
  source and wheel licenses before distributing it. GPLv3-or-later is the
  conservative project direction, not a legal opinion on every binary artifact.
- OCP's published no-VTK 8.0.1.1.0 wheels cover Python 3.11–3.14 and several
  OS/architecture pairs, but publication does not prove our compatibility on each.
  [PyPI release files](https://pypi.org/project/cadquery-ocp-novtk/) and
  [build system](https://github.com/CadQuery/ocp-build-system/blob/main/README.md).
  Only this cloud Linux CPython 3.12 worker was exercised in this adapter task.
- Keep a pinned wheel/hash matrix and native notices. Do not install both VTK and
  no-VTK OCP distributions into one environment: they provide the same namespace.
  OCP 8 removed old `TopoDS.Face_s`-style aliases; the adapter uses `TopoDS.Face`.

## Release gates and important limits

Canonical units are millimetres. STEP/STL part export currently requires one valid
positive-volume solid. STL checks both the tessellation and actual encoded
float32 triangles after numerical seam welding: closed consistently oriented
edges, manifold vertex links, no degenerate/duplicate triangles, positive signed
volume. The mesh check does not establish absence of all self-intersections,
machining feasibility, wall-thickness suitability, mechanical strength, or
tolerance compliance. STL has no intrinsic units or editable feature history.

Binary STL has a separate fidelity gate: maximum Euclidean vertex error after
binary32 rounding must not exceed `min(0.00001 mm, 0.1 * linear_deflection)`.
The report includes the observed error and allowed limit, and the actual file's
triangle-coordinate multiset must match the checked quantized source. This
intentionally strict independent precision ceiling can reject large translated
parts even when a coarse mesh was requested. Failures leave any prior destination
untouched; recentering is an explicit user edit, never an automatic export change.
Signed mesh volume uses a local origin to avoid catastrophic cancellation.

Analytic-circle tessellation has a conservative preflight resource budget, and
actual output is capped at 100,000 vertices / 200,000 triangles. The request fails
rather than silently loosening deflection. This is not a hard memory/CPU bound for
arbitrary imported splines or native Boolean algorithms; worker-level resource
isolation and cancellation remain necessary.

Before widening scope: test nearly tangent/coincident cuts, tiny and large
coordinates, curved seams, fillet failures, undo/save/reload/rebuild, cancellation,
and actual Blender LTS installation on each supported platform. Preserve original
errors and last-good geometry; never hide a failed CAD operation behind an
apparently plausible display mesh.
