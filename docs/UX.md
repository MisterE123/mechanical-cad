# Interaction contract and acceptance criteria

## Current preview: 0.5 explicit constraints

The current preview has three CAD workspaces, direct line/circle drawing,
line-distance and circle-radius annotations with compact expression editing,
persistent recoverable drafts, and downstream sketch-to-Part edits. The rectangle
shortcut remains available. The 0.3 rooted-tree assembly workflow is retained.
Version 0.5 adds explicit Points, H/V, Fix here, confirmed Fix at origin, relation
inspection, solved-position release and confirmed authored-position recovery.
Check/Finish/Cancel now retain their left-palette positions across context changes.
See [the current workflow](GENERAL_SKETCH_WORKFLOW.md) and
[verification scope](VERIFICATION.md). This is still a bounded preview, not the
complete requested sketch/Part/assembly application. Broader constraint editing,
contextual geometry, multiple regions and general assembly solving remain open.

The exact 0.4 installed ZIP passed native Blender 5.2.2 GUI creation, compact
radius editing, invalid-input retention, same-Part upstream edits, annotation
persistence, legacy Rectangle Resume, and fresh-process reload/Edit. See the
[bounded installed receipt](audits/line_circle_installed_040.md). First outside
click suspension, lack of IME support and broader constraint/UI limitations stay
explicit; this is not a claim of finished full-CAD usability.

The exact 0.5 installed ZIP separately passed manual four-line constraint authoring
to 0 DoF, 4 × 3 × 10 mm extrusion, same-feature width edit to 5 mm, release/Undo,
conflict-recovery Apply/Cancel, Circle-center anchoring, legacy Rectangle Resume
and fresh-process reopen with exact annotations. The final Part was 150 mm³.
See [the installed 0.5 receipt](audits/constraint_installed_050.md). Mouse Cancel
Check and startup-failure paths were not manually observed in that run; their
automated native evidence remains separately identified. Arcs are still absent.

The following stage records are historical. Their exclusions describe the named
stage, not the current preview. Keep them separate from later test evidence.


## Status and purpose

This is the product interaction contract, not a claim that every item is implemented.
The first slice is an experimental, panel-driven parametric foundation. It is **not
the requested full 2D-to-mechanical-assembly MVP**. Implementation and verification
must be reported separately. See [ROADMAP.md](ROADMAP.md) for the three stages.

The current scope retains construction sketches and skips 2D drawing sheets or
document output. The goal is watertight object creation and mechanical assembly
verification before manufacturing. This does not imply structural/load validation.

The first-slice scope agreed with the implementation owner is:

- Blank document and example document entry points.
- Rectangle and circle profiles entered with explicit millimetre coordinates.
- Extrude with an explicit profile; cut with explicit base and tool solids.
- Editable parameters, feature history/status/errors, and an active output.
- JSON save/load and document JSON persisted in the Blender file.
- Contextual in-app help and tool/property descriptions.

The released foundation does not include viewport sketch drawing, snapping, a
general geometric constraint editor, mates, assemblies, or mechanism motion. A
subsequent source prototype now has a narrow solver-backed viewport rectangle
workflow, with evidence recorded below. Do not label this rectangle subset as a
completed constrained-sketch editor.

### Review status and remaining limitations

The first UI implementation uses editable document parameters rather than a full
feature-property editor; no feature deletion is promised. Parameter changes mark
the document Dirty and hide its display until Regenerate. A failed regeneration
now restores a wireframe explicitly named STALE / last-good, while the panel shows
Failed and identifies the invalid input. Correction and successful regeneration
restore the current solid. A successful B-rep replay does not alone establish that
the display mesh is welded/manifold or suitable for manufacturing.

Actual GUI review on Blender 4.3.2, 2026-10-16, exercised these source-loaded UI
workflows (separate from automated tests and ZIP installation):

- Demo creation: Undo removes the CAD document/output; Redo restores five features,
  four parameters, and the drilled plate.
- Width `40` to `60`, then Regenerate: Dirty becomes Ready with a wider plate.
  Undo returns the Dirty `60` state; a second Undo restores the Ready `40` plate.
  Two Redo steps restore those states in order, with matching geometry/status.
- Rectangle Apply adds a profile and five named parameters. Undo restores the
  prior drilled plate; Redo restores the profile and its parameters.
- Rectangle draft width `100`, inline Help through all five pages, then collapse:
  the draft values survive. Esc cancels without changing history or the solid.
  Earlier nested-popup draft loss was fixed by keeping help in the draft dialog.
- Width `-1`, then Regenerate: explicit Failed status and STALE last-good wireframe.
  Correcting to `60` and regenerating restores Ready and the prior valid solid.
- Focus Result isolates the CAD output; Whole Scene restores unrelated objects.
  Standalone contextual popups use bounded pages. Failed-build text wraps within
  the default sidebar width; a separate full-diagnostic popup is readable.

Remaining observed issue: Demo Undo/Redo does not restore Local View isolation or
framing; Focus Result recovers visibility. This is an explicit open UI finding,
not a pass of the corresponding visibility criterion. The previous off-screen
Help text and nested-popup draft-loss issues were retested after their fixes.
This source-loaded GUI evidence does not verify Blender 5.2.2, full operand
authoring, all tooltips, unit-suffix handling, or missing-backend recovery.
Report separate test evidence for those paths and exact runtimes.

A separate clean Blender 4.3.2 GUI run installed the final `689a414` ZIP through
Preferences → Add-ons → Install from Disk, with Enable on Install selected. The
installed add-on reported version `0.1.0`. After configuring the existing project
root and external Python in Preferences, Demo created five named features, the
40 × 30 × 10 mm plate with radius 4 mm, and volume 11,497.345 mm³. The panel read
`Ready: CAD replay passed`. This used the installed module, with no source import
or console registration. The QA scene was saved as `dist/installed-qa.blend`.
The installed ZIP's SHA-256 was
`00893cd76c17d5ddcd78632cf548638cf4c519aac475b689673f2cdffd2088a0`.

## Next working interface: three real workspaces

### Version 0.2 native interaction evidence, 2026-10-16

Actual source-loaded Blender **5.2.2 LTS** GUI testing passed this narrow loop:

- Part → New Sketch activated the actual Sketch workspace. Two viewport clicks
  created a transient XY rectangle, with visible millimetre dimensions and an
  explicit fixed lower-left corner. The unvalidated draft was labelled unverified.
- Dimensions → width `40`, height `30` → Apply returned a real solver result with
  zero remaining degrees of freedom. Finish committed `sketch_1` and returned to
  Part. Explicit +Z extrusion length `10` created `extrude_1`.
- Selecting the original sketch preserved the active solid display. Edit Sketch,
  width `60`, inline Help paging, Apply, and Finish rebuilt the same `extrude_1`
  with two history entries, rather than creating another sketch or part.
- Native Undo restored the smaller solid; Redo restored the larger one, with
  matching history/status and usable Local View. In-app Geometry Check reported
  volume **18,000 mm³**, one valid solid, and closed, oriented seam-welded
  tessellation for the rebuilt result.
- The generated QA scene was saved to a distinct `.blend` artifact and reopened
  in a fresh process with the add-on's real load handler active. Saved history
  loaded Dirty with geometry Outdated. Rebuild restored the same part, and Edit
  Sketch reopened its stored `60 × 30` dimensions.
- Releasing **Fix rectangle position** gave a real two remaining degrees of
  freedom without moving the existing rectangle. Finish preserved the same part;
  one Undo restored zero DoF and Redo restored two. Reopening the free sketch and
  re-fixing its current corner gave zero DoF without movement. Cancel preserved
  the committed free sketch and its two DoF.
- Width `-1` and unsupported unit-suffixed input `60mm` were rejected while the
  last valid outline and raw input remained available. Correcting to `60` solved
  successfully. The current dialog explicitly explains entering `60` for 60 mm,
  not `60mm`; unit suffixes and conversion remain unavailable.
- Cancel restored the original committed anchor and history. A temporary width
  `90` followed by switching to Part without Finish left the committed volume at
  **18,000 mm³**, as confirmed by Geometry Check. Repeated editing remained usable.
- The final cancellation-disclosure check showed a warning before switching,
  then a wrapped destination notice that no draft changes were committed. The
  transient outline and controls disappeared. Assembly explicitly said its tools
  were not implemented.

An actual native-dialog confirmation bug was found and fixed before the successful
run: Apply re-polled while its own popup flag was set, leaving the tool locked.
Plain Apply and Help → Apply were retested successfully after the correction.
An old-seed-induced jump on releasing the fixed corner was also found and fixed;
the no-jump, Finish, Undo/Redo, re-fix and Cancel sequence above was retested in a
fresh process. These results describe source-loaded version 0.2 behavior, separate
from the shipped Stage 1 ZIP and any subsequent final-package installation test.

Remaining interface limits include no live extrusion preview, no general sketch
constraint editor or snapping, no viewport circle/line authoring, and no assembly
operations. Draft dimension labels can extend under the sidebar when editing a
larger profile; the old downstream display is visible behind the edit preview.
The left palette's native glyphs are small and low-contrast before hover. These
are visible usability findings, not completed polish gates.

The final staged setup was visually checked in a fresh Blender 5.2.2 process at
1180-pixel width and maximized: **Sketch → Part → Assembly → Layout → Modeling…**.
The active CAD tab is immediately visible, and ordinary tabs retain their relative
order. This fixes the earlier trailing-tab discoverability issue. Light theme, high-DPI,
Industry Compatible keymap, all operand-authoring paths, and every tooltip were
not comprehensively retested in this native interaction pass.

### Required workflow

The user explicitly requested **Sketch**, **Part**, and **Assembly** as three
actual workspace tabs, with distinct contextual tools and menus. They share one
canonical CAD document. A selector inside one sidebar does not meet this request.
The final design is sketching-first: compact tools on the left, editable geometry
and dimensions in the viewport, and feature history with a small selected-feature
inspector on the right. Instructions and parameter tables are expandable help,
not the dominant screen. See [NATIVE_CAD_WORKSPACE.md](NATIVE_CAD_WORKSPACE.md) for
supported Blender API boundaries and the isolated prototype.

The first interactive increment has a narrow but real acceptance loop:

1. From Part, New Sketch opens the actual Sketch tab on an explicitly identified
   plane. The origin, units, selected tool, and Finish/Cancel controls are visible.
2. Draw a rectangle in the viewport. Before commit, see its dimensions, type exact
   width/depth, navigate without accidental commit, and cancel without a history
   or mesh change. Repeat the tool without accumulating previews or handlers.
3. Finish Sketch commits one named profile and returns to Part. Select it and
   preview an extrusion with an explicit direction and length. Apply creates one
   solid feature; Cancel restores the previous document and display.
4. Edit Sketch from that part's history opens the original profile. Change its
   on-screen dimension, Finish, and obtain the rebuilt downstream part. Feature
   identity and references survive; this must not create an unrelated duplicate.
5. Undo/Redo restores matching document, geometry, selection/status, and a usable
   view. Save/reopen preserves the same editable cross-workspace workflow.
6. Draw a circle, dimension it, and make a finite extrusion/cut with clearly named
   and highlighted operands. Invalid dimensions or failed geometry leave a
   correctable draft and an explicitly identified last committed result.
7. Assembly exists as its own tab, but clearly states which assembly actions are
   available. Until components/mates/motion are implemented, an empty assembly
   screen is a scaffold, not a completed assembly workflow.

Three tabs, icon rendering, or a temporary drawing overlay alone do not pass this
loop. Primitive dimensions do not establish a general constraint solver; no fake
fully-constrained/DoF badges are acceptable. Every best-guess snap or relation must
be shown before acceptance, explainable locally, and rejectable. Workspace changes
during a draft deterministically cancel or explicitly suspend it, never silently
commit. Modal tools must release their draw handlers and event ownership on Esc,
file load, window/scene changes, add-on disable, and external Undo.

Record actual GUI evidence for normal and narrow viewports, light/dark themes,
ordinary/high-DPI scale, and the supported navigation keymaps. Each icon has a
hover explanation and a named searchable action; workspace identity, dimensions,
units, operands, and failures retain text. The default workflow must be usable
without opening Help, while Help remains available without losing draft values.

## A shared mental model

1. **Document:** design parameters and an explicit dependency graph of features.
2. **Profile/sketch:** geometry in a named plane; a valid closed profile can create a
   solid. A future sketch need not be fully constrained to create a solid.
3. **Feature:** a named, editable operation with named inputs and parameters.
4. **Body/part:** the current solid result, with its design history still available.
5. **Component instance:** a placed use of a part, with assembly relationships.

The CAD document is authoritative. Blender geometry is its displayed result.
Selecting or renaming a displayed object must not silently change dependency IDs.
Blender Undo and Adjust Last Operation are useful integration points, but neither
replaces editable feature history that survives save/reopen.

Use familiar Blender navigation, selection highlighting, panels, tool search,
gizmos, and Undo where they help. Do not globally replace the user's keymap. Tools
must have visible controls and clear current-mode instructions so shortcuts are
optional. An eventual sketch editor must visibly distinguish sketch entity editing
from Blender mesh Edit Mode.

Generated-mesh edits must never be silently represented as parametric CAD edits.
Until transform/edit integration exists, disclose which changes rebuild will
overwrite. A future explicit “Create mesh copy” action can support Blender-native
work without destroying the original design history.

## Next-version icon-first interface

This is planned after the Stage 1 baseline; it is not an asset or UI change already
shipped in that baseline. Prefer Google Material Symbols for common actions and
original mechanical glyphs when a generic symbol would obscure the operation.
Keep dimensions, parameter and operand names, units, and warnings readable as text.

Acceptance criteria:

- Every icon has a stable action ID and an accurate hover description: action name,
  result, required input, and any important limit. Keyboard focus and tool search
  expose the same action name; hover is not the only way to discover meaning.
- Use one visual family, optical scale, and stroke weight. Test light/dark themes,
  normal/high-DPI scaling, and both enabled and disabled states in Blender.
- Selected, inferred, dirty, failed, and stale states have text/shape cues; color
  alone must not carry their meaning. Hide no failure reason behind a tiny icon.
- Preserve optional labels for learning and unfamiliar CAD actions. Destructive
  or ambiguous actions keep a plain-language confirmation/operand explanation.
- Boolean Cut, sketch Trim, and Delete use distinct glyphs. Extrude shows a closed
  profile and a normal-direction arrow; a generic upload arrow is insufficient.
- Bundle only selected assets for offline use, with a source/version/license
  manifest. Keep the upstream license and relevant notices; identify modifications.
  Custom glyphs record authorship and the project's chosen license.

Proposed semantic map (Material names are candidates to verify against the pinned
upstream revision before importing assets):

| Action ID | Preferred symbol or original glyph | Hover-description content |
| --- | --- | --- |
| `document.new` | `add_box` | Start an empty CAD document; explain replacement/Undo. |
| `document.load` | `folder_open` | Open a saved CAD history; preserve current design on rejection. |
| `document.save` | `save` | Save editable CAD history as `.mcad.json`. |
| `history.regenerate` | `refresh` | Rebuild from saved parameters; diagnose failed dependencies. |
| `view.focus` | `center_focus_strong` | Isolate and frame the current CAD result. |
| `view.whole_scene` | `select_all` candidate | Leave isolated view; do not imply selecting every object. |
| `help.context` | `help` | Explain this tool's inputs, recovery, and current limits. |
| `units` | `straighten` | Explain model units and numeric-entry conventions. |
| `setup.backend` | `settings` | Configure and check the external CAD backend. |
| `sketch.rectangle` | Original rectangle/corner glyph | Create an XY profile with explicit corner and dimensions. |
| `sketch.circle` | Original circle/radius glyph | Create an XY profile with explicit centre and radius. |
| `feature.extrude` | Original profile/normal-arrow glyph | Choose a profile and positive +Z length in mm. |
| `feature.cut` | Original solid/removed-volume glyph | Subtract Tool from Base; show both named operands. |
| `assembly.instance` | Original repeated-part/placement glyph | Place a linked part instance; planned capability. |
| `mate.revolute`, `mate.slider` | Distinct axis/rotation and axis/translation glyphs | Show allowed motion and remaining DoF; planned. |
| `verify.interference`, `verify.clearance` | Overlapping solids / dimension between faces | Explain exact check, tolerance, and unchecked cases; planned. |

Official sources checked 2026-10-16:
[Google Material Symbols guide](https://developers.google.com/fonts/docs/material_symbols)
and [Google's icon repository](https://github.com/google/material-design-icons)
state Apache License 2.0. Use the exact upstream license file in the asset package;
do not confuse Google's symbols with similarly named third-party icon libraries.

## First-slice reference workflow

Use a small mounting plate as the reproducible acceptance example:

1. Open a blank document. The UI shows `mm`, the active document, and where to start.
2. Add `Plate profile`: XY rectangle, corner `(0, 0, 0)`, width `80`, height `50`.
3. Extrude that profile `8` to create `Plate solid`.
4. Add `Hole profile`: XY circle, centre `(15, 25, 0)`, radius `5`.
5. Extrude that profile `8` to create `Hole tool`.
6. Cut `Plate solid` using `Hole tool`; make `Drilled plate` the active output.
7. Edit width to `100` and rebuild. The hole remains at the explicitly defined
   coordinates. Edit radius to `6` and confirm that the cut updates.
8. Cancel a parameter edit, then try an invalid radius. Neither silently destroys
   the previously valid model. Correct the value and rebuild successfully.
9. Save JSON and a `.blend`, close/reopen, edit the original profile, and rebuild.

In this slice, a cut uses two finite solids. Do not describe it as “Through all”
unless that feature is implemented. If thickness changes, the tool extrusion must
also be changed or both lengths must reference the same supported parameter.

## First-slice release gates

These are testable requirements. Record **pass**, **fail**, or **not run** for the
exact tested Blender version; do not infer UI success from core unit tests.

### F1. Discoverability and help

- The first screen offers a clear blank/demo choice and a short workflow overview.
- Every visible action and editable property has a meaningful tooltip. Each
  workflow section exposes contextual help without opening a browser or terminal.
- Invalid/unavailable actions explain the required selection or prerequisite.
- Popups use short lines and ordinary language. They fit the normal panel/window
  size without clipped essential text. Long topics are split into smaller topics.
- Current limitations appear in-app, including fixed-plane profiles and mm-only
  numeric/formula entry. Planned functions cannot look like working controls.

### F2. Explicit operand selection

- Extrude displays the chosen profile's name/ID. Cut displays **Base (kept solid)**
  and **Tool (material to remove)** separately before committing.
- Inputs are type-checked. A missing, wrong-type, or same-as-base tool selection
  produces a specific corrective message, with no partial operation.
- The active output is visibly distinct from the selected history row and from
  the chosen tool. Renaming a feature does not break existing references.
- Repeating a create operation produces a distinct feature ID. Repeated rebuilds
  do not append duplicate features or Blender output objects.
- A suggested operand is visible and changeable. An ambiguous selection is not
  silently converted into a subtraction decision.

### F3. True history and parameter editing

- The list shows feature name, operation type, and readable status. Selecting a
  row exposes its saved parameters and named inputs, not generic new-feature defaults.
- Changing an earlier profile rebuilds affected downstream geometry while
  retaining identities and unrelated parameters.
- Deleting an input with dependents is blocked with their names, or uses an
  explicit dependency-aware workflow. No silent cascade or substitute reference.
- A JSON round trip and a `.blend` reopen preserve parameters, input IDs, feature
  order/dependencies, active output, and subsequent editability.
- If the first UI only edits document parameters, not arbitrary feature fields,
  disclose that limit; do not claim full feature editing has passed.

### F4. Preview, commit, cancel, and recovery

- Opening and cancelling a create/edit dialog leaves saved document content,
  displayed geometry, active output, and selection unchanged.
- A successful operation is one understandable Undo step. Undo/redo keeps the
  persisted CAD document and displayed output synchronized.
- Edits are validated before replacing the committed document/output. Failed
  rebuilds retain the last-good geometry and identify the failed feature/parameter.
- If edited document data is retained after a failed build, label the output
  **Out of date: showing last successful build**. Never show “up to date” merely
  because some mesh is visible. Distinguish saved, changed, building, failed,
  and current-output status where these states exist.
- A panel dialog without live geometry is described as **no live preview**.
  It must still have reliable Cancel. A future viewport preview is temporary,
  distinguishable from the committed solid, and removed on Cancel/Esc.
- Repeated Apply/Rebuild clicks and a failure followed by correction neither
  duplicate features nor accumulate orphan preview objects.
- A cancelled file dialog or failed load preserves the previously open document.

### F5. Units and numeric input

- Every dimensional field or tightly grouped field set says `mm`. Circle size
  says **radius**, not an ambiguous “size”; the resulting diameter is explainable.
- The current expression language supports unitless arithmetic/names under the
  document's millimetre convention; it is not a dimensional-analysis engine.
- Bare `25.4` means 25.4 mm. If `1in`, `25mm`, or mixed-unit expressions are not
  implemented, reject them clearly; never silently interpret them as millimetres.
- Invalid text, unknown parameters, division by zero, non-finite values, and
  non-positive lengths receive actionable messages without replacing good geometry.
- Document-space mm converts to the correct Blender display/world scale exactly
  once. Test default scene units and a non-default unit scale. Changing a scene
  display preference must not silently resize the CAD design.
- Export/reload preserves physical dimensions. Formula entry displays the saved
  expression and, where available, its evaluated value.

### F6. Kernel/sidecar setup and failures

- Missing sidecar Python, unavailable kernel dependency, or an incompatible backend
  does not appear as an empty model or unexplained Python traceback.
- The popup says what component is missing, where to configure/check its path,
  and the next supported setup step. An in-app help topic explains why an external
  process is needed and which operations remain available while it is unavailable.
- A runtime failure retains the CAD document and last-good result. A corrected
  configuration can rebuild without restarting the whole design workflow.
- No “working” claim until the actual add-on communicates successfully with the
  backend in the stated Blender version.

### F7. Visible, correctable intent

- A best guess is shown as a suggestion with its reason, affected entities, and
  control to change/disable it. Do not invent numerical confidence scores.
- The first slice's defaults are described as defaults, not as a geometric intent
  inference system. Future accepted inferences become ordinary editable features
  or constraints, with their provenance inspectable.
- Explicit user selections/dimensions override heuristic suggestions. A corrected
  suggestion does not reappear immediately and undo the user's choice.

### F8. Solid validity and output precision

- Before describing a result as watertight, verify the kernel solid is valid and
  closed and that any delivered mesh passes the declared manifold/closed-mesh checks.
- Surface a clear valid/invalid/unchecked state; a plausible shaded preview is
  not a geometry-quality check. Report tessellation tolerance and length units.
- Check dimensions/volume against the analytic plate-and-circular-hole fixture.
  Export/reload and tessellation must stay within the stated numerical tolerance.
- An invalid or open solid cannot be silently exported with a “watertight” claim.
  Keep the last-good shape and give the failed feature and corrective action.
- Exact B-rep geometry and tessellated mesh approximation are explained separately;
  a smoother display is not evidence of improved design precision.

## In-app explanation contract

External documentation supports the application; it does not satisfy the request
for in-app explanations. The add-on should keep its tooltip/help catalog together
so wording and topic coverage can be tested. Topic identifiers below are suggested
stable names, not a claim about the eventual operator implementation.

Each popup should answer, as applicable:

1. What does this tool/property mean?
2. What should I select or enter?
3. What will Apply change, and what will remain editable?
4. How do I cancel, undo, or fix a likely error?
5. What does this version not support?

Minimum topics and required distinctions:

- `workflow.overview`: profile → solid feature → cut → edit history → rebuild/save.
- `sketch.plane`: current fixed XY plane and z offset; later chosen planes/faces.
- `sketch.rectangle`: corner coordinates, width/height, and positive dimensions.
- `sketch.circle`: centre coordinates, radius versus diameter.
- `sketch.dimensions`: parameterized profiles now; driving/reference dimensions
  and general geometric constraints later.
- `feature.extrude`: profile input, positive length, direction supported today.
- `feature.boolean_operands`: base/tool roles and finite-tool extent.
- `history.edit`: saved design dependency history versus Blender's session Undo.
- `intent.suggestion`: defaults/suggestions, their reason, and how to override.
- `units`: millimetres, supported formula syntax, unsupported unit suffixes.
- `error.rebuild`: failed feature, last-good/stale output, repair/retry path.
- `setup.backend`: sidecar configuration, diagnostic check, recovery path.
- `verification.geometry`: solid validity, watertight meshes, precision/tessellation
  tolerance, and the limits of current verification.
- `roadmap`: viewport constrained sketches and assembly functionality are planned.

Suggested short explanations:

> Snapping places geometry at a useful point. A persistent constraint keeps a
> relationship when you edit the sketch later.

> The feature list is saved design history. You can return to an earlier feature
> and rebuild later features. Blender Undo reverses recent session actions.

> The cut keeps the Base and removes the overlapping Tool volume. Change either
> input here if the suggested pair is wrong.

> This output is from the last successful build. Fix the highlighted feature and
> rebuild to see your current parameters.

## Interactive sketch/part MVP acceptance (Stage 2, planned)

- **Plane selection:** choose XY/XZ/YZ or a supported planar face, see origin/axes
  and normal before entering the sketch, and return to the prior view on exit.
- **Drawing:** line/polyline, rectangle, circle and construction geometry; visible
  point/entity selection, close-loop indication, and normal Blender navigation.
- **Snapping:** origin, grid, endpoint, midpoint and centre candidates highlight
  before clicking. Show the snap type; provide temporary disable/candidate cycling.
  Screen-space hit tolerance works across zoom levels. Snapping alone does not
  silently create hidden persistent constraints.
- **Dimensions:** select relevant entities then place/edit a dimension in the
  viewport or panel. Driving and reference dimensions have distinct text/icons.
  A dimension and its parameter expression are two views of the same saved value.
- **Constraints:** coincidence, horizontal/vertical, parallel, perpendicular,
  equal, tangent and symmetry grow from a tested minimal subset. Show remaining
  freedom, highlight constrained entities, and allow deleting/editing a relation.
  Underconstrained is a useful state, not a generic error. Conflicts identify the
  contradictory relations and preserve the last valid sketch.
- **Inference:** preview a proposed relation with its reason; accept, suppress, or
  correct it before it becomes persistent. Accepted relations remain inspectable.
- **Features:** profile-region selection, extent/direction, and new/add/cut target
  are explicit. Preview uses temporary geometry; Apply is atomic; Cancel restores
  the prior model. Through-all/mid-plane/up-to-face are offered only when supported.
- **History:** edit a sketch in context, rebuild its dependents, inspect failed
  references, suppress/restore safely, and prevent invalid dependency reordering.
- **Usability:** engineers and Blender users can complete the mounting-plate flow,
  revise an early dimension, and recover from an invalid edit using only in-app
  guidance. Test both the default and Industry Compatible keymaps; record observed
  confusion instead of calling the UI intuitive based on developer familiarity.

## Assembly/motion acceptance (Stage 3, planned)

- Create a component from a part and insert multiple named instances without
  duplicating its design history. Explain linked instances versus independent copies.
- Ground a component and define rigid, revolute and slider relationships using
  visible axes/origins/faces. Show which two instances and references each mate uses.
- Explain remaining degrees of freedom, redundant constraints, and conflicts.
  Highlight the affected components; let the user disable/repair a mate.
- Drag a permitted degree of freedom and preview joint limits; Cancel restores
  placement. A driven-motion preview obeys the mate model and identifies failures.
- Part edits propagate to instances. Missing/changed mating references produce
  repairable errors, not arbitrary new attachments or a silently plausible pose.
- Demonstrate a grounded base, rotating component, and sliding component; test
  limits, a conflicting mate, a part edit, save/reopen, and recovery.
- Explicitly distinguish kinematic mechanism motion from physical simulation.
  Reuse Blender visualization/animation where helpful without claiming that an
  animated mesh alone proves a mechanically constrained assembly.
- Verify interference and clearance for named component pairs with explicit units
  and tolerances. Distinguish overlapping, touching, separated and unchecked.
  Motion-dependent checks state the joint range and sampling; sampled positions
  do not establish continuous collision-free motion.
- Report solid/manifold validity and export tessellation tolerances alongside
  mechanism freedom, joint limits and clearance. Do not imply load capacity,
  stress/fatigue performance or structural safety; those analyses are unimplemented.
- Every new assembly action, mate property, inference and failure has contextual
  help before the assembly workflow is called complete.

## Verification record expectations

For each release/demo, attach the exact add-on commit, backend version, Blender
version, environment, tested workflow, and pass/fail/not-run checklist. A 4.3.2
smoke test is fallback evidence, not proof of 5.2.2 compatibility. UI screenshots
and an actual save/reopen/edit run complement automated geometry/graph tests.

### Blender integration references

These document Blender's behavior, not this add-on's implementation:

- [Current Blender download and version](https://www.blender.org/download/).
- [Undo, redo, and Adjust Last Operation](https://docs.blender.org/manual/en/latest/interface/undo_redo.html).
- [Keymap presets](https://docs.blender.org/manual/en/5.2/editors/preferences/keymap.html).
- [Snapping](https://docs.blender.org/manual/en/latest/editors/3dview/controls/snapping.html?highlight=snapping).
- [Scene units and scale](https://docs.blender.org/manual/en/latest/scene_layout/scene/properties.html).

Reviewed 2026-10-16. Target Blender 5.2.2 LTS; record actual runtime verification
separately rather than relying on this target label.

### Compact Sketch/Part status hierarchy (source change)

The history panel keeps solver state and closed-profile availability separate.
Only a current successful native solve can show Fully defined or Underdefined;
pending/stale evidence cannot. Inconsistent constraints are shown as conflicting,
while native nonconvergence remains Solve failed, not overdefined. Build failures
and last-good/stale warnings stay visible with a short corrective summary.

Sketch details, read-only measurement reports and Part details start collapsed.
The disclosure controls change UI presentation only. Full errors remain reachable
through their diagnostic action; Part details retain geometry-check measurements.
Current Part means a current replay, not passed manifold/export checks. Geometry
checks independently show unchecked, pending, failed, stale or passed status.
Focus CAD retains its explicit saved-draft Resume and fresh Check behavior.

Focused native-free state and draw-port tests cover this hierarchy. Actual native
GUI comparison, narrow/high-DPI review and installed-package verification must be
recorded separately; these source tests do not establish those outcomes.

### Empty Part starting tools

An explicitly empty canonical Part graph shows only New Sketch, XY Rectangle,
and Import STEP in the viewport palette. The history sidebar keeps named sketch
starters and a separate readable Import STEP row. Tools & Document / CAD retains
the complete named Part tool menu, including advanced routes. A missing display
cache is not treated as an empty model: nonempty, malformed, and missing document
JSON keep their existing palette. Draft and staged-edit owners keep their existing
controls and guards. Status, stale/error messages and Rebuild are not filtered.
This is a cheap graph-shape presentation check, not native geometry validation.

Bounded verification (2026-10-24): 92 compact-status/glyph tests, native Blender
5.2.2 empty-palette action/poll smoke and icon contract passed. Source-loaded cloud
GUI comparison confirmed the 26-to-3 icon reduction, readable Import row and
retained Dirty/Rebuild display; Import opened its file chooser and was cancelled.
This does not establish a newly installed ZIP, persistence, Windows or exhaustive
GUI qualification. The inherited arc-UI file has the same 31 failures on baseline
803e738 and this change (older palette/policy/status expectations); it is not a
clean-suite claim.

Before a document exists, a genuinely fresh Part workspace omits the viewport
palette entirely and leads with the existing named New CAD Document, Open CAD
Document and Import STEP Solid sidebar buttons. Fresh means empty-string JSON,
EMPTY status and no feature rows, retained document/cache identifiers, parameters,
draft/repair data or errors/reports. Other roles and active/retained owners keep
their existing palette. The full named menu and all warning rendering are unchanged.

Bounded follow-up verification: 120 compact-status/glyph tests pass, including
malformed/retained-state exclusions and empty-layout gizmo hiding. A disposable
source-loaded Blender 5.2.2 GUI visibly showed the three named starters with no
palette/backdrop and the complete named menu still reachable. No user's unsaved
scene was reset; no installer, package or platform qualification was added.
