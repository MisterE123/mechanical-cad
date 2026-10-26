# GUI-authored spur-pair exercise

This bounded cloud/Linux exercise uses the existing configurator and joint editor,
not the script-built two-stage gearbox. It is a geometry and coordinate-relation
example, not a qualified printable transmission or contact simulation.

## Accepted design

- Driver/driven: 19 / 39 teeth, module 2 mm, pressure angle 20°.
- Shared thickness 8 mm; literal CAD bore diameters 5 / 8 mm.
- Pair circular pitch backlash 0.2 mm; root clearance 0.25 × module;
  involute profile tolerance 0.01 mm.
- Shaft spacing 58 mm; driven/driver coordinate ratio −19/39.
- Driver pose 27°; driven coordinate is the generated phase plus ratio × driver.
- Two editable source Parts and the generated non-printable grounded reference.

Blender 5.2.2 GUI authoring on source `9a96fff` created a 19/37 pair, canceled
an 11-mm thickness proposal, edited the pair to 19/39 and the 8-mm driven bore,
then applied 27° through the independent joint editor. Captured canonical data
confirmed cancellation preservation, retained source/assembly identities and the
coherent 56→58-mm spacing and ratio update. The bootstrap only registered the
add-on, set up the view and observed/saved accepted state; it did not author gears
or mate data. Canonical copies and `.blend` were saved before clean GUI exit.

## Usability correction

The observed pair Edit and gear-only source-opening controls required expanding
Reusable Parts and scrolling past the reference-base mate frames. They now appear
once beneath Save/Focus, before Instances; low-level source/frame details remain
in their existing closed-by-default section. The source-opening operator still
asks before replacing the working Part. It is not a direct mesh export shortcut.

Gear-coupled Joints now lead with driver guidance instead of teaching unavailable
visual connector operations. Ordinary non-geared connector controls and help are
unchanged. Named Mate Frame editing remains available under Reusable Parts.
No geometry, recognition, permission, transaction or history rules change.

This presentation correction is later source development, **not part of the
already-built 1.24 installer**. Focused recording tests cover ordering and
nonduplicated actions, preserved driver targets and absence of the unavailable
connector tutorial. The source-loaded final GUI reopened the exact saved assembly, verified the
promoted Edit dialog and Cancel, and opened both exact embedded source Parts
through their unchanged confirmation dialogs. The accepted assembly stayed
byte-for-byte unchanged. The final reviewed `.blend` preserves the working Gear B
and focused Assembly view without overwriting the original fixture.

Independent native replay exported each individual gear as STEP and binary STL;
STEP reimport preserved one solid and volume within relative 1e-7. Binary STL
triangle records were independently counted and length-checked. Five exact pair
checks at driver 27°, 0°, 3.2210526316°, 9.2842105263° and 15.7263157895° had zero
common volume and minimum separation 0.093954991–0.094021480 mm. These five samples
do not establish contact or clearance between samples.

36 focused pure tests, touched-file Ruff, and the native Blender recording-layout
smoke passed. Its initial run exposed an inherited old progress-copy assertion
(`New pair interference NOT checked.`); the test now matches the existing
`Interference NOT checked by this update.` copy. No production progress code
changed. The initial failed log is retained, not presented as a pass.

## Evidence boundary

Development evidence is retained outside Git in
`cad_engineering_evidence/gui_gear_pair_20261025/`:

- `accepted_assembly_01.json` through `accepted_assembly_03.json` preserve revisions.
- `gui_authored_gear_pair.mcad-assembly.json` and `gui_authored_gear_pair.blend`
  preserve the accepted 27° state, including embedded Part sources.
- `gui_gear_pair_reviewed.blend`, `gui-reopen.log` and source-opening receipts
  establish the final saved state and unchanged canonical assembly.
- `independent_native_report.json` and `independent-native.log` retain exact
  replay/export, STEP reimport and all five discrete-pose results.
- Screenshots `01`–`11`, `preview.png`, `gui.log`, and `pure-tests.log` separate observed GUI,
  exact state and focused tests.

The tiny reference base is NOT FOR PRINT. Export the individual gear Parts for
gear-only STEP/STL. Neither replay nor the coordinate equation proves continuous
collision freedom, useful tooth contact, printable bore fit, load, strength,
wear, bearings or shaft design. No Windows, broad historical-suite, or new
installer qualification is implied.
