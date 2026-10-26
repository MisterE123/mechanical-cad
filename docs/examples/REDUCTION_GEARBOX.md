# Editable two-stage reduction gearbox demonstrator

A deliberately complex CAD test model, not a build-ready transmission.

## Start here

1. Install/enable Mechanical CAD Linux 1.17 in Blender 5.2.2, then open `reduction_gearbox.blend`.
2. Select the Assembly workspace/panel and Replay if needed. The file embeds all five editable source Part definitions and nine instances. No mesh is the authoritative design.
3. The saved display shows the housing as wireframe and hides the cover so the moving gears are visible. Replay/reopen rebuilds disposable display objects and may reset these appearance choices; hide the cover again and choose wireframe housing if needed. Unhide the cover in the Outliner and change the housing object's viewport Display As to Solid to inspect the enclosure. These are display choices, not removals from the assembly.
4. Edit the independent `Input Rotation` joint. The two gear relations derive the intermediate and output rotations; do not override their controlled coordinates.
5. Open a chosen Embedded Source as Working Part, edit named parameters or feature dimensions, Replay, then explicitly Update All Instances. Saving the `.blend` retains both the working Part and accepted assembly revision. A working-Part edit does not silently update accepted assembly sources.

The portable `reduction_gearbox.mcad-assembly.json` also contains every source Part and can be opened with Load Assembly. Individual `.mcad.json` files can be loaded as working Parts. The plain-text source files are canonical data, not executable code.

## Design

- Two external spur stages: 20:40 and 20:40, module 2 mm, pressure angle 20°, 4:1 overall speed reduction. Intermediate motion reverses; output motion has the input sign.
- Three parallel +Z shaft axes at X = 0, 60 and 120 mm. The middle shaft carries both the first-stage 40-tooth wheel and the second-stage 20-tooth pinion, with explicit fixed joints.
- Gear face width 8 mm; stages occupy Z = 8–16 and 24–32 mm.
- Housing stock: 200 × 100 × 42 mm, X = −30 to 170, Y = −50 to 50; inward shell wall 4 mm; four selected vertical outer corner fillets of radius 8 mm. Mounting ears extend the total X envelope to 216 mm.
- Four screw pillars, four external mounting ears, three bottom shaft bores; separate 5 mm thick cover at Z = 42–47 with matching shaft and screw holes.
- Three 8 mm diameter, 57 mm long shafts are reference-only geometry, not printable parts. They establish explicit rigid groups and revolute frames.
- Gear bores 8.4 mm; housing/cover shaft bores 8.6 mm. Backlash is 0.1 mm per gear (0.2 mm total pair circular backlash). Root clearance is 0.25 module. These are unqualified examples, not measured print fits or bearing specifications.

## Print/export inventory

| File stem | Quantity | Scope |
| --- | ---: | --- |
| gearbox_housing | 1 | Housing, shell, pillars, ears and bores |
| gearbox_cover | 1 | Removable cover |
| pinion | 2 | Both 20-tooth gears |
| wheel | 2 | Both 40-tooth gears |

Each row has checked `.stl` and `.step` exports. STL coordinates are millimetres; explicitly choose mm when importing into a slicer. STEP is exact solid exchange, not the editable feature history. The JSON/Blender documents retain that history. Gear reuse is intentional: four gear occurrences require only two reusable Part definitions.

No reference shaft or assembled/multi-part STL is included in the print set. Do not send the entire displayed mechanism to a slicer as one fused component. Screw hardware, bearings, keys, retaining rings, shaft shoulders and lubrication are not designed here.

## Edit examples

`edit_examples/` holds two independent, canonical assembly revisions:
- `wall_4_5_wider_deeper`: shell wall 4.5 mm, housing/cover 210 × 106 mm.
- `teeth_21_42_centers_63`: both stages 21:42, module 2, 63 mm centers, enlarged 210 × 106 mm housing/cover. Gear source parameters, shaft frames, bores, and relation phases are explicitly regenerated together by the example authoring script.

Do not use exactly 5 mm for the nominal housing wall with unchanged pillar positions: the pillars become tangent to the inner X walls along a line, and the checked mesh/export correctly rejects that degenerate case. The supplied 4.5 mm revision preserves a positive gap. A 5 mm failing repro is retained for diagnosis, not printing.

Assembly mate frames are literal numeric placements, not cross-document expressions. Changing a tooth count in one Part alone does not automatically move shafts or update a relation ratio/phase. Revise the related frames/bores/relations explicitly, or regenerate the coherent example variant. This is a current workflow limitation, not hidden associativity.

## Scope and cautions

This is a geometry and editability demonstrator. The gear coupling is coordinate kinematics, not tooth contact dynamics. The loose reference shafts are not keyed to the gears; fixed assembly joints express intended motion only. In particular, the separate round-bore intermediate wheel and pinion do not establish physical torque transmission without an added coupling method. No strength, torque, wear, thermal, bearing, fastening, print orientation, actual print fit, or continuous collision claim is made. Exact collision evidence covers only the listed poses and pairs, never all motion.

The source authoring and verification scripts are provided separately for reproducibility. They require the application's pinned Python/native dependencies and must run outside Blender. Native OCCT is never imported into Blender.

## Native edited revision

`reopened_wall45_updated_assembly.blend` and `native_wall45_updated_assembly.mcad-assembly.json` retain the original 200 × 100 mm footprint with the housing wall edited to 4.5 mm through the native Part parameter UI. Update All Instances explicitly accepted that source while preserving both gear relations. `native_wall45_housing.step` is the checked edited housing export. This is a separate revision; the main file remains the nominal 4 mm design.
