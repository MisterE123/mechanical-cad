# Independent review of the bounded arc authoring proposal

Date: 2026-10-17 UTC. Source inspected read-only at
`ce5b50bb011b3949a6599c7cbc28d31024805e0a`.

## Disposition

**Bounded acceptance of the architecture, conditional on the two concrete
proposal amendments below before implementation approval.** The reviewed
three-document proposal is a usable-authoring preview design, not a delivered
feature or a qualification result. No production/test edits, project-code
execution, native processes or new geometry research were performed for this
review.

### 1. Specify the missing exact-point-to-gesture action

The proposed shared-ID workflow is feasible with an unambiguous pointer pick,
but its promised explicit-point fallback is not supplied by today's controls:

- `general_viewport.py:_anchor` obtains a PointRef only by repicking the pointer;
  it does not use the selected point. An ambiguous point pick rejects.
- `constraint_ui.py:MCAD_OT_constraint_select` only changes selection.
  `_require_ui_idle` rejects that control while a proposal exists.
- `general_proposals.py:prepare_proposal` already has an explicit PointRef
  endpoint route for a line, but the inspector does not invoke it.

Add the bounded **Use selected point** action for Line and Center Arc, including
the initial anchor and each subsequent point phase. Require exactly one current,
explicit point selection; carry its exact ID through the same detached
PointRef/proposal/checkpoint CAS path. Define the UI route for obtaining that
selection while a proposal is retained, without reviving pointer capture or
silently accepting a click. Center/Start/End controls must validate the exact
source curve kind, ID and role before selecting the point. Selection alone must
remain selection; the separate action binds the proposal phase. No coordinate
snap, synthetic click, new point, implicit coincidence or nearest-ID fallback.

Amend authoring sections 5, 7 and 10 and P11/G03 to cover initial and subsequent
Line/Arc phases, overlapping distinct point IDs, wrong/missing source role,
stale selection/source, cancellation, and suspend/Resume. Keep the ordinary
hand-drawn positive workflow required. This is within the already named UI,
proposal and owner files; it does not need a new snapping framework.

### 2. Predeclare the native-failure GUI witness entry path

`operators.py:MCAD_OT_load.execute` routes JSON loading through
`document_state._commit_candidate`; it does not publish an unsuccessful replay
as editable committed data. Thus the retained native-failing witness must not
be described as a Part successfully imported by that action.

For authoring N05/G06 and owner E04, specify a predeclared, version-valid saved
draft containing the exact failed witness and its exact canonical base. Restore
pure intent through ordinary Resume, then perform genuine Check and Finish in
the installed GUI. Record fixture/base/witness identity and retain the failed
native result. No fixture may inject solve/current/publication authority. This
setup is permitted only for the negative recovery control; G01/E01 remain the
separate manually drawn positive workflow. Loading the failing canonical JSON
must remain a rejection with the prior committed Part and input file intact.

## Accepted boundaries and implementation obligations

- The default-v2 `GuardedEvidence.revalidate`/publication-consume choice is
  concrete and conservative. Explicit schema-derived 3 and snapshot-only None
  close the broad-default hole; the proposed wrapper/AST and dynamic sink
  checks are still required. `GuardedJob.result` is correctly identified as a
  necessary explicit-version caller.
- Journal3/UI2/envelope3 is explicitly separate from schema/result selection.
  The expected-old restoration default plus old read **and write** rejection,
  including empty UI1, addresses the actual shared-class old-codec risk.
  Retained history and allocation tombstones must not silently force result3.
- The arc-bearing one-arc/no-circle/two-line restriction and imported editor/
  Resume refusal are compatible with arc-empty schema3 retaining its existing
  line/circle behavior. Enforce the same current-candidate admission on direct
  commands and history transitions; do not infer it merely from visible tools.
- Raw new-point observations and exact existing PointRefs are coherent with
  untouched authored seeds. The provisional endpoint discrepancy must remain
  visible. In owner section 5, “accepted seeds” should explicitly mean the
  runtime `_Solution` solved-position cache, not canonical point records;
  `GeneralSketchDraft.accept_edit` currently makes that distinction.
- The initial solve, exact trial/downstream pair and distinct fresh Finish
  replay are fully identified. Same-owner clones retain the whole chain. The
  proposed runtime-only failed-attempt report addresses the current exception
  path that otherwise clears trial evidence; it grants no driver/seed/Part
  authority and must expire on input/source/backend change.
- Geometry/export preflight is correctly placed before the existing runtime
  clears and BUILDING/CHECKING changes in `run_geometry_action`. Whole-source
  Assembly preflight, including inactive and arc-empty schema3 sources, and
  snapshot isolation are explicit. Check actual operator/error wrappers as
  planned, not only the central transport. Ordinary JSON/Blender persistence
  remains distinct from guarded snapshots and export certification.

## Precise choices for parent review

1. Approve the narrow explicit **Use selected point** action and its above
   phase/identity semantics, or withdraw the claimed overlapping-ID gesture
   fallback. The former is recommended.
2. Approve pure saved-draft Resume as the negative native-failure GUI fixture
   setup, while retaining manual drawing for the positive qualification.
3. Decide the six product/scope choices already listed in `PROPOSAL.md`.
   This review adds no kernel, graph, export, Assembly or dependency expansion.

The two amendments close specific UI/qualification omissions. This review found
no additional architecture blocker in the finite requested boundary; it does
not replace exact-source implementation review or any declared acceptance gate.
