# MCAD-TNP-END-001: explicit staged Up to Face correction

## Bounded contract

An exact target that splits or disappears remains unresolved. After a supported
single upstream feature/sketch edit, retain the failed attempt separately from
the accepted model. The user explicitly chooses an earlier dependency-safe solid
and unique stable parallel face. Direction, offset expression/type and profile
are unchanged. The face supplies an infinite plane, not finite-face trimming.
No nearest-face suggestion, automatic rebinding or fragment identity promotion.

Each corrected extrusion must rebuild natively before partial repair is kept.
The whole Part must succeed before atomic publication. The immutable original
proposal branch bounds further eligible reference failures after retargeting;
it supplies no native geometry evidence. Cancel retains work, Proposal Undo
reverses one repair, and Discard abandons the proposed edit. Version-1 saved
intent carries exact canonical states only and Resume revalidates each state.
Unexpected kernel/profile/parameter failures and unrelated branches remain out
of scope. Old sketch repair records keep their existing interpretation.

## Reproducible source fixture

Load `examples/topology_end_face/staged_end_face_repair.mcad.json`. It is an
accepted 10 × 10 × 10 mm block, shallow slot and two explicit Up to Face consumers.
An earlier `replacement` solid translates the block +3 mm in Z, deliberately
retaining the same inherited `block/face/cap.end` ID on a different source.

1. Edit **Upstream slot depth** (`slot_tool`) from 2 to 6 mm. The proposed Cut
   splits the old top face. The edit is retained, both consumers fail, and the
   accepted display/model stay unchanged.
2. On **First Up to Face**, choose **Replace End Face**. Select
   **Independent replacement plane [replacement]**, then `block/face/cap.end`.
   Nothing is preselected. Apply keeps this repair only in the proposal.
3. Cancel the second review, save/reopen, and explicitly Resume Repair. The first
   correction and its Proposal Undo remain available after fresh validation.
4. Make the same explicit source/face replacement for **Second Up to Face**.
   Only now does complete replay publish the upstream edit and both corrections.

Expected measurements:

- Original slot Cut volume: 960 mm³. Proposed Cut: 900 mm³, with split top fragments.
- First extrusion: profile at Z20, Opposite, offset `gap = -0.5`; final endpoint
  Z13.5 and volume 6.5π mm³ (formerly endpoint Z10.5 and volume 9.5π).
- Second extrusion: profile at Z0, Along, offset `gap + allowance = -0.25`;
  final endpoint Z12.75 and volume 12.75π mm³ (formerly Z9.75 and 9.75π).
- The active transformed second extrusion retains volume 12.75π mm³ after repair.
- The exact source **replacement** matters even though the face ID is inherited.

`tests/end_face_repair_cases.py` also supplies a complete-disappearance variant.

## Implemented evidence, not universal recovery

- `tests/integration/test_extrusion_end_face_failures.py`: actual Cut split/deletion,
  exact volumes, sequential correction, all typed target gates, v1/v2/v3 and
  injected unexpected native/profile/offset failures.
- `tests/integration/test_end_face_repair_catalog.py`: current source-qualified
  catalogs, rotated and attached profile planes, explicit choices, newly exposed
  downstream failure, exact native replay and independent v2/v3 response checks.
- `tests/unit/test_staged_end_face_repair.py`: narrow/type-preserving transitions,
  unsafe targets, unrelated branch rejection, saved-state corruption, fresh Resume,
  mixed end-face/support repair, Proposal Undo and legacy envelope compatibility.
- `tests/unit/test_end_face_repair_ui.py`: stale review refusal, receipt release,
  no default selection and Cancel ownership.
- `tests/blender_end_face_repair_smoke.py`: registered native RNA, proposal-only
  partial Apply/Cancel, actual Save and separate-process reopen, fresh Resume,
  Proposal Undo and final full replay with no core/native imports in Blender.

Native background checks intercept popup presentation. They do not establish
actual GUI legibility, mouse/keyboard interaction, installer qualification,
arbitrary blend/Shell/mate repair or universal TNP recovery.
