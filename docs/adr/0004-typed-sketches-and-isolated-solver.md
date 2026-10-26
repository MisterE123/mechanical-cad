# ADR 0004: typed sketches and an isolated constraint solver

Status: accepted for the bounded line-sketch milestone, 2026-10-16.

## Decision

Use the real SolveSpace solver through optional pinned `slvs==3.2`, inside the
existing CPython sidecar. Keep pure immutable sketch records, expression
resolution, native solving and closed-region extraction in separate modules.
Do not inject the native binding into Blender or persist its temporary handles.

Document schema 2 adds a typed `Feature.sketch` payload for `sketch_constrained`.
Schema 1 retains its exact serializer and historical hashes. Migration is an
explicit transaction; primitive rectangles/circles are not automatically rewritten.
Source formulas, entity IDs and seeds are authoritative. Solved coordinates,
DoF, residuals and diagnostic candidates are derived build results only.

Native calls use a lock and clear their global convenience-API state before and
after each solve. We independently check residuals for the supported relation
subset. Exact duplicate equations are classified for temporary compilation only,
with canonical symmetric endpoint/equation ordering, explicit redundancy status
and unchanged saved constraints. General consistency/redundancy is still the
native solver's job; failure IDs are diagnostic candidates, not deletion advice.

A profile requires one explicitly connected, simple line loop. Shared IDs or
explicit coincidence relations establish connectivity. The region validator
rejects holes, branching, open/touching/crossed loops; it never chooses a region
or repairs a gap by proximity. Each boundary's stable line ID is passed through
OCCT wire/prism history into `side.line.<ID>` provenance. The face is constructed
on the known workplane rather than an inferred fit.

## Alternatives and tradeoffs

- Keep rectangle primitives only: reliable but cannot represent engineering
  relations or real remaining freedom. Existing primitive operations remain.
- Write a general nonlinear solver now: would make numerical robustness and
  diagnostics our responsibility before the viewport workflow is established.
- Couple the document to Blender mesh topology or solver handles: would make
  persistence, replay and dependency evolution implementation-dependent.
- Embed the binding in Blender Python: avoidable native ABI and deployment risk.

The small adapter adds optional installation work and a process call when
validating a sketch. Mouse-move preview must remain lightweight and explicitly
unvalidated. The first viewport editor supports its own XY rectangle definition;
the backend supports additional line systems and explicit quaternion planes.

## Evidence and limits

See `docs/SKETCH_SOLVER.md` for the API, bounds, licensing and primary sources;
`docs/regressions/catalog.json` records permanent cases for duplicate equations,
region connectivity, line identity, migration and native resolution boundaries.
Tests use real solver output, B-rep volume/validity, watertight tessellation,
parameter replay, STEP roundtrip and legacy hash fixtures.

No global solution-branch continuity theorem, nearest-feasible dragging,
curves/arcs/tangency, arbitrary-region UI, assembly constraints or large-model
performance claim is made. Input bounds do not guarantee native resolution at
nanometre scale. The `slvs` wheel's bundled GPL license governs this integration;
its misleading MIT classifier is not used as a redistribution basis.
