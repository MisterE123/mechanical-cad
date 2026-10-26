# MCAD-TNP-SUPPORT-001: Preserve a sketch's logical plane after a Cut splits its face

Search: topological naming, TNP, split face, attachment, slot, sketch jumped,
assumed intent, preserve plane, anchor, undo, strict support.

## User intent and visible behavior

An attached sketch is often intended to stay on the original construction plane,
not jump to the centroid of whichever fragment remains largest. New constrained
face sketches save the Preserve logical plane intent by default; the authoring UI
explains the assumption. Existing documents without this record stay strict.
The support controls explain why an assumption applied and allow changing the
supporting solid/face or choosing Strict. Successful changes use the ordinary
atomic Part commit and Blender Undo. Cancel does not alter the document.

This rule does **not** pick a face. It keeps a logical construction plane which may
span a slot or removed material. A resulting sketch/extrusion is not a guarantee
of contact, attachment strength, manufacturability, or a valid subsequent Union.
The actual downstream operation must still pass its native geometry checks.

Example documents: `examples/topology_support/before_split.mcad.json` and
`examples/topology_support/split_plane_preserved.mcad.json`.

## Reproduction

1. Make a 20 × 20 × 10 mm block. Cut a 2 × 22 mm slot tool at (9, -1, 7),
   initially extruded only 1 mm. The top face remains intact.
2. Attach a radius-2 mm constrained circle at the top face's local origin.
   Save its planar signature and Preserve logical plane intent.
3. Increase the slot tool's extrusion to 5 mm. The cut reaches the top and splits
   it into two equal pieces. Neither piece is the original whole top face.
4. The sketch stays at (10, 10, 10), not either fragment centroid; an independent
   2 mm extrusion has volume 8π mm³. The supporting block has volume 3880 mm³.
5. Save/reopen or reorder the diagnostic snapshot faces: the construction plane
   and decision remain identical. Strict instead reports the unresolved support.

The equal-piece example is intentional: there is no area or proximity winner.
The common plane is unambiguous under the explicitly saved plane intent.

## Proof boundary and deterministic decision

The optional canonical feature field is:

    support_intent = {
      "version": 1,
      "policy": "preserve_plane",
      "signature": {"surface": "plane", "area": ..., "centroid": [...], "normal": [...]},
      "source_signature": {"surface": "plane", "area": ..., "centroid": [...], "normal": [...]}
    }

Only an attached constrained sketch accepts it. The signature records the chosen
original plane and anchor in canonical millimetres; source_signature records the
original unsplit source workplane used as its local frame. Omitted source_signature
means the chosen signature is itself the source frame (zero relative offset). It is immutable in the core
model, participates in the document hash, and survives draft/save/reopen.
The decision is recomputed from this versioned rule plus the canonical upstream
replay, not stored as a potentially stale “accepted face” cache. Its explanation
identifies the original semantic face, rule and number of descendants. There is
no score, confidence percentage or inferred stable face alias.

1. Without saved intent, a unique stable planar face resolves normally. With
   Preserve logical plane and proven one-image ordinary Cut ancestry, use the
   saved source-relative frame even while the face identity remains exact. This
   prevents a changing single Modified face centroid from dragging the sketch
   before a split or after unsplitting. Exact non-Cut support retains its existing
   placement semantics. Identity status and assumed placement policy are distinct.
2. For a split require at least two complete descendants with the exact saved source
   face ID, one source, one ordinary Cut operation, explicit native Modified or
   unchanged lineage, and image counts equal to the complete descendant set.
3. Bind the original stable source face in the current Cut base, not a snapshot ID.
4. Every descendant must be planar, have the current source orientation, and lie on that
   current original source plane. Orientation tolerance is 1e-7 in unit-vector
   distance; coplanarity tolerance is 1e-7 mm. These are geometric tolerances, not
   calibrated probabilities or generic similarity thresholds.
5. Express the saved chosen anchor relative to its saved source frame, then
   reconstruct that local offset on the current stable source workplane. The
   existing projected-world-axis frame convention defines U/V. Width, normal,
   translation and tilted-plane changes follow this proven source, never a
   fragment centroid; snapshot enumeration is irrelevant.

The pure decision rule is mirrored byte-for-byte in the Blender client. Full
replay and solve-only context validate the same plane against current upstream
results; forged world-plane output is rejected. Native face records remain split,
with snapshot-only IDs. Other face consumers (mates, projections, blends, shell
openings) do not inherit a false stable identity from this rule. Downstream
features that consume the sketch use its actual resolved plane and geometry.

## Refusal and correction cases

- Source-workplane motion follows the established deterministic projected-world-axis
  convention, not arbitrary material spin. A rotation about the source normal does
  not rotate U/V; the world-X/world-Y fallback can also change basis near X-facing
  normals. This is the existing face-frame convention, not rigid body matching.
- A saved chosen anchor and source frame must be coplanar and consistently oriented.
  If the current unsplit source is unavailable, no transport is invented.
- An explicit legacy repair has no historical anchor record. The dialog discloses
  that enabling Preserve adopts the *current* original source workplane/centroid.
  The user can instead choose another stable support. Existing saved anchors are
  never overwritten merely by reopening or accepting the dialog.
- Missing, merged, generated-only, nonplanar, oppositely oriented, noncoplanar,
  multi-operation or incomplete split ancestry remains unresolved. No subset of
  favorable descendants is picked. Unbound legacy records do not cover multi-stage split chains. New explicit
  source-feature bindings cover the bounded chain in [case 003](MCAD-TNP-SUPPORT-003.md).
- Strict on an already split reference cannot produce valid geometry; the atomic
  edit requires choosing a valid replacement face as well. Cancel leaves the
  previous accepted document intact. Undo restores the previous canonical edit.
- Explicitly selecting a different stable planar support is the correction path.
  Arbitrary selection of a split fragment is not yet a persistent feature.

## Verification links

- Native geometry, save/replay, strict/repair/restore, normal translation, tilted
  planes, source rotation/translation/width changes, saved local offsets, reordering,
  ambiguous refusal,
  downstream volume and full client contract:
  `tests/integration/test_split_support_intent.py`.
- Bounded record validation and mirrored pure rule:
  `tests/unit/test_support_intent.py`.
- Existing attached-sketch contract and geometry regressions remain unchanged.
- `tests/blender_support_intent_smoke.py`: native registered review, explicit legacy
  repair, atomic replacement, Cancel bytes, stale evidence, native .blend save and
  independent reopen. Dialog/layout are exercised through a harness; actual mouse
  interaction and native Undo remain unqualified.
- These tests do not establish interactive usability, all topology cases, a ZIP
  installation qualification, or a complete TNP solution.


## Continuity correction: Modified → split → unsplit

A real asymmetric notch exposed a jump in the initial rule: extending the notch
from 10 to 14 mm moved a still-single top face centroid from
(10.235602, 10.259162, 10) to (10.347594, 10.243316, 10) mm. The old exact-face
shortcut followed that centroid, then switched back to the saved anchor on split.
The policy now applies to complete one-image Cut ancestry too.

The native regression captures the first notch's nonzero anchor relative to the
original block frame and replays notch heights 10 → 14 → 22 → 14 → 10 mm, with
save/reload each time. The anchor remains unchanged while identity changes
stable → stable → split → stable → stable. Legacy Strict deliberately still
follows the exact face centroid at 14 mm. Decision evidence records both
`identity_status` and `policy`; frame assumption does not change face identity.

Records using the historical projected-world-axis basis still have its known
threshold discontinuity. New optional minimal-twist orientation addresses that
specific case separately: [MCAD-TNP-SUPPORT-002](MCAD-TNP-SUPPORT-002.md).
Omitted orientation never silently changes behavior.
