# Direct blend selection (development)

Fillet and Chamfer can start with **Pick two faces sharing the edge** in the
Part viewport. Hover shows the current face in cyan; click the first face to
retain it in amber, then click the other face beside the intended edge. Middle
mouse and the wheel still navigate. Esc or right-click cancels without changing
the model. The dialog then allows an editable radius or chamfer distance.

This is deliberately a two-face gesture, not one-click edge selection. The
current display provides an exact triangle-to-face map, but no native edge map.
Triangle diagonals are never offered as CAD edges, and no persistent edge ID is
invented from screen proximity or coincident mesh vertices. Curved faces are
eligible when their semantic lineage is stable. Unknown, split, merged or stale
identity remains unavailable.

The picked pair is intent, not a claim that native adjacency has been checked.
Apply performs the existing exact native check that both stable faces share
exactly one edge, then builds the requested blend. Nonadjacent or ambiguous
pairs fail without replacing the old document. All Edges and named-face lists
remain the advanced fallback.

Picking is tied to the same current document, replay evidence, scene, viewport
and undeformed display publication as face-attached sketch selection. An edited,
transformed, modified or stale mesh is not identity evidence. Picking never
changes Blender object selection or the document by itself.

Focused native coverage: `tests/blender_blend_face_pick_smoke.py` exercises exact
face IDs across tessellation diagonals, curved-face eligibility, invalid lineage,
incomplete maps, duplicate picks, display edits, cancellation, and successful
native fillet/chamfer versus atomically rejected nonadjacent faces. Headless
coverage does not establish real GUI usability.
