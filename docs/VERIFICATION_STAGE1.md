# Stage 1 verification record

Date: 2026-10-16. This is an experimental foundation checkpoint, not full-product
acceptance. Counts below describe executed checks, not percent test coverage.

## Reproducible automated checks

- `.venv/bin/python -m ruff check .`: passed.
- `.venv/bin/python -m pytest -q`: **187 passed**. These include safe formulas,
  document persistence/immutability, graph/replay failures, subprocess protocol,
  conservative topology and real Open CASCADE geometry/export regressions.
- Native `/usr/bin/blender` **4.3.2**, Python **3.13.5**:
  `tests/blender_smoke.py`: **138 checks passed**, process exit 0.
- Official standalone **Blender 5.2.2 LTS**, build `d13f752e3b9c`: the delivered
  `689a414` source passed the same **138 checks**, and its exact delivered ZIP
  passed actual install/enable/Demo/disable in background mode. Official archive
  SHA-256 was independently checked before running it. This is supplementary
  evidence obtained after the initial preview archive was assembled.
- Official PyPI **bpy 5.2.2 LTS**, separate Python **3.13.5** environment:
  the same `tests/blender_smoke.py`: **138 checks passed**, process exit 0.
- Official bpy 5.2.2: `tests/blender_persistence.py` in two separate processes
  (`MCAD_MODE=save`, then `reopen`): passed. Saved authoritative JSON survived,
  cached display became untrusted on reopen, and editing/rebuilding worked.
- Native Blender 4.3.2 and official bpy 5.2.2: `tests/blender_install_smoke.py`
  installed the actual add-on ZIP into isolated scripts directories, enabled it,
  configured the sidecar, created the example and disabled it successfully.
  The native test caught and drove a fix for Blender's restricted registration
  context; source-import testing alone did not catch that packaging defect.

The sidecar test environment is Linux x86_64, CPython 3.12.14, with
cadquery-ocp-novtk 8.0.1.1.0. The core imports without Blender. The add-on tests
assert that Blender never imports OCP or the core kernel package.

Run `scripts/run_checks.sh` with `BLENDER` and `MCAD_BPY_PYTHON` set to reproduce
both host checks. See each standalone test script's docstring for install and
separate-process persistence environment variables.

## Important exercised cases

- Blank → rectangle → extrusion → circle → extrusion → cut, entirely through
  add-on operators; parameter/formula edits and stable output identity.
- Analytic volumes, one valid solid, proper hole faces, planar profile previews,
  deterministic pinned-kernel replay and STEP round-trip geometry.
- Invalid dimensions, missing references, cycles, unsupported schema/units,
  malicious expressions, duplicate/non-finite JSON, subprocess timeout/crash and
  malformed/wrong-document responses.
- Explicit split/merge/deleted/ambiguous topology states. Candidate order/index
  changes do not decide identity. No geometric heuristic silently repairs a ref.
- Preserved unrelated parameter precision, formula toggles and dependencies,
  non-default scene unit scales and distant small-part display warnings.
- Shared-scene/collection ownership, parent/delta/deformation reset, stale failure
  cache restored from a private last-good copy, no current volume/render while
  failed, correction/recovery and repeated registration.
- Watertight/oriented/manifold tessellation gates, binary-STL coordinate fidelity,
  rejected distant small-part exports without overwriting the destination, and
  bounded analytic tessellation budgets.

Independent review also exercised 40 seeded analytic bore models and targeted
failure/export/retention cases. Those extra probes are supplementary evidence;
only tests committed in this repository are counted in the 187 above.

## GUI and remaining release gates

The actual cloud Blender **4.3.2 GUI** has been opened and inspected, with real
screenshots of the part, editable panel and contextual help. This does not prove
5.2.2 native GUI behavior. The requested target is **5.2.2 LTS**, now also
verified with its official standalone executable in background mode. Native
5.2.2 GUI review of the complete released workflow remains open. Windows/macOS setup also remains untested.

The exact final `689a414` add-on ZIP was subsequently installed through the
actual 4.3.2 Preferences GUI in a clean session, configured and used to generate
the five-feature example successfully. No source import was used for this gate.

Actual 4.3.2 GUI Undo/Redo passed for New Demo, parameter change + Regenerate,
and profile creation. Inline authoring Help retained a width-100 draft through all five pages and
collapse; Cancel preserved the prior accepted model. Standalone paged Help and
full-diagnostic popups were readable, and default-width sidebar errors wrapped.
Demo Redo can lose viewport Local View isolation; Focus Result restores it. Headless operator execution alone does not prove
modal usability. No claim of full constraint, assembly, manufacturability or
structural/load validation is made.

## Example geometry

`examples/drilled_plate.mcad.json` regenerates to one valid solid with seven faces,
exact volume **11497.345175425633 mm³**, and area **3950.7964473723105 mm²**.
At 0.1 mm linear deflection, the checked mesh has 134 welded vertices and
268 triangles. Its approximate volume is **11498.178053157104 mm³**, demonstrating
why tessellation is a display/export approximation rather than canonical CAD.
