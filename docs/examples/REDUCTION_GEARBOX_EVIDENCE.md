# Geometry stress-test report

## Build identity

The demonstrator targets Mechanical CAD Linux 1.17, frozen source `95a85d88607a2b236f598076cf5767e7f3197d2d`, with the existing OCCT sidecar. The example scripts and notes are new; no application implementation or topology/currentness/security guard was changed to accept the design.

## Verified geometry

Five reusable editable source Parts produce nine assembly instances. The housing has 66 exact faces, the cover 17, each 20-tooth pinion 163, each 40-tooth wheel 323, and the reference shaft 3. Every source regenerates as one valid solid. The housing's feature graph combines a selected-four-edge fillet, open-face shell, eight additive cylinders, eleven subtractive bores and their explicit sketches/extrusions/booleans.

The exported print set contains four unique Part definitions: housing, cover, pinion and wheel. Each has a freshly regenerated and checked STEP and binary STL; the pinion and wheel are reused twice. Mesh manifold checks and STL float32 encoding checks are applied by the application's export service. The reference shafts are excluded.

`geometry_evidence.json` records source dimensions/volumes, export metadata, the exact pose list and pair measurements, and upstream revisions. Both gear meshes had zero Common volume and minimum surface separations of approximately 0.09396–0.09401 mm at input angles 0°, 3.06°, 8.82°, 14.94° and 90°. The 0°/90° cases additionally checked seven housing/gear/shaft pairs and two cover/gear pairs: 28 explicit static pair checks total, all complete with no interference. Listed static poses do not prove collision-free continuous motion.

Both upstream revisions regenerated all five sources as valid single solids: a 4.5 mm wall / wider-deeper case and a coherent 21:42-tooth / 63 mm-center case. Variant geometry validity is established; the nominal pose-sampling result is not silently applied to those variants.

## Native edit loop

At the unchanged 60-second per-backend-action limit, a fresh Blender process reopened the nominal file and revalidated sources (24.362 s), opened embedded housing (41.880 s), edited the numeric wall from 4 to 4.5 mm and regenerated (26.960 s), and exported an actual PASSED STEP file (45.190 s, 269,306 bytes). Explicit Update All Instances then completed in 25.410 s, retained both gear relations, and saved the revised assembly. The source volume changed from 179,010.4696 to 198,005.6785 mm³. A second independent process reopened the revised file, preserved its exact canonical assembly, and revalidated it in 24.107 s. Both native passes finished with exit code 0 and the explicit GEARBOX_NATIVE_OK marker. Timings are measured end-to-end stage durations, not solely kernel time.

## Findings, carefully classified

1. Design correction, not an application defect: an initial 2 mm outer fillet combined with an inward 4 mm shell failed OCCT construction. The inner corner radius would collapse. An explicit 8 mm outer radius makes the design coherent; the final shell and subsequent features regenerate. The four-feature failing input is retained in `repros/shell_radius_smaller_than_wall.mcad.json`, with the original failure diagnostic in the evidence record. No topology reference was guessed or silently replaced.
2. Contention-associated timeout, not a reproduced geometry/default-limit bug: opening an embedded pinion after loading the full assembly reached the Linux default 60-second sidecar deadline while another native exact-geometry check was active. It failed visibly without publishing stale output. After both core batches stopped, a sequential repeat at the unchanged 60-second setting passed: Load Assembly 24.611 s, embedded pinion open 5.072 s, STL export 6.174 s, `.blend` save 5.398 s. The canonical assembly is 38,296 bytes. No higher timeout or application-default change was needed. Native stage reports preserve the measured conditions and durations.
3. Explicit design limitation: assembly frames are literals. Gear tooth-count edits alone do not drive housing bores, shaft centers or relation phase/ratio. The supplied coherent revision changes these together; ordinary UI work requires explicit related edits. Automatic cross-Part design equations are not claimed.

Native evidence uses Blender 5.2.2 LTS with the enabled source add-on and the established isolated native runtime. It is a background native workflow check, not a new ZIP-installer qualification, Windows test, or interactive GUI usability claim. Three focused authoring/kinematics tests pass; the full historical suite was not rerun for this example-only branch.

4. Expected tangent-design rejection: at exactly 5 mm wall thickness, the radius-5 pillars at X = −20/160 become tangent to the inner X walls at −25/165. Replay still reports a valid single B-rep, but manifold/export checks reject it at both 0.1 mm and Blender’s float32 representation of that tolerance. The focused investigation confirmed four welded vertical mesh edges with four triangle incidences, at X = −25/165, Y = ±39, Z = 6–42. Separate probes at wall 4.5 and 5.1 pass. The deliverable edit example uses 4.5 mm, and the wall-5 inputs and probe evidence are retained under `repros/`, not the print set.
5. Failure-diagnostic defect exposed by that rejected source: Update All Instances wraps the genuine mesh failure as “associative pose lacks resolved part evidence” because the literal geared pre-build pose is checked as though native Parts already exist. The authentic source rejection must remain noncurrent; the isolated application fix `e789984` restores the specific failure diagnostic without granting Parts/verification authority or relaxing face-associated evidence checks. It is supplied separately for integration; the primary model was built on the frozen 1.17 feature source.

A Blender export operator returning FINISHED means its report transaction completed, not necessarily that a file was written; actual file existence and PASSED geometry status are checked in the corrected native proof.

The nominal model and safe revisions are valid; the tangent case is not made printable by hiding its rejection. The case is retained as a repeatable complex modeling and usability benchmark rather than manufacturing assurance.
