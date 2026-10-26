# Two editable topology walkthroughs

Open either `.mcad.json` with the CAD document **Open** command, not Blender's
`.blend` Open. Use the current development add-on; these source examples do not
update an older installed ZIP. All dimensions are millimetres. Each file ends in
one fused solid, with readable feature labels and named project parameters.
Save a copy before experimenting, edit one parameter at a time, rebuild, and
save/reopen that copy to inspect the same intended attachment again.

## 1. Source-relative pad on a slotted plate

Open `source_relative_slotted_plate.mcad.json`. A 20 × 20 × 10 plate has a 2 mm
wide slot across its top, leaving a 7 mm floor. A radius-2, height-2 pad is fused
to the right-hand top region. Its constrained sketch deliberately retains the
original top-plane anchor and places its circle 5 mm along local X from there.

Try these edits in the named parameters:

1. Change `slot_length` from 22 to 10, then back to 22. The top changes from two
   face fragments to one notched face and back. The pad center stays at
   (15, 10, 10), rather than following a fragment or the notched face's centroid.
2. With `slot_length = 22`, change `plate_width` from 20 to 24. The source-plane
   origin moves from (10, 10, 10) to (12, 10, 10); the pad center follows to
   (17, 10, 10). The saved intent is source-relative, not a frozen world position.
3. `pad_radius` and `pad_height` drive the pad itself. Keep it on the right-hand
   material when exploring other dimensions; plane preservation is not a contact
   or clearance guarantee.

Inspect the sketch's support-intent explanation: **Preserve logical plane** is
an explicit assumption, not a stable identity for either split fragment. The
saved source is `plate/face/cap.end`. Both split descendants must be proven
coplanar Cut descendants. The logical plane can span the removed slot. Changing
to Strict on this split cannot select a fragment automatically; choose a valid
replacement support or cancel the edit. This example does not exercise rotated
frames or imply material-spin tracking.

Expected checks (all features `ok`, final solid valid):

- Default: slotted plate 3880 mm³; finished plate 3905.132741 mm³.
- Width 24, slot length 22: finished plate 4705.132741 mm³.
- Width 20, slot length 10: finished plate 3971.132741 mm³.
- Without preserve-plane intent at length 22: sketch `failed`, final union
  `blocked`. This is intentional fail-closed behavior, not a fallback attachment.

## 2. Pad on an enclosure's generated inner wall

Open `shell_inner_wall_pad.mcad.json`. Shell removes the top of a 20 × 15 × 10
blank with 1 mm walls. A constrained radius-2 circle is centered on the inner
left wall and extruded 3 mm into the cavity, then fused to the enclosure.

1. Change `wall_thickness` from 1 to 2. The sketch plane moves inward with the
   generated inner wall, not the retained outer left face.
2. Change `box_width` from 20 to 30. With thickness 2, the sketch-plane origin is
   (2, 7.5, 6); the pad remains on the left inner wall.
3. Save/reopen. Inspect the sketch's support and Shell's opening. The intended
   support is **the inner offset of the blank's left face**, not the top lip,
   a nearest face, or a mesh triangle. Its long saved ID encodes that source
   identity; it is not something to retype or a geometry hash.

The opening remains the blank's top face throughout these edits. If you change
Shell's opening to the left face, that particular inner wall is removed: the
sketch must fail and its downstream features must block until you choose a new
valid support. No plane-preservation assumption is enabled for this sketch.
Curved inner walls do not become planar sketch supports.

Expected checks (all features `ok`, final solid valid):

- Default: enclosure 894 mm³; with pad 931.699112 mm³.
- Width 30, thickness 2: enclosure 2212 mm³; with pad 2249.699112 mm³.

## Reproduce without Blender

From the source checkout, using the native sidecar Python with the package on
`PYTHONPATH` (replace `python` with that interpreter):

```sh
PYTHONPATH=src python -m mechanical_cad.cli replay \
  examples/topology_walkthroughs/source_relative_slotted_plate.mcad.json \
  --result-version 2 --output /tmp/slotted-plate-result.json
PYTHONPATH=src python -m mechanical_cad.cli replay \
  examples/topology_walkthroughs/shell_inner_wall_pad.mcad.json \
  --result-version 2 --output /tmp/inner-wall-result.json
PYTHONPATH=src python -m pytest -q \
  tests/integration/test_topology_walkthrough_examples.py
```

The targeted tests save/load edited copies, verify native volumes and support
origins, distinguish assumed placement from strict identity, and check the two
intentional failure cases. Native replay is not GUI or installer qualification,
and these two bounded constructions are not a general TNP solution.
