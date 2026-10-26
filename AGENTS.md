# Mechanical CAD development guide

This is an experimental GPL-3.0-or-later project. Read README.md and
`docs/ARCHITECTURE.md` before changing behavior; read the relevant ADR for a kernel,
persistence or topology change. Keep changes scoped and commit coherent milestones.

## Invariants

- The versioned feature graph is canonical. Blender meshes are display caches.
- Do not import OCP or the core native kernel inside Blender. Use the JSON sidecar.
- Never execute model text, pickle model data or silently discard unknown fields.
- Names/mesh indices are not persistent CAD identity. Provenance is explicit;
  ambiguous/split/merged/deleted face identity fails closed. Heuristics only suggest.
  Versioned, visible logical construction intent may preserve a sketch plane across
  proven coplanar splits (ADR 0002); never relabel an inferred face as stable.
- Keep failure/dirty/stale status visible. Last-good display is a marked cache,
  never current geometry or an export source. Exports replay canonical data.
- Protect unrelated Blender objects/scenes, preserve user unit settings and handle
  precision deliberately. Numeric widgets must not rewrite untouched parameters.
- Keep source Git, model feature history and session Undo distinct. Do not publish
  or configure automatic model Git commits as a side effect of development.

## Source map

- `model.py`: schema, immutable snapshots, DAG, atomic persistence.
- `expressions.py`: bounded arithmetic and named parameter dependencies.
- `sketch_model.py` / `sketch_solver.py`: pure typed sketch records and lazy native
  solve; `profile_region.py` retains explicit line identity through closed loops.
- `engine.py`: ordered full replay and failed/blocked feature results.
- `kernel_ocp.py`: exact geometry, construction history, tessellation and export.
- `topology.py`: strict semantic resolution and explicit geometric suggestions.
- `actions.py`: fresh canonical geometry checks and atomic explicit part exports.
- `sidecar.py` and add-on `bridge.py`: versioned subprocess boundary.
- `blender_addon/`: Blender-only interaction and disposable display; see the
  module map in `docs/ARCHITECTURE.md`. Keep the entry point minimal.
- `docs/regressions/catalog.json`: stable IDs and actual/planned regression links.

## Verification

Run Ruff and the complete pytest suite. For UI changes also run Blender smoke,
real ZIP-install/enable and two-process `.blend` persistence tests. Native Blender
must use `--python-exit-code 1`; check the explicit result marker. Review real GUI
Apply/Cancel, Undo/Redo, help visibility and error recovery. Headless success does
not establish GUI usability or platform compatibility.

Add real kernel assertions for each geometry operation, including dimensions,
volume/validity and edge cases. Do not inflate implemented coverage with planned
catalog entries. Keep generated binaries, dependency environments and release
archives out of Git. Update scope/limitations documentation when behavior changes.
