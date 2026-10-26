# 1.1.0: direct modeling and editing

This update concentrates on everyday interaction, not an assertion of complete
Onshape parity. The frozen 1.0.0 installer and its recorded evidence are unchanged.

## Improvements

- Start a sketch by clicking a current stable planar face. Esc cancels; an
  advanced face list remains available. Hover caching retains complete mesh
  checks and full acceptance-time evidence validation.
- Draw a rectangle within any drawn datum or face sketch. Four shared corners,
  four lines and four explicit H/V relations remain ordinary editable geometry.
- Placing a dimension immediately opens its selected numeric value. Enter accepts
  a checked value/formula; Esc cancels numeric editing without deleting the
  placed dimension. Existing labels remain double-click editable.
- Drag an ordinary sketch point in Select mode. A transient target/tether previews
  intent; release performs a guarded solve and one Undo step. This is not live
  continuously solved deformation. Constraints/formulas remain intact, and fixed
  or projected points are protected. Fully constrained geometry need not move.
- Solid sketch context replaces the distracting triangulation wire display.
  Temporary viewport presentation is restored on exit, suspension or error.
- Depth and direction are explicit in extrusion dialogs. Remove defaults inward
  for a standard outward face sketch attached to its selected base. Arbitrary
  flipped, offset or formula-defined planes are not guessed.
- Edit an Add/Remove operation's linked extrusion profile and signed depth in the
  same dialog. Shared-tool consumers are listed and require explicit opt-in.
- Start a fillet/chamfer by picking the two stable faces beside its intended edge.
  Native Apply requires exactly one shared edge. This is not one-click edge
  selection; mesh triangulation diagonals are never treated as CAD edge identity.
- Ordinary Cut can retain exact one-to-one native tool-face ancestry, allowing
  stable hole walls to participate in supported blends and planar supports.
  Splits, merged/aliased identities, generated-only ancestry and patterned cuts
  remain unresolved. Legacy result-v1 output remains unchanged; typed v2/v3
  consumers use the new evidence.
- Parameter names, usage and unused status are readable, with copy-name support.

## Verification boundaries

Focused real-kernel tests, native Blender interaction/persistence checks and
source GUI walkthroughs are distinct from installed-artifact qualification.
The source walkthrough confirmed face picking, attached rectangles, immediate
8 mm dimension entry, constraint-preserving corner dragging, inward pocketing
and editing the selected pocket's depth from -5 to -7 in one dialog.

The complete inherited pytest suite was attempted on an earlier coherent snapshot
but interrupted after temporary storage exhaustion. It is not a completed or
green run. Historical byte snapshots, old feature restrictions and stale UI
fixtures account for inspected failure categories; unclassified failures remain
unresolved rather than assumed harmless. See the delivered verification receipt
for the exact final artifact and checks actually performed.

Qualified target remains Linux x86_64 and Blender 5.2.2 LTS. Windows testing is
explicitly deferred. Drawing sheets, general closed-loop assembly solving,
continuous-motion collision certification and structural certification are not
claimed. There is no automatic model-history publication or GitHub push.
