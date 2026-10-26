# Cyclic coordinate-equality solver guard

The pinned `slvs==3.2` solver can undercount remaining degrees of freedom for
cycles of active-coordinate equalities. This affects the released 0.5 line/circle
adapter, not only the separately proposed arc work. A native `OKAY` status and
zero geometric residual do **not** establish a trustworthy DoF in these cases.

## Minimal released reproduction

Three points `p0`, `p1`, `p2` all seeded at `(0, 0)`, with three distinct
coincidence relations `p0–p1`, `p0–p2`, `p1–p2`, have two free translation
coordinates. The released adapter returns `OKAY`, `remaining_dof=0`, and
`max_residual=0`. There are no arcs and no exact duplicate authored relations.

The problem is broader than coincidence. Three points `(0,0)`, `(5,0)`, `(10,0)`
joined by three distinct lines, each constrained horizontal, have four DoF
(three independent u coordinates and one shared v coordinate). Native output
reports three. Vertical and mixed coordinate-equality cycles are also relevant.
Extra circle radii do not protect the count. Such H/V relations can be authored
with the existing general line editor; general Coincident authoring is still not
exposed, but imported canonical documents can contain those relations.

## Conservative capability boundary

After the existing **exact relation deduplication**, and before loading or
calling the native solver, build separate graphs for active u and v coordinates:

- Coincident contributes an edge in each graph.
- Horizontal contributes a v edge between that line's endpoints.
- Vertical contributes a u edge between that line's endpoints.
- Fixed targets belong to the native fixed group, not the active substitution
  graph. Distance and radius equations are not coordinate-equality edges.

If an edge closes a cycle in either graph, reject with the structured error
`solver_dof_indeterminate`. Different line records can create the same scalar
equation; their parallel edges also close a cycle. Shared endpoint identities
and authored relation identities remain exact. Seed positions, tolerances,
relation ordering, camera view and workplane orientation do not determine the
gate. Anchoring some or all affected points does not bypass it.

This is deliberately conservative: a cyclic case might happen to receive a
correct DoF, but this pinned native substitution path is not trusted. The check
does not compute a substitute rank, remove equations, replace the authored graph
with a spanning tree, or identify a particular relation as safe to delete. It is
not a new general constraint solver or a proof that all other numerical systems
are correct.

## Recovery and compatibility

The complete authored state remains intact. The user can retain the recoverable
draft, explicitly review its equality relations, and use ordinary Undo or an
explicitly chosen release/recovery operation. No choice is made on their behalf.
The failure is about unavailable trusted solver evidence, not a claim that the
intended geometry is impossible.

Existing result versions require integer DoF on successful reports. This patch
therefore uses the existing structured failure envelope, with no current solved
geometry or profile, rather than fabricating zero or relaxing those schemas to
accept a successful null DoF. Dependent geometry is blocked; exports must not
replace accepted files. Canonical v1/v2 document bytes, hashes and relations do
not change. Exact duplicate relations retain their already disclosed compile-time
deduplication behavior; acyclic equality graphs continue through the native path.

The released 0.5 packages remain immutable. This guard is developed and verified
separately before a corrective package is qualified. It adds no arc capability,
new schema, automatic migration or hidden relation rewriting.
