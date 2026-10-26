# Circular-arc profile and B-rep contract investigation

Status: isolated contract/research spike, 2026-10-16. No production code, schema, UI, model data, dependency, or release artifact was changed. No commit or publication was performed.

Source inspected: `mechanical_cad` commit `1a27e74a8f30aeb3fadac8edec935bcf12e3c304` (released 0.5 source). Runtime actually exercised: CPython 3.12.14, `cadquery-ocp-novtk` 8.0.1.1.0, `OCP.__version__` 8.0.1.1. The binding does not expose the underlying OCCT runtime version; no inference about another OCCT version is made.

## Decision summary

1. **Proposed:** persist an explicit clockwise/counterclockwise sense, relative to the sketch's local +normal, with stable center/start/end point references. Center/start/end alone do not choose between the two circular arcs. Minor/major is derived from the directed sweep, not an additional independently mutable field.
2. **Verified:** build a true `Geom_Circle` edge with increasing parameters; reverse its topological orientation for clockwise traversal. Explicit workplane +U fixes parameter zero. Shared endpoint vertices and retained `MakeWire.Edge()` handles produce working line/arc loops and builder-derived `side.arc.<entity_id>` cylindrical faces.
3. **Critical verified boundary:** OCCT can reinterpret zero or extremely small positive parameter intervals as an entire circle. **Proposed:** independently guard angular span and physical endpoint separation before construction, and verify the native result afterward. A physical chord guard alone is insufficient.
4. **Proposed:** extend the pure identity/coincidence endpoint graph to lines and arcs, with exact analytic contact/intersection checks. Admit one open unbranched chain, and one simple closed loop, including two-edge curved loops. Never use native wire welding or display sampling to decide authored connectivity.
5. **Verified:** existing generic extrusion/cut provenance handles arc source edges correctly in the spike. A split arc side fails semantic resolution; a single unambiguous modified image can retain it. Blender-side validators and negotiated schemas currently reject new arc semantics and need deliberate versioned integration.

## Reproduction and evidence

Portable copies are retained here. Run from the repository root using
[the commands in the research README](../README.md). Output goes to the explicit
`MCAD_ARC_EVIDENCE` directory; tracked original results remain under `reference/`.

Observed: **97 bounded evidence assertions passed**. These scripts exercise actual installed OCP; they are not mocks and do not implement a production schema or solver. The independent endpoint walker is explicitly only a graph proof, not an intersection validator. Native experiments temporarily register `_Operation(kind="arc_profile_spike")` inside an isolated `OCPKernel` instance to exercise the existing generic extrusion/cut path. That operation kind is not added to production code or claimed to be an accepted protocol value.

Evidence files:

- `probe_contract_results.json`: directed edges, parameter boundaries, radial mismatch, nine extruded profiles, topology, and tessellation checks.
- `probe_boundaries_results.json`: 108 radius/parameter/vertex-constructor combinations, native open wire, and replaced-edge history.
- `probe_lineage_results.json`: 384 endpoint-orientation/input-order graph combinations, 64 native rebuilds, open/closed/branch examples, and two cut-history cases.

These bounded experiments establish construction feasibility and specific failure boundaries. They do not establish a complete robust analytic classifier, production arc solver integration, all-radius meshing, GUI behavior, file migration, installed-package compatibility, or platform qualification.

## 1. Directed arc semantics

### Proposed canonical record

A future explicitly opted-in sketch version can carry an arc with:

- a stable entity `id` in the existing global sketch identity namespace;
- `center`, `start`, and `end` point IDs;
- `direction` with exactly `ccw` or `cw`;
- no authored tessellation, B-rep handle, implicit closure, or separately stored derived sweep.

The names above are an outline, not an implemented schema. A native solver may represent clockwise arcs by exchanging endpoint handles internally; the returned authored IDs, endpoint roles, and direction must stay unchanged. Intrinsic equality of center-to-start and center-to-end radii must be part of native arc semantics and independently checked in solved evidence, even without an explicit radius dimension. Profile checking cannot compensate for a solver that simply treats an arc as three unrelated free points.

Let `a = atan2(start.v-center.v, start.u-center.u)` and `b` be the analogous end angle, in the authoritative sketch UV plane:

- CCW sweep: `delta = (b-a) mod (2*pi)`.
- CW sweep: `delta = -((a-b) mod (2*pi))`.
- Minor/major follows `abs(delta) < pi` or `> pi`. At exactly pi, clockwise and counterclockwise describe opposite semicircles.
- Swapping start/end **and** switching direction preserves the geometric arc and reverses authored traversal. Swapping endpoints alone selects the complementary arc; it is not an orientation-invariant edit.
- Reversing a profile walk reverses the traversal of every edge without rewriting authored records. For an arc, the walk's effective sweep changes sign. Entity identity and source-boundary role do not change.
- Screen orientation, camera direction, or point-array order must not choose the arc branch.

### Verified native construction

Use the existing `_profile_plane(..., strict=True)` convention: temporarily normalize the accepted near-unit WXYZ quaternion, retain authored bytes, compute origin/U/V/normal, and transform local points. A `gp_Ax2(center_world, normal, U)` makes the circle's angular origin explicit.

For CCW, use the increasing interval `[a, a+delta]`. For CW, construct `[a+delta, a]` with end/start vertices in that order, then apply `TopoDS.Edge(edge.Reversed())`. `Geom_Circle` supports the `BRepBuilderAPI_MakeEdge(curve, vertex1, vertex2, parameter1, parameter2)` overload. The `gp_Circ` overload does not expose that exact vertex-plus-parameter signature in this binding.

The probe verified at radius 10 mm:

| Endpoints/direction | Expected native arc length | Observed |
| --- | ---: | ---: |
| 0° to 90°, CCW | 5*pi | 15.707963267948966 |
| 0° to 90°, CW | 15*pi | 47.12388980384689 |
| 90° to 0°, CW | 5*pi | 15.707963267948966 |
| 90° to 0°, CCW | 15*pi | 47.12388980384689 |
| 350° to 10°, CCW | 10*pi/9 | 3.4906585039886546 |
| 0° to 180°, either sense | 10*pi | 31.41592653589793 |

All seven are valid circular edges with distinct endpoint vertices and the expected directed start/end positions. Do not choose an arc by asking OCCT to infer a shorter span, or by fitting a three-point arc whose fitted center could differ from the authored center.

## 2. Degeneracy and tolerance boundaries

### Verified native surprises

Installed values: `Precision.Confusion_s() = 1e-7` mm, `Precision.PConfusion_s() = 1e-9` in parameter space, and `Precision.Angular_s() = 1e-12`.

For raw `MakeEdge(circle, 0, end)` at radius 10:

- `end=0`: succeeds as a **full circle**, length 62.83185307179586; first/last vertices are the same.
- `end=1e-10`: succeeds with a near-full-circle parameter interval and length 62.831853072795866.
- `end=1e-8`: length is 1e-7 mm, but endpoints are collapsed into the same vertex.
- `end=1e-7`: length 1e-6 mm and distinct vertices.
- `end=2*pi`: a full circle; `end=4*pi` also reduces to one full circle.
- `end=2*pi+1e-6`: becomes a tiny arc, not a turn-plus-arc.

At radius **1e6**, an intended sweep of **1e-10 rad** has a perfectly nonzero **0.0001 mm chord**, yet both the parameter-only and explicit-vertex constructors return an arc about **6,283,185 mm** long. Thus a chord-only guard fails even when the chord is 100 times the existing minimum edge length. In this probe, 0.999e-9 rad wraps, while 1e-9 and 1.001e-9 do not; code should not depend on equality at the kernel cliff.

### Proposed independent preflight contract

Keep current coordinate/radius bounds and strict finite-number rules. Reject booleans, non-finite values, invalid IDs, unresolved point references, and malformed enums before native work. Define named constants rather than scattering tolerances:

- `PROFILE_TOLERANCE_MM = 1e-7`, retained.
- `MIN_LENGTH_MM = 1e-6`, retained.
- Proposed `MIN_ARC_SWEEP_RAD = 1e-8`, a deliberate 10x margin above the observed parametric confusion; this is a product support limit, not an OCCT universal truth.

Reject:

1. Start and end belonging to the same identity/coincidence class, even if a nominal direction was supplied.
2. A zero/too-small radius or radius outside 1e-6–1e6 mm.
3. Start/end chord length below 1e-6 mm, independently of arc length.
4. `abs(delta) <= MIN_ARC_SWEEP_RAD` or `abs(delta) >= 2*pi-MIN_ARC_SWEEP_RAD`.
5. Center-to-endpoint radius disagreement above the accepted radial residual budget.
6. Any analytic overlap, self-contact, or unusable closed area under the region policy below.

Zero/full-turn arcs must never be silently converted to a circle. The existing circle entity remains the only representation of one unbroken full circular boundary. A two-arc circle is different authored topology and retains two arc side roles.

These guards should run for original seeds where structurally applicable, successful native solved geometry, the pure region classifier, and the exact kernel port. Test just below, at, and above each proposed boundary. The exact accepted boundary policy needs approval; only the native cliffs above have been measured.

After native construction, verify that the edge remains circular, its angular span and length agree with the requested arc within the documented numerical budget, first/last vertices are distinct and correspond to the intended endpoints, and the B-rep is valid. `IsDone()` and B-rep validity alone did not catch the full-circle reinterpretation.

### Proposed symmetric radial convention

Use one deterministic coincidence representative for each point ID class before deriving geometry, including referenced centers. Validate all coincident members against the existing 1e-7 mm group tolerance. Then calculate both radii from those representative coordinates.

For tolerance-level solver differences, a **proposed** orientation-invariant adapter radius is `(r_start+r_end)/2`, subject to `abs(r_start-r_end) <= 1e-7`. This is a temporary exact-curve construction convention, not a change to canonical or returned solved points. Shared native endpoint vertices stay at the validated representative positions; their small curve-point residual remains explicit native tolerance. Do not silently project canonical points, fit a shifted center, or increase native tolerance to rescue rejected geometry. This convention should be approved alongside the solver residual policy; choosing only `r_start` makes endpoint reversal change the exact radius by the allowed mismatch.

Verified at R≈10 with explicit native vertices: start-derived radius succeeds through a 1e-7 mm endpoint radial discrepancy and rejects 1.1e-7; mean radius succeeds at 1.1e-7 discrepancy but rejects a 2e-7 boundary in the tested floating-point construction. **The application must apply its own 1e-7 discrepancy guard**, even when a native constructor accepts more. Native acceptance is not the definition of the user-facing tolerance.

A point changed to a coincidence representative can move within tolerance. Therefore recheck the arc's radial residual after representative selection; do not assume the pre-union solver residual proves the post-union curve. An ill-conditioned case can legitimately solve successfully yet fail profile readiness.

## 3. Mixed line/arc profile classification

### Verified existing contract

`profile_region.py` uses shared point IDs and explicit `coincident` relations, with deterministic union roots and a 1e-7 mm positional check. It does not join nearest coordinates. Existing `ClosedProfile(points, edge_ids)` and `OpenChainProfile(points, edge_ids)` only describe straight edges. A standalone circle is separate. Existing line-loop code requires at least three edges; this requirement cannot be copied to curved loops.

### Proposed extension

Add a distinct ordered curve-boundary representation carrying edge kind, stable entity ID, traversal direction, and enough solved analytic geometry/point identity to construct each arc. Preserve the old straight polygon path and its semantics. An open curve-chain type is preferable to pretending the existing point/polyline record describes curved segments.

For the endpoint **multigraph**:

- Include only line start/end and arc start/end references as incidences. An arc center is not a boundary endpoint merely because its ID is referenced by the arc.
- Union only explicitly shared IDs/coincidence relations; validate the representative positions before geometry use.
- One connected component, maximum degree two, and exactly two degree-one vertices describes an open chain. A single valid arc is such a chain.
- One connected component with every degree two describes a candidate closed loop. Two distinct curved boundaries may close a region with only two endpoint vertices: arc+chord, two semicircles, or a two-arc lens. Geometry checks must still reject double coverage or overlap.
- Degree >2 is a branch; multiple components, separate cycles, or circle plus any other boundary remain unsupported. Retain a specific failure instead of converting any failed region into an open success.
- For open chains start at the lexicographically smallest endpoint root. For loops start at the smallest boundary vertex root and choose the smallest unvisited edge ID. Traverse deterministically, then normalize closed winding while carrying boundary IDs and effective directions together.
- Native `MakeWire` must never decide which authored vertices are connected.

The isolated graph proof exercised 24 permutations of a four-edge loop times 16 independent endpoint reversals (with arc direction flipped on reversal): **384 inputs produced one canonical traversal**. Sixty-four actual native rebuilds after that traversal produced identical semantic role/status/surface maps and exactly the same volume. It also admitted one arc, a mixed open chain, explicit-coincidence connectivity, and a two-arc disk; it rejected a branch and equal-coordinate endpoints with distinct unconnected IDs. The graph proof intentionally lacks geometric intersection/tolerance validation and is not ready for production reuse.

The actual native mixed open wire has two edges, three unique vertices, valid B-rep, and `Closed() == False`. This proves the topology is constructible; the application should still return a successful solved open sketch **without an extrusion profile or native output shape**, preserving current typed-output semantics.

### Required pure analytic geometry checks, not implemented by this spike

Solve-only readiness must remain OCCT-free. Its classifier needs line–line, finite line–arc, and directed arc–arc intersection/contact tests, with a shared bounded tolerance policy:

- Solve supporting-line/circle or circle/circle intersections, then filter by finite line intervals and directed arc spans.
- Handle tangent contact, both intersections, endpoint contact, and cocircular overlapping angular intervals explicitly.
- Adjacent boundaries may meet only at their declared shared endpoint(s); reject any extra crossing, touching, or interval overlap. In a two-edge loop, both shared endpoints are legitimate. Two complementary semicircles are legitimate; two copies of the same arc are not.
- Nonadjacent contacts are invalid even if the contact is tangential or coordinates coincide. Do not quietly snap a near crossing.
- Cocircular arcs can be disjoint or complementary without overlapping; equal centers/radii alone do not prove invalidity.
- Reject near-degenerate slivers conservatively where geometry is indistinguishable at the supported tolerance. A minimum area alone does not certify enough clearance between neighboring curves.

A sampled polyline is inadequate as the authority: it can miss a small crossing, misclassify a major arc, or turn an arc/line tangency into a gap. This analytic classifier and its adversarial cases are a remaining implementation prerequisite.

### Signed area and winding

A useful exact analytic formula for an ordered directed loop is the polygon cross-sum of the endpoints plus, for each arc, `0.5*r*r*(delta-sin(delta))`. The sweep is signed along the current boundary walk. Compute cross-products around a nearby local reference and sum carefully to reduce large-offset cancellation. For very small sweeps, use a stable evaluation/series for `delta-sin(delta)` rather than subtracting nearly equal doubles.

Normalize negative signed area by reversing traversal order and every edge's effective direction while retaining its authored ID. Existing polygon minimum area is 1e-12 mm²; keeping or tightening this for curved slivers should be explicit. Profile readiness and actual kernel validity remain separate checks.

## 4. Exact extrusion and semantic topology

### Verified feasible profiles

All following native solids are valid; height is 7 mm and radius is 10 mm:

| Profile | Analytic area | Analytic volume | Observed volume |
| --- | ---: | ---: | ---: |
| Semicircle + diameter | 50*pi | 1099.5574287564277 | 1099.5574287564275 |
| Quarter arc + chord | 50*(pi/2-1) | 199.7787143782138 | 199.77871437821383 |
| Major 270° arc + chord | 50*(3*pi/2+1) | 1999.3361431346414 | 1999.3361431346414 |
| Two semicircles | 100*pi | 2199.1148575128555 | 2199.1148575128555 |
| 10×20 rectangle plus semicircle | 200+50*pi | 2499.5574287564277 | 2499.5574287564277 |

The mixed rounded rectangle was also exercised with a reversed entire wire, a tilted quaternion workplane, origin `(1e6,-1e6,1e6)`, and a negative native extrusion vector. All are valid with the expected absolute volume; the large-origin volume differs by about 1.25e-9 mm³. Negative native extrusion is a kernel observation, not a proposal to change the current engine's positive feature-length contract.

### Preserve inserted edge handles

The existing `polygon()` already captures `wire.Edge()` after each `wire.Add()`, because `MakeWire` can replace the edge to share existing vertices. The mixed arc probe reproduced this exactly:

- The first arc remains `IsSame` as its inserted edge.
- An independently built chord is replaced.
- `prism.Generated(raw_chord)` returns no face.
- `prism.Generated(inserted_chord)` returns one face.

Prefer one pre-created native vertex per validated endpoint class; still retain the actual inserted edge. After the full wire is built, verify every retained edge is actually in the final wire and each expected role maps to one boundary. Do not recover lost lineage by enumerating edges or matching geometric signatures.

### Stable role contract

Keep existing roles unchanged. Add the qualified boundary key `arc.<entity_id>` so existing extrusion history can emit:

- `role: side.arc.<entity_id>`;
- `id: <extrusion_feature_id>/face/side.arc.<entity_id>`;
- `source_boundary: arc.<entity_id>`;
- `operation: extrude`;
- `relation/evolution: generated_from_profile_edge`;
- `semantic_status: stable` only when exactly one generated output face belongs to that edge and the final assignment is unambiguous.

Arc extrusions yield cylindrical signatures, using the existing radius/axis signature shape. A partial cylindrical surface is still `surface="cylinder"`; no new analytic surface enum is required. Caps retain `cap.start` and `cap.end` with builder FirstShape/LastShape evidence. A profile construction operation would need explicit registration alongside `polygon`/`circle_profile` in `topology()`; the spike does not register it.

No persistent seam edge, arc endpoint side edge, triangle index, or B-rep enumeration identity is introduced. Two arcs covering one circle stay two authored boundaries and, in the tested prism, two distinct cylindrical faces. Do not merge those faces by analytic-cylinder equality.

### Verified cut evolution

On a semicircular extrusion:

- A full-height 2×3 mm notch at x=-1, y=8 splits the arc-derived cylinder into two images. Both become `semantic_status="split"`; `resolve_reference(TopologyReference("ext", "side.arc.round"), ...)` returns **ambiguous**.
- The same notch only from z=1 to z=6 leaves one connected modified cylindrical image. Its lineage remains stable and the reference resolves.

Existing generic cut history therefore works for these bounded arc examples. Preserve the same unknown/split/merged/generated failure policy for untested cases; proximity is never authority to rebind a lost arc face.

## 5. Tessellation and display

### Verified exact-solid display

The current `OCPKernel.tessellate()` handles the tested partial cylindrical faces without a new meshing algorithm. All nine profile/pose variants produced bounded meshes with every triangle bound to a topology face ID. `check_watertight_mesh()` reported watertight, vertex-manifold, consistently oriented triangles for all tested solids at 0.01 mm deflection. Triangle counts range from 100 for the quarter segment to 396 for the two-arc disk. Mesh volume is only an approximation: for example, the semicircle mesh volume is 1098.834091762984 versus the exact 1099.5574287564275 mm³.

Current analytic-circle preflight treats every circular edge as a **whole circle**, ignoring the adaptor's parameter span. This remains conservative for arcs, but may reject a short large-radius arc whose actual tessellation fits. A future span-aware budget can use the actual guarded angular span and requested chordal deflection, with a conservative endpoint/face allowance and the existing post-mesh 100,000-vertex/200,000-triangle gate. Never loosen requested deflection to fit a budget. Actual high-radius/short-arc resource cases still need qualification.

### Proposed solved open-curve display

`sketch_display.solved_line_wire()` is line-only. It indexes authored points and one edge per line, returns no triangles, and preserves `point_ids`/`line_ids`. Do not mislabel sampled arc vertices as authored points or put arc tessellation into canonical JSON.

Add a bounded, deterministic display-only curve sampler/converter, using the same directed sweep and plane convention. Preserve a mapping from each sampled segment to its authored `(kind, entity_id)`, and map only true endpoints/centers to authored point identities. Shared endpoint classes must remain explicit; unrelated equal-coordinate points cannot be welded into model identity. Use a documented screen/physical sampling policy and resource budget. The initial and final samples must coincide with the validated solved endpoints within the display contract.

An open sketch keeps `mesh=None`, `stats=None`, `topology=[]` in replay evidence; its viewport wire is a derived cache. No triangles, volume, or manufacturing/export claim may appear just because an open arc is visually smooth. Closed profile/solid meshes remain exact-kernel-derived, not sampled sketch approximations.

## 6. Typed-output and compatibility implications

### Verified current boundaries

The released implementation is intentionally strict:

- `sketch_model.py`: embedded sketch versions {1,2}; version 2 requires `circles`; unknown keys and versions fail. Legacy default stays 1.
- `engine.validate_result_version()`: Part result versions {1,2}; embedded schema 2 rejects result 1. `_sketch_output()` only has circle, open line chain, and line-loop branches.
- `outputs.py`: `AvailableProfile(shape, region_kind, boundary_ids)` versus `OpenProfile(reason)` already provides the right high-level output algebra. No new solid type is needed.
- `sketch_service.py`: pure readiness recognizes a bounded explicit profile-error set. New expected arc errors must be deliberately included, not swallowed by broad exception handling.
- `sketch_bridge.py`: closed `region_kind` is `circle` or `line_loop`; unavailable profiles require schema-2 linework and no circles. Solved-evidence identity checks preserve line records and circle identity/center, so arc IDs/endpoints/direction must get equally strict checks.
- `topology_evidence.py`: allowed roles enumerate lines/circles only; every non-circle side role is currently required to be a plane. Allowed constrained-profile operation kinds are `polygon` and `circle_profile` only.
- `sketch_display.py`: result negotiation accepts embedded versions {1,2}, and the open display converter handles straight lines only.
- `part_contracts.py`, `part_result_bridge.py`, `sketch_action_bridge.py`, `part_snapshot_bridge.py`, `assembly_bridge.py`, and `assembly_validation_model.py` have strict source/version/output paths. Assembly source summaries also hardcode open linework and circle/line-loop kinds.
- `sketch_protocol.py` applies new numeric-policy guards through explicit checks for result 2 or embedded schema 2; new versions must not accidentally bypass those guards. `sidecar.py` and `actions.py` also explicitly echo/support only result versions 1 and 2.

### Proposed versioning decision for approval

Do not add `arcs` to embedded schema 2 or start emitting a new meaning under a legacy schema on load. An explicit **embedded sketch schema 3** with required arc data is the straightforward compatibility boundary. Preserve exact v1/v2 serialization, canonical hashes, unknown-field rejection, legacy default, and existing result behavior. Adding the first arc can explicitly opt in later; this investigation performs no migration.

For outputs, two designs are possible, and must be chosen before integration:

1. **Recommended conservative path:** negotiate **result version 3** for schema-3/arc-aware replay, solve-only, checks/exports, and assembly reuse. Keep result 1/2 contracts frozen; reject downgrade early with an upgrade explanation. A new `curve_loop` region kind distinguishes any loop containing arcs, including all-arc loops, while `line_loop` and `circle` retain their meanings.
2. Keep result 2 only if its published contract is deliberately extended by an explicit additional capability negotiation and matching validators. Merely allowing schema 3 somewhere is not enough: released result-2 consumers reject arc roles/regions and may assume every non-circle side face is planar. Do not call this transparent backward compatibility.

The outer sidecar transport can remain protocol 1 if framing, actions, and failure envelopes stay unchanged; transport version and semantic result version are separate. Part document version 2 can still contain independently versioned sketches if the model contract explicitly permits the new embedded version. A top-level Part version bump is not inherently required by exact arc geometry.

Whichever path is approved, bind the full source document and request fingerprint, retain intrinsic-radius residual evidence, preserve arc record direction/endpoint intent in successful solved data, update resource budgets/DoF ceilings correctly, and reject unrecognized capabilities before invoking native work. Explicitly test standalone Part, solve-only, snapshot receipts, embedded assembly sources, exports, and unsupported old consumers. Updating only the core parser would leave several native-free validators inconsistent.

## 7. Minimum implementation acceptance matrix

These are proposed tests, not claims that the feature is implemented:

- Schema/identity: explicit opt-in; exact old round trips/hashes; required arcs list only in the new version; duplicate/cross-kind IDs; missing center/endpoints; invalid direction; no unknown-field dropping; reordered records preserve geometry and semantic identity.
- Native arc: minor/major both senses; seam crossing; two semicircle choices; endpoint+direction reversal; arbitrary plane and quaternion normalization; radius limits; finite/bool bounds; solved residual mismatch; canonical coincidence representative effects.
- Degeneracy: same endpoint IDs, explicit-coincidence collapse, distinct equal coordinates, chord threshold, angular zero/full-turn guard on both sides, high-radius parameter cliff, radial mismatch boundary, tiny sagitta, open arc versus unusable closed sliver.
- Profiles: single arc; mixed open chain; arc+chord; two-arc circle/lens; rounded rectangle; concave mixed loop; shuffled entities; branches; disconnected cycles; holes/multiple regions; circle mixed with lines/arcs; crossings, nonadjacent tangencies, adjacent extra intersections, cocircular overlap and valid complements.
- Exact geometry: B-rep validity, analytic arc length/area/volume, one real solid where required, workplane extrusion and tilted/large-origin cases, independent display-volume distinction.
- Provenance: retained inserted handles; one generated cylindrical side per arc; stable IDs across reorder/reversal/rebuild; split, merged, deleted, generated, and untracked references fail closed; mesh-to-face coverage; no seam role invented.
- Boundary/protocol: old result fixtures remain unchanged; new results cannot downgrade; malformed/source-mismatched arc evidence rejected natively and in Blender-free validators; solve-only imports no OCP; open sketches have no profile/solid stats; downstream extrusion blocks specifically; prior export remains untouched on failure.
- Display/resources: open arc samples bounded and clearly disposable; authored identity not confused with sample indices; fine deflection, short high-radius arcs, budget rejection; no native imports in Blender; UI and file lifecycle qualification only after separate implementation.

## Source anchors

Paths below are relative to the inspected repository and are evidence/code locations, not changes made by this spike:

- `src/mechanical_cad/profile_region.py`: profile records, `validate_polygon`, `_line_connectivity`, `classify_profile`.
- `src/mechanical_cad/kernel_ocp.py`: `_profile_plane`; `circle_profile` around line 387; `polygon` around 437; `extrude` around 487; `topology` around 811; `_cut_topology` around 900; `tessellate` around 970.
- `src/mechanical_cad/outputs.py`: process-local typed output algebra.
- `src/mechanical_cad/engine.py`: result version gate and `_sketch_output` around lines 89–149.
- `src/mechanical_cad/sketch_model.py`: version constants, strict parser, serializer, budgets and entity identity.
- `src/mechanical_cad/sketch_solver.py`: solved-output revalidation and 1e-7 residual gate.
- `src/mechanical_cad/sketch_service.py`, `sketch_protocol.py`: kernel-free readiness, request binding and numeric guards.
- `src/mechanical_cad/topology.py`: adapter-attested stable semantic identity and fail-closed resolution.
- `blender_addon/mechanical_cad_blender/sketch_bridge.py`: solved identity/residual and profile/output validation.
- `blender_addon/mechanical_cad_blender/topology_evidence.py`: allowed roles, analytic surface constraints, operation provenance, triangle bindings.
- `blender_addon/mechanical_cad_blender/sketch_display.py`: version negotiation and derived open line display.
- `blender_addon/mechanical_cad_blender/assembly_validation_model.py`: strict embedded source/output summaries.
- `docs/adr/0002-conservative-topology-and-history.md`, `docs/adr/0005-typed-sketch-outputs.md`: retained provenance and wire compatibility decisions.
