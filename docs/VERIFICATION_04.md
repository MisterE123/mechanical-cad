# 0.4 line/circle preview verification

Date: 2026-10-16. Qualified environment: Linux x86_64, native Blender **5.2.2 LTS**
(build `d13f752e3b9c`), CPython 3.12.14 sidecar, cadquery-ocp-novtk 8.0.1.1.0,
and slvs 3.2. The minimum Blender version is 5.2. Windows/macOS, other Blender
releases, all input devices/keymaps, and maximum-cap interactive performance are
not qualified. The immutable [0.3 record](VERIFICATION_03.md) remains separate.

## Scope

The production Sketch workspace now exposes Line, Circle, Dimension, Check,
Finish and Cancel tools. The dimension editor supports line distance and circle
radius drivers, raw expressions, selection/caret/clipboard operations, checked
Enter acceptance, Esc cancellation and outside-click suspension. Rectangle is a
separate retained shortcut. General open connected chains can be solved and saved
as editable geometry without claiming an extrudable profile. Simple closed line
loops and single circles can produce exact profiles and downstream solids.

Current solve evidence, retained unverified outlines, pending raw input and
committed Part status are separate. A broken dependent extrusion blocks publishing
an upstream edit and keeps its draft recoverable. Annotation placement is scene
UI metadata; it does not change canonical geometry hashes. Version negotiation is
explicit, including assemblies that contain the newer sketch payloads.

The existing Part export and rooted fixed/revolute/slider assembly workflow remain
available. Assembly checks concern accepted revisions and specified poses, not
continuous collision, structural/load analysis or manufacturing certification.

## Reproduce the automation

From a clean source checkout with the pinned development/sketch extras installed:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[dev,sketch]'
export MCAD_PYTHON="$PWD/.venv/bin/python"
export BLENDER=/absolute/path/to/blender-5.2.2/blender
bash scripts/run_checks.sh
```

The final combined gate on source `4b53129c5aa27bb97fd5f130233431e2d04d7e13`
passed Ruff/format, **2,899 pytest tests plus 19,597 subtests**, all **31 native
suite entrypoints**, and both separately CPython-launched real Blender
exit/owned-child-reaping gates. The exact installed ZIP also passed its isolated
background gate, including 116 production dispatch assertions. The
[completed installed GUI receipt](audits/line_circle_installed_040.md) identifies
final package/source hashes, manual workflows and fresh-process evidence.
A separate standalone `bpy` wheel run is not required or claimed for this gate.

The native suites cover legacy Rectangle, drafts/history/load, shared editor
ownership, typed open/solid display, atomic Part/annotation publication, exclusive
execution leases, asynchronous sketch checks, general input/proposal dispatch,
viewport isolation, assembly transactions/presets/cancellation, and workspaces.
The source scripts contain their independent-process setup where applicable.
[Async sketch reproduction](ASYNC_SKETCH.md) includes the process-lifecycle commands.

For an isolated install, set `MCAD_ROOT`, `MCAD_PYTHON`, `MCAD_ADDON_ZIP`,
`BLENDER_USER_SCRIPTS` and `BLENDER_USER_CONFIG` to the intended source, interpreter,
ZIP and fresh temporary directories, then run:

```sh
"$BLENDER" --background --factory-startup --python-exit-code 1 \
  --python tests/blender_install_smoke.py
```

This installs the actual ZIP, tests blank-document creation, Part replay/export
checks, assembly verification, and New/Edit/Resume for both sketch editors. It
asserts every imported add-on module came from the isolated installed package and
that no OCP/SolveSpace module entered Blender's Python process.

## Independent review and actual GUI evidence

Separate frozen-source audits cover [core/typed contracts](audits/typed_and_draft_boundaries.md),
[shared lifecycle](audits/shared_sketch_lifecycle.md),
[authoring state](audits/general_authoring_state.md),
[typed display rollback](audits/typed_sketch_display.md),
[GeneralSession failure recovery](audits/general_session.md), and
[atomic annotation publication](audits/annotation_publication.md).
Each report names its exact tested source and boundaries; these are not blanket
GUI or cross-platform qualifications.

Native 5.2.2 source-loaded GUI review on the `b9ba79a` runtime exercised a drawn
circle, placed radius annotation, double-click expression edit, successful Enter,
invalid raw retention, Esc, outside-click/Reopen, normal Finish/Extrude/Edit,
annotation persistence, view restoration, workspace suspension/Resume, and a
joined open chain with a direct 20 mm length. Display Selected showed that chain
as an explicitly non-solid output. The legacy Rectangle shortcut and Resume also
passed. Earlier `2a75732` GUI review verified editing the same sketch updates the
same extrusion to the analytic R15 volume. These source-loaded checks are distinct
from the final installed-package receipt bundled with the complete preview.

A pending field consumed the first outside click as designed: it suspends raw
input and consumes that release. A subsequent explicit Cancel Input discards it.
The native GUI solve completed before the attempted Cancel Check click; that
attempt is not evidence of mouse cancellation. Cancellation has separate real
process/native headless and independent owner-lifecycle coverage.

## Remaining limits

- Global-XY line/circle authoring; existing supported constraints are retained,
  but the editing UI is not a full constraint editor. No arcs, trim/extend,
  construction tools, tangent/equal tools, diameter/reference dimensions,
  multiple regions, holes, or contextual reference geometry yet.
- The compact custom text field has no IME composition or screen-reader support.
  Font/theme/input-device coverage is bounded. Dense annotations can still overlap.
- Mesh context is temporarily filtered only in the owning Sketch viewport and
  restored on exit. Resume requires the exact original Part revision and a fresh
  check; saved display and old DoF reports cannot authorize a new commit.
- `.blend` preserves annotation positions and draft UI; portable `.mcad.json`
  preserves canonical design only. Reopened cached output is unverified until replay.
- Assembly frames remain literal authored coordinates. General closed loops,
  nested assemblies and joint dragging are not supported. Some assembly controls
  remain text-heavy and default Blender side editors consume space.
- No remote account or Git service is needed. Source Git history, CAD feature
  history, draft command Undo, and Blender Undo have different documented roles.
