# Independent capability wire review

Reviewed 2026-10-17. Scope: request/receipt fields, phase and failure semantics,
projection into existing operation contracts, numeric/resource accounting, and
actual selected-root/interpreter binding. This is a design review, not production
implementation, native qualification, or installed-GUI validation.

Sources: the proposed `CAPABILITY_PROPOSAL.md`; immutable 0.5.1 `AGENTS.md`,
`README.md`, `docs/ARCHITECTURE.md`, `docs/NEXT_SKETCH_ARCS.md`,
`docs/RELEASE_051.md`, `docs/SOLVER_DOF_GUARD.md`; core sidecar, sketch/assembly
protocol, snapshot, engine and solver modules; add-on bridge, request contracts,
SidecarJob, Part/snapshot/sketch/assembly validators; real-process snapshot tests;
retained mixed-install witness. No source checkout was changed and no GitHub or
user-computer access was used. Existing old-sidecar rejection evidence was read;
the rejection probes were not rerun.

## Verdict

The per-operation same-process boundary is appropriate. Approve the direction,
but do not freeze the initial proposal as an implementation-ready contract until
the following corrections and explicit decisions are incorporated. Most are
small contract clarifications; result-v1 acceptance requires a deliberate scope
choice. The separate publication/lifecycle reviewer owns consumer integration and
configuration/cancellation behavior.

## Required corrections

1. **Do not claim strict guarded v1 publication through the old v1 validator.**
   `bridge._exchange` at lines 328–346 checks only selected replay fields and
   sketch reports; arbitrary envelope and result keys can survive. Removing only
   `backend_receipt` and using that function therefore does not establish the
   proposal's strict unknown-field rule. Recommended bounded first slice:
   production potentially-solving requests explicitly ask for result 2 with
   legacy schema-1/2 input, and result 3 only for explicitly selected arc-family
   work. Pure canonical snapshot retains its no-result-version action contract.
   Keep unguarded result-v1 tooling and canonical/wire fixtures unchanged. If
   guarded v1 publication is required, specify and independently qualify its
   complete strict schemas instead; merely checking top-level keys is inadequate.

2. **Define a strict failure-only projection branch.**
   `assembly_bridge.validate_response` requires a complete assembly result.
   Its `accept_response` lines 440–454 handles common early failures separately
   and only loosely checks the error record. Specify exact common failure keys,
   including only the ordinary action's existing result-version stamping, with
   `ok:false`, `result:null`, and bounded exact `{code,message}`. This branch may
   show an error, never mint operation/publication evidence. A guarded dispatched
   ordinary failure should not be relabeled malformed, silently accepted with
   extra fields, or padded into a fictitious assembly result. Leave the legacy
   operation validators unchanged.

3. **Make solver-origin nullability phase-sensitive.**
   A missing or unimportable solver adapter cannot provide an actual origin.
   A pre-dispatch capability failure must remain representable without inventing
   one. Require a non-null actual solver origin for dispatched potentially-solving
   actions. A rejected-before-dispatch receipt may have null when that identity
   could not be obtained; it remains failure-only. Dispatched pure snapshot must
   have null and must not import solver, engine, actions, profile or kernel.

4. **Enforce minimum requirements on both guarded boundaries.**
   The text currently calls the minimum policy client-owned. Explicitly require
   the server to derive the same specified action/schema/result minimum and reject
   a below-minimum supplied list before ordinary dispatch. For example, a replay
   requesting only `mcad.backend-contract/1` cannot bypass the guard by omission.
   Use a contract-invalid failure; never silently add names. The no-contract
   legacy route remains a separate intentional compatibility route.

5. **Allocate bounded metadata node overhead as well as bytes.**
   Raising only G's byte cap while reusing O's full-request node limit can reduce
   the usable old operation-node budget. Validate O independently at its old
   limits and validate the small fixed metadata shape independently. Permit only
   the bounded extra metadata nodes in G, without increasing O's allowance.
   With the current helpers' value-only node counting, one contract adds at most
   36 nodes: its object, version, nonce, capability array, and 32 names. Confirm
   this accounting in the implementation and add exact node-edge fixtures.

## Decisions to freeze in the ADR

- **Interpreter comparison:** require both invocation-path equivalence and
  captured resolved-target equivalence. Comparing only the base binary collapses
  distinct venvs. Choose qualified platform-specific lexical/case normalization
  explicitly; do not resolve away the invocation identity. Root/package/module
  checks use resolved path equality or checked ancestry, never string prefixes.
- **Prefix semantics:** the proposal makes prefix/base-prefix diagnostic, while
  the hybrid-install test promises rejection of a mismatched prefix. There is no
  captured expected-prefix source yet. Either specify one for the supported
  installation layout or narrow that test to strict type/path bounds and retained
  observations. Do not infer it from Blender's interpreter.
- **Encoded-byte semantics:** fingerprints use compact ASCII JSON; current
  add-on request snapshots account for default separators, while core snapshot
  fingerprints account for compact separators. State which serializer measures
  O, G and the metadata contribution, including punctuation. Keep each existing
  legacy boundary intact; no accidental normalization of numeric types, signed
  floating zero, arrays, formulas or defaults. Preserve the raw 2 MiB cap for
  contract-absent wire input independently of the larger guarded read ceiling.
- **Bounded transports:** synchronous `_exchange_raw` currently captures both
  streams in memory and checks stdout only afterward. SidecarJob has the bounded
  file-backed loop. The proposal must not describe both current paths as already
  bounded. The integration reviewer is addressing shared bounded guarded
  transport, including stderr and export uncertainty.

## Sound aspects retained

- All nine actions are identified; primitive-only and old-document solving paths
  cannot be exempted merely because no arc appears in the request.
- Pure snapshot is correctly contract-only. It grants serialization identity,
  not solve/profile/solid/export authority, and cannot load native or solver code.
- Separate full-G and ordinary-O fingerprints preserve existing canonical and
  operation identities. Unknown fields are not generally stripped.
- Capability meaning is attached to the actual imported guard implementation,
  not inferred from a package version. This detects accidental incompatibility,
  not malicious interpreter behavior or arbitrary nonlinear-rank errors.
- Old 0.5/0.5.1 rejection is honest: absence of the extension does not prove the
  installed solver lacks the 0.5.1 repair. No automatic unguarded retry is allowed.
- Only a valid pre-dispatch receipt establishes no operation dispatch. A lost or
  invalid launched-export response leaves outcome unknown, and never triggers an
  automatic retry.

Final approval requires checking the amended proposal against the points above;
this record intentionally does not claim that an implementation exists or passes.

## Final recheck and verdict

Rechecked the amended proposal on 2026-10-17 after the design author incorporated
the review. **Acceptable as a design, with no remaining blocking contract
inconsistency in this review's scope.** The initial findings above are retained
as the audit trail, not as unresolved defects.

Confirmed resolutions:

- Both guarded boundaries require explicit typed result 2 for legacy-data
  solving paths and reject guarded result 1; canonical snapshot remains separate.
- Dispatched common early failures have a strict failure-only adapter, preserving
  existing action-level failures and preventing forged publication evidence.
- Solver-origin nullability is phase-sensitive, all other identity paths are
  required strings, and receipt/Python version integers explicitly exclude bool.
- Client and server independently reject missing minimum requirements.
- O retains its own old budgets. Contract metadata has explicit default-JSON
  byte accounting, at most 36 extra value/container nodes, and a separate depth
  bound; compact fingerprint accounting remains distinct.
- Linux invocation identity and child-observed resolved executable target must
  both match the prelaunch capture. `python_executable_target` is an explicit
  receipt field. Prefix/base-prefix remain bounded diagnostic observations.
- Guarded synchronous and asynchronous calls share bounded file-backed transport;
  the old synchronous capture behavior is correctly identified rather than
  described as already bounded.

At this recheck, adoption of the final capability names and approval of the
documented 4 KiB extension budget remained design signoffs. Both were subsequently
resolved in the final signoff below. Additional platforms still require their own
path policy and qualification.

Implementation still requires independent pure-contract mutation tests, exact
byte/node/depth and numeric edges, all nine actual guarded action paths, genuine
missing-adapter and ordinary-error receipts, mixed-root/interpreter cases, and
the full production consumer/native/installed-GUI gates. This review ran no new
production implementation or native tests and grants no implementation authority.

## Frozen-contract signoff

Rechecked the 766-line proposal on 2026-10-17 after the parent froze the specified
capability names and approved the exact 4 KiB/36-node overhead, with O's budgets
independently unchanged. Linux-only direct-executable identity is the agreed
first implementation scope. **All blockers from this wire/projection/resource/
identity review are addressed; no name or budget decision remains pending.**
The contract is ready for staged implementation in this reviewed scope. This
signoff is design approval only; all implementation and qualification gates above
remain required. No production code or external system was changed by this review.
