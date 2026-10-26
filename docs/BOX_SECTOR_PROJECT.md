# One editable box-and-sector project

Use [the portable example](../examples/box_sector/assembly.mcad-assembly.json)
with the development backend supporting `mcad.assembly-result/3` and
`mcad.snapshot-sketch3/1`. It contains a 40 × 30 × 10 mm box and two instances
of one fully constrained quarter-sector Part, radius 5 mm and height 10 mm.
The delivered 0.6 preview does not support this integrated workflow.

1. In **Assembly**, load the example. The grounded instance is `base` and the
   reusable definitions are `box` and `sector`. `sector_a` and `sector_b`
   both use the same embedded `box_sector_quadrant` source. **Replay** rebuilds
   display geometry; **Check** separately verifies the selected requirements.
2. To edit the box, select `box` and choose **Edit Part / Export Part**.
   Confirm replacing the working Part. Its `width`, `depth` and `height`
   parameters drive the rectangle and extrusion. Change a dimension and
   regenerate, then return to Assembly and explicitly **Update All Instances**.
   Opening or editing a working Part never silently changes accepted instances.
3. To edit both sectors, select `sector`, choose **Edit Part / Export Part**,
   and confirm. Change `radius` from 5 to 7 and regenerate, or edit the sketch's
   `sector_radius` dimension. The arc `rim`, two radial lines, profile and `pad`
   extrusion keep their IDs. **Update All Instances** accepts the revised source
   for both `sector_a` and `sector_b` together; **Check** again afterward.
4. Inspect the named box frames `seat_a` and `seat_b`. Their literal coordinates
   are (10,10,10) and (25,10,10) mm. The joints `slide_a` and `slide_b` join these
   frames to the sector's `origin` with +Z sliders. Each saved coordinate is
   10 mm, so the sector origins are at z=20 mm. Slider coordinates use
   millimetres; revolute authoring uses degrees and saves radians. Literal
   frames do not follow a changed box height automatically.
5. The active `base_clearance` preset explicitly requires at least 2 mm between
   the box and each sector. At the initial dimensions and coordinate 10 mm,
   each gap is 10 mm. Edit `slide_a` to -5 mm and sample `-5, 10` to see a known
   collision at the first pose. Restore the saved coordinate to 10 mm and
   **Check**. Sampling leaves the saved coordinate alone. Only listed poses
   were checked; this does not establish continuous collision freedom.
6. To export, select the desired reusable Part, use **Edit Part / Export Part**,
   then run Part **Geometry Check** and **Export STEP** or **Export STL** to
   your chosen path. These are individual-Part exports; Assembly-wide export
   is not available. Import STL coordinates as millimetres.
7. Save the portable Assembly JSON and the Blender project. Reopening keeps
   editable source snapshots and readable historical reports. Explicitly
   **Replay**, then **Check**, to obtain current evidence after reopening.

The checked-in example is canonical source-generated JSON, not a claim that it
was drawn manually in the GUI. The
[native project regression](../tests/blender_sector_assembly_workflow_smoke.py)
starts from blank Parts, uses the existing sector point/constraint adapters and
registered operators, and generates the actual `.blend`, source JSON and Part
exports in a new test-owned output directory. Its STEP/STL assertions observe the
actual writer output, and a second Blender process tests reopening. It does not
establish installed-package or manual-GUI qualification. Geometry and clearance
checks are not physical-fit, structural or manufacturing certification.
