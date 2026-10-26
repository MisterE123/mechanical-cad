# ADR 0007: directed arc records and a bounded native solver core

Status: core milestone under qualification; profile, process-result and viewport
integration remain unavailable.

## Decision

Embedded sketch schema 3 explicitly adds a required `arcs` array. Each arc has a
stable ID, three distinct existing point references (`center`, `start`, `end`) and
an authored `cw` or `ccw` direction. Radius and sweep are derived, never additional
saved authorities. Existing schema-1/2 canonical serializers and hashes remain
unchanged. Migration is explicit and preserves IDs, raw expressions, point values,
plane and record order; it does not change existing circles or add constraints.

The pure `arc_geometry` policy measures the directed local-workplane sweep and
checks finite coordinates, endpoint radii, chord and distance from a zero/full
turn. Radius and coordinate bounds are inclusive computed-double comparisons.
Authored endpoint radii may differ within the structural domain so the real solver
can resolve them. Accepted solved radii must agree within
`min(1e-7 mm, 1e-8 × start radius)`. The canonical start is the radius authority;
neither endpoints nor radius are averaged or projected after solving.

The pinned `slvs==3.2` adapter reuses the same point handles for lines and arcs.
Its native arc is CCW, so CW mapping swaps only the temporary native start/end
arguments. One intrinsic equal-radius equation gives a free arc five DoF. A
radius relation compiles to a native diameter constraint, without an additional
saved dimension. Intrinsic redundant arc equations are not fabricated authored
constraint IDs. Failed native or independent geometric validation retains the
exact authored input and publishes no successful DoF or solved geometry.

The 0.5.1 active-coordinate equality guard remains before native loading. Arc
intrinsic equations are not coordinate equality edges, and the presence of an
arc does not authorize a cyclic equality count. Exact relation deduplication and
the fixed-target policy are unchanged. This remains a targeted safeguard, not
an independent general rank solver.

## Resource and compatibility boundary

Schema 3 retains the existing total curve limit of 256 and active scalar limit
of 512. Arcs share point scalars. Its conservative native equation budget counts
one intrinsic row per arc, two rows per fixed/coincident relation and one per
other supported relation, before exact authored relation deduplication. More than
1,024 rows rejects before native loading. Native controls exercise 256 intrinsic
arcs and 1,024 compiled rows at 512 active scalars; this is not a general
complexity, runtime or numerical-conditioning guarantee.

Record and low-level solver support do not imply usable Part or UI support.
Schema-3 sketches require a future result version 3. Existing replay, solve-only,
geometry/export, canonical snapshot and assembly capture/update consumers reject
them rather than flattening them into an older result. Pure profile classification
also rejects schema 3 until its mixed analytic boundary policy is implemented.
No arc extrusion, topology lineage, native drawing tool or saved arc draft is
claimed by this milestone. The shared result-version policy is a pure leaf so
canonical snapshots retain their stricter engine/geometry-free import boundary.

## Verification

- `test_sketch_v3.py` and `test_arc_geometry.py`: strict records, migration,
  numerical boundaries, legacy bytes and resource accounting.
- `test_sketch_arc_solver.py`: real native direction/radius mapping, intrinsic
  equations, shared identities and independent solved-output failure gates.
- `test_arc_native_ceiling.py`: native equation controls and pre-native overflow.
- `test_arc_core_boundary.py`: unsupported consumers fail closed without geometry
  work, publication or replacing an existing export.
- `test_arc_dof_guard.py`: both arc directions retain the pre-native equality
  cycle rejection; acyclic relations still reach the native boundary.

The full directed-arc plan remains in `docs/NEXT_SKETCH_ARCS.md`. Capability
negotiation is a separate reviewed boundary before new process/UI consumption.
