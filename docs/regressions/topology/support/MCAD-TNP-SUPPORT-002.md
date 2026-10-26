# MCAD-TNP-SUPPORT-002: Saved minimal-twist support orientation

Status: implemented bounded source-frame policy; not a material-spin inference.
Search: support frame, tangent, rotation, projected world axis, discontinuity, TNP,
minimal twist, antiparallel, reset saved frame, orientation.

## Problem and explicit intent

The historical face-frame convention projects world X into the plane, switching
to world Y when |normal.x| > 0.9. Its U/V frame changes abruptly at that threshold.
A nonzero sketch/source offset or asymmetric profile can therefore jump or spin
although the surface normal changes smoothly.

New Preserve logical plane authoring additionally saves an explicit Minimal
twist orientation: the original source tangent and its baseline normal. Replay
rotates that tangent by the shortest normal-to-normal rotation, directly from the
saved baseline. It never accumulates transient intermediate rebuilds, guesses a
material patch's spin, or ranks edges/fragments to invent a tangent.

New sketches disclose this default. Review Support exposes Orientation: Minimal
twist / World axes and Reset saved frame here. Choosing a different policy or
reset can rotate/move the sketch with its local coordinates unchanged; the dialog
warns before the ordinary atomic Apply. Cancel leaves canonical bytes unchanged,
and edits use the existing session Undo registration. Existing documents missing
orientation keep exactly their historical World axes behavior until explicitly
changed. Strict exact-face support remains unchanged.

## Saved record and geometry rule

The optional `support_intent.orientation` is exactly:

    {"policy": "minimal_twist", "tangent": [x, y, z]}

The tangent must be finite, unit length and perpendicular to the saved
`source_signature.normal` (or the saved chosen signature if source_signature is
absent). Capture uses that original source workplane's projected-world-axis U
once, storing it rather than reconstructing it from future normals. The record
is deeply immutable and participates in canonical serialization and hashing.

Let n0 be the saved unit source normal, n the current unit source normal, and t0
the saved tangent. With v = n0 × n and c = n0 · n, transport uses the shortest
rotation formula t = t0 + v × t0 + v × (v × t0)/(1+c), followed by bounded
orthogonality cleanup and normalization. This is a deterministic construction
choice, not a confidence probability or a proof of material spin. Local anchor
coordinates use the saved U/V frame and are reconstructed on current transported
U/V. The sketch's authored local quaternion is then composed onto this frame.

The rule applies to unique stable planar support and to the already qualified
complete single-image/split ordinary Cut ancestry in MCAD-TNP-SUPPORT-001. A frame
assumption does not weaken face provenance: native topology has no tangent field
and no new inferred stable identity. A synthetic tangent exists only in logical
frame computation. Core and Blender independently derive the same expected
world plane from canonical intent and current replay evidence.

## Refusal and deliberate correction

- `1 + n0·n <= 1e-8` is refused, covering antiparallel/near-antiparallel normals.
  At 180° the shortest rotation axis is nonunique; nearby the construction is
  ill-conditioned. No arbitrary axis or fragment order resolves this.
- Missing/invalid source ancestry, nonplanarity or conflicting descendant planes
  retain their existing explicit support failures.
- Zero, nonunit, nonfinite, nonperpendicular or unknown-policy tangent records are
  rejected. No unrequested normalization turns corrupt intent into a new choice.
- A degenerate transported tangent refuses rather than choosing a fallback axis.
- World axes deliberately restores the historical frame convention, including
  its threshold behavior. It is a user correction option, not a hidden fallback.
- Reset saved frame here explicitly adopts the current World axes construction
  and stores it as a fresh minimal-twist baseline, retaining the current logical
  anchor/source relationship. It can alter orientation and is disclosed. This
  recovers an antiparallel old baseline without pretending its orientation was
  knowable. The old canonical record is untouched until a successful Apply.

Minimal twist is baseline-relative and path-independent. A closed sequence of
rebuilds is not physical parallel transport, and rotation about an unchanged
normal does not infer material spin. Users needing a known roll can still change
the sketch's saved local placement or explicitly reset/select support. Continuous
arbitrary operation-frame/material tracking is outside this case.

## Reproduction and evidence

Saveable example pair: `examples/topology_support/minimal_twist_before.mcad.json`
and `minimal_twist_after.mcad.json`. The original chosen anchor is the actual
centroid of a single asymmetrically notched face, not synthetic fragment ordering.

The native example uses a 6×4 mm asymmetric sketch and two nonzero offsets on a
planar source rotated about Y. Capturing at 64°, then replaying 64.3°, 65°, 90°,
110° and back to 64° crosses the old |normal.x|=0.9 threshold while retaining the
transported U axis and correct source-relative origin. Both stable single-image
and split Cut support are exercised; a 2 mm extrusion retains volume 48 mm³.

- `tests/integration/test_support_orientation_intent.py`: threshold crossing,
  normal changes, asymmetric geometry, source/local offsets, exact non-Cut
  support, save/replay, legacy behavior, antiparallel refusal and explicit reset,
  immutable tangent, unchanged native topology, solve/full client frame binding
  and forged-frame rejection.
- `tests/unit/test_support_intent.py`: invalid tangent and policy rejection,
  native-free core/client mirror equality.
- `tests/unit/test_support_intent_edit.py`: explicit choices, unchanged legacy
  Apply, saved tangent preservation and reset authoring.
- `tests/blender_support_intent_smoke.py`: native registered dialog/layout harness,
  Cancel/unchanged legacy bytes, orientation Apply, antiparallel/reset, Strict,
  stale evidence and independent-process .blend persistence.
- These cases do not establish arbitrary normal-path continuity, physical spin,
  actual mouse/Undo usability, fresh installer qualification, all topology cases,
  or complete TNP resolution.

## Review dialog RNA lifecycle regression

Real GUI opening of `minimal_twist_after.mcad.json` exposed a callback boundary:
Blender passes `OperatorProperties` to dynamic enum callbacks, without invoke's
Python `_document`/`_review_result` attributes. The source list collapsed to `NONE`,
rejecting the saved `slotted` source before the dialog opened. Review now builds a
hidden, skip-save RNA choice snapshot before assigning either enum. It contains
only display choices, never authority to commit; Apply still validates the original
guarded replay evidence and current document binding. Review/Why controls appear
before the multiline assumption explanation so correction stays discoverable.

`tests/blender_support_rna_smoke.py` reproduces the original failure and checks the
fix on genuine registered Blender Operator/OperatorProperties, including source
updates, Cancel and unchanged Apply for both orientation examples. Background
Blender dispatches INVOKE_DEFAULT to execute, so the test uses an execute trampoline
to the unchanged invoke body and intercepts only final dialog presentation. It does
not replace operator properties with Python stubs or claim mouse/Undo coverage.
