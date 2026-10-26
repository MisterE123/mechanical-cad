# Versioned sketch service (development core)

This is the next slice's tested core contract. The released 0.3 Blender UI still
has its rectangle workflow. General line/circle authoring and typed open-sketch
viewport display are not yet wired into a qualified add-on release.

## Three different outcomes

1. **Solved sketch:** libslvs succeeded, with real remaining degrees of freedom.
   A redundant-success state is a warning; diagnostics on failure are candidates
   for inspection, not proof of which constraint should be deleted.
2. **Supported profile:** the pure classifier recognizes one simple line loop or
   one analytic circle. A connected open chain can be a valid editable sketch but
   has no closed profile. Crossing, branching, collapsed or mixed boundaries are
   distinct region-policy errors even if constraint solving succeeded.
3. **Validated solid:** OCCT built the complete feature history and the requested
   active solid passed its geometry gates. A solved sketch is not a solid.

## Explicit capability opt-in

Keep the outer Part document schema at 2. Embedded sketch schema 1 retains its
serializer, hash and closed-loop behavior. Embedded sketch schema 2 adds a
required `circles` array and radius constraints; migration is explicit.

Protocol envelope 1 remains unchanged. New replay/check/export requests include
`result_version: 2`. The response envelope and replay echo this version. The
opted-in Part envelope also binds the complete raw request with
`input_fingerprint`, including action, tessellation tolerance and destination;
a matching document hash alone does not qualify a response for another request. An old
request containing new capability data fails with `unsupported_result_version`;
clients must explain that matching add-on and backend versions are required.
Never retry by silently dropping the version field.

An available sketch output has kind `sketch`, display `solved_sketch` and profile
state `available` with region kind `line_loop` or `circle`. A supported open chain
has profile state `unavailable` with reason `open_profile`, successful solver
evidence, null mesh/stats and empty topology. A blocked extrusion names its
unavailable profile. Failed/blocked outputs are null. Primitive profiles and
solids have their own output discriminants and continue using meshes.

## Solve-only authoring request

Send exactly protocol_version, action=`solve_sketch`, result_version=2,
`document` (the full detached candidate), and `feature_id` (a constrained sketch).
No options, destination, external command or export operation is accepted.

The response contains the entire input fingerprint, candidate document ID/hash,
selected feature ID, the strict solver report and a separate `profile_check`.
Its `ok` flag describes successful solving. Thus an open sketch can return
`ok: true`, profile readiness false, and no top-level error. On solver failure,
solved data and DoF are null and profile checking is explicitly skipped.

This operation does not import OCCT or replay downstream features. Use it on
explicit Apply/Validate; cheap pointer overlays are unvalidated previews. Finish
must replay the complete candidate and publish only under an exact-base guard.
If opening a consumed sketch blocks its extrusion, retain the recoverable draft
and identify that consumer rather than committing broken history.

## Reproducible core examples

- `examples/circle_sketch_part.mcad.json`: a 30 mm diameter, 5 mm thick disk. The
  named diameter drives exactly one radius relation through `diameter / 2`.
- `examples/open_line_sketch.mcad.json`: a constrained 30 by 20 mm open chain.
  It is editable sketch data with no manufactured solid implied.

For development, use `mechanical-cad replay examples/open_line_sketch.mcad.json
--result-version 2`, or the same flag with `check-geometry`, `export-step` or
`export-stl`. The Python APIs accept `result_version=2` on `regenerate` and
`run_geometry_action`. The default CLI and released UI do not silently opt into
these new semantics.

## Limits and trust

See ADR 0005 and SKETCH_SOLVER.md. Sidecar inputs are bounded; actual native solve
and Boolean time still need process timeouts. Available-profile evidence requires
kernel success; a pure readiness check is not an export certificate. Native-free
client checks bind evidence to source IDs, workplanes, relations, dimensions and
request identity. They do not independently rerun the native solver or OCCT.

## Reusing a new sketch-based Part in an assembly

Assembly protocol 1 accepts an explicit `result_version: 2` when embedded Part
sources contain sketch schema 2. The assembly service validates every source's
version before native work, replays each source under that negotiated version,
and requires an actual typed solid at each selected Part output. An independent
open sketch may remain in a source document whose selected output is a valid
solid; the open sketch itself cannot become an assembly Part.

The response and service request echo version 2. In this negotiated version,
each source-feature summary also carries its typed `output` discriminant. This
lets the client verify that a successful extrusion consumes an available profile
and a Boolean consumes two current solids. Failed/blocked features cannot carry
current output. Full raw-request, typed-argument and report fingerprints bind
that choice. Omitted or explicit version 1 retains
its prior response shape and fingerprint policy. Old requests with new embedded
data fail with a matching-backend explanation rather than silently dropping
capabilities. Explicit source-update preflight uses the same negotiation and
canonical source normalization. These are development service/client contracts;
the released 0.3 assembly UI still uses its qualified legacy path.

## Evidence consistency gates

The new client path checks exact nested schemas for native statistics, analytic
face signatures, manufacturing mesh counts and STL encoding policy. Successful
checks require actual check evidence; successful exports additionally require an
exact destination/revision receipt. Export failure may retain completed checks,
but cannot claim a completed file write.

Mesh face IDs bind to the same output topology. Stable sides reference actual
authored line/circle IDs; cut inheritance follows only the base chain, with
split/merged/generated identities remaining snapshot-local. Full Part replay
also matches each inherited base/tool source against the actual intermediate
face payload. Assembly summaries bind source origins/roles to canonical history
without duplicating every intermediate face payload. These protocol consistency
gates do not independently reproduce the native solver or prove geometry from
hashes. A rehashed contradiction is still rejected.
