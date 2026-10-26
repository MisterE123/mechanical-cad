# Bounded analytic arc profiles and explicit result-v3 services

Status: **proposal, not enabled**. Review baseline: `f0ff9bf090dd9465d44cc2b9deeb2f9d2dd31836`.
The delivered 0.5.2 source is `df65fb422ca56dafbd217b4251d453a3a863f982`;
the intervening commit records delivery only. No delivered archive is rebuilt.
The subsequent [numerical review](NUMERICAL_REVIEW.md) records bounded measurements
and the remaining endpoint-incidence blocker; this proposal is still not enabled.
The [reviewed transverse-join boundary](TRANSVERSE_JOIN_REVIEW.md) now narrows the
first closed-profile slice to one arc plus a chord or two radial lines. It adopts
provisional pure reference semantics and permits isolated arithmetic primitives
only. Wider mixed-loop forms below remain future work; no profile/service path is
activated by the design review.

This is commit boundary 2 of [NEXT_SKETCH_ARCS](../../NEXT_SKETCH_ARCS.md), after
[ADR 0007](../../adr/0007-directed-arc-core.md) and the independently qualified
[backend capability boundary](../backend_capability/CAPABILITY_PROPOSAL.md).
It supersedes the earlier research spike's mean-radius/coincidence-representative
suggestions. The canonical-start policy in ADR 0007 remains authoritative.

## 1. Outcome and hard boundaries

The bounded outcome is an explicit service request that solves a schema-3 sketch,
classifies one analytic line/arc boundary, builds a valid simple extrusion when
supported, and returns strictly validated result-v3 data with stable arc-face
provenance. A supported open chain is successful editable sketch data without
native profile, mesh, topology, solid statistics, export or Assembly capture.

This slice covers pure classification, kernel construction, result contracts,
service dispatch, data-only client validators, and independent core/service review.
Production `GuardedEvidence`, transport, publication, owners, current-evidence
readers, lifecycle and UI stay **v2-only**. No arc tool, automatic migration,
journal change, saved-envelope change, new editor owner or UI version negotiation
is included. Schema-3 canonical snapshot admission is a separate future review.

The following remain byte-exact:

- The qualified arc record/solver leaves: `sketch_model.py`, `sketch_solver.py`,
  `sketch_evaluation.py` and `arc_geometry.py`. This includes all three audited
  guard functions: `solve`, `_unique_relations`,
  `_require_acyclic_coordinate_equalities`.
- Every existing add-on Python module, including capability admission, prepared
  request, transport, execution lease, evidence factory, one-shot publication,
  revocation, Part/Rectangle/General/Assembly owners, saved codecs and UI modules.
  New v3 validators may reuse existing strict leaf helpers. A required refactor
  of an old module needs a separately reviewed proposal revision first.
- Existing canonical schema-1/2 serializers and numeric meaning. Legacy result-v1/2
  bytes, accepted fields, errors and optional-field omission remain compatible.

`BASELINE.json` records the starting Python-file hashes and protected files. New
implementation files are not permission to change a protected old consumer.

## 2. Pure analytic boundary model

Add a pure, native-free layer, provisionally `profile_curves.py` and
`profile_intersections.py`. Its immutable records distinguish a line boundary,
an arc boundary, one traversal use, a closed curve loop and an open curve chain.
Each boundary retains its entity ID, exact point references and solved coordinates;
an arc retains its authored center/start/end/direction and the unchanged
`arc_geometry(..., require_equal_radii=True)` result. A traversal reversal is a
separate flag. It never swaps the authored radius authority or rewrites coordinates.

Do not repurpose `ClosedProfile.points` as an arc chord polygon. Existing polygon
and circle kernel paths and legacy profile classes retain their behavior. Existing
`classify_profile` and `closed_profile` entry points retain their schema-1/2 gate;
a new explicit `classify_profile_v3` entry point owns schema-3 admission. A private
legacy geometry helper may be factored without changing the old public gate.

### Connectivity is identity, never a geometric repair

For a sketch containing at least one arc:

1. The boundary endpoint multigraph uses exact point IDs from line and arc
   endpoints. Equal coordinates with distinct IDs do not connect.
2. A center contributes no incidence merely because it is an arc center. A point
   deliberately also used as an endpoint participates only in that endpoint role.
3. Explicit coincidence classes may be inspected for diagnostics. A class with
   two distinct boundary endpoint IDs is rejected as
   `unsupported_profile_coincidence`, including a line-to-line alias elsewhere
   in a mixed profile. It cannot supply a hidden join. No representative point
   substitution, averaging, welding or solver-output rewrite is permitted.
4. A coincidence involving at most one boundary endpoint does not create a join.
   Existing solver rules still apply; the profile classifier does not invent
   native equations or remove a relation.
5. One connected component with two degree-one vertices and all others degree two
   is an open chain. All degree two is a candidate loop. Branches, multiple
   components, holes, multiple loops and full-circle-plus-other-boundary mixtures
   are explicit unsupported-profile failures. Unused points do not add components.
6. Two-edge curved loops are legitimate candidates: arc/chord, complementary arcs,
   or a lens. Two overlapping curves are not a loop. A two-arc disk retains two
   authored boundaries and two side roles.
7. Deterministic traversal starts from stable endpoint/edge IDs. Geometry then
   establishes winding; reversing traversal retains all authored identities.

**Arc-empty schema 3 is important:** with `arcs: []`, use the unchanged legacy
line/circle classification and coincidence semantics. Migration alone must not
invalidate an otherwise supported legacy sketch. Its explicit service request
still requires result version 3; it must not leak through result version 2.

### Contacts and supported shape

Check every pair, including adjacent boundaries, analytically: finite line-line,
line-circle restricted to directed arc, circle-circle restricted to both arcs,
and cocircular angular interval overlap, including the zero-angle seam.

- Only the declared common endpoint contact of adjacent boundaries is allowed;
  both declared endpoints are allowed in a two-edge loop.
- A smooth tangent continuation at that endpoint is allowed. Tangent reversal,
  cusp or contact whose one-sided orientation cannot be certified is rejected.
- Additional adjacent intersections, nonadjacent crossings/touches, overlapping
  intervals and unresolved near contacts fail closed.
- Preserve the number and identity of roots. Two close roots must never be merged
  so that an extra interior crossing becomes the permitted endpoint contact.
- Distinguish certified unsupported geometry from `numerically_ambiguous_profile`.
  Uncertainty must not be relabeled as `open_profile` or as a solver failure.
- Tessellation, OCCT wire welding and mesh proximity are never the classifier.

Successful solving and profile readiness stay separate. A solve-only response may
carry a successful solve and a precise failed profile check. Part replay cannot
promote that result into an available profile.

## 3. Numeric acceptance policy

The exact proposed constants, interval/area rules and the remaining native
measurement gate are specified in [NUMERICAL_POLICY.md](NUMERICAL_POLICY.md).
No production classifier, kernel service dispatch or capability advertisement
may be enabled until that policy's prerequisite gate is reviewed.

The previously qualified arc domain is frozen: coordinates bounded by ±1e6 mm;
start and end radii within [1e-6, 1e6] mm; endpoint chord at least 1e-6 mm; sweep
at least 1e-8 rad from zero and a full turn; radial disagreement at most
`min(1e-7 mm, 1e-8 * canonical_start_radius)`. Comparisons are inclusive on the
computed doubles, with no epsilon expansion. Test boundaries and `nextafter`
neighbors. A profile policy may reject uncertain geometry; it cannot relax these
definitions or silently repair a passed-but-unusable solved arc.

## 4. Native construction and semantic provenance

Introduce `Kernel.curve_profile(region, *, origin, quaternion)` without changing
legacy `polygon` or `circle_profile` semantics.

- Use the existing strict workplane transform and explicit plane. Retain the
  large-aspect-ratio safeguard; no best-fit plane or mesh-derived geometry.
- Precreate one vertex for each exact boundary endpoint ID, at its transformed
  solved point. Keep different IDs different, including geometrically close IDs.
- Build the circle from the original center and canonical start radius with the
  workplane +U fixing parameter zero. Never average radii or project an endpoint.
- Use an increasing circle interval for CCW. For CW, reverse the temporary
  parameter/vertex traversal and then the topological edge. Preserve the authored
  arc and its radius authority.
- Retain the actual `MakeWire.Edge()` returned after insertion, then verify the
  complete wire's edge/vertex membership and incidence. A native substitution
  cannot silently change authored connectivity or provenance.
- Postflight must establish circle kind, radius, intended directed trim/length,
  distinct endpoint vertices, bounded endpoint/curve discrepancy, native
  tolerance ceiling and valid B-rep. `IsDone()` is insufficient.
- Check the planar face's area against analytic evidence under the reviewed
  numerical budget. Extrusion must produce one valid solid and the expected
  area-times-positive-feature-height volume. Native adapter tests may separately
  exercise negative extrusion direction without changing the feature contract.

Register `curve_profile` construction provenance. Lines retain `line.<id>` and
arcs use `arc.<id>` boundary roles. Extrusion uses actual inserted-edge history
for `side.arc.<id>` and actual first/last shapes for caps. Splits, merges, deleted
faces and ambiguous Boolean descendants retain the existing conservative status
policy; a snapshot face index is not a stable semantic identity.

Do not impose a new center-plus-radius or circle-extrema coordinate restriction:
the frozen policy bounds the authored points/radius. Native checks must report an
unsupported construction honestly, without changing those canonical bounds.

## 5. Explicit result versions and exact wire changes

For a document, `required_result` is the maximum embedded sketch capability,
defaulting to 1. Schema 3 requires result 3 even when its arc array is empty.
For Assembly it is the maximum over **all** embedded sources, including unused
sources; preflight every source before any native replay.

- Omitted or explicit result 1 retains the existing contract and requires
  `required_result <= 1`.
- Explicit result 2 retains the existing contract and requires
  `required_result <= 2`.
- Explicit result 3 uses the new reviewed contract and requires
  `required_result <= 3`.
- Unknown versions, booleans, floats and strings reject before native work.
- No inferred version, downgrade retry, line approximation or unguarded retry.
- Outer Part schema 1/2, Assembly schema/protocol 1 and sidecar protocol 1 remain
  unchanged. Canonical snapshot has no result-version field and remains closed
  to schema 3 in this slice.

### Part, solve and geometry v3

Keep the existing strict envelope and feature shapes, explicitly stamping 3 at
both envelope and replay-result locations where the existing v2 contract stamps
2. Preserve exact input fingerprint and error-stage meaning.

A successful sketch report's `solved` value is the strict numeric embedded sketch;
schema 3 requires both `circles` and `arcs`. Exact IDs, referenced point roles,
authored direction, constraints and parameter bindings must match the request.
Clients derive radius/sweep/chord/residual using the frozen shared policy. Do not
add independent radius, sweep or repaired-point authorities to the wire.

Available sketch output retains `{state, region_kind}`. New `curve_loop` is legal
only under v3 and only for an independently classified closed boundary containing
an arc. Arc-empty lines use `line_loop`; a whole circle uses `circle`. Unavailable
profile uses the existing `{state, reason}` with `open_profile` only for a truly
supported open chain. It has no native shape, mesh, topology or solid statistics.
Failed/blocked feature output remains null.

Solve-only keeps its current exact fields, document/feature bindings and
`profile_check: {ready, error}`. Its callable default remains result 2; result 3
is explicit. Successful solve plus unsupported profile remains a successful
solve-only report, not a usable Part profile. Failed solving supplies no solved
coordinates, DoF or readiness. A v3-only profile-readiness error allowlist includes
`unsupported_profile_coincidence` and `numerically_ambiguous_profile`; these keep
successful solve evidence with failed readiness. The existing v2 allowlist and
whole-action failure behavior stay unchanged.

Common dispatched failures carry the requested result stamp, including 3.
Contract pre-dispatch failures retain the existing unstamped failure envelope.
A valid receipt does not turn an ordinary failure into geometry evidence.
Geometry checks/exports replay the requested document and selected actual solid;
preflight rejection preserves existing destination bytes. Post-launch missing or
invalid replies retain uncertain outcome and zero automatic retries.

### Assembly v3 requires richer source summaries

The outer response, service-request echo and every source summary explicitly
carry result version 3. Bind 3 into the existing type-tagged
`argument_types_fingerprint`, semantic `request_fingerprint` and
`report_fingerprint` chains. Preserve the separate complete raw-input fingerprint;
none of these identities substitutes for another.

Do not extend only the v2 enums. Each v3 source summary has exactly:

`source_document_id`, `source_digest`, `result_version: 3`, `status`, `parameters`,
`features`.

Each feature summary has exactly:

`id`, `status`, `error`, `resolved_params`, `stats`, `output`, `sketch`, `topology`.

Use `sketch: null` when absent; otherwise include the complete solve report,
including solve success retained after profile-stage failure. Include actual
intermediate topology for usable outputs and an empty array for open/failed/
blocked outputs. Do not duplicate intermediate meshes. Apply the whole-response 64 MiB,
4,000,000-node and depth-32 limits before walking the richer summaries. Meshes
remain only in the existing maximum 16 selected Part rows. Repeated references
to the same source/digest/output must have identical mesh/topology/check payloads,
matching the existing native construction cache.

Selected Part payloads retain their existing mesh, topology, geometry check,
source/output identity and mate-frame fields. Strict validation must establish:

- canonical source/feature order, exact source digest, membership and parameters;
- the same solved-profile classifier and dependency algebra as Part replay;
- failed dependency causes `upstream_failed`; a genuine open profile causes
  `profile_unavailable`; extrusion consumes an available profile; cut consumes
  two actual solids;
- source status agrees with feature status aggregation;
- only an actual successful `SolidOutput` can supply an Assembly Part;
- selected payload topology exactly equals selected-summary topology, with mesh
  triangle/face membership and geometry-check statistics bound to that output;
- cut ancestry refers to actual intermediate base/tool faces, not plausible
  invented role strings or face indexes.

Separate topology metadata/lineage validation from mesh binding. Intermediate
summaries require the former; selected payloads require both. Preserve source-
prefix failures and do not replay later sources or publish partial Parts.

## 6. Shared policy, implementation ownership and capability activation

The frozen pure `arc_geometry.py` has SHA-256
`b2017ca26300712cdaece7325fcd12fd1330d650896a5494dea56967fa1a82aa`.
Install a committed byte-exact copy under the add-on package for native-free v3
validators. Use equality/hash tests and exact installed-ZIP byte checks. The
add-on imports only its relative leaf: no core import, path discovery, runtime
copy or code generation. Document ownership separately, without divergent file
headers. Apply the same source-equality rule to the new shared pure curve policy.

Core seams are `result_policy`, new pure curve modules, explicit profile dispatch,
`engine`/kernel port, `sketch_service`/`sketch_protocol`, `sidecar`, `actions`,
`assembly_service`/`assembly_protocol`, and implementation-owned capability markers.
Add new v3 client modules that compose existing strict leaf helpers and new shared
curve policy; do not copy entire v2 validators or widen current defaults, notably
`part_contracts._expected_document`. Keep existing modules byte-exact in this slice.
If a common-helper extraction proves necessary, stop for a bounded revision and
byte-compatibility review rather than silently extending the protected file set.
Legacy v1/v2 entry points retain exact accepted variants and unknown-field rejection.

Retain the existing capability minimum algebra, exact nonce, O/G fingerprints,
origin checks, imported-root identity, execution selection and all budgets. The
recognized future names are already defined; activate each only when the actual
implementation and independent client/core gate pass:

- `mcad.sketch-arcs/1`: qualified record/solver/profile semantics;
- `mcad.solve-result/3`: explicit solve-only contract;
- `mcad.part-result/3`: full replay and topology;
- `mcad.geometry-result/3`: fresh-solid check/export;
- `mcad.assembly-result/3`: rich summaries, selected solid and exact lineage.

`mcad.snapshot-sketch3/1` remains unadvertised. Do not advertise names from a
package-version literal or an unconditional future-capability set. Attach them to
actual imported implementation markers and checked module origins. A capability
is neither proof that optional native dependencies are installed nor proof an
operation succeeded.

### Test-only guarded service route, no new authority

Service integration tests may use unchanged `backend_contracts.PreparedRequest`
and `SidecarJob.from_selection`, with one fresh prepared v3 operation and its
captured selection. Explicitly compare that selection immediately before launch
and consumption; `from_selection` alone does not perform these live checks.
Validate the same-process receipt, project only the receipt field away, and run
the explicit strict v3 action validator. Return detached ordinary data only.
For an export already launched, receipt or action-validation failure must become
`outcome_unknown` with zero retries. `SidecarJob` transport handling alone does not
replace `guarded_transport`'s post-reply validation-error protection; this test
helper must implement that data-only outcome distinction explicitly.

That helper must not construct `GuardedEvidence`, `EvidencePublication`, trusted
Assembly response state, accepted drafts or a CURRENT marker. Tests must prove
that even a genuine otherwise-valid v3 response cannot enter the unchanged
GuardedEvidence factory or live Part/Rectangle/General/Assembly publishers.

Future v3 evidence admission is a separate atomic consumer review. Today's
revalidation relies on the factory's v2 guarantee; widening it alone would widen
all retained readers. That future review must cover sync/async owners, exact G,
clone/trial/downstream chains, consume-once, rollback, history/load/disable ABA,
current readers, snapshot/capture and export uncertainty together.

## 7. Commit and qualification gates

1. **Proposal and bounded numerical qualification.** Review this contract first.
   Freeze baseline goldens and protected hashes; run a separate, durable numerical
   kernel probe only after authorization to execute that gate. Resolve all native
   measurement blockers before enabling a production consumer.
2. **Pure profile layer.** Add direct-ID graph, analytic contacts and certified
   area/ambiguity evidence with bounded resources. Unit/property adversarial tests;
   no service advertisement or UI change. Independent numerical review.
3. **Kernel construction and provenance.** Direct port tests against exact frozen
   fixtures, serial native tests, area/volume/trim/tolerance/lineage verification.
4. **Explicit v3 services and data-only contracts.** Reviewed dispatch, rich
   Assembly summaries and capability markers, cross-version and hostile-response
   tests. Production publishers remain v2-only.
5. **Freeze core/service.** Full Ruff/format/pytest, serial native/service gates,
   portable Git-free source and exact package/source identity, independent
   numerical plus protocol review. Only then propose v3 owner integration.

Every gate writes a distinct log plus completion JSON: commit/source hashes,
interpreter/native version, exact command, start/end, exit status, explicit result
marker and log hash. Interrupted or unknown runs are not passes. Collect/reap a
native process before releasing its slot. Never replace finished evidence with a
rerun or weaken legacy assertions to accommodate the new contract.

Required coverage includes:

- exact v1/v2 response and failure bytes against portable baseline fixtures,
  including omission semantics, numeric representation, canonical hashes and
  old-backend rejection; no `git show` runtime dependency;
- arc-empty schema-3 legacy line/circle/coincidence behavior through explicit v3,
  with continued rejection through v1/v2 and canonical snapshot;
- quarter/major sectors, arc/chord minor/half/major segments, two-arc disk/lens,
  rounded mixed loop, permutations, reversed traversal and tilted/far-origin planes;
- standalone/open arcs without native output, branches, equal-coordinate distinct
  IDs, unsupported coincidence joins, center-only incidence, holes/multiple loops,
  interval overlap, interior tangency, close double roots, local slivers and cusps;
- frozen arc-domain/residual boundaries and `nextafter` neighbors, native span
  wrapping/collapse, both authored directions, and canonical-start invariance;
- forged IDs/direction/coordinates, output algebra, arc-side roles, intermediate
  cut ancestry, selected topology/mesh binding, and recomputed hostile hashes;
- every existing coordinate-cycle, DoF, curve/scalar/row, byte/node/depth/Unicode/
  numeric-token/shared-container/cycle budget, before native execution;
- correct and missing capabilities, wrong selection/root/interpreter, nonce and
  full-request mismatch, dispatched failure and post-export uncertainty;
- native-free client imports and OCCT-free solve-only readiness; snapshot remains
  solver/engine-free; v3 cannot enter any production publisher.

## 8. Review disposition

No production enablement, capability advertisement, release claim or UI exposure
is authorized by this document itself. The next decision is the parent-reviewed
numerical probe and pure-layer implementation boundary. Any changed support
limit, new coincidence mapping or wider owner contract requires a visible revision
and a new corresponding review gate.
