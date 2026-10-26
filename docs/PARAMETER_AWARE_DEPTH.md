# Explicit feature-only or shared depth editing

Development source, not a new installer. The initial scope is direct Blind or
Symmetric extrusions whose depth is exactly an existing named parameter. General
formulas, linked cutting tools, and other feature kinds retain their current
editors. There is no graph or persistence-schema change.

The depth editor defaults to **This feature only**. Replacing `height` with `14`
changes only that feature's expression. **Shared parameter** instead shows the
parameter name, its editable value/formula, and affected uses (including uses via
other named parameters). Apply changes the shared parameter and keeps the feature
linked. Separate drafts are retained when switching choices, but only the visible
choice is committed. Cancel changes neither. Untouched authored values retain
their numeric types. Existing stale-document checks, atomic rebuild, error state
and Undo boundaries remain authoritative; no action executes from drawing.

## Verified October 25, 2026

- 30 focused helper/history/unit tests passed. Source Ruff passed (generated
  evidence fixtures excluded). Real Blender 5.2.2 RNA smoke passed shared/local,
  untouched-type, hidden-draft isolation and stale-document cases.
- Final development ZIP installed and enabled in an isolated Blender 5.2.2
  scripts directory. Actual GUI reviewed both choices and listed Plate and Hole
  tool uses before applying a shared height change.
- Cancel retained height 10 and volume 11,497.345 mm³. Shared height 12 retained
  both depth links and produced 13,796.814 mm³; a hidden local draft 14 did not
  apply. Feature-only depth 14 then retained shared height 12 and the hole-tool
  link, producing 16,196.814 mm³.
- Local Undo/Redo restored/replaced the link without changing height 12. Shared
  Undo/Redo between heights 12 and 13 retained both links and restored the proper
  volume. The timer-created demo had no initial interactive Undo checkpoint;
  its first Undo returned to empty. This fixture limitation was not counted as
  passing Undo evidence. Later real interactive edit history supplied the tested
  baseline; no product workaround was added.
- Shared and local saved .blend files reopened in an independent process,
  correctly started unverified, then regenerated with exact expected links,
  parameters and volumes (`PARAMETER_DEPTH_REOPEN_OK`).

Evidence is private workspace `evidence/parameter-depth-20261025/`. This is not a
full-suite, Windows, manufacturing, or self-contained installer qualification.
The earlier aggregate remains failed, as documented in FEATURE_HISTORY_GLYPHS.md;
it was not rerun for this bounded workflow.

## Linked Boolean tool continuity

The same explicit choice is now available when editing the final Cut or Union
and its exactly linked fixed-depth extrusion tool: **Tool formula only** versus
**Shared parameter**. The latter keeps the tool's parameter reference and edits
the existing project parameter. Direct extrusion behavior is unchanged.

Tool sharing and parameter sharing are independent. Other direct consumers of
the tool are still listed and require the existing separate consent checkbox.
The parameter-impact list does not grant that consent. In particular, an
unchanged tool formula can still change geometry through its parameter: the new
wrapper checks consent for that case instead of relying on the existing
formula-edit helper's unchanged-tool early return. Missing, duplicate, rebound,
or unsupported bindings reject rather than guessing. No schema changes.

Additional bounded verification, October 25:

- 48 focused unit tests passed, including unchanged-formula shared edits denied
  without consent and accepted with explicit consent; rejected candidates and
  originals remain unchanged. Source Ruff, real linked RNA smoke and prior direct
  depth RNA smoke passed. Final development ZIP installed/enabled successfully.
- Actual Blender 5.2.2 GUI showed disabled depth choices until shared-tool consent.
  After entering height 12 then revoking consent, Apply visibly rejected and
  retained height 10, both links and original geometry. Cancel also retained the
  original design; reopening reset consent and returned to Tool formula only.
- With consent, shared height 12 kept both Plate/Hole tool links and volume
  13,796.814 mm³. Tool formula only changed the tool to 6 while height stayed 12
  and the Plate remained linked: volume 14,098.407 mm³. The separate Other tool
  use branch retained its exact tool input throughout.
- Actual Undo/Redo passed for both edits with recorded parameters, links and
  geometry. This fixture explicitly established its initial Undo baseline.
- Both saved .blend results reopened independently, started unverified, and
  regenerated with expected parameters, links and volumes
  (`LINKED_PARAMETER_REOPEN_OK`).

Linked-tool evidence is in `evidence/linked-parameter-depth-20261025/`.
Full aggregate and installer/platform qualification remain as limited above.

## Consent refusal without losing the draft

Pending depth changes now explain the missing shared-tool permission inline.
A typed preflight refusal keeps permission failures distinct from actual geometry
failures: it says the model is unchanged and names the consent checkbox, rather
than suggesting overlap or cut-depth repairs. Genuine geometric errors retain
their existing guidance.

For this refusal only, the editor returns once with its copied string draft and
a visible restored-draft notice. Consent always resets to false. The supported
fields are allowlisted and bounded; the document, feature and linked-tool binding
must still match exactly. The deferred callback is single-shot and checks its
window, scene, workspace, view layer, area, mode and idle execution state. Lifecycle
cancellation revokes pending returns. A newer Edit Feature invocation supersedes
an older queued return in the same window/scene. Cancel never queues another dialog. Nothing
is persisted to the model schema or disguised as a geometric repair proposal.

Additional verification, October 25:

- 73 focused unit tests passed; source Ruff passed. Real Blender 5.2.2 linked
  operator smoke passed, including restored RNA values with consent reset and
  accepted retry. Controlled callback checks under Blender covered changed or
  closed context, lifecycle cancellation and single-shot execution. Those race
  checks are not claimed as manual GUI coverage. An independent static review
  identified the newer-editor race; the final guard passed real RNA invocation
  and controlled deferred-callback regression checks.
- Final development ZIP installed/enabled. Actual GUI showed the pending warning,
  rejected Apply without changing height 10 or volume 11,497.345 mm³, and reopened
  with the entered height 12 retained and permission unchecked. Cancel closed it
  without a reopen loop or model change.
- A second actual refusal restored the same draft; explicitly granting permission
  and applying changed height to 12 once, retaining both links and producing
  13,796.814 mm³. One Undo restored height 10 and original volume; Redo restored 12.
- The saved result reopened in an independent Blender process, started unverified,
  and regenerated with the expected parameter, links and volume
  (`CONSENT_RETRY_REOPEN_OK`).

Evidence is in `evidence/consent-guidance-20261025/`. The earlier full-suite failure
and platform/installer qualification limits remain unchanged; no aggregate rerun.

## Primitive circle radius continuity

Exact named radius references in `sketch_circle` and `sketch_face_circle` now offer
**This feature only** and **Shared parameter** in Edit Feature. The shared choice
names the parameter and lists its uses before Apply; it preserves the radius
reference. Local replacement changes only that circle expression. Separate drafts
remain isolated. Formulas and numeric radii retain the original editor. The field
is explicitly **Radius (mm)**, not diameter; the separate constrained-sketch
Diameter tool and its conversion semantics are unchanged. No model schema change.

Verified October 25:

- 91 focused tests passed, including six real-OCP integration cases for free and
  face-supported circles. Shared 0.6 cm gives radius 6 (not 3), with exact boss
  volume pi*6²*2 for both uses; local radius 5 leaves the other use at 6. Stable
  supporting plane z=10 remains unchanged. Invalid radius replay fails without
  mutating the original. Source Ruff passed.
- Real Blender RNA shared/local, untouched-type, hidden draft and stale checks
  passed for both circle kinds. Face-choice data in this RNA-only test is a
  controlled fixture; the separate OCP tests establish exact face geometry.
- Final ZIP installed/enabled. Actual free-circle GUI Cancel preserved radius 4
  and original volume. Shared radius 6 kept both Hole profile/Other circle links
  and produced 10,869.026 mm³. Local radius 5 kept shared parameter 6 and Other
  circle linked, producing 11,214.602 mm³. Both edits passed actual Undo/Redo.
- Both saved results reopened independently, started unverified and regenerated
  with expected links, parameters and exact expected plate volume
  (`PARAMETER_RADIUS_REOPEN_OK`).

Evidence is in `evidence/parameter-radius-20261025/`. This bounded milestone does
not claim a fresh full-suite pass or new installer/platform qualification. Face-supported circle GUI was checked additionally after independent review found
and corrected a stale candidate-feature pointer: shared parameter replacement
copies the candidate, so support-face assignment must reacquire its target.

- Native RNA regression changes the shared radius, support input and face in one
  dispatch. Real kernel regressions verify both a same-base bottom-face change
  (boss z=-2..0) and a new support body bottom face (boss z=18..20), with radius 6
  and exact pi*6²*2 volume; the other boss remains on its original top face.
- Actual face-circle GUI Cancel retained radius 3 and cap.end. Shared radius 6
  plus cap.start in the same Apply preserved both changes: volume 226.195 mm³.
  Undo restored radius 3/cap.end; Redo restored 6/cap.start. Feature-only radius 5
  retained shared 6 and cap.start, volume 157.080 mm³, with Undo/Redo checked.
- Independent saved-face-model replay checks both exact boss volumes, the changed
  bottom support placement, and the unchanged other top support
  (`FACE_RADIUS_REOPEN_OK`).
