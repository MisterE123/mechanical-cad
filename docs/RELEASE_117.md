# 1.17.0 Linux development checkpoint

This bounded checkpoint packages four ongoing workflow improvements:

- Straight-line Trim/Extend against circles and signed finite arcs. Finite arc
  sweeps are respected; this does not trim curved targets or infer full circles.
- Explicit multi-edge Fillet/Chamfer with editable edge sets. Generated-face
  identities are pair-derived only when native history proves a unique result;
  ambiguous, shared, split or merged histories remain unstable and fail closed.
- Mirror Result across explicit datum planes, with XY/XZ/YZ/Custom presets,
  preserved expressions and reflected outward normals. It produces one reflected
  solid, not an automatic union or a mirrored assembly instance.
- Two-point sketch symmetry about an arbitrary authored line axis, checked by
  native SolveSpace and independent residual checks.

See [Trim/Extend](SKETCH_TRIM_EXTEND.md), [edge blends](MULTIPLE_EDGE_BLENDS.md),
[Mirror Result](MIRROR_RESULT.md) and [sketch relations](SKETCH_RELATIONS.md).

## Evidence boundaries

Feature source is frozen at 0109d4a1c44a1fd3cdf242749bcb9c95f46c9e3a.
The packaging commit changes release metadata and documentation only. Focused
source tests and source GUI observations are separate from exact installed ZIP
qualification. Final installer checks and archive hashes are in the companion
verification receipt; source GUI evidence is not final installed GUI evidence.

Source GUI observations cover circle/arc preview, Cancel, Apply, Undo and finite
arc sweep refusal at 0c56b70 plus HUD f8f6b4e; multi-edge selection, orbit, Apply,
Edit, reselection Cancel and Chamfer at 123e644; and Mirror presets/expression
Apply/Edit plus point-axis-point symmetry selection, solve and Undo at 8bb3013.
The newer pair-derived generated-face identity change at 0109d4a is native-only
coverage, not separately observed GUI coverage.

The full historical suite was interrupted at 89% under resource pressure, with
many failures not classified. It is not a clean suite and failures are not
assumed inherited. This checkpoint does not repeat the exhaustive historical
suite. Focused checks cannot establish the condition of unrun stages.

## Scope and limits

Native OCCT and SolveSpace remain in the isolated sidecar, never Blender.
The native pin remains cadquery-ocp-novtk 8.0.1.1.0. All 1,030 existing external
runtime files/modes and 42 unresolved materials/source declarations are retained.
Packaging is not legal clearance, source correspondence or a functional rebuild.

Prior Linux 1.16 and Windows 1.15 artifacts/tags remain immutable. Windows 1.16
has separate incomplete qualification; no Windows 1.17 work is claimed here.
No universal topological naming, professional CAD completion, arbitrary geometry,
manufacturing fit/strength or exhaustive GUI Undo/Redo qualification is claimed.
The canonical feature graph remains authoritative and display meshes are caches.
