# Proposed backend capability boundary for the arc continuation

Status: reviewed design contract for staged implementation; not an implemented
or release-qualified feature. Prepared on
2026-10-17 against immutable 0.5.1 commit
`d6f13afbda1dbae5516e5fe53cda533902c595b2`. No source checkout was modified.

## Recommendation

Add an explicit, opt-in `backend_contract` to each operation request and a
strict `backend_receipt` to its response. The selected sidecar must check the
requirements **in the process that will execute the operation, before dispatch**.
The next add-on must require this contract on every production backend path,
including older documents. Use explicit typed result 2 for production operations
on schema-1/2 data, and result 3 only for the explicit arc family; retain legacy
result-1 APIs/wire behavior for tooling without publication authority. Canonical
snapshot keeps its separate no-result-version schema. Do not gate only arc requests.

Keep protocol 1, existing operation/result schemas and canonical serializers
unchanged when the extension is absent. Keep result 3 as a separately explicit
arc-output contract. The extension must not turn an old result 2 into result 3,
or infer a safety capability from an add-on/core/package version string.

Do not add a separate startup handshake in the first implementation. Every
operation currently starts a fresh process, so a successful handshake in a
different process cannot authorize the later operation. A future read-only
backend-info action may improve diagnostics, but its cached output must never
substitute for a per-operation receipt.

The boundary detects accidental incompatible installations and stale/malformed
responses. It is not authentication, remote attestation, a sandbox, or protection
against a deliberately dishonest user-selected interpreter. Hashes and fresh
request IDs establish correspondence, not cryptographic trust in the solver.

## 1. Problem and source evidence

The retained mixed-install witness shows the 0.5.1 add-on accepting an old 0.5
core's `okay`/zero-residual horizontal-cycle solve and making it current. The old
core reports 3 DoF where 4 remain. A matching request fingerprint and strict
result-2 validation do not identify the algorithm that produced the numbers.

Relevant reviewed source paths, relative to `../cad_dof_hotfix/`:

| Source | Existing boundary or evidence |
| --- | --- |
| `docs/ARCHITECTURE.md`, `AGENTS.md` | Canonical graph, native isolation, stale-cache and strict-field invariants |
| `docs/RELEASE_051.md` | Both components must be upgraded; 0.5.1 has no guard negotiation |
| `docs/SOLVER_DOF_GUARD.md` | Exact limited semantics of the coordinate-equality safeguard |
| `research/solver_dof/old_sidecar_new_addon_witness.json` | `known_mismatch_reproduced=true`, accepted false DoF and current solution |
| `research/solver_dof/probe_ui_sidecar_mismatch.py` | Reproducible separate add-on/core witness; no GUI claim |
| `src/mechanical_cad/sketch_solver.py:114` | `solve()` deduplicates exact relations and checks equality cycles before `_load_backend()` |
| `src/mechanical_cad/sidecar.py:34` | Protocol check; early assembly/solve dispatch; strict Part request fields |
| `src/mechanical_cad/sketch_protocol.py:48` | Solve-only exact request fields; result-2 fingerprint |
| `src/mechanical_cad/assembly_protocol.py:11` | Strict assembly fields and separate assembly protocol 1 |
| `src/mechanical_cad/part_snapshot.py:89` | Exact decoded-input fingerprint; no canonical model normalization |
| `blender_addon/mechanical_cad_blender/bridge.py:63,239` | Actual root/interpreter resolution and fresh-process synchronous transport |
| `blender_addon/mechanical_cad_blender/sidecar_job.py:64` | Detached request/configuration, bounded streams, cancellation and one-shot result |
| `blender_addon/mechanical_cad_blender/request_contracts.py` | Native-free bounded snapshots, shared-container/cycle protection |
| `blender_addon/mechanical_cad_blender/{sketch_action_bridge,part_result_bridge,part_snapshot_bridge,assembly_bridge}.py` | Existing exact action validators, with distinct legacy failure contracts |
| `blender_addon/mechanical_cad_blender/{sketch_pending,part_publication,general_session}.py` | Existing main-thread owner/configuration/transaction guards |
| `blender_addon/mechanical_cad_blender/{assembly_pending,assembly_state}.py` | Existing assembly ownership and report publication; configuration binding needs extension |
| `docs/NEXT_SKETCH_ARCS.md`, `docs/adr/0005-typed-sketch-outputs.md` | Explicit schema/result evolution; no implicit legacy migration |

### Verified old-sidecar rejection

A read-only direct-dispatch probe was run against the retained immutable 0.5
source and the delivered 0.5.1 source. For each of the nine actions below, adding
the proposed top-level `backend_contract` caused `invalid_request` before model
parsing or loading OCP/slvs. The probe replaced document parsing with a sentinel
that would fail if reached. Evidence: `LEGACY_CAPABILITY_REJECTION_PROBE.json`;
reproduction: `probe_legacy_capability_rejection.py --old-source <0.5 source>
--hotfix-source <0.5.1 source> --output <evidence.json>`. The script writes only
the selected evidence file and disables source bytecode writes.

- Part: `replay`, `canonical_snapshot`, `check_geometry`, `export_step`, `export_stl`
- Sketch: `solve_sketch`
- Assembly: `assembly_replay`, `assembly_check`, `assembly_sample`

Part rejects an unknown top-level field before action/model dispatch. Solve-only
performs bounded input fingerprinting, then its exact-field check rejects it.
Assembly's field allowlist rejects it before parsing the assembly. The old entry
point dispatches assembly/solve before checking Part fields; all three paths must
remain covered. The probe is not a new-contract implementation test or a claim
that every historical third-party sidecar is strict. A permissive sidecar that
ignores the field still cannot produce an acceptable guarded success without a
valid receipt, and the new add-on must not retry without the field.

0.5.1 itself will reject the extension despite containing the solver repair.
Report an unsupported capability contract, not a proven missing solver repair.
There is no change or backport to the immutable 0.5/0.5.1 packages.

## 2. Contract version 1

### 2.1 Request extension

Let `O` be one ordinary, explicitly versioned operation request. Production
potentially-solving requests explicitly select result 2 or reviewed result 3;
result 1 is not a guarded publication format. Let `G` be a
detached copy of `O` plus exactly this top-level member. This example is for a
potentially solving action; canonical_snapshot requests only the first baseline
capability, as specified in section 3:

```json
{
  "backend_contract": {
    "version": 1,
    "request_id": "62fc53815a66466ba081e53a10bfd2e61",
    "required_capabilities": [
      "mcad.backend-contract/1",
      "mcad.solver-dof-cycle-guard/1"
    ]
  }
}
```

Normative rules:

1. `version` is an exact integer 1, never boolean, string or float. Unknown
   contract versions reject. Absence selects the unchanged legacy wire path;
   null, an empty object or malformed presence does not select legacy mode.
2. `request_id` is a new 32-character lowercase hexadecimal identifier for each
   explicitly launched operation, including repeated identical input. It is
   generated by the client, captured once, and reused only for that one operation.
   It is an anti-confusion identifier, not a credential. No automatic retries.
3. `required_capabilities` is a sorted, duplicate-free nonempty array of at most
   32 exact, case-sensitive ASCII names, each 1–96 characters. Names use a fixed
   lowercase `[a-z0-9][a-z0-9._/-]*` grammar. No ranges, wildcards, aliases,
   silently trimmed whitespace, feature-name guessing or minimum-version tests.
4. Unknown fields at every contract level reject. Unknown requested names reject
   as unsupported. The server must satisfy every requested name, not just the
   names it happens to recognize. Requirements are a conjunction.
5. One specified minimum-requirement policy covers action, explicit result
   version and all relevant embedded source schemas. Both guarded boundaries
   enforce it: native-free client policy before launch, and independent pure
   server policy before dispatch. A hand-built guarded replay with only the
   backend-contract name must not bypass the solver requirement. Missing minimum
   names are `backend_contract_invalid`; never silently add them. A caller cannot
   remove the baseline through a model field, advanced preference or UI fallback.
   Both sides reject guarded result 1 under the production contract; the no-
   contract legacy branch intentionally retains its old behavior.
6. No `backend_contract` is accepted inside a document, sketch, assembly,
   snapshot, geometry `options`, verification `requirements`, or nested operation.
   This transport requirement is not authored CAD data. In particular it must
   not be confused with assembly clearance `requirements`.
7. Detach and bound `O`, then attach and bound the contract before starting any
   process or recursively scanning schemas. Model limits, exact raw expression
   text and all existing type-sensitive fingerprints remain in force.

### 2.2 Same-process receipt

An admitted operation returns its ordinary response `R` plus one top-level
`backend_receipt`. The receipt has exactly these fields:

```json
{
  "version": 1,
  "request_id": "62fc53815a66466ba081e53a10bfd2e61",
  "request_fingerprint": "<SHA-256 of the complete guarded request G>",
  "required_capabilities": [
    "mcad.backend-contract/1",
    "mcad.solver-dof-cycle-guard/1"
  ],
  "confirmed_capabilities": [
    "mcad.backend-contract/1",
    "mcad.solver-dof-cycle-guard/1"
  ],
  "missing_capabilities": [],
  "phase": "dispatched",
  "backend": {
    "core_version": "<actual imported mechanical_cad.__version__>",
    "project_root": "<absolute launch working directory>",
    "core_origin": "<actual imported mechanical_cad package directory>",
    "solver_origin": "<actual imported sketch_solver path, or null when not required>",
    "python_executable": "<absolute sys.executable preserving the venv path>",
    "python_executable_target": "<resolved executable target observed by this child>",
    "python_prefix": "<absolute sys.prefix>",
    "python_base_prefix": "<absolute sys.base_prefix>",
    "python_version": [3, 12, 14]
  }
}
```

The placeholders illustrate fields, not an executable golden response. Version
and path values are observed at runtime; 3.12.14 is not a hardcoded requirement.

- Receipt `version` is an exact integer 1, excluding booleans, floats and strings.
- `phase` is exactly `dispatched` or `rejected_before_dispatch`. It describes
  whether the ordinary operation dispatcher was entered, not whether the solve
  or geometry succeeded, or whether an export wrote a file.
- For `dispatched`, confirmed capabilities equal the entire requested list and
  missing is empty. The ordinary response may be a successful result, a truthful
  failed/partial result, or an early ordinary validation error. A positive
  capability receipt never converts `ok:false` into operation success.
- For a well-formed unsupported requirement, `phase` is
  `rejected_before_dispatch`; confirmed is exactly the supported intersection
  and missing is exactly the remaining requested names. Both lists retain the
  sorted unique policy. Missing must be nonempty for `backend_capability_missing`.
- Capability lists contain only names in the request. A future backend may
  implement extra capabilities but does not append them to this receipt. This
  avoids treating unknown response names as implicitly selected semantics.
- For `dispatched`, `solver_origin` is null exactly on the pure canonical-
  snapshot path, which does not request the solver guard. Every dispatched
  potentially solving action requires an actual guard-owning module origin,
  including primitive-only Part requests. For `rejected_before_dispatch`, it may
  also be null when the adapter is missing or could not be imported/identified;
  never invent a path in order to report a compatibility failure.
- `backend` is a strict bounded object. Only `solver_origin` may be null under
  the rules above; all other path fields are required strings. Paths are nonempty absolute strings
  without NUL, at most 4,096 characters each; core version is nonempty at most
  64 characters; Python version is exactly three nonnegative exact integers,
  each at most 1,000, excluding booleans, floats and strings. Unknown/missing nested fields reject. These strings are diagnostic
  data, never shell commands or executable instructions.
- IDs and fingerprints must equal the captured values exactly; SHA-256 strings
  are 64 lowercase hex characters. Recomputing a hash cannot legitimize changed
  action data: ordinary source/output validation is still mandatory.

Fingerprint `G` with the existing input-identity JSON convention: finite JSON,
sorted object keys, compact separators, ASCII escaping and UTF-8 SHA-256. Do not
normalize numeric types, fill defaults, sort arrays, normalize formulas, or
canonicalize the CAD model before this fingerprint. Whitespace/object-member
order are transport details; `1`, `1.0`, `true` and signed floating zero remain
distinct where existing fingerprints distinguish them.

### 2.3 Rejections and lost replies

For a well-formed guarded request rejected by capability checking, return exactly
`protocol_version`, `ok:false`, `result:null`, `error:{code,message}`, and the
receipt. This is a **new contract-level failure**, not a fabricated Part/assembly
result. It has no meshes, export receipt, geometry-check pass, sketch report,
profile, canonical capture receipt or scene-publication authority. Do not insert
a result-version field into this contract-level failure.

Proposed error codes:

- `backend_capability_missing`: a named requirement is unsupported;
- `backend_contract_invalid`: malformed/unknown contract fields or version;
- `backend_identity_mismatch`: selected package/import origin differs;
- client-side `backend_contract_unavailable`: no usable receipt from this backend;
- client-side `backend_response_invalid`: malformed, mismatched or stale receipt.

If input parsing or the contract itself is too malformed to produce a valid
receipt, the bounded existing common failure envelope is sufficient. It is
displayable only as a failure. An unguarded success is never accepted, even if
the ordinary result validates. Do not invent or copy a receipt into a response
after an unguarded execution.

Only a validated `rejected_before_dispatch` receipt establishes that this new
sidecar did not enter the operation. For a launched export with a lost,
malformed, missing or mismatched receipt, preserve the existing conservative
`outcome_unknown` warning: the destination may already have been replaced.
Do not infer “nothing was written” from a missing success receipt, timeout,
cancellation, or an old sidecar's free-form error. Never automatically retry an
export. A client-side rejection before launch is definitely no-write.

## 3. Capability meanings and action coverage

Capability names below are the chosen frozen contracts for this implementation,
not claims about the delivered 0.5.1 package. Adopt these exact names together in
the contract ADR, core manifest, add-on policy and tests before production use.

### Baseline and solver requirement

Every new-add-on operation, including pure canonical capture, requires:

- `mcad.backend-contract/1`: this exact request/receipt, strict rejection,
  same-process pre-dispatch enforcement and complete action routing contract.

Every action that can solve (Part replay, solve-only, geometry/check/export and
all assembly actions) additionally requires, even for a primitive-only input:

- `mcad.solver-dof-cycle-guard/1`: every constrained-sketch solve reachable by
  this backend uses the audited coordinate-equality guard from 0.5.1: exact
  relation deduplication first, independent active u/v graphs, coincidence and
  H/V scalar edges including parallel equations, conservative cycle rejection
  before native load/solve, no invented DoF/failed relation IDs or authored edits.
  Anchoring does not bypass the guard. Acyclic cases still use the native solver.

The guard capability is deliberately narrow. It does not certify arbitrary
nonlinear rank, all intrinsic arc equations, mathematical feasibility, kernel
correctness, manufacturing safety, or dependency availability. In particular,
an arc's intrinsic redundancy is not an authored-coordinate cycle or permission
to fabricate a deletable relation ID.

Register the guard capability next to the implementation that owns `solve()`;
the dispatcher obtains it from that **same imported module**, not from an
unrelated manifest or a core-version comparison. Loading this pure adapter must
not import slvs/OCP. An old copied-in solver adapter lacking the required marker
cannot be relabeled by a newer sidecar. An action must not use a second solver
entry point that bypasses the declared guard. Regression tests, not the marker
alone, establish that the implementation honors the contract.

### Strict production result policy

Existing `bridge._exchange` deliberately preserves permissive result-1 replay
acceptance. Its validation cannot establish strict unknown-field rejection or
full typed source/output algebra merely by adding a receipt. The bounded choice
for this slice is therefore:

- new production guarded Part, solve, geometry and assembly requests explicitly
  use result 2 for existing schema-1/2 data, including primitive-only documents;
- result 3 is explicitly selected for the reviewed arc family, never inferred
  from a successful parser import or automatically substituted on error;
- canonical_snapshot retains its own strict receipt schema, with no result-version
  argument;
- legacy unguarded result-1 APIs, defaults, accepted wire behavior and golden
  bytes remain available for legacy tooling, but their output cannot enter new
  production publication/current-evidence seams;
- guarded result-1 operation requests are rejected by the new production API
  before launch. Supporting guarded result-1 publication would require a
  separately specified strict v1 evidence schema and is outside this slice.

Choosing typed result 2 changes only the requested output contract. It does not
migrate, reserialize or rewrite a schema-1/2 document. New baseline-capable servers
must support the existing typed result-2 paths for all guarded solving actions.

### Arc/result contracts

Use the following small explicit additions, rather than a global `supports_arcs`
boolean that fails to describe which output boundary was implemented:

| Operation | Required additions for schema-3/result-3 work |
| --- | --- |
| `solve_sketch` | `mcad.sketch-arcs/1`, `mcad.solve-result/3`; explicit result 3 |
| `replay` | `mcad.sketch-arcs/1`, `mcad.part-result/3`; explicit result 3 |
| `check_geometry`, `export_step`, `export_stl` | `mcad.sketch-arcs/1`, `mcad.part-result/3`, `mcad.geometry-result/3`; explicit result 3 |
| `canonical_snapshot` | `mcad.snapshot-sketch3/1`; retain snapshot action's separate schema, with no fake result-version argument |
| `assembly_replay`, `assembly_check`, `assembly_sample` | `mcad.sketch-arcs/1`, `mcad.part-result/3`, `mcad.assembly-result/3`; explicit assembly result 3 |

The backend-contract requirement applies to every row. The solver-guard
requirement also applies to every row except pure `canonical_snapshot`, and to
ordinary typed-v2 operations that have no arcs. Snapshot must not import engine,
solver, profile, actions or kernel merely to advertise capabilities; its pure
contract registry covers serialization only. A snapshot is serialization evidence,
not proof of a valid solved profile or SolidOutput. Subsequent solve, Part capture
for assembly, source-update replay and geometry actions independently require the
guard. This is a narrow read-only exception, never a route to unguarded solve or
publication. Unneeded solver-guard requests on a snapshot are rejected as an
unsupported action/capability combination, without importing the solver.

`mcad.sketch-arcs/1` names the reviewed directed center/start/end schema-3,
native mapping, numerical-policy and bounded open/simple mixed-profile behavior
in the arc ADR. It is advertised only after those semantics are integrated and
qualified, not merely because a parser recognizes an `arcs` key. No UI capability
is implied. Result capabilities name their full typed source/output/provenance
contracts; a primitive-only explicit result-3 request still requires the matching
result capability. An explicit result-3 request uses the arc-contract family even
if that particular document contains no arcs.

Scan all potentially replayed Part features and all embedded assembly sources,
not merely the selected visible feature or selected Part. A schema-3 source with
an empty arc array is still schema 3. Reject schema-3 requests paired with result
1/2 before native work; do not delete the array, approximate arcs with lines or
quietly choose a lower version. Unknown schemas/results remain errors.

Dependency loading remains action-specific. Successful negotiation does not mean
slvs or OCP is installed, or that a dependency matches its pinned version. The
ordinary dependency/version errors remain authoritative. Solve-only and canonical
capture must retain their no-OCCT-import property. Do not load every native
dependency merely to advertise implementation capabilities.

## 4. Server ordering and preservation of legacy contracts

1. Keep bounded raw reading, duplicate-key rejection, finite numbers and stderr
   isolation before dispatch. Strictness must also cover direct Python calls.
2. If `backend_contract` is absent, run the existing legacy dispatch unchanged.
   Do not append capabilities, core versions, receipt fields or new defaults to
   its response. Retain legacy accepted numeric-lexeme behavior and error shapes.
3. If present, validate the extension and full guarded request, resolve the
   actual imported implementation identity and requirements, and freeze that
   evidence before any operation/native/export call. Unknown requirements fail
   before execution. No request-controlled dynamic import or native dispatch.
4. Construct `O` by removing **only** the known top-level contract member from
   detached `G`. Do not filter arbitrary unknown fields. Pass `O` through the
   unchanged operation validators/dispatcher. It must not recurse through the
   guarded entry point or renegotiate after entering an operation.
5. Produce ordinary `R`, whose existing `input_fingerprint` continues to bind
   `O`, using its existing action-specific fingerprint algorithm. The receipt's
   fingerprint binds full `G`, including requirements and nonce. The two hashes
   have distinct documented purposes. Existing assembly service/report hashes
   and canonical document/assembly hashes are unchanged.
6. Attach the receipt in the same process for every dispatched response,
   including existing operation-level failures and caught exceptions. Never let
   the generic `main()` result-version stamping rewrite a contract-level failure.
   One JSON response, normal exit conventions, no handshake preamble on stdout.

### Resource budgets

Preserve every old model, selected-sketch, journal, depth, numeric-token, expanded
node and response bound. Introduce a separate maximum **4 KiB serialized request
contract including its top-level member**. A guarded request can consume at most
the existing 2 MiB operation-request budget plus this fixed 4 KiB overhead;
`O` must independently pass the existing request budget. This avoids lowering the
usable old request limit merely because metadata was added.

The entry point may read at most `2 MiB + 4 KiB + 1` to determine the path, but
must still reject a legacy wire request over its original 2 MiB raw-byte cap.
The new full-request snapshot/fingerprint helper has the larger bounded envelope
budget; it must not accidentally call a 2 MiB helper on `G` or loosen `O`'s bound.
Use exact separate accounting policies:

- Transport and direct-client snapshots use the existing `json.dumps` default
  ASCII escaping and default separators, plus `allow_nan=False`. Let E be its
  UTF-8 encoding. Require `len(E(O)) <= 2 MiB` and
  `len(E({"backend_contract": C})) <= 4 KiB`. Since O is nonempty, the latter
  equals the added serialized member/separator overhead in G. Bound raw guarded
  stdin independently to 2 MiB + 4 KiB, including any wire whitespace.
- Canonical request fingerprints use compact separators and sorted keys as
  already specified. Existing core input/model compact-encoding checks remain
  independent; do not change their serializer to match transport accounting.
- Validate O with its unchanged expanded-node and depth policies. Validate C
  separately at no more than 36 value/container nodes and depth 2 relative to
  its object root. Under current accounting (object keys cost bytes but are not
  value nodes), G adds at most 36 nodes and reaches depth at most max(O depth, 3).
  Thus full-envelope helpers may allow 1,000,036 nodes while O remains capped at
  1,000,000; preserve each existing O depth limit instead of silently raising it.
- Whole raw response stays within the current 64 MiB transport cap. Receipt
  metadata separately uses `len(E({"backend_receipt": receipt})) <= 64 KiB`.
  Apply the existing bounded response tree validation too; a receipt does not
  authorize unbounded logs, deep containers or lists.

Test byte, node and depth edges independently for each serializer and projected
object, including escaping and shared DAG expansion. The bounded-path
implementation and exact-edge tests require review.

## 5. Binding to the actual selected backend

Create one immutable `BackendSelection` per operation on the main thread, shared
by synchronous and asynchronous transports. It contains resolved Project Root,
the selected absolute executable path (preserving its virtualenv invocation),
the executable's resolved target for comparison, exact launch environment policy,
timeout, and a monotonic in-memory configuration generation. Resolve defaults
and `MCAD_ROOT`/`MCAD_PYTHON` once; do not resolve again to a different selection
between request capture and subprocess launch.

Launch through the captured executable with no shell, `cwd=selected root`,
`PYTHONPATH=selected root/src`, `PYTHONHOME` removed, and existing no-user-site and
encoding settings. These are already the current bridge's launch semantics.

Check receipt origins against the captured selection before accepting anything:

- `project_root` equals the captured resolved root;
- actual package origin is the expected `root/src/mechanical_cad`; any non-null
  solver origin belongs to that package. Require an actual guard-owning origin
  for dispatched potentially-solving actions; allow null on a pre-dispatch
  rejection when the module could not be imported/identified. Dispatched pure
  snapshots require null solver origin, never a guessed path;
- actual `sys.executable` corresponds to the captured invocation path and the
  child-observed `python_executable_target` equals the captured resolved target.
  The child observes the target before dispatch; a parent-side resolution after
  the reply alone is insufficient. Require both invocation-path equivalence and
  resolved-target equivalence, not either one.
  Lexical normalization must preserve virtualenv identity rather than collapsing
  all venvs to the same base binary;
- validate and retain actual prefix/base-prefix/version for diagnostics. They
  are observations, not guessed values computed from the add-on's Python;
- mixed roots/module families or an unresolvable identity fail closed. Normal
  symlinks and platform case rules must have explicit tests; no basename-only
  comparison or string-prefix containment test.

The initial implementation/qualification scope is Linux only: Project Root/package/module origins
are resolved absolute paths; executable invocation comparison uses absolute
lexical normalization (`abspath`/`normpath` without following symlinks), and target
comparison uses strict resolved absolute paths. Capture the invocation and target
before launch, observe both in the child before dispatch, and require both pairs
to match. The launched argument is the captured absolute invocation, preserving
virtualenv selection. Do not compare only basenames or only shared base binaries.
Prefix/base-prefix remain bounded diagnostics. File replacement at an unchanged
path is not code attestation. Windows/macOS path normalization is not qualified
by Linux checks and needs a separate explicit policy and installed gate.

For the first slice, accept direct Python executables supported by the current
installation flow. Do not silently bless arbitrary shell launchers/wrappers
whose actual interpreter cannot be matched to the selected path. Report the
observed executable and ask for the direct sidecar Python path. If wrapper
support becomes a requirement, give it a separately reviewed identity contract.

No session-wide “backend OK” boolean is authority. A different installation at
the same path is checked afresh in the next process. A capability name's semantics
cannot change under the same name. An already launched process may finish using
the implementation it loaded; swapping files on disk does not retroactively
change that process. Live installation edits are unsupported. Optional file
hashes/stat identities can assist diagnostics but cannot prove which bytecode
executed or replace the per-operation gate.

## 6. Client validation, freshness and all publication paths

Add a pure `backend_contracts` leaf, with no bpy/core/OCP/slvs imports, for request
construction, requirement policy, receipt validation and explicit projections.
Transport/configuration code translates its errors into existing `BridgeError`
behavior. Guarded synchronous calls must use the same bounded file-backed process
transport as managed jobs (a synchronous wait adapter over one underlying job is
sufficient). The current legacy `_exchange_raw` uses unbounded `capture_output`
before applying its final size check; do not reproduce that behavior for guarded
production calls. Preserve one process/lease, shared cleanup, stdout/stderr caps,
result consumption and export-uncertainty semantics. Modal code continues polling;
it must not call the synchronous wait adapter. Reuse the current bounded JSON/fingerprint leaves; do not copy the
full Part, sketch or assembly validators to create “guarded” versions.

Validation order for a guarded response:

1. Confirm process/stream bounds, strict JSON, top-level protocol and exit status.
2. Check the captured guarded request is still the exact one transported.
3. Validate the receipt, exact nonce/full-request fingerprint, requirement set,
   phase and actual backend identity. Missing/malformed/foreign receipts never
   reach a success consumer. A strict contract-level rejection becomes only a
   readable compatibility error.
4. For `dispatched`, remove only `backend_receipt` from detached response `R` and
   run the existing correct operation/result-version validator against exact
   `O`. Unknown response fields anywhere else still reject.
5. Carry both the original guarded envelope/receipt and validated operation
   evidence in an immutable retained-evidence record. It can be re-read for
   current UI, exact same-revision seed consumption and command-clone validation,
   while its owner/configuration binding remains current. Separately, the
   operation/publication lease is one-shot: retained evidence cannot relaunch
   work, publish twice or transfer to another owner. Publication revalidates both
   boundaries and captured configuration/owner identity. A plain dictionary
   that passed a legacy validator is not guarded publication authority.

For dispatched early failures that precede an ordinary action fingerprint, use
a narrow failure-only adapter rather than inventing an operation result. In
particular `assembly_bridge.validate_response` requires a complete assembly
result, while legacy `accept_response` has a permissive error branch. The guarded
adapter accepts only exact `protocol_version:1`, `ok:false`, `result:null`, and
`error:{code,message}`, plus exactly the requested result-version stamping for
Part/solve/assembly result 2 or reviewed result 3; snapshot has no result version.
Require exact strings with lengths 1–128 for code and 1–100,000 for message,
and no unknown keys, action,
geometry/export evidence or other payload. A correctly typed action-level
failure with its normal fingerprint uses the ordinary strict action validator.
These early failures can only be shown as errors; they cannot produce accepted
operation/current-display evidence. Leave the unguarded legacy error acceptance
unchanged.

This wrapper/projection is intentional protocol composition, not silent unknown
field dropping. Preserve existing legacy validation APIs for compatibility tests
and explicit legacy tooling, but production add-on consumers must use guarded
evidence. Do not expose a user preference or error fallback that switches them
back to unguarded publication.

Mandatory integration inventory:

- synchronous document replay, rectangle operations and formula-triggered replay;
  retain the result-only legacy `bridge.replay` API for tooling but add a guarded
  entry point that preserves envelope ownership through
  `document_state._run_sidecar`, `_apply_result` and `_publish_candidate_locked`;
- general Check, dimension/constraint trial solves, downstream replay and Finish,
  including `GeneralSketchDraft.record_validated_solution`; that pure draft
  acceptance seam must not promote a plain legacy response into current evidence;
- synchronous geometry Check, STEP export and STL export, including
  `geometry_operations.run_geometry_action` and `_record_report`; retain guarded
  evidence while adding presentation-only fields such as requested destination;
- canonical Part capture/update and each resulting assembly replay;
- assembly candidate/source-update replay, verification Check and Sample, both
  synchronous and `SidecarJob` paths;
- publication revalidation in `part_publication`, draft acceptance and assembly
  accepted-response/report handoff; no “already validated” bypass;
- saved/reopened data and stale display paths: historical saved receipts cannot
  restore current solve, backend compatibility or export authority. In particular
  `viewport_sketch.RectangleSession.initialize_preview` currently reconstructs
  accepted replay from saved CURRENT row flags; require a live generation-bound
  guarded evidence association for reuse. Otherwise show authored/unverified
  preview and require an explicit supported validation action: General Check,
  or Rectangle Apply Dimensions/Finish as appropriate. This does not require a
  new Rectangle Check control. Do not synthesize accepted replay from saved flags
  or launch a passive native check just to restore authority. Guard
  seed-consuming constraint operations too. `document_state._parameter_mode_changed`
  cannot convert a formula to a retained resolved value merely because a saved
  READY status survived; it requires the same current guarded runtime binding.

The detailed “Explicit production sink inventory” and “Required targeted tests”
in `CAPABILITY_PUBLICATION_REVIEW.md` are part of this proposal's mandatory
cutover checklist, including projection/copy/restore paths. This is not satisfied
by adding a field to the two transports while leaving their consumers untouched.

GeneralSession already captures resolved configuration in its pending identity,
and PartPublicationIntent checks configuration again. AssemblyState currently
captures scene/window/base/units/history but **does not capture backend settings**.
Extend the shared transaction/selection seam there rather than assuming the
current assembly lifecycle already supplies this guard.

### Configuration and lifetime changes

- Increment a shared generation when backend root/interpreter or relevant launch
  settings change, even A→B→A. Invalidate current execution evidence, retain
  authored state and visibly stale last-good display. This must revoke already
  accepted sketch DoF, Part solve/geometry reports and assembly current flags as
  well as pending jobs. Add shared preference update callbacks (currently absent
  in `properties.py`) and bind runtime current-evidence checks to generation.
  Revoke prepared constraint intents and failed-solve diagnostic/recovery evidence
  too, before they can change relations or authored seeds. Trial-solve evidence,
  downstream replay and final driver acceptance must share a still-current
  owner/configuration generation; do not combine a solve under A with replay
  under B. Preserve raw input and authored expressions for explicit recovery.
  Compare both generation
  and effective resolved settings before launch, every poll, result consumption
  and final main-thread publication. Explicit preference callbacks detect A→B→A
  even without an intervening operation. Effective environment-default changes
  are checked at those observation boundaries and each current-evidence/seed-use
  preflight. No claim is made to detect arbitrary os.environ A→B→A mutations that
  occur entirely between observations; launch always uses the captured values.
- Reuse the existing execution lease and one cleanup supervisor. Cancellation
  invalidates ready-but-unconsumed results and all capability evidence. Retain
  ownership until process reaping/file cleanup; stale cleanup cannot release a
  newer job's lease. No new background handshake service or arc-specific owner.
- Scene/window/base/command/input token/units, load, Undo/Redo, disable, quit,
  owner retirement and publication rollback retain their existing checks.
  Retire RNA publication intent before lifecycle invalidation. No worker reads
  Blender state. Re-enabling does not revive a prior receipt or pending result.
  `registration._rebind_existing_documents` and other rebind paths must invalidate
  persisted Part READY/CURRENT status as well
  as assembly runtime authority. Use a new runtime lifetime epoch on register or
  reload, so resetting a generation counter cannot match an old retained object.
  Runtime selection/epoch/generation tokens never enter canonical data, draft
  codecs, annotations or command journals.
- Rollback is not permission to resurrect authority. If generation changes inside
  `_apply_result`, `_write_fields` or staged display publication and a later step
  fails, restore authored state/display caches as appropriate but recheck the
  live generation. `document_state._publish_candidate_locked` and
  `assembly_state._recover_failure` must never restore a captured old-generation
  READY/CURRENT flag, runtime report binding, lease or accepted-evidence token.
  Invalidating settings wins over rollback, including A→B→A.
- A response for a prior identical document and configuration still fails on
  its fresh request ID; a valid receipt from another operation/action is not
  transferable. A capability response alone never authorizes Finish.
- Cancellation or changing settings cannot undo an export that already replaced
  a file. Preserve uncertainty reporting and explicit retry semantics. A valid
  typed export receipt followed by stale-scene/settings or publication failure
  remains historical evidence that the earlier request wrote that destination;
  mark current display/check authority stale without falsely reporting that the
  file outcome is unknown. A missing/malformed receipt after launch is unknown.

## 7. Migration and user-facing behavior

Compatibility matrix:

| Client/request | Backend | Behavior |
| --- | --- | --- |
| Existing v1 operation without contract | New backend | Existing supported wire/result shape and canonical bytes; no injected metadata |
| New guarded operation | 0.5 or 0.5.1 | Strict unknown-field rejection; no trusted current result; no downgrade retry |
| New guarded operation | New backend missing any requirement | Bound pre-dispatch failure, no native work/export |
| New guarded typed-v2 operation on old data | Matching guarded backend | Strict action/result validator plus new receipt; ordinary acyclic results unchanged |
| New guarded result-1 request | Any backend | New production client rejects before launch; legacy unguarded tooling remains supported |
| New schema-3/result-3 operation | Baseline-only guarded backend | Explicit missing arc/result capability failure |
| New schema-3/result-3 operation | Matching arc backend | Separate schema/result-3 validation and guarded evidence |
| Old add-on reading schema/result 3 | Any backend | Unsupported version; no automatic downgrade or approximation |

No canonical data migration is caused by negotiation. Do not change document
schema 1/2, embedded sketch schema 1/2, hashes, stable IDs, raw expressions,
source order semantics, rectangle payloads, old journals or saved annotation
bytes. Arc migration remains an explicit Undoable authoring operation under
`NEXT_SKETCH_ARCS.md`. Error recovery retains complete drafts, seeds and relation
history. No relation removal, automatic equation reduction or replacement DoF.

Keep old accepted wire behavior separate from permission to use unguarded
evidence in the new add-on. Backward-readable data does not require backward-
unsafe execution. Reading, inspecting, backing up or explicitly saving an old
document can remain available while Check/Finish/export are compatibility-blocked.

Examples of truthful messages:

- No contract: “The selected backend does not provide this add-on's required
  capability contract. Install the matching core and select its Project Root
  and Sidecar Python, then Check/Rebuild again. Your draft is retained.”
- Missing named guard: “This backend did not confirm the cyclic-equality DoF
  safeguard. No current solve was accepted. Update the selected backend and
  Check again.” Show the observed paths/version and exact missing name in details.
- Missing arc/result capability: “This backend cannot process the requested
  arc/result contract. Use matching arc-capable core and add-on versions.”
- Selection changed: “Backend settings changed while the operation was running.
  Its result was not accepted. Check again using the current settings.”
- Guarded operation reaches the actual cyclic case: preserve the existing
  `solver_dof_indeterminate` explanation. This is a model-specific unavailable
  DoF result, not a backend-installation failure or an impossible-geometry claim.

No “safe”, “repaired” or “verified solver” badge based solely on negotiation.
An explicit installation check may exercise the cycle plus acyclic controls in
the exact chosen process and show observed paths. Keep it distinct from model
Check and from a guarantee about another Blender process's preferences.

## 8. Required test matrix

These are acceptance requirements for implementation, not claims that the
proposed contract already passes. Existing tests and retained evidence provide
fixtures; an independent audit must challenge both capability and result layers.

| Group | Cases and required outcome |
| --- | --- |
| Legacy bytes | Golden schema 1/2 Part, embedded sketch 1/2, assembly sources, snapshots, hashes, journals, rectangle drafts and result 1/2 replies unchanged with no extension |
| Legacy request semantics | Missing action, omitted defaults, old accepted numeric lexemes, old early errors and exact limits retain their current behavior |
| Mixed installs | Immutable 0.5 core/new add-on and 0.5.1 core/new add-on reject all nine guarded actions; no automatic unguarded retry |
| Original false-current witness | Replay the retained horizontal-cycle authoring path against old 0.5; false DoF never enters current_solution, Check/Finish/display/exports remain blocked |
| Baseline on old data | Schema-1/2 and primitive-only potentially-solving requests still require guard negotiation; pure snapshot requires contract-only and yields no solve authority; an arc-only gate cannot pass |
| Minimum requirements | Hand-built G omitting solver guard, dropping required result/arc names, or selecting guarded result 1 rejects independently on server before dispatch; client and server never silently add requirements |
| Unknown capability | Unknown name, future revision, case change, whitespace, malformed grammar, duplicate/unsorted list, empty list, excessive count/length reject before dispatch |
| Contract structure | Unknown fields, missing/null fields, booleans as versions, float/string versions, repeated JSON keys, nonfinite values, nested metadata, unsupported contract versions reject |
| Positive admission | Same actual module satisfies the exact required set; no version-string inference; future backend with additional unrequested support remains compatible |
| Hybrid installation | New sidecar plus old solver module, wrong package origin, conflicting site-package import, wrong PYTHONPATH, copied version string, mismatched invocation path or real executable target fail or produce no trusted result; prefix fields are bounded diagnostic observations, not an unproven expected-prefix comparison |
| Native independence | Capability gate imports no OCP/slvs; snapshot additionally imports no solver/engine/profile/actions; solve-only imports no OCP; missing/wrong native dependency preserves truthful ordinary errors after admission |
| Server dispatch order | Fault-inject model parsing, solver load, OCP construction, export tempfile creation and replace; none are reached for missing requirements |
| Failure receipts | Bound pre-dispatch rejection is non-authoritative; all admitted operation failure shapes remain valid through projection, including assembly early errors and partial geometry/write failures |
| Missing/forged receipt | Legacy success, null receipt, copied receipt, wrong phase, unsupported/extra response fields, partial confirmed set, invented capabilities or contradictory missing set reject |
| Stale correspondence | Different nonce, input, feature, action, destination, requirements, result version, coordinates, preset/policy/samples and assembly source reject, including identical model bytes with a new request |
| Inner evidence | A valid receipt plus a forged DoF/result/arc direction/source hash/output algebra/face lineage/export receipt still fails the existing/new typed action validator |
| Fingerprints | Distinguish omitted defaults, ordered arrays, bool/int/float and signed float zero; retain existing canonical hashes separately; no normalizing away requirement changes |
| Budgets | Exact 2 MiB legacy and operation edges; 4 KiB contract and combined edges; separate default/compact serializer and exact 1,000,000+36 node/depth edges; Unicode escaping, depth, integer token/bit limits, cyclic/shared DAGs and 64 MiB response/64 KiB metadata bounds |
| Selection paths | Explicit settings, MCAD_ROOT/MCAD_PYTHON defaults, spaces/non-ASCII, venv symlinks, same base Python across different venvs, bounded prefix diagnostics, case behavior and direct-executable policy |
| Configuration changes | Root/Python/timeout/tolerance and effective env changes before launch, running, ready and inside publication; A→B→A generation changes; no stale publication |
| Cancellation/cleanup | Before start, running, ready, concurrent consume/cancel, timeout, malformed output, crash, cleanup failure; one supervisor, one-shot consumption, correct lease retention |
| Lifecycle | Scene/window/workspace/base/command/raw-input/unit changes; Undo/Redo/load/disable/re-enable/quit; saved receipt cannot restore trust; unrelated objects/scenes/processes untouched |
| All consumers | Instrument production entry points so every solve, Part, geometry/export, snapshot and assembly path emits G and requires guarded evidence; pure snapshot exception cannot reach solve or geometry; direct legacy validator cannot publish |
| Rollback revocation | Change settings inside _apply_result/_write_fields/publication, then throw; restore authored/display content without reviving old-generation authority, including A→B→A; visible labels and runtime predicates remain stale |
| Export uncertainty | Gate failure preserves destination byte-for-byte; successful export remains atomic; lost/malformed post-launch reply or cancel after replace reports unknown outcome and does not retry |
| DoF regression | Cycle/parallel-edge/mixed-axis/anchored/permuted cases reject exactly as 0.5.1; exact duplicates retain disclosed behavior; no relation/seed rewrite or fabricated conflict IDs |
| Completed-evidence invalidation | Change settings after completed Check and A→B→A without a new native request; no stale general Finish, H/V/fixed solved seeds, rectangle initialized preview, Part CURRENT diagnostics or assembly Check preflight |
| Retained evidence vs one-shot publication | Re-read immutable same-revision evidence for UI/command validation; reject a second publication, changed evidence, stale generation, different owner or fresh operation using an old nonce |
| Native acyclic controls | Coincident/H/V forests, mixed and independent axes, anchors, exact duplicates, rectangles, circles and shipped Part/assembly examples keep native success, DoF, dimensions/volume and source identities |
| Arc semantics | Schema-3 empty/nonempty arcs, explicit result 3, all directed sectors/segments, supported open/closed profiles, intrinsic redundancy, small/large/far-origin numeric gates, provenance and native dependency errors |
| Arc negotiation coverage | Snapshot, solve, full Part, check/export and all assembly actions reject missing per-action result support; validate every embedded/replayed source; no result-2 fallback |
| Independent validators | Core/client fixtures agree but mutation tests do not share a single unreviewed oracle; core never imports add-on, add-on never imports core/native; import-DAG invariant passes |
| Exact installed gate | Install final add-on ZIP with matching and deliberately mismatched source/interpreter; actual GUI correction of settings, Check recovery, Cancel, Finish/export, save/reopen; match tested source/archive hashes |

Reuse and extend `tests/unit/test_dof_cycle_boundary.py`,
`tests/integration/test_sketch_dof_cycles.py`, `test_sidecar_install_verifier.py`,
the `test_bridge*`, `test_part_snapshot_bridge`, `test_assembly_bridge*`,
`test_sidecar_job` and pure-contract suites. Retain the independent native
acyclic qualification rather than treating a capability-name test as its
replacement. Run complete Ruff/pytest and the required native Blender/ZIP,
two-process persistence, lifecycle and real GUI gates on final code. Label
unexecuted and platform-unqualified stages explicitly.

## 9. Proposed implementation/review sequence

1. Freeze this extension's fields, capability meanings, projection/error rules,
   resource accounting and interpreter identity policy in an ADR. Freeze legacy
   golden fixtures and the mixed-install witness first.
2. Implement pure core/client contract leaves and same-process server gating;
   add all-action legacy rejection, malformed/forged response and native-free
   tests. Keep production UI disabled until every consumer has been inventoried.
3. Integrate both transports, guarded evidence records, the shared selection
   generation and all publication/assembly transaction paths. Independently
   audit bypasses, cancellation and export uncertainty before enabling it.
4. Add schema/result-3 capabilities only as the corresponding reviewed arc
   contracts land. Advertise no capability for a research-only or partial path.
5. Qualify one exact source/add-on package with deliberate old-core pairing and
   corrected-settings recovery, retaining all ordinary acyclic native controls.

Design decisions are frozen for staged implementation: the exact capability
names in section 3; 4 KiB/36-node metadata overhead with independently unchanged
operation budgets; explicit typed-v2 production output for existing data;
contract-only pure snapshots; and Linux-only direct-executable identity using
both invocation and child-observed resolved-target equality. Additional platforms
need their own explicit path policy and qualification. No implementation, native
or installed-GUI qualification is implied by accepting this design.

## Review record

- Source inspection and 18 old-dispatch rejection cases: completed for this
  proposal; no native solver/kernel loaded by those probes.
- Independent wire/projection/resource/Linux identity review: acceptable as a
  design, with no remaining blocker in that scope after the documented fixes.
  See `CAPABILITY_WIRE_REVIEW.md` for initial findings and final recheck.
- Independent publication/configuration/lifecycle review: bounded approval for
  implementation after incorporating its dispositions and mandatory sink/tests
  checklist. See `CAPABILITY_PUBLICATION_REVIEW.md`. This is not release approval.
- Production implementation, full regression run, arc/native qualification and
  installed GUI compatibility checks: not performed by this design task.
