# Installed 0.5 constraint-authoring preview receipt

Date: 2026-10-16. Qualified runtime: official native Blender **5.2.2 LTS**
(`d13f752e3b9c`), Linux x86_64, with CPython 3.12.14, OCP 8.0.1.1.0 and slvs 3.2
in the separate sidecar. This is a bounded release receipt, not a full-CAD or
cross-platform correctness guarantee.

## Immutable identities

- Released source: `1a27e74a8f30aeb3fadac8edec935bcf12e3c304`.
- Add-on ZIP SHA-256:
  `5548e79e502c40c3814481b2c49ea0f42cab85a89facf3df1e72c3dcc2382f2f`.
- Complete archive: `mechanical-cad-0.5.0-constraint-authoring-preview-1a27e74-complete-preview.zip`.
- Complete archive SHA-256:
  `718942d6d462d5e67f9848a670e6f5b93098ef0674a25467a4ddf1a5b530df94`.
- Complete archive size: 5,994,923 bytes; 58 payload files, including SHA256SUMS.
- The source ZIP matched all 834 files restored from its full Git bundle.
- Actual installed example, `examples/installed-constraints-050.blend`:
  `b7f2c91bf061066e465993afc00d54cd208fa2dbf64078eda66f273e33dc4145`.

The complete archive was re-extracted, every payload checksum checked, and its
portable receipt verifier rerun successfully. The delivered 0.4 archive remains
byte-identical, SHA-256
`f72b0df540fe7bf0f8f9b449eb25c222639c72275f398f3f31a53395a99b2516`.
This later documentation commit changes none of those released artifacts.

## Actual clean installed GUI

A fresh profile installed the exact ZIP through Preferences → Add-ons → Install
from Disk and showed version 0.5.0. All 601 ZIP members matched the installed files;
all 70 loaded CAD modules came from that installed tree. No source registration
or scripted geometry creation was used for this workflow.

1. New CAD Document → Sketch → New Sketch. Four lines with explicit endpoint reuse
   produced four points/four lines and 8 DoF. Explicit H/V on the four sides gave
   4 DoF. Points → corner → Fix at origin confirmation gave 2 DoF. Placed distance
   labels and double-click expression editing accepted 4 and 3 mm, giving 0 DoF.
2. Finish → Part → Extrude 10 mm produced READY, 120 mm³. Normal Edit restored the
   same sketch and exact label-offset dictionaries.
3. Reapplying H inspected its existing relation without a duplicate. Release
   removed only that relation, cleared only its selection and gave 1 DoF without
   a missing-ID warning. Local Undo restored 0 DoF.
4. Incompatible V produced an inconsistent, unverified draft with Finish disabled.
   Authored-position recovery Cancel preserved the exact intent. Apply removed
   only the disclosed relation, preserved authored point bytes and checked to 0 DoF.
5. Esc suspension and ordinary Resume preserved sketch intent, history and labels.
   Resume restored no solver authority; explicit Check verified the sketch again.
6. Direct width edit 4→5 and Finish rebuilt the same `sketch_1` / `extrude_1` to
   READY, 150 mm³. This is the saved installed example.
7. A separate drawn circle used inspector Center, confirmed Fix at origin and a
   radius dimension to reach 0 DoF. Cancel preserved the main Part.
8. The legacy Rectangle shortcut, workspace switch, Resume and Cancel retained
   its editor-specific dimensions and left the main Part unchanged.
9. A fresh native process reopened the saved example as DIRTY. Visible Rebuild
   restored READY, 150 mm³. Normal Edit restored the exact sketch and both label
   offsets with real 0 DoF. The original example's hash stayed unchanged.

The left Check/Finish/Cancel centers remained at local y=479/521/563 across clear,
line, point, relation and pending-input states. This does not promise that the
separate, scrollable inspector's controls have fixed screen coordinates.

## Automation and independent scope

Exact `1a27e74` passed Ruff/format, **3,085 tests plus 19,597 subtests**, all **40
native entrypoints**, and both real Blender exit/owned-child-reaping gates.
The separate exact installed-background gate passed dispatch 116, constraint
actions 201 and inspector 170 assertions. Native palette layout coverage passed
2,427 assertions; the GUI check above complements it.

Independent core review passed at `f90b0fc`; owner/action review passed at
`50e1b76`; the final removed-selection transaction passed 60 independent native
assertions on both `c13ea25` and the final packaged source. These bounded reviews
retain their own file/behavior scopes. See [constraint verification](../CONSTRAINT_VERIFICATION.md).
The package also contains 26 durable GUI receipt invariants and a portable
`evidence/gui-receipts/verify_receipts.py`; replaying receipts is not a new GUI run.

Reproduce the full source gate with the pinned dependencies and
`bash scripts/run_checks.sh`, setting `MCAD_PYTHON` and `BLENDER` as described in
[VERIFICATION.md](../VERIFICATION.md). The package's START_HERE and
[INSTALL.md](../INSTALL.md) explain the separate trusted sidecar setup.

## Remaining limits

- Mouse Cancel Check and backend-startup failure were not manually observed in
  this installed run; natural solves finished too quickly. Their native automated
  failure/cancellation tests are separate evidence.
- A failed relation or resumed draft may show unverified authored positions that
  differ from the last solved outline. Pending raw dimensions retain an explicitly
  unverified solved outline. Neither is current solver authority.
- Each drawing command waits for asynchronous acceptance. Busy gestures are not
  silently queued. Long raw numeric literals can remain in inspector details.
- Arcs, trim/extend, construction geometry, general Coincident creation,
  tangent/equal tools, diameter/reference dimensions, arbitrary sketch planes,
  multiple regions/holes and contextual reference geometry remain unavailable.
- The compact field lacks IME composition and screen-reader integration. Other
  platforms, every keymap/UI scale/device, and maximum-cap interactive workloads
  have not been qualified.
- Assembly checks remain explicit rooted-tree and specified-pose checks, not
  continuous collision, general closed-loop solving, structural or safety analysis.
