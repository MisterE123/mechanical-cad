# Imported mounting adapter: fixed copied plane

A bounded current-source modeling exercise, not a manufactured part design or
fastener/strength/fit certification. The base is an oblique imported 80 × 60 ×
12 mm plate with a 20 × 10 mm through slot. Its STEP bytes are self-contained in
the canonical model, and every imported face retains unknown semantic identity.
The adapter is a separate 60 × 40 × 6 mm solid with four Ø6 mm bolt clearances at
local (±22, ±12) mm and a central Ø14 mm clearance. No bolts, spacers, matching
base bolt holes, assembly joints or load cases are modeled.

The adapter outline uses the same analytic face-frame helper as the copied-face
workflow, then the production one-time fixed-plane helper offsets it by 2 mm.
A four-corner H/V and dimension-constrained outline is extruded; five independently
fixed local circle profiles make five successive Cuts. They share the literal
plane, not a centroid-relative face attachment. No imported face ID, support port,
projection or reassociation rule is saved. The helper picks the generated fixture's
top normal once inside the current exact replay; it is not general face recognition
or evidence of stable imported topology. Its projected-world axes need not equal
the STEP author's original UV axes.

## Use and reproduce

Open imported_mounting_adapter.mcad.json using matching post-1.19 development
source. Its active output is the adapter. The imported_base history branch remains
separate; export each selected active output separately rather than treating this
Part graph as a two-solid assembly. Changing thickness, bolt_radius or
clearance_radius rebuilds the adapter. Width/height change the outline from the
fixed lower-left anchor; bolt centers do not automatically track those dimensions.
The six sketches each store their own identical literal plane. A later offset of
only the outline does not move the bore profiles: update all six planes explicitly
if changing their placement together. No editable named gap parameter is implied: 2 mm was a literal, one-time offset.

From the repository root, run in the isolated CAD Python runtime (not Blender):

    PYTHONPATH=src /path/to/cad-python scripts/generate_imported_adapter.py /new/output/path

The output directory must not already exist. The script writes the complete
canonical model, two independently checked STEP and STL exports, presentation
mesh data, replacement-source and
diameter/thickness-edit models, plus verification.json. STEP exporter metadata
may differ by run; byte-for-byte STEP/canonical regeneration is not promised.
Geometric dimensions and graph intent are reproduced and independently checked.
Generated STEP binaries and execution receipts stay outside source Git.

## Verification and intentional limitations

The 2026-10-24 cloud run used Python 3.12.14 and cadquery-ocp-novtk 8.0.1.1.0:

- Valid single-solid base: 55,200 mm³; adapter: 12,797.787746669 mm³,
  matching independent analytic volumes to 1e-6 mm³ absolute tolerance.
- Exact minimum separation 2 mm and zero intersection volume; all five native
  cylindrical bore axes match the intended local centers within 1e-6 mm.
- Canonical save/reload/replay and fresh canonical STEP exports pass; both exported
  solids independently reimport with matching volumes.
- Replacing source bytes with a base translated by (100,100,100) mm leaves every
  adapter feature and its geometry/bounds unchanged. Separation then exceeds
  100 mm, deliberately demonstrating that the adapter does not follow edits.
- Thickness 8 mm and bolt radius 3.5 mm rebuild with the analytic expected volume.
  Invalid zero thickness fails replay and cannot write a STEP export.

scripts/tests/test_imported_adapter_example.py covers the native-free graph
contract, a fresh generator subprocess, and an independent checked-in-model
geometry replay process. This example found no new integration defect in this
bounded path. It is not Blender GUI, Undo, .blend, installed-package, Windows,
continuous motion, tolerancing or manufacturing qualification. Existing copied
plane UI evidence is described separately in docs/COPIED_FACE_PLANE.md.

## Optional native Blender presentation

With MCAD_ROOT set to this checkout, MCAD_PYTHON to the isolated CAD interpreter,
and MCAD_ADAPTER_OUTPUT to the generated output directory, run Blender 5.2.2 in
background/factory-startup mode with --python-exit-code 1 and
scripts/blender_imported_adapter_visual.py. It loads the canonical graph into an
editable Part scene and saves a separate contrasting-color presentation scene.
That scene uses replay-generated meshes only, at the actual 2 mm gap, not an
exploded or associative assembly. The saved .blend includes both scenes; open the
Editable adapter Part scene for canonical editing and Replay. The render is
script-generated illustration, not evidence of interactive UI authoring.
