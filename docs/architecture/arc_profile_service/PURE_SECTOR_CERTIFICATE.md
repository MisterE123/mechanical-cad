# Pure sector certificate checkpoint

This is the pure gate of the approved bounded sector milestone. Native construction,
result-v3 services and live Blender publication are not activated by these modules.
The latest usable release remains the independently delivered 0.5.2 preview.
See [the reviewed implementation proposal](SECTOR_IMPLEMENTATION_PROPOSAL.md) for
fixed numerical limits and the separate native and service exit criteria.

## Supported geometry and evidence

The complete policy accepts one directed arc and two radial lines joined by shared
endpoint IDs, with exact nonpositive authored-ray dot product and canonical radius
1–1000 mm. The extrusion height check is a separate nominal 1–1000 mm prerequisite.
Unsupported coincidence-only joins fail explicitly; authored coordinates are never
rewritten. A tiny positive circle/vertex gap is retained and must pass the exact
1e-9 mm discrepancy condition and the complete incidence-cell proof. Exact zero
has a distinct branch. This policy does not redefine general arc geometry.

The certificate retains all prerequisite support roots, finite membership and
multiplicity, every source-cell and proxy exit, clearance inequalities, a simple
reference-region class, bounded signed angle, source perimeter and area enclosure.
The reference-region proof does not claim that a literal connector is simple.
Mathematical bounds do not certify an OCCT mass calculation. Native conversion,
actual stored curve and pcurve correspondence, provenance, and the unchanged R0/C0
comparison criteria remain separate gates.

## One mathematical implementation, separate source bindings

- `arc_profile_intervals` shares the existing checked arithmetic context and owns
  finite outward interval arithmetic and the bounded angle/pi construction.
- `arc_profile_sector_source` validates strict geometry-only records and computes
  its own prerequisite. It does not accept a caller-supplied root ledger.
- `arc_profile_sector_policy` is the sole complete geometric certificate/checker.
- `arc_profile_sector` accepts an unchanged genuine `Sketch`, calls the qualified
  incidence prerequisite, projects validated geometry, and compares every source,
  core-geometry and root-ledger field with the shared policy's fresh prerequisite.

The core certificate binds full canonical Sketch bytes separately from the
geometry certificate. Geometry-only records cannot establish schema, constraints,
plane, solved state, backend admission or current publication authority. The shared
five-file mathematical closure can be copied byte-for-byte to a separately reviewed
client validator; no old model, expression or solver implementation is copied.

A checker recomputes the entire certificate from the bound source. It only
normalizes absolute operation offsets; hashes, dataclass names or a claimed passing
status do not authenticate a candidate. Every stage continues the same checked
100,000-operation context. Integer allocation, refinement, structure and certificate
size limits are fail-closed. The source perimeter uses both authored radial lengths,
not an assumed `2*r` when a nonzero endpoint discrepancy exists.

## Deliberate dependency extension and qualification

The two historical dependency guards now allow only the exact new core file paths
needed by this isolated policy. They still reject every existing runtime/classifier/
service consumer and every add-on consumer, including basename impostors and reverse
or cyclic edges. The other 77 historical test function/class spans are unchanged.
A new mutation suite verifies 134 allowed/forbidden import cases. No prior runtime
Python file, canonical guard, solver or add-on owner is edited in this checkpoint.

Before freezing, 1,190 focused pure tests and 200 independently authored checks passed.
These counts are preliminary mutable-tree evidence. The exact committed Git-free
snapshot must separately pass full Ruff, formatting, pytest and the independent
preservation-checked audit before the next native gate begins. There is no UI or
release claim in this checkpoint.
