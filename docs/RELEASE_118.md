# 1.18.0 Linux development checkpoint

This bounded checkpoint prioritizes compact, usable CAD workflows:

- Ordered multi-section Loft and editable simple/counterbored round holes.
- A compact icon-led Sketch/Part/Assembly workspace, earlier primary actions,
  Focus controls, and discoverable first-use assembly Check setup.
- Boolean cleanup isolated from caller-owned shapes and explicit persisted
  assembly replay tolerance rather than a silent global tolerance change.
- Named intended-contact policy: a complete report may be policy-accepted while
  its raw interference check remains failed. Accepted never means raw passed.
- Faster current-Part lookups scoped to one call, retaining filesystem identity
  and freshness checks rather than granting persistent cache authority.
- Editable reduction-gearbox and ventilated-enclosure development examples.

## Evidence boundaries

Feature source is frozen at d4537e6. Release metadata and documentation are
recorded in the packaging commit. The companion verification receipt identifies the exact feature and packaging
commits, archive hashes, checks run and outcomes. Source GUI observations and
source/native test results are separate from exact installed archive checks.
Headless operator checks do not establish installed interactive GUI usability.

Qualification is intentionally bounded: exact archive enable and identity,
representative enclosure load/edit/check/export/save, independent process
reopening, and focused registration checks. Only stages with explicit successful
process markers in the companion receipt are claimed as passed. Existing
source-level coverage is not represented as new installed qualification.

The full historical suite was previously interrupted at 89% under resource
pressure, with failures unclassified. It is not a clean suite, and failures are
not assumed inherited. This checkpoint does not repeat that exhaustive suite.

## Scope and limits

The canonical feature graph remains authoritative; Blender meshes are display
caches. Native OCCT and SolveSpace remain in the isolated sidecar, never Blender.
The native pin remains cadquery-ocp-novtk 8.0.1.1.0. Existing external runtime files
and modes and unresolved materials/source declarations are retained. Packaging
is not legal clearance, source correspondence or a functional recipient rebuild.

Examples demonstrate bounded editable workflows, not manufacturing fit, gear
strength, clearance certification, or general assembly solvability. Datum-driven
mounting holes are used in the primary enclosure example; separate grouped-hole
workflow regressions and their evidence are retained rather than disguised.

Earlier delivered Linux 1.17 and Windows 1.16 artifacts remain immutable. There
is no Windows 1.18 qualification. No professional CAD completion, universal
persistent topological naming, arbitrary geometry support, exhaustive GUI
Undo/Redo qualification or manufacturing certification is claimed.
