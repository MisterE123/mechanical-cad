# Literal geared assembly source-failure diagnostic

Bounded native OCCT investigation, 2026-10-24. No GUI, installer, Windows,
full-suite or manufacturing qualification is implied.

## Geometry classification

The retained reduction gearbox housing has a 200 × 100 mm envelope, 8 mm
outer corner fillets and an editable wall. Exact comparison of its wall=5 mm
canonical input on frozen `95a85d8` and development `ca7c1e2` gives the same
valid single B-rep solid: 76 faces, volume 216689.82948754684 mm³.
Both 0.1 and 0.10000000149011612 mm tessellation deflections fail the existing
closed oriented manifold mesh check on both versions. The intervening Boolean
operand-copy fix does not remove this failure.

Inspection of the check's welded edge incidence identifies four non-manifold
vertical edges, each used by four triangles, at x=-25 or 165 mm and y=-39 or
39 mm, spanning z=6 to 42 mm. These are exact tangent pillar/wall contacts,
not evidence that a triangulation-cleanup workaround is warranted. Native B-rep
validity is not sufficient for the application's stricter export contract.
No welding tolerance, mesh, solid, currentness or export guard was changed.

## Diagnostic defect and bounded correction

For an assembly with gear relations but exclusively literal mate frames, the
service evaluates canonical kinematics before checking source geometry. A source
failure can therefore correctly return the evaluated literal base pose, no
resolved Part payloads, no verification poses, and complete=false/passed=false.
The client previously required native resolved Parts for that literal pose and
replaced the real source failure with “associative pose lacks resolved part
evidence”.

The client now rederives exclusively literal geared transforms from canonical
literal mate frames. Face-attached datums still require complete resolved native
Part evidence; forged transforms remain rejected. No failed response acquires
geometry, display, export or verification authority.

Using the exact wall=5 housing as the source in a four-instance literal geared
fixture reproduced the native failure before and after the correction:

- Before: client rejects the packet as malformed, masking `assembly_kernel_error`.
- After: client validates the failure packet and retains “Mesh is not watertight
  with consistently oriented manifold edges”; zero Parts and verification poses,
  complete=false and passed=false remain unchanged.
- Fresh source STEP export remains ok=false with `geometry_check_failed`, a null
  export receipt, and an existing destination sentinel preserved byte-for-byte.

## Operator return contract

The Part geometry operators' `FINISHED` return means their explicit report/display
transaction completed, not that a file was written. Existing native
`blender_geometry_actions_smoke.py` tests intentionally expect that return even
for failed replay and export I/O, and separately assert failure status, null
receipts and preserved destination files. No operator-return behavior was changed.
Callers must inspect the geometry report/status and export receipt instead of
using `FINISHED` as proof of an exported file.

## Focused verification

33 tests passed across `test_assembly_gear_service.py`,
`test_assembly_face_frames.py`, and `test_assembly_gears.py`, using the pinned
native development interpreter. Added regressions cover native replay failure,
an injected mesh-gate failure after native replay, forged literal transforms,
and the retained resolved-evidence requirement for face-attached geared frames.
The exact complex housing was additionally exercised through native replay,
mesh check, assembly failure-packet validation and protected STEP export as
reported above. Changed Python files pass Ruff. No broad suite was run.
