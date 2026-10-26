# 0.2 constrained-rectangle preview verification

Date: 2026-10-16. Linux x86_64, CPython 3.12.14 sidecar,
`cadquery-ocp-novtk==8.0.1.1.0`, `slvs==3.2`.
Counts describe executed checks, not percent coverage or full-product acceptance.
The unchanged delivered 0.1 evidence is in [the Stage 1 record](VERIFICATION_STAGE1.md).

## Reproducible automated checks

- `ruff check .` and `ruff format --check .`: passed.
- `pytest -q`: **615 passed** in the integrated working tree, including real
  OCCT/libslvs geometry, strict schema/bridge validation and pure draft behavior.
- Official standalone **Blender 5.2.2 LTS**, build `d13f752e3b9c`, verified official
  archive SHA-256 before use:
  - `tests/blender_smoke.py`: 138 checks.
  - `tests/blender_module_smoke.py`: 15 main-process + 9 fresh-process checks.
  - `tests/blender_geometry_actions_smoke.py`: 75 checks.
  - `tests/blender_viewport_sketch_smoke.py`: 190 checks; real solver release/refix,
    source-preserving Cancel and same-part replay included.
  - `tests/blender_constrained_persistence.py`: 7 save + 16 fresh-process reopen
    checks. Saved canonical schema-2 JSON survives exactly; geometry and DoF
    caches become untrusted, then replay and the same-part dimension edit work.
  - `scripts/blender_workspace_smoke.py`: registration, scoped ownership/palette,
    shared document and staged setup lifecycle assertions pass.
- Native Blender 4.3.2 and official standalone `bpy==5.2.2` are supplemental host
  checks. They are distinct from actual native LTS GUI evidence below.

The viewport operator suite additionally exercises Apply/Finish/Cancel, exact
source preservation, stable downstream IDs, 0/2 DoF, release-position intent,
untouched precision, stale reports, navigation/lifecycle and transient state.
Its executed check count and timing observations are included in the packaged logs.

Run `scripts/run_checks.sh` with `BLENDER=/path/to/blender` to execute lint,
format, pytest and all six host suites. Set `MCAD_BPY_PYTHON` for supplementary
standalone-bpy runs. ZIP installation uses `tests/blender_install_smoke.py` with
an isolated `BLENDER_USER_SCRIPTS`; see that script's docstring.

## Independent geometry audit

`scripts/audit_constrained_geometry.py` is a persisted seeded audit with separate
analytic expectations, beyond pytest. It passed:

- 180 convex/concave profiles, shuffled/reversed line records, arbitrary workplanes,
  native solve, exact volume, manifold mesh and stable line-face provenance.
- 500 legacy serializer/hash comparisons and explicit schema-2 migrations.
- 1,500 nearby triangle dimension-edit pairs: 1,499 converged without mirror flips;
  one pair conservatively returned `DIDNT_CONVERGE` for both edits.
- 84 duplicate-constraint variants retaining geometry/DoF, 24 near-unit-quaternion
  large-plane cases, five invalid region topologies, and 12 STEP/binary-STL roundtrips.

See [audit details](audits/constrained_geometry.md) and the searchable
[regression catalog](regressions/README.md). Tiny dimensions within parser bounds
can still fail native geometric tolerances; they fail closed, not as valid solids.

## Actual native 5.2.2 GUI evidence

Source-loaded native LTS review exercised two-click rectangle drawing, exact
40 × 30 mm dimensions, real 0 DoF validation, Finish, a 10 mm extrusion, and editing
the original rectangle width to 60 mm. The same extrusion rebuilds to **18000 mm³**.
Inline Help/Apply, visual Undo/Redo and fresh canonical Geometry Check passed.

These screenshots are of the actual application. Direct preview pointer movement
performs no native solve; 1,000 motion updates took tens of milliseconds in the
host fixture. Explicit Apply/Finish uses a synchronous sidecar; bounded commits
were approximately one second on the test computer. These are observations,
not a latency guarantee or an asynchronous interaction claim.

Actual owned-workspace creation/reopen fixtures verify idempotency, preservation
of original user layouts, shared canonical JSON and role tags. Headless operator
success alone does not establish visual tab ordering or modal usability.
Final installed-ZIP GUI acceptance is recorded separately with the release artifact.
An independent transaction review also passed nine unsupported-orientation cases
and active-draft load/Undo/popup cleanup probes. Imported mirrored branches fail
closed before preview validation or Finish can change canonical data.

## Known preview limits

- Only the tool's four-corner global-XY rectangle is editable through the viewport.
  Broader line constraints exist in the backend, not a general constraint editor.
- Leaving Sketch cancels an unfinished draft. The draft warns before switching
  and cancellation is reported afterwards; suspended-draft restoration is planned.
- No extrusion preview, general line/circle/arc drawing, arbitrary-plane UI,
  face-attached features, assembly instances/mates or motion verification.
- Palette icon contrast, label occlusion near the history panel and redundant
  default Blender layout areas still need refinement. Undo can lose local-view
  framing; Focus CAD Result recovers it.
- Windows/macOS installation remains untested. Blender/native dependency versions
  outside the pinned test environment are not implied compatible.
- Geometry/export gates do not certify manufacturing, assembly fit, loads or safety.

A preview succeeds when its documented narrow workflow and failure recovery pass.
It is not acceptance of the entire planned CAD product.
