# Single-click Fillet and Chamfer (development)

Fillet and Chamfer in the Part palette now start a transient edge picker. Hover
near a supported edge for an amber highlight, click once, and enter the radius
or distance in the existing feature dialog. Esc/right-click cancels; normal
viewport navigation remains available. At a corner or overlapping projected
edges, move along the intended edge instead of guessing.

Press F while picking to switch to the original two-face workflow. The Part
feature menu also keeps **Fillet/Chamfer (Pick Two Faces)** and advanced
all/named-edge options. Only explicit face-pair intent is saved in the model.

This first slice supports exact native straight and circular edges with two
unambiguous stable adjacent faces sharing exactly one edge. Examples include
box edges and stable cylinder rims. It does not select seams, tessellation
diagonals, imported snapshot-only topology, unsupported spline edges, or edges
whose adjacent faces share multiple native edges. A later exact blend can still
fail for an excessive size or unsupported geometry; the existing transactional
dialog reports that rather than silently blending another edge.

The catalog is fetched through a guarded sidecar operation when the tool starts;
preparation is cancellable and runs asynchronously, so navigation remains available. No OCCT is imported in Blender.
The current Part, backend, units and complete display must still match at click.
An edited/deformed/transformed display is not valid selection evidence.

## Focused evidence

The focused integration test checks guarded v2/v3 catalog validation, twelve box
edges driving real native Fillet and Chamfer, two cylinder rims excluding the
seam, stale/forged/malformed catalog rejection, legacy replay compatibility and
real subprocess guarded transport. Native Blender 5.2.2 background registration and invocation-method smoke passed,
including async completion, immediate cancellation/reaping, stale/lifecycle
rejection, actual scene rays with controlled projection, hidden back-edge and
ambiguous-corner rejection. The background harness substitutes modal-handler
registration because Blender background mode has no input event. Interactive source GUI verified single-click Fillet and Chamfer on correct
outer edges, amber edge-only hover, zoom navigation and Esc cancellation.
Circular-rim GUI selection, interaction Undo and installed-package qualification
remain pending; no complete regression-suite pass is claimed. The existing 1.1 package is not changed by this branch.

### Silhouette regression

A saved-demo real perspective regression now covers an exact silhouette ray
missing the Part and hitting unrelated background geometry. Background objects
no longer prematurely block subpixel adjacent-face probes; actual foreground
occluders still block. The bounded distance allowance accounts for face
foreshortening (capped at 10× the view-plane pixel size), without relaxing exact
object, unchanged-display, stable adjacent-face or ambiguity checks.
`tests/blender_direct_edge_projection_smoke.py` starts from factory settings
and repository fixtures containing the generated 1.1 pocket-fillet model and
its saved perspective matrices. It requires no external .blend file. It checks the surviving
outer cap.end/side.l_d8 edge, a foreground blocker, and recovery after its removal.
The already-filleted cap.end/side.l_d6 boundary remains intentionally unsupported:
its replacement blend face has no stable authored identity.
