# 0.2.1 draft-recovery preview verification

Date: 2026-10-16. Linux x86_64; native Blender 5.2.2 LTS; CPython 3.12.14
sidecar, cadquery-ocp-novtk 8.0.1.1.0 and slvs 3.2. The immutable delivered 0.2
archive and its original evidence remain unchanged in [the 0.2 record](VERIFICATION_02.md).

## New bounded capability

An unfinished viewport rectangle can be suspended across workspace changes and
explicitly resumed. Raw invalid text, unapplied native dialog RNA values, constraint
intent, stable feature identity and the exact base document are retained separately
from canonical design history. Restored previews and solver status are unverified.
A changed base is rejected; the user can restore that exact base or explicitly
discard the draft. Export and conflicting edits cannot silently consume a preview.
See [the detailed lifecycle](DRAFT_LIFECYCLE.md).

## Evidence

- Pure typed draft codec tests cover malformed snapshots, exact raw text, decimal
  precision, all placement phases, stale base and optimistic edit identity.
- Native `blender_draft_suspension_smoke.py` passes 208 lifecycle assertions and
  18 assertions in a separate process reopening its saved `.blend`.
- Existing native viewport regressions pass 190 assertions; no mouse-motion
  sidecar replay is introduced.
- Actual native 5.2.2 source-loaded GUI review covers invalid input, repeated
  Part→Sketch→Resume, pending popup text after native field confirmation,
  correction through the same sketch/extrusion history, explicit Discard and
  a labeled stale-base injection. The detailed receipt is recorded separately.
- Full-suite and exact distributable installation results are recorded with the
  release manifest/receipt once run on the final committed package.

Native text keystrokes belong to Blender's private edit buffer until confirmation
or focus loss updates RNA. The application does not claim to intercept that buffer.
Deleted-scene recovery is limited to the current session; loading a different file
uses that file's saved draft. Save `.blend` before leaving a file to keep its draft.

## Unchanged limits

The viewport editor remains a four-corner global-XY rectangle workflow. General
sketch entity/constraint tools, arbitrary workplane UI, extrusion preview and
assembly authoring are not part of this release. The new assembly backend is an
independently tested development foundation, with no exposed assembly workflow.
Icon contrast, viewport-label occlusion and default-layout cleanup remain open.
Windows/macOS installation is unqualified. Geometry checks are not structural,
manufacturing or continuous-motion safety certification.
