# Bounded arc authoring and persistence proposal

Status: bounded design approved by the parent subject to independent consistency review; the two review amendments are incorporated. Implementation and qualification are not claimed here.

Reviewed source: `cad_arc_core` at `ce5b50bb011b3949a6599c7cbc28d31024805e0a`, read on 2026-10-17. Production source and tests were not edited, and no native process or test suite was run for this proposal.

## 1. Decision in one paragraph

Expose Center Arc in the existing General sketch owner, with three explicit center/start/end clicks, an explicit Reverse sweep action, the existing driving-radius field, and the existing fixed-point/H/V controls. Add strict journal 3, UI 2 and general envelope 3 capabilities; preserve old codecs, old entries and exact original document bytes. The first accepted arc alone upgrades the embedded sketch to schema 3 in one local-Undo command. The first usable committed output is the already-qualified one-arc/two-shared-ID-radial-line sector, optionally followed by its sole extrusion. Open/incomplete arcs remain editable, suspendable drafts; this slice does not claim canonical open-arc Finish, arbitrary curved profiles, STEP/STL, geometry checks or Assembly reuse. Native trim validation and all numerical limits remain unchanged.

This proposal agrees with the sibling owner-admission proposal: wire version comes from the complete exact candidate document, never from a tool, UI envelope, historical entry or allocation tombstone. General and Part gain bounded result-3 solve/replay admission. Rectangle, Assembly, canonical-snapshot capture and geometry/export actions do not gain result-3 authority.

## 2. What the existing code actually requires

- `general_sketch_commands.py` fixes `JOURNAL_VERSION = 2`, supports point/line/circle/constraint IDs, and makes radius edits ordinary `driver` commands. `_validate_sketch` admits only the legacy native-free normalizer and global XY authoring. The legacy AddCircle command upgrades embedded schema 1 to 2; this behavior must remain exact.
- `general_sketch_journal.py` restores every retained command, including redo entries. Sequence, allocation-before/after, anchor watermark and permanent allocated-ID ledger are checked. Local Undo changes the cursor and accepted sketch, not the monotonically increasing allocation ledger or live revision.
- `general_sketch_draft.py` saves exact `document_json`, accepts no solved coordinates as canonical model edits, and presently hardcodes result 2 in solve/replay requests. Pending driver acceptance already requires downstream replay when the sketch is consumed.
- General envelope 1 contains a command draft. Envelope 2 contains that draft plus UI schema 1. `general_authoring_store.py`, `general_draft_store.py` and `draft_dispatch.py` currently reject other versions. Several owner/proposal/constraint paths directly call the envelope-2 store and need explicit dispatch, not an indiscriminate version-literal bump.
- UI schema 1 accepts only Select/Line/Circle/Dimension, point/line/circle/constraint bindings and line/circle proposals. Its radius annotation binding assumes a circle. `constraint_ui.py` currently infers the source curve kind from role: Center means circle and Start/End means line. An arc needs an exact source-kind/role check instead.
- `general_view_geometry.py` and the overlay know only lines and full circles. Circle leaders can terminate anywhere on the support circle; an arc leader must terminate on its finite sweep. Picking is bounded and explicitly ambiguous/incomplete, and must stay that way.
- `result_v3._graph` accepts only one arc-containing constrained feature and at most its sole extrusion in an arc-bearing replay. A different Part graph can solve an individual sketch yet cannot Finish it through this service.
- `ARC_SECTOR_DATA_SERVICE.md` distinguishes solve success, pure profile readiness and native replay success. A real DoF-5 solve passes pure readiness but fails the stored-turn-shifted native trim guard. This is a retained service limitation, not permission to modify the kernel.

## 3. Exact version policy

| Boundary | Legacy behavior retained | New authoring capability |
|---|---|---|
| Outer Part | Schemas 1/2; no Part schema 3 | Existing new-constrained-feature transition to Part 2 only |
| Embedded sketch | Schemas 1/2 and their original record shapes | Schema 3, required `circles` and `arcs`; no duplicate saved radius/sweep |
| Local journal | Journal 2 parser/writer and operation records retained | Journal 3, explicitly selected per draft |
| Authoring UI | UI 1 parser/writer retained | UI 2 adds Arc tool, arc bindings and proposal |
| General saved envelope | Envelope 1 and 2 read/restore unchanged | Envelope 3 requires exactly journal 3 plus UI 2 |
| Rectangle saved envelope | Rectangle 1 unchanged | No migration or arc path |
| Scene annotation layout | Layout 1 shape and ordinary writer bytes retained | Same shape, source-aware arc-radius binding validation |
| Operation result | Legacy documents use production result 2 | Any embedded schema-3 feature in the exact candidate requires result 3 |

An arc-empty schema-3 document stays schema 3 and uses result 3. Conversely, local Undo restoring the only schema-3 sketch to schema 1/2 uses result 2 if the complete candidate contains no other schema-3 sketch, even when its envelope/journal remain arc-capable.

### Explicit capability upgrade before an unfinished gesture

An unfinished Center Arc proposal must survive suspension before an arc exists. Therefore the UI-capability transition cannot wait until the third click.

On first Center Arc activation in an old general draft, show one bounded disclosure: “Enable arc editing for this draft? Its saved draft will need this version of the add-on. Existing geometry and local history stay unchanged.” Confirming stages and validates journal 2 → 3, UI 1 → 2, envelope 1/2 → 3 in one owner-controlled checkpoint. Cancel leaves the original saved slot byte-for-byte unchanged. Starting a draft from an existing schema-3 feature uses the new capable versions explicitly.

This is a UI capability transition, not a geometric command and not a model-history edit. The embedded sketch remains its old version until AddArc. Existing selection, annotations, raw dimension text, revision, anchor, cursor, redo entries, allocation ledger and watermarks are copied exactly. Envelope-1 drafts receive the same explicitly chosen empty UI defaults as the existing editor route, then the reviewed capability upgrade. Do not normalize old commands, regenerate old history, or insert `arcs: []` into old before/after snapshots.

Keep the capable envelope after Cancel Proposal or Undo of AddArc. Downgrading a journal that still contains arc redo records or `a_dN` tombstones would lose information. Do not implement automatic downgrade or history compaction for this slice. Finishing/cancelling the whole draft ends that separate local-history container; a new legacy-only draft can again use legacy versions.

### Exact legacy-byte claim

Loading, inspecting, selecting another tool, saving a `.blend`, and restoring a legacy draft without the explicit upgrade must not change its version or data merely because the software understands arcs. Preserve the exact original suspended-slot bytes until an actual authorized checkpoint update. Keep exact canonical base JSON as a string, including whitespace. For existing deterministic legacy serializers, maintain identical bytes on equivalent old-only operations. Newly written envelopes use the existing compact canonical JSON policy; this is not a promise to preserve arbitrary whitespace inside every updated JSON subtree.

Unknown fields/versions, corruption or unsupported journals fail closed with their original raw slot text retained. Never load a “known subset,” drop unknown fields, strip an arc or manufacture a legacy-shaped response. A new codec must not normalize original source record order, integer/float distinctions, negative zero, formula strings or optional legacy-field presence merely to validate it.

### Cross-version codec admission is an independent obligation

Generalizing the shared draft class must not broaden the old envelope codecs. Recommend `GeneralSketchDraft.from_checkpoint_payload(state, *, expected_journal_version=2)`: the conservative omitted argument requires exact integer journal 2, while only an explicitly arc-capable caller passes 3. It validates that expected version before history restoration; it does not infer permission from schema-3 records or an empty UI. The new envelope-3 codec passes 3 explicitly. Internal UI-wrapper clones likewise pass their already-validated explicit capability, rather than relying on a permissive default.

Envelope-1 and envelope-2 `loads`, `restore` and `dumps` continue to require journal 2 even after the shared restoration implementation understands journal 3. Their existing default restoration call can enforce this, or a narrowly scoped explicit expected-version guard can be added to `general_draft_store.py` and `general_authoring_store.py`. In either implementation, a live capable draft passed to an old writer fails without producing an old envelope or mutating that draft. Envelope 2 additionally requires UI 1; envelope 3 requires journal 3 plus UI 2. Every mismatched pair rejects. UI fields alone are not a journal-version barrier.

## 4. Command and journal specification

Use the existing `GeneralSketchDraft`, reducer and history owner. Do not introduce a separate arc session or a second model.

### New typed commands

1. `AddArc(center: PointInput, start: PointInput, end: PointInput, direction: Literal["ccw", "cw"])`.
   - A PointInput remains either an explicit PointRef or a newly authored PointSeed.
   - Reserve new points in center/start/end role order, then one arc ID with prefix `a_dN` using the same global counter. Referenced existing points reserve no new IDs.
   - Require three distinct point IDs and the existing structural arc policy. Unequal authored radii remain permissible seeds; successful solved radii use the already-qualified solved policy.
   - Journal record has exact keys `op: "add_arc"`, `points`, `arc`, `source_schema_version`. `points` contains only newly allocated points in role-allocation order; `arc` contains exactly id/center/start/end/direction. No constraints, solved positions, derived radius, sweep, temporary native endpoint order or repair instruction are stored.
   - The reducer verifies the declared source version against `before`. For source 1, add empty `circles`; for source 1/2, set schema 3 and add `arcs`. Preserve every old value/record, then append the one arc. Source 3 stays 3.
   - One accepted command contains the migration plus new entity. Its `before` is the exact old sketch and its `after` the explicit new sketch. Local Undo restores the prior embedded version and old field presence; Redo uses the same IDs, points and direction.
2. `ReverseArcSweep(arc_id)`.
   - Journal record has exact keys `op: "reverse_arc"`, `arc_id`, `from_direction`, `to_direction`.
   - Validate current direction and the only permitted opposite value. Change only direction. Keep point roles, point values, curve/feature/relation IDs, expressions and array order.
   - A second explicit reversal produces a second local command. No automatic complementary-branch selection or endpoint swap occurs.
3. Existing radius `AddRelation` and `driver` commands retain their representation and duplicate rules. Radius target validation dispatches to circle or arc from actual source records. Do not introduce diameter or a second saved radius authority.

### Legacy operations inside journal 3

Journal 3 reads the existing `add`, `driver`, `fixed_target` and legacy `delete` records with their exact old key sets. Historical journal-2 entries are not rewritten to add empty arc lists. The old allocator order for legacy add operations remains points → lines → circles → constraints. The new AddArc operation owns its explicitly separate allocation order.

For deletes accepted against a schema-3 state, use a new `delete_v3` operation with the existing targets/seeds shape plus an explicit `removed.arcs` list. Compute and disclose the full cascade: removing an arc center/start/end point removes incident arcs; removing an arc removes dependent radius relations; removing an arc alone never invents permission to delete its still-shared points or radial lines. Old deletion records remain replayable only with their original schema/cascade meaning.

The existing normal release policy continues to require current guarded solved positions and stores the disclosed point/circle seed transition. Arc geometry has no independent radius scalar to reseed: its center/start/end are already in the complete points list. Authored-position recovery copies current authored points/circle radii and removes only the explicitly selected relation. It does not reverse arcs, change branch, or add another relation. Intrinsic arc equations never become fabricated removable relation IDs.

`restore_history` must strictly dispatch on journal version before accepting a state. Journal 2 rejects schema 3 and every new operation. Journal 3 accepts old-state anchors and mixed retained history, then checks every transition, redo entry, ID kind, source schema and watermark. Add `a_dN` recognition only to the new capability. Preserve imported ID reservations, including an imported literal ID that already resembles `a_dN`. Pruning and branching keep the old no-reuse guarantee; undone/rejected native work does not authorize allocation reuse. A failed structural command/checkpoint consumes no allocation and changes no live state.

Do not install a normalized return value from `normalize_sketch_v3` into authored state. Use the current pure validators as validation only. Draft and envelope resource caps remain 2 MiB canonical document, 2 MiB journal, 64 retained entries, 8,192 allocated IDs, 8 MiB envelope, 64 KiB raw text; sketch limits remain 256 points, 256 aggregate curves, 512 active scalars, 512 authored constraints and 1,024 native equation rows. No limit increase is part of this proposal.

## 5. Three-click gesture and exact third-click policy

Recommended decision: preserve the current authored-seed semantics for both new and referenced points. **Do not write circle-projected coordinates at drawing time.** This intentionally replaces the earlier, unimplemented projected-new-end gesture described in `NEXT_SKETCH_ARCS.md`; update that document explicitly rather than leaving two contradictory policies.

- First click chooses center as exact PointRef or raw sketch-plane PointSeed.
- Second click chooses start by the same rule. The start-center distance defines the provisional support-circle radius.
- Third click chooses end as exact PointRef or raw sketch-plane PointSeed. A new endpoint stores the actual observed local pointer coordinate, not its circle projection. An existing endpoint keeps its authored point record and ID exactly, even if a current solved display has a different coordinate. The real solver may subsequently move unconstrained points.
- Center/start/end must be distinct IDs and structurally nondegenerate. A zero/tiny radius, coincident end/start, full-turn ambiguity or out-of-bounds observation fails acceptance without deleting the proposal. Different start/end radii alone do not authorize a rewrite and are not a hidden fixed constraint.
- The provisional arc stroke uses the start-radius support circle and observed endpoint direction. Show the actual end-seed marker and a visibly provisional gap/leader if it is off that circle. Caption: “Unsolved end seed; Check solves the sketch.” This describes the requested operation, not a promise that solving succeeds. Do not draw an apparently exact shared join while hiding a discrepant endpoint.
- Existing-point picking is an explicit reference choice. Point-only ambiguity still rejects; no nearest-ID fallback, point duplication or coincidence constraint is created. An existing endpoint that fails structural validation remains the selected rejected observation, not a new free point.
- The preview can use current validated solved display positions where available, otherwise authored positions, with its existing source labeling. Final construction stores raw new seeds and exact refs, and separately validates the unchanged authored records. It never copies solved coordinates back into existing seeds. The command/source/owner must still be current at acceptance; a changed source requires a fresh explicit click.

### Explicit exact-ID gesture input

Add one phase-aware **Use existing point** action for Line and Center Arc. It opens an explicit bounded picker over the current points (at most the existing 256-point cap), displaying stable point IDs and exact source-curve/role labels where applicable. It supports the initial anchor and each later point phase. No candidate is silently selected when distinct IDs occupy the same position. The chosen ID is carried as a PointRef directly into the same detached point-input/proposal/checkpoint-CAS handler as a viewport click; there is no cursor repick, synthetic click, nearest-ID fallback, coordinate snap, allocation or implicit constraint. Inspector Center/Start/End remains selection-only and does not accept a gesture.

The picker captures exact draft/source/revision/slot/owner/backend-generation/phase identity. On confirmation, revalidate the selected point and any curve-kind/ID/role source, the phase and all CAS bindings; reject missing/deleted or replaced IDs, repeated arc-role IDs, stale picker input or double acceptance without changing intent. Cancel creates no command or allocation. Existing native-busy, raw-input and cleanup barriers remain in force. A retained or resumed proposal can use this action only while pointer capture is inactive; it does not revive capture. A terminal phase uses the ordinary AddLine/AddArc acceptance transaction and explicit asynchronous Check semantics. Successful shared-ID closure must be exercised in the installed GUI, including coincident distinct IDs and suspend/Resume.

UI-2 arc proposal has exact fields `kind: "arc"`, `phase: "start" | "end"`, `center`, `start`, `observation`, `direction`. The center/start/observation use the existing `{kind: "existing", point_id}` or `{kind: "new", position}` shape; start is null in start phase, observation may be null. Pointer motion updates only the observed new position; the click resolves any explicit existing reference. In end phase, start must be present. The current observation can preserve a rejected existing-end reference. There are no allocated entity IDs in the proposal and no saved derived radius/sweep.

Resume restores these raw observations and all reference bindings without capture, replayed clicks, solving or queued acceptance. Any missing bound identity blocks Continue until explicitly restored or the proposal is cancelled. Because solved evidence is not restored, the resumed outline is visibly authored/unverified; it is not a promise of the former solved pose. Continue explicitly reacquires capture, and a later explicit third click accepts.

Reverse sweep is available both during the proposal (a UI-only direction toggle) and for one selected accepted arc (the typed local command). Show CCW/CW in local UV, signed sweep and minor/major or semicircle classification. Before Check, values are provisional; after Check, values come from exact validated solved output. A camera flip does not change direction. The accepted Reverse sweep action discloses that the complementary region may substantially change area; the ordinary Undo action reverses it. No endpoint labels are swapped.

Third-click acceptance follows the existing detached proposal transaction: clone exact source snapshot → prepare AddArc → clear only the proposal → validate complete combined envelope → owner/base/slot CAS → one checkpoint → existing asynchronous Check. A Check launch failure leaves the accepted reversible command and checkpoint intact, visibly unverified; it is not reported as if the click never happened.

## 6. Deliberately bounded tool availability

The first release workflow is global XY authoring at zero world origin. The unchanged native service bounds are radius and extrusion height 1–1000 mm inclusive, exact solved center-to-endpoint ray dot product at most zero, necessary endpoint discrepancy at most 1e-9 mm followed by the full existing checks, and exact signed-permutation frames at zero world origin. The backend's additional signed-permutation frames are not new arbitrary-plane UI support; unsupported editor planes continue to refuse without changing source. The UI does not substitute a rounded angle for the exact ray-dot check.

Before accepting the first arc, apply the same authoritative native-free result-3 replay graph admissibility rule to the exact candidate: one constrained feature and optionally its sole extrusion. Reject an unsupported multi-feature graph before changing live intent or the saved slot, with “This arc preview supports a separate sector Part. Start a new Part, or keep this sketch without arcs.” Do not auto-copy/delete unrelated features.

Recommended first-slice authoring admission is one arc and no full circles, with at most two line records while arc authoring is active. This does not claim the two lines already have the correct shared IDs. A new second arc, full circle or third line is visibly unavailable in this bounded mode; legacy line/circle tools stay unchanged when no arc exists. Recommend explicitly refusing both new editor entry and Resume entry for imported arc-bearing schema-3 content outside this structural subset, with a precise reason and unchanged canonical/slot bytes, rather than exposing a broad repair editor. This arc-bearing restriction does not newly reject arc-empty schema-3 line/circle workflows. Known supported drafts with an unfinished sector, invalid raw dimension or native replay failure retain ordinary Resume and correction. For an out-of-subset saved draft, preserve its exact text and offer explicit Discard or restoration in a compatible workflow; do not partially load or reduce it. Approval of this product restriction is listed below.

Do not run the full profile classifier or native kernel on pointer motion. Only a checked result may say the two lines are a supported radial closure. Incomplete sectors, wrong endpoints, isolated arcs and arc/chord shapes can be retained as drafts; Finish explains the actual readiness reason. There is no newly claimed canonical open-arc save path.

## 7. Selection, dimensioning and annotation implications

- Extend kind maps, occupied-ID maps, history binding provenance and retained generated-ID recognizers with arc. Keep exact ID and kind matching; missing bindings remain retained/quarantined, never rebound to nearby geometry.
- Points mode includes the actual arc center/start/end point IDs, which are already ordinary points. For a selected arc expose Center point, Start point and End point. Verify source curve kind, stable source ID, selected arc and requested role together; do not infer kind solely from “Center”. The inspector includes relations incident to the arc and its three point roles, without claiming transitive solver influence.
- The separate Use existing point gesture picker binds an exact PointRef as specified in section 5. Inspector selection remains selection-only; unrelated constraint mutators stay blocked during a proposal.
- Ordinary Select and Dimension admit finite arc picks. Radius Dimension targets the arc ID, never either radial line, the support circle or a generated edge. Selecting an already-driven arc finds the exact existing radius relation and places/edits that label rather than adding another driver.
- Double-click radius uses the unchanged input controller, raw text buffer and lease. Enter checks one exact trial. A consumed sector needs successful exact downstream replay before accepting the driver; Finish still performs its own publication replay. Outside-click retains raw text and consumes its first press/release; Esc cancels the field, not the whole sketch. Formula spelling, untouched numeric values and relation IDs remain exact.
- Scene annotation layout stays schema 1: constraint ID → `{kind: "radius", refs: [arc_id], display: "radius", offset: [u,v]}` already has the necessary identity. Source-aware lookup adds schema-3 validation and arc IDs to occupied entities. UI-1 still rejects arc targets; UI-2 validates radius targets as circle or arc. Legacy layout records do not acquire a new target-kind field or get rewritten on load.
- Retain current offset meaning: radius offsets are local-UV millimetres from center. For an arc leader, use the offset direction if it lies inside the directed finite sweep; otherwise use the nearer sweep endpoint, breaking an exact endpoint tie toward canonical start. A zero offset uses the swept midpoint. The label remains at center + saved offset. This is presentation geometry only and must not change points, constraints or native evidence. A Reverse sweep may move the leader endpoint but preserves label offset and binding.
- Existing missing/changed/unverified annotation quarantine, unrelated-feature retention, Finish layout CAS, transaction rollback, `.blend` save/reopen and Blender Undo/Redo remain unchanged. `.mcad.json` still contains canonical design only, not scene label placement or draft UI.

## 8. Bounded drawing and picking

Add a detached ArcGeometry display record containing exact center/start/end IDs, source positions, start radius, direction and derived signed sweep. It carries no solver authority. Authored unequal-radius arcs remain explicitly provisional as described above; solved display requires strict result-3 validation and current owner evidence.

Reuse circle sampling machinery over `[start_angle, start_angle + signed_sweep]`, with actual interval endpoints included. Never sample the complementary part of the support circle or close the arc as a full circle. Both CCW/CW and sweeps across the angular seam must render/pick correctly.

Keep existing shared per-operation projection budget: default 32,768 calls, hard maximum 65,536; default 512 sampled leaves per curve, hard maximum 2,048; overlay total maximum 16,384 segments. Use a finite initial subdivision of at most eight spans over the arc, then the existing bounded refinement. Count arc and circle work against the same budget rather than granting each kind a second global budget. Approximation error remains a sampling diagnostic, not a geometric proof.

No solver, subprocess, journal allocation, capability negotiation or profile construction runs from pointer-move/draw/pick. Cache detached geometry by existing command/source/view currency, and rebuild selection-binding evidence only after command revisions. Invisible spans, exhausted budgets and near ties produce incomplete/ambiguous results; they do not invent a pick. Shared endpoint ties with curves use existing Points/explicit role controls, without hidden point priority. Keep GPU state restoration, isolated viewport visibility and unrelated-scene/object protection.

Reserve a stable Center Arc palette slot and a stable Reverse sweep contextual slot; Check/Finish/Cancel must not shift when selection changes. Use the existing named-menu/header fallback in short viewports and at large UI scale. No new general palette framework, snapping system, tangent inference, arbitrary-plane controls or reference geometry is required.

## 9. Truthful status and recoverable native failure

Present three distinct facts in the existing right status area:

1. Constraint solve: successful with actual DoF, or failed/unverified.
2. Pure sector profile readiness: ready or its exact unsupported reason.
3. Native replay: not run, succeeded, or failed at the profile/native stage; downstream extrusion may be blocked.

For an arc-bearing sketch, Finish is enabled only after a current successful solve, `profile_check.ready == true`, no unfinished field/proposal, supported exact Part graph and ordinary owner guards. That enables a request to attempt fresh replay; it does not promise native success. Arc-empty schema 3 and old open line chains keep their existing service semantics, rather than accidentally receiving the arc-bearing readiness restriction.

After the known stored-tau-shifted trim failure, a suitable status is: “Constraints solved: 5 DoF. Sector checks passed. Native profile build rejected this arc representation; extrusion was not created. Your draft is retained. Edit constraints, Check and retry, or Cancel.” The native error code/detail remains available in existing diagnostics/help. Do not relabel this as solver failure, open-profile success or a tolerance problem that was repaired.

The genuine solve report may remain visible only while bound to the same exact candidate/input/backend. For a driver trial, label it “Pending radius input” and preserve the rejected raw text. Follow the companion owner proposal's runtime-only attempt-report association using the original guarded solve and failed replay evidence, expected prepared requests and pending-input bindings; clear the command's trial-acceptance/seed association after failed downstream replay. The report is not accepted seed or publication authority. On source/input/backend/owner change, retire its currency; no restored success badge or DoF appears from saved UI data.

Failure retains the exact command journal, proposal/input, canonical Part bytes, annotations and old accepted Part. An old committed mesh shown for the rejected candidate must be visibly stale/last-good and cannot certify that candidate. If existing rollback fully restores the prior committed Part and its still-valid prior evidence without revocation, preserve that ordinary prior-current state; failed candidate evidence never becomes evidence for it. Offer explicit Check/retry, editable constraints, local Undo, Suspend/Resume and Cancel. Never automatically add fixed/H/V constraints, change seeds, reverse direction, normalize a stored native interval, retry with another backend, or widen the kernel policy.

## 10. Practical first-user workflow and required result

This must be performed through ordinary installed GUI controls, with no helper script creating the geometry and no pixel-perfect seed assumption.

1. Create a new empty CAD Document. New Sketch opens the existing XY general editor.
2. Choose Center Arc and accept its one-time draft-format disclosure. Click near the desired center, a start point to its right, and an end point above it. Approximate positions are enough. Keep CCW for the intended quarter-sector. The preview is explicitly unsolved.
3. Select the arc, choose its exact Center point button, and explicitly apply **Fix at origin**, confirming the existing movement disclosure. This creates the visible fixed relation; the click location does not need to be exactly `(0,0)`.
4. Draw a line reusing the arc's center and start point IDs, then a second line reusing end and center IDs. Endpoint/center indicators show exact reuse. The phase-aware Use existing point picker binds exact IDs at both the initial and later line phases; overlapping identities require this explicit choice instead of a guess.
5. Select the center→start line and explicitly apply Horizontal. Select the end→center line and explicitly apply Vertical. No relation is inferred from the drawing gesture.
6. Select the arc, choose Dimension, place its radius label, double-click it and enter `5`. Accept the checked field. The successful constrained result must report **0 DoF**, radius 5 mm, shared-ID radial closure and supported quarter-sector readiness. Display the actual sweep; if the chosen initial branch solved differently, allow explicit edit/reverse rather than claiming it remained a quarter-sector.
7. Finish performs fresh result-3 native profile replay and commits that same sketch feature. From Part choose Extrude, enter 10 mm, Apply. Existing extrusion authoring creates its normal named length parameter. Native replay must produce one valid solid with five faces and volume approximately 196.34954084936206 mm³.
8. Edit the same upstream sketch. Double-click the existing radius label, change only its driving text from `5` to `7`, and accept. The trial solve and downstream replay must succeed before local acceptance. Finish commits to the same sketch and extrusion features. Authored point seeds, arc/line/point/relation IDs and direction are unchanged; only the intended radius source changes. Radius 7 mm, height 10 mm gives approximately 384.84510006474966 mm³ and five faces.
9. Save and reopen `.blend`; inspect the same feature/constraint IDs and label placement. Reopen/edit and Check afresh; no saved native capability is trusted. Save ordinary canonical `.mcad.json` and reopen it through the bounded Part replay path. Explain that STEP/STL, geometry-check certification and Assembly insertion are unavailable for this arc preview.

Also exercise the published data example separately: open `examples/sector_profile_data_only.mcad.json`, change its named `radius` parameter from 5 to 7 outside an active draft, then regenerate through result 3. That preserves the radius relation's exact `"radius"` expression and point seeds. It is a useful formula-regression control, not a substitute for the hand-drawn GUI workflow above.

For Reverse sweep acceptance, use the same endpoints and explicit reversal to obtain the complementary 270° sector; verify area/volume change and stable side provenance, then local Undo/Redo. Test both local directions, not just a single camera view.

For the known native-failure negative control only, prepare a predeclared version-valid saved General draft containing the exact DoF5 witness and canonical base. Record base, witness and envelope identities. Restore pure intent through ordinary Resume, then use genuine Check and Finish in the installed GUI. No fixture injects solver/current/publication evidence. Failed canonical JSON file loading remains a rejection preserving the prior committed Part and input file. This fixture cannot substitute for the manually drawn positive workflow.

## 11. Exact planned production file set

All paths below are relative to `cad_arc_core`. This is a proposed implementation set; a discovered additional owner dependency must be added to the reviewed manifest before freeze.

### Pure authoring and persistence

- `blender_addon/mechanical_cad_blender/general_sketch_commands.py`: typed AddArc/ReverseArcSweep, explicit version-aware validation/reduction, arc ID/kind/cascade handling and immutable legacy operation shapes.
- `blender_addon/mechanical_cad_blender/general_sketch_journal.py`: strict journal 2/3 dispatch, mixed old/new entry replay, arc allocation and source-schema transitions.
- `blender_addon/mechanical_cad_blender/general_sketch_draft.py`: explicit per-instance journal capability, checkpoint restoration, new commands, and owner-provided exact-document request/response version dispatch. Keep raw driver/seed semantics.
- `blender_addon/mechanical_cad_blender/general_authoring.py`: strict UI 1/2 dispatch, explicit capability promotion, arc proposal/selection/radius binding; retain old UI records unchanged.
- New `blender_addon/mechanical_cad_blender/general_arc_authoring_store.py`: envelope 3 only, requiring journal 3/UI 2 and the same byte/checksum/base protections. No copy of solver, lifecycle or model logic.
- `blender_addon/mechanical_cad_blender/draft_dispatch.py`: explicit envelope-3 route; inspection and dumps use stored capability, never guess from geometry. Replace new-capability callers' hardcoded envelope-2 serialization with this existing dispatcher.
- `blender_addon/mechanical_cad_blender/general_proposals.py`: detached three-phase proposal acceptance and raw-seed AddArc, using dispatch for source and candidate snapshots.
- `blender_addon/mechanical_cad_blender/sketch_annotation_store.py`: schema-3 source validation and arc occupied-ID lookup; unchanged layout-1 shape.

Keep `general_draft_store.py`, `general_authoring_store.py` and rectangle `draft_store.py` as their old-version codecs. If any shared-class change requires a compatibility adapter there, it may only enforce old-version admission and must preserve old writer bytes; it must not emit version 3.

### UI and interaction

- `blender_addon/mechanical_cad_blender/general_view_geometry.py`: detached finite-arc geometry, shared-budget finite-arc picking, radius leader endpoint policy and version-dispatched solved display.
- `blender_addon/mechanical_cad_blender/general_sketch_overlay.py`: finite arc/proposal strokes, raw endpoint discrepancy marker, direction/sweep labels and arc radius measured display.
- `blender_addon/mechanical_cad_blender/general_viewport.py`: Center Arc stages, explicit reverse command, arc Dimension target, first-use disclosure, exact existing-point choice and no pointer native work.
- `blender_addon/mechanical_cad_blender/general_session.py`: versioned serialization throughout, admission preflight, capability-aware tool availability and separate readiness/native-failure status, preserving the existing owner/async/rollback seams.
- `blender_addon/mechanical_cad_blender/constraint_selection.py`: arc binding kind, point filters and one-hop relation inspection.
- `blender_addon/mechanical_cad_blender/constraint_ui.py`: exact arc Center/Start/End source-kind validation, existing relation controls and version-dispatched checkpoint serialization.
- `blender_addon/mechanical_cad_blender/viewport_sketch.py`: Edit routes schema-3 sketches to General before rectangle recognition; never redirect them to Rectangle by shape resemblance.
- `blender_addon/mechanical_cad_blender/workspace_ui.py`: stable palette slots, named actions and separate solve/readiness/replay status.
- `blender_addon/mechanical_cad_blender/help_topics.py`: bounded arc workflow, sweep semantics, seed policy, native-limit recovery and disabled operations.
- `blender_addon/mechanical_cad_blender/palette_shapes.py` and the existing icon-asset manifest only if a checked-in Center Arc glyph is required; prefer the existing asset workflow and standard icon fallback, not a new runtime dependency.

The sibling owner proposal owns the exact changes to `guarded_evidence.py`, `backend_contracts.py`, `sketch_pending.py`, `part_publication.py`, `document_state.py`, Part display/read contracts, action eligibility and portable-file handling. Integrate against its named version-policy helper; do not independently reimplement policy in panels or recast data-only packets as production authority. No `kernel_ocp.py`, native sector/predicate policy, solver mapping, tolerance or data-service geometry expansion is part of this authoring slice.

### Documentation and example

Update `docs/NEXT_SKETCH_ARCS.md`, `docs/GENERAL_SKETCH_WORKFLOW.md`, `docs/SKETCH_ANNOTATION_LAYOUT.md`, `docs/DRAFT_LIFECYCLE.md`, `docs/CONSTRAINT_INSPECTOR.md`, `docs/ARCHITECTURE.md`, `docs/UX.md`, `docs/VERIFICATION.md`, `docs/regressions/catalog.json` and README scope. Add a short `docs/ARC_AUTHORING_WORKFLOW.md` containing the actual user workflow and limits. Retain the qualified data-only example; add a separately identified canonical example exported from the genuine GUI acceptance run only after it succeeds. Do not rewrite old release artifacts or historical failed-case records.

## 12. Finite acceptance matrix

These are planned tests, not test results. Run existing complete Ruff/format/pytest and native legacy suites against the eventual frozen source; do not substitute the rows below for the full regression. New tests should reuse current harnesses and acceptance records, with no new speculative proof framework.

### Pure gates

| ID | Finite cases | Required outcome |
|---|---|---|
| P01 | Envelope1, envelope2, Rectangle1; read-only load/save and one old supported edit each | Legacy deterministic bytes and exact raw/base retention; no migration |
| P02 | Envelope1→3 and envelope2→3, accept/cancel/failing checkpoint | Complete old journal/UI/raw data preserved; atomic transition; Cancel/failure exact bytes unchanged |
| P03 | Embedded1,2,arc-empty3 × AddArc CW/CCW × all-new/all-existing/mixed refs | Explicit fields/IDs; one command; no seed normalization; strict role identity |
| P04 | First AddArc Undo/Redo; reverse Undo/Redo; delete arc/center/start/end/relation | Exact before/after versions, disclosed cascades, same IDs and non-recycled ledger |
| P05 | Imported `a_dN` collision, branch after Undo, 64-entry pruning, allocation/byte limits | Same global allocation provenance; no hidden history rewrite or eviction |
| P06 | Arc proposal start/end phases × new/existing observations × Continue/Cancel/Resume | Exact raw observations; no ID allocation/native work/input capture on restore |
| P07 | Duplicate/unknown fields, versions, malformed refs/direction, nonfinite/Unicode/depth/shared containers | Fail closed and preserve original snapshot; no permissive field stripping |
| P08 | Schema2 after Undo, schema3 empty arcs, schema3 bearing arc | Correct exact-document wire version; envelope version never determines it |
| P09 | Unsupported multi-feature graph, second arc, mixed circle, third line | Explicit bounded admission/refusal with live state unchanged |
| P10 | Radius numeric/formula/unchanged text; duplicate driver; invalid and oversized raw text | Same relation identity/expression semantics; no accepted trial on failure |
| P11 | Inspector and exact-ID gesture picker; initial/later Line/Arc phases, coincident distinct IDs, wrong/missing source kind/role, repeated arc roles, stale source/revision/slot/backend/phase, Cancel/double acceptance, suspend/Resume | Exact PointRef proposal/CAS binding or rejection; selection alone does not bind; no guessed ID/allocation/capture revival |
| P12 | Finite sweeps ±90°, ±180°, ±270° across angular seam; support-circle complement clicks | Correct directed draw/pick; no complementary-circle false hit |
| P13 | Invisible span, projection/refinement/frame budgets, near tie, endpoint/arc overlap | Explicit incomplete/ambiguous results and bounded call/segment counts |
| P14 | Radius leader inside/outside sweep, zero offset and endpoint tie; reverse/edit | Deterministic finite leader and preserved binding/offset |
| P15 | Layout1 roundtrip, arc target, wrong target, deleted/restored relation, unrelated layouts | No schema bump/data loss; quarantined unavailable records retained |
| P16 | Failed proposal checkpoint, stale source/slot/backend, late solve, raw edit supersession | Atomic owner rejection; original data retained; no stale current geometry |
| P17 | Known solve-success/native-failure packet and changed input/backend after failure | Distinct genuine DoF/readiness/native failure; no capability resurrection |
| P18 | (a) New fields/operations injected into old journal/UI/envelope; (b) envelope1 with journal3; (c) envelope2 with journal3 and otherwise valid empty UI1; (d) journal3 capable command draft passed to envelope1 dumps; (e) journal3/UI2 capable wrapper passed to envelope2 dumps; (f) journal3 wrapper paired with empty UI1 passed to envelope2 dumps; (g) envelope3 with journal2 or UI1 | Every mismatched read/restore/write rejects by explicit journal/UI admission, before output or mutation; exact original bytes/capable draft remain unchanged; no inference from empty UI fields |

Suggested test locations: extend `tests/unit/test_general_sketch_draft.py`, `test_general_draft_store.py`, `test_general_authoring.py`, `test_general_authoring_store.py`, `test_general_proposals.py`, `test_general_view_geometry.py`, `test_constraint_selection.py`, `test_sketch_annotation_store.py`, `test_draft_dispatch.py`, `test_palette_shapes.py`; add `tests/unit/test_general_arc_authoring.py` for the cross-version arc fixtures. Owner evidence tests remain in the sibling matrix.

### Genuine native/Blender background gates

| ID | Cases | Required outcome |
|---|---|---|
| N01 | Four explicit quarter/major directed orientations at radius5 and7, height10: eight end-to-end outcomes | 0 DoF with explicit fixed/H/V/radius; valid five-face solids; analytic volume and stable side.arc/side.line provenance |
| N02 | Quarter-sector radius1/1000 × height1/1000: four outcomes | Inclusive service bounds through real owner solve/replay; no altered numerical policy |
| N03 | Opposite-ray semicircle CW/CCW with explicit center/H/H/radius: two declared positive outcomes | 0 DoF, signed sweep magnitude π and valid native solid from the existing supported fixture family; an unexpected rejection blocks this positive gate and cannot be relabeled a pass |
| N04 | Ordinary direct driver5→7 and imported parameter-radius5→7 | Same feature/entity/relation IDs and unchanged point seeds; expression retained in parameter case |
| N05 | Original stored-turn-shifted DoF5 case restored from predeclared pure saved draft through Resume | Actual solver success/pure-ready/native rejection preserved; no mesh/topology/current solid publication; editable failure recovery |
| N06 | Open arc, arc/chord, wrong point-ID closure, unsupported acute-ray dot, unsupported placement | Supported solve status kept separate from unsupported Finish/replay; original input retained |
| N07 | Radius/height just outside service bounds; contradictory fixed/radius relations | Recoverable input/native errors, no silent constraint release or tolerance change |
| N08 | Suspend/resume at both gesture phases and with invalid radius text; save/reopen in a second Blender process | Exact raw snapshot/history/annotations; no restored evidence or capture |
| N09 | Canonical Undo/Redo, disable/re-enable, load/quit/cancel during solve/replay, scene/window change | Existing single-owner cancellation/reaping and original-scene recovery remain valid |
| N10 | Checkpoint/publication/layout write failure and late external slot/layout/backend changes | Existing rollback seam restores exact prior canonical/display/layout state; no external overwrite |

Use genuine pinned slvs/OCCT and native Blender 5.2.2 LTS for the appropriate rows. Every Blender background invocation uses `--python-exit-code 1` and an explicit completion marker. Suggested additions: `tests/integration/test_general_arc_authoring_native.py`, `tests/blender_general_arc_authoring_smoke.py`, and `tests/blender_general_arc_persistence.py`; keep the existing shared owner, install, annotation, selection, lifecycle and v3 service suites intact. Kernel tests remain original, rather than replacing their historic rejected representation with a newly passing expectation.

### Exact installed-ZIP GUI gates

Use a clean profile, the exact candidate ZIP plus matching sidecar, and record their hashes and runtime versions. Headless invocation is not a substitute.

| ID | User-visible exercise | Acceptance |
|---|---|---|
| G01 | New blank Part and the complete hand-drawn workflow in section10 | Center/start/end, shared-ID lines, explicit Fix-at-origin/H/V/radius, 0 DoF, Finish, Extrude10, same-ID radius7, correct visible Part |
| G02 | Reverse while drawing and after selection; local Undo/Redo; view from opposite side | CW/CCW/local convention and complementary sweep are understandable; IDs/labels retained |
| G03 | Point/arc ambiguity; exact Center/Start/End selection; phase-aware Use existing point in initial/later Line/Arc phases including coincident distinct IDs and Resume; radius labels | Correct exact-ID shared closure; stale/wrong-role/double/cancel controls fail safely; finite leader; no incidental distance or second radius driver |
| G04 | Radius number/formula/caret/select/copy/paste; Enter/Esc/outside-click; rapid repeated Enter | Exact raw text, one acceptance, input lease respected, no click-through geometry |
| G05 | Both unfinished gesture phases and invalid raw input; suspend, Resume, save/reopen process | No unexpected capture; explicit Continue/Reopen; visible unverified state; local history preserved |
| G06 | Original native trim failure entered as predeclared pure saved draft via Resume, then genuine Check/Finish; separate manually drawn constrained positive | Truthful solved DoF + native failure, unchanged draft and stale Part; explicit corrections/retry succeed when supported |
| G07 | Mismatched backend and backend change mid-job; cancellation/load/disable/quit | Useful recovery message, no fallback, no late publication, all child processes reaped |
| G08 | Short viewport, large UI scale, hidden gizmos and hover help | Stable Check/Finish/Cancel locations; usable named fallback; no clipped critical controls |
| G09 | `.blend` plus `.mcad.json` persistence; edit same feature; annotation Undo/Redo | Canonical/scene-only separation, exact IDs, fresh current evidence; ordinary save usable |
| G10 | Legacy Rectangle and line/circle edits; multi-feature first-arc refusal; unsupported export/Assembly buttons | Old workflows unchanged; refusals clear before mutation; no unrelated-object/scene effects |

Do not call the arc editor usable or delivered until G01, G05, G06 and G09 have passed on the actual installed artifact, together with the remaining matrix and existing regression gates. Retain each failed attempt separately; do not erase it by changing the declared case.

## 13. Parent-approved decisions and implementation boundary

1. Approve explicit first Center Arc activation as the authoring-envelope upgrade, with embedded-schema migration only at accepted AddArc and no automatic downgrade. This is necessary to persist unfinished arc intent without silent format changes.
2. Approve raw-pointer/new-point seeds and exact existing PointRefs, rather than the earlier proposed tool-side circle projection. The overlay must visibly disclose unequal-radius provisional geometry. The ordinary constrained workflow remains the positive acceptance target.
3. Approve strict one-arc/no-circle/at-most-two-line tool admission while arc-bearing, and the recommended explicit editor/Resume-entry refusal for imported arc-bearing schema-3 content outside that structural UI subset. Original canonical/saved draft bytes and explicit recovery/Discard remain intact. Supported unfinished sectors and failed native builds remain resumable, and arc-empty schema-3 line/circle behavior is unchanged. A broader imported-draft repair editor is a scope change, not an implicit fallback.
4. Approve keeping scene annotation layout1 and its existing exact signature/offset format; require finite-sweep leaders and source-aware arc validation instead of adding redundant target-kind data.
5. Approve the limited product claim: supported sector Finish/extrude/same-ID radius edit and ordinary file persistence; incomplete/open arcs are draft-only, and geometry checks, STEP/STL, snapshots and Assembly remain unsupported. Broader arcs and periodic-native representation improvements are separate work.

No other design blocker needs speculative geometry research or a new proof layer. Implementation follows pure dormant contracts/persistence first, then complete owner integration and independent audit before pointer/selection/display exposure, then the finite native and installed GUI gates.
