# Export the placed Assembly as STEP

0.7.1 candidate: checked Assembly STEP export is implemented. Focused native
writer/readback, service and registered-operator save/reopen checks passed. Exact
0.7.1 installer/manual-GUI qualification remains pending. This feature is not
present in the immutable delivered 0.7.0 installer. See [release scope](RELEASE_071.md).

1. Open the box-and-sector project, or create an Assembly from accepted Parts.
2. Edit a source Part and explicitly Update All Instances when desired. Set the
   saved joint coordinates, then Replay and Check Pose with the active preset.
3. A complete passing current-pose check, or explicit intended-contact policy
   acceptance described below, enables **Export Assembly STEP** in the Assembly workspace. Choose an explicit destination and confirm replacement
   of an existing file in Blender's file selector.
4. Export freshly rebuilds every accepted source and repeats that saved-pose
   check. A failed or incomplete check leaves the destination unchanged.

The file contains one named Assembly, one definition per referenced Part ID and
named placed instances. Two instances of one Part reference the same definition;
two different Part IDs remain distinct even if they use the same exact geometry.
Translations and rotations use the evaluated canonical pose in millimetres.
Parts are not fused. Geometry is not reconstructed from Blender display meshes.

STEP carries exchange geometry, names and placements. Use `.blend` or the
Assembly JSON file for editable source features, stable CAD IDs, joint definitions,
verification presets and revision history. STEP does not preserve these editing
contracts. No Assembly-wide STL action is included.

The last export receipt is historical file information. Undo, a source edit,
backend change or reopening the project cannot undo a file already written.
An interrupted or invalid completion is visibly unconfirmed; inspect the selected
destination before deliberately exporting again. No automatic retry occurs.
Saved PASS labels never enable export: after reopening, Replay and Check Pose
are required again.

The active preset checks only the saved pose. It does not establish continuous
motion clearance, physical fit, wall thickness, load capacity or manufacturing
approval. Broader arc/profile and rooted-tree Assembly limits remain unchanged.
Windows execution is deferred and remains unqualified.

## Focused regression

`test_assembly_step_kernel.py` reads actual XCAF STEP files back and checks names,
definition reuse, different logical identities, translated/rotated placements,
volumes, bounds and source preservation. `test_assembly_step_workflow.py` exercises
the box/sector service and an interfering-pose destination-preservation case.
`blender_assembly_step_export_smoke.py` exercises the registered operator across
two processes, stale file-selector rejection and a genuine write followed by
backend revocation. Its exact files receive a separate read-only inspection.
These are automated source-loaded checks; installed GUI qualification is separate.

## Explicit contact intent (development)

See [intended-contact policy](ASSEMBLY_INTENDED_CONTACT.md) for the optional
named zero-clearance pair exception. Measured clearance pass and threshold flags
remain unchanged; separate authored policy acceptance can permit a fresh STEP
export without claiming exact contact, no penetration, or physical fit. Legacy
defaults stay strict.
