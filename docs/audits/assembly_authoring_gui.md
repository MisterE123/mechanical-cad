# Native assembly authoring GUI audit

Date: 2026-10-16. Source gate complete on **2419fc8**, with one open
Part-view discoverability/isolation issue for the final candidate.

## Result

Actual mouse/keyboard authoring passed from an ordinary constrained rectangle
Part through two reused instances, named literal frames and a slider, an explicit
minimum-clearance preset, current-pose and listed-pose checks, source editing,
all-instance Update, Cancel, invalid-input rejection, Undo/Redo, save, fresh-process
reopen, replay and fresh verification. A real 32-pose request was cancelled with
Escape while pending; a second request allowed viewport zoom before cancellation.
This qualifies the frozen source workflow, **not the final installed ZIP**.

The remaining GUI issue is that returning to Part after Assembly/reopen can show
the coincident working Part and grounded instance together. Explicit Part Focus
is absent from the compact menu/panel and unavailable through F3 on this candidate.
A visible Focus/Whole Scene fix and its actual isolation result remain to be tested.

## Environment and evidence method

- Actual native Blender **5.2.2 LTS**, cloud desktop, 1364×1024 native-window captures.
- Initial defect discovery on frozen `5366e3b`; accepted workflow and gates below
  on `<workspace>/assembly_gui_2419fc8`.
- Real sidecar Python: repository `.venv/bin/python`; sidecar project root was the
  frozen extraction, not the concurrently edited main repository.
- Startup helper registered the add-on and requested Part workspace. It created
  **no** sketch, extrusion, Part, frame, joint, preset or assembly. A read-only timer
  recorded exact Part/Assembly strings, status, object dimensions, selection, mesh
  identities and viewport distances. It also made the fresh-process launch enter
  Part explicitly, rather than claiming this was the saved default workspace.
- All model authoring, settings, checks, save actions and Undo/Redo were native UI
  actions. Source/file inspection was used only to inspect or record evidence.
- Artifacts: `/workspace/shared/cad_artifacts/assembly/`.

Ten obsolete generated QA Blender sessions were preserved before closure: six
unsaved sessions received distinct native Save As checkpoints; four already saved
sessions closed normally without overwriting their artifacts. No Don't Save or
warning bypass was used. Parent measured host memory falling 8.5→3.2 GB. This is
an environmental cleanup observation, not a product performance benchmark. Mapping
and hashes are in `../gui-session-checkpoints/`.

## Authentic Part and two-instance authoring

1. New CAD Document named `guide block`.
2. Rectangle palette tool, two viewport corners, Dimensions **12×8 mm**; solver
   okay, remaining DoF 0; Finish Sketch.
3. Extrude the Rectangle sketch **4 mm**. Native history contains Rectangle sketch
   and Extrusion; Part Check passed one valid solid, **384 mm³**, closed/oriented.
4. In Assembly, New Assembly from Part: `guide pair`, first instance `fixed block`,
   explicit Ground first instance at world origin.
5. Add literal frame `rail datum`, translation 0,0,0 mm, rotation 0,90,0 degrees.
6. Insert second instance `moving block`, reusing the same embedded Part definition;
   slider `rail slide`, both ends on rail datum, coordinate **30 mm**, limits **0–40**.

The Part is schema 2. The genuine clicked sketch anchor is
X=-0.051566694310167804 mm, Y=0; no script corrected or replaced it. The literal
frame rotates local +Z motion into world X. The second instance is translated
30 mm in X (floating-point Z residual about 5.3e-15 mm). Named instance/joint
history selects the corresponding display and frame axes. Both instances reference
one Part definition and share one generated definition mesh.

Identity anchors for artifact inspection:

- Part document: `document_7dee282e5ff041ab80b9d01ba7b676e4`
- Assembly: `assembly_27b4cb8a3339421eb25853229dab73c3`
- Reusable Part: `part_3ad8dafa193e4446b29f64580ac1efd2`
- Slider: `joint_8b1daa8db3594daaa1f11f72760c33ed`

Evidence: `01_user_created_part.png`, `04_part_exact_geometry_pass.png`,
`06_authentic_two_instances.png`, `07_named_joint_cad_palette.png`,
`authoring.blend`, `guide-pair-2419fc8.blend`, `events.jsonl`.

## Explicit clearance and sampled evidence

Created preset `guide clearance`, explicitly selected it as active, and created
requirement `running gap` between fixed/moving blocks with **minimum 2 mm**.
Preset creation alone remained UNCHECKED. Saved the accepted scene before checks.

**Current pose:** native Check Pose opened a readable workload dialog naming the
preset and 2 instances / 1 pair × 1 pose. Check transitioned to an actual pending
modal with disabled authoring controls and Checking status, then completed:
CURRENT, complete, passed; exact minimum distance **18 mm**, common volume **0**.
The simple request finished too quickly to claim manual cancellation/navigation
from that first request.

**Listed samples:** entered **0,30 mm** in the native Sample dialog. Workload changed
to 2 poses / 2 pair checks. Completed report was current and complete, aggregate
failed with known interference and clearance violation:

- 0 mm: distance **0 mm**, common volume **384 mm³**, failed.
- 30 mm: distance **18 mm**, common volume **0 mm³**, passed.

Exact accepted Part/Assembly strings and object records (locations, dimensions,
mesh identities and selection) stayed unchanged. The accepted slider remained
30 mm; sampling did not move the display. The UI and report state that only listed
discrete poses were checked. No continuous-motion collision guarantee, physical-fit,
load or manufacturing certification is claimed.

Inspect Evidence stayed in one bounded dialog, with Summary, Coordinates, Pairs
and Diagnostics sections and paging. The actual two-pose Summary used two pages;
the Pairs view showed names, distance, required distance, common volume and verdict
readably. This is direct small-example readability evidence, not a manual review
of the maximum-size 15-joint / 8-pair case.

Evidence: `08_check_workload.png`, `09_current_clearance_pair.png`,
`10_sampled_collision_and_clear.png`, `first-check.state.json`,
`pre-sample.state.json`, `sample-0-30.state.json`.

## Embedded source edit and all-instance update

Opened the reusable Part's pencil action, reviewed Open Embedded Source as Working
Part and its replacement checkbox, then accepted. In native Part Named Parameters,
changed width **12→16 mm** and rebuilt. The working Part became **16×8×4 mm**;
the assembly still contained both accepted **12×8×4 mm** instances. Assembly history
clearly said a working Part update was available and the accepted revision remained
in use.

Update All Instances dialog displayed old/new revision prefixes and explicitly
listed `fixed block` and `moving block`, with the literal-frame preservation warning.
Cancel left exact Part, Assembly, objects, report and status records unchanged.
Reopening and applying updated both instances to **16×8×4 mm**, **512 mm³** each,
sharing the updated definition mesh. Named frames and slider coordinate/limits
stayed unchanged. Verification became UNCHECKED; update/replay was not presented
as verification.

Source digest changed from `bdc884a1fc0f…` to `62e4f14265d1…`.
Evidence: `11_update_all_scope.png`, `edited-source-before-update.state.json`,
`pre-update-cancel.state.json`, `update-cancel-comparison.json`,
`after-update.state.json`.

## Native Undo/Redo, save and fresh reopen

Immediately after Update All Instances:

- Ctrl-Z restored the **exact prior Assembly JSON** and both 12 mm display widths,
  while preserving the edited 16 mm working Part. Display and evidence became STALE.
- Ctrl-Shift-Z restored the **exact updated Assembly JSON** and both 16 mm widths.
  Display/evidence still required replay/fresh checking.
- Explicit Replay restored CURRENT geometry and left UNCHECKED evidence.

Saved through native Save As to distinct `guide-pair-updated-2419fc8.blend`, verified
the file and clean title, then Ctrl-Q closed normally. Launched a **fresh process**
with the same frozen source and that saved file. Part and Assembly strings matched
exactly; display/evidence were STALE. Native Assembly Replay restored CURRENT
geometry without verifying. A new explicit Check passed at 30 mm with exact
clearance **14 mm** against the same **2 mm** requirement, common volume 0, complete.
This agrees with the widened 16 mm blocks.

Evidence: `undo-update.state.json`, `redo-update.state.json`,
`pre-reopen.state.json`, `fresh-reopen.state.json`, `fresh-replay.state.json`,
`fresh-check.state.json`, `gui-reopen.log`, `18_updated_reopened_assembly.png`.

## Real cancellation, navigation and invalid input

Entered **32 explicit sample coordinates, 0 through 31 mm**, through the native
Sample field. The workload preview showed 32 pair checks. Apply visibly entered
pending state. Escape then produced **Assembly check cancelled by the user**.
Exact Part, Assembly, objects, prior report, verification status/message and display
status stayed unchanged, retaining the prior accepted current-pose result.

Repeated with the same 32-pose workload. While the controls were visibly disabled
and status still said Checking, viewport wheel zoom worked: view distance changed
**0.06133989→0.08832945 m**. Escape cancelled; the exact model/object/report records
again remained unchanged. No synthetic backend delay was used. This tests Escape;
the pending Cancel Check button itself was not separately clicked.

Edited the slider through its native pencil dialog to **50 mm** while keeping
explicit limits **0–40 mm**. Apply rejected with `limit_violation: Authored coordinate
is outside its limits`. Exact accepted model, objects, report and currentness stayed
unchanged; the history still showed 30 mm.

Earlier on 5366e3b, native New Assembly edited-name Cancel and Escape also preserved
all accepted records. On 2419fc8, all-instance Update Cancel and the live Escape
checks above are the candidate-specific cancellation evidence.

Evidence: `12_sample_32_workload.png`, `13_live_check_cancelled.png`,
`14_navigation_cancelled.png`, `15_invalid_joint_preserved.png`,
`running-cancel-comparison.json`, `after-running-cancel.state.json`,
`navigation-cancel-comparison.json`, `invalid-joint-comparison.json`.
Some short-lived notifications appear in tool captures/events rather than every
saved screenshot; JSON comparisons and the observed native notification establish
the cancellation/rejection result.

## UI observations and remaining limits

- Hiding Blender's stock toolbar with **T** exposed the contextual CAD palette.
  Keeping the stock toolbar visible intentionally suppresses the overlapping CAD
  palette. Screenshot 06 shows the stock toolbar; 07 shows the real CAD palette.
- Part vector glyphs are large and distinct at native scale (rectangle, extrusion,
  check, export); disabled Cut is muted. Actual extrusion hover highlighted blue
  and showed readable action help (`16_part_glyph_hover.png`).
- Editing the original rectangle showed distinct Dimensions, Finish and Cancel
  glyphs. Dimensions hover highlighted blue and displayed readable millimetre/
  expression help (`17_sketch_glyph_hover.png`). Cancel Sketch discarded the
  unchanged inspection draft; accepted Part remained semantically unchanged and
  Assembly/report strings stayed exact/current.
- Assembly icons are smaller and less distinctive than the Part/Sketch glyphs.
  Named history labels and selected orange axes are useful; unselected black axes
  have weaker contrast. No exhaustive icon accessibility or high-DPI audit occurred.
- Default Outliner/Properties consume substantial width. The compact CAD panel
  requires vertical scrolling and truncates long labels, including the two sketch
  parameter labels to `sketch...`. Result dialogs are substantially clearer than
  the narrow sidebar. These are layout polish findings, not integrity failures.
- **Open:** returning to Part can expose coincident working Part/grounded assembly
  display with z-fighting. Display Selected rebuilds without isolating it. Compact
  Part menu/history omit Focus/Whole Scene; F3 searches for Focus CAD and Regenerate/
  Rebuild returned no results. The Focus operators lack the REGISTER flag and are absent from the compact
  menu; the exact search-index cause is not established. Visible controls are planned. Their final-button isolation behavior is
  not yet qualified. Sketch view also inherited assembly datum overlays.
- The original near-plane defect was fixed on this candidate: Assembly focus and
  opening embedded source used clip start about **1.49666e-5 m**, giving intact box
  faces. This does not close the separate coincident-display issue above.
- On the first frame-dialog attempt, automation input ran before text focus was
  confirmed; a default frame was applied and subsequent keys reached Blender
  shortcuts, briefly disturbing display/selection. Stopped the input and used
  explicit Replay to restore the accepted display, then edited the frame normally.
  This is recorded as an input-timing incident, not a product authoring failure.
  Later dialogs used verified caret/focus before text entry. The frame number 234
  visible in screenshots came from that incident and has no CAD pose meaning.
- No final installed-ZIP, other Blender version, maximum-size dialog, closed-loop
  assembly, arbitrary mating-face inference, or continuous collision pass is claimed.

## Defects discovered earlier and verified fixed here

On 5366e3b, capture of the authentic schema-2 Part failed closed with source_mismatch
because raw UI optional constraint fields and core canonical serialization hashed
differently. Parent fixed authoritative snapshot serialization (`5afacba`); actual
capture/reuse/source-update/fresh-reopen on 2419fc8 passed with the same real Part.
Evidence: `02_schema2_capture_blocker.png`, original schema-2 JSON/state.

The earlier Part viewport near plane 0.01 m intersected the focused millimetre-scale
box, showing triangular patches/clipped silhouette despite valid exact geometry.
A native Clip Start 0.00001 m experiment immediately fixed the appearance; it was
restored before production-fix validation. Parent scoped CAD focus fix `b7d7f55`
was included in 2419fc8 and exercised by real assembly/open-source focus above.
Evidence: `03_part_orbit_shading.png`, `04_part_exact_geometry_pass.png`,
`05_part_near_plane_fixed.png`.
