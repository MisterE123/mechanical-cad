# Assembly replay and exact pose service

This is a tested backend development milestone after the immutable 0.2 preview.
It does not establish the user-facing assembly authoring workflow. Existing Part
schema 1/2 and their protocol-v1 requests remain unchanged.

## Sources, reuse and publication

`assembly_service.run_assembly_action` accepts an immutable `AssemblyDocument`.
Every operation freshly replays its embedded canonical Part sources. Each source
is built once; repeated definitions/instances reuse the verified explicit output.
Every output passes the existing one-solid and closed oriented manifold-mesh gate.
Native handles stay process-local. The response includes per-definition mesh,
source revision, explicit output ID and literal frame definitions for display.

`preflight_source_update` constructs and checks a complete replacement candidate.
It preserves definition/instance/frame/joint IDs, reports every affected instance,
and leaves the accepted assembly untouched. A failed replay publishes no candidate.
This service preflight is **not** a Blender transaction: the UI must still stage
all affected displays, check that its original source revision is unchanged, and
publish canonical JSON and display together or roll both back. That UI gate must
be tested independently before a release claims editable assemblies.

Literal frames retain their authored part-local coordinates. Changing thickness
never implies that a numeric midplane frame follows the new geometry. Source
update previews must show the frames and all affected instances explicitly.

## Separate bounded protocol

The sidecar accepts a separate envelope containing:

- `protocol_version: 1`, `kind: "assembly"`, `assembly_protocol_version: 1`
- `assembly`: the strict embedded-source assembly document
- Explicit `action`: `assembly_replay`, `assembly_check`, or `assembly_sample`
- Optional `coordinates`: numeric joint-ID overrides for one pose
- Optional `preset_id`: explicit saved verification preset; otherwise the document
  active preset is used. A missing selection never picks the only preset.
- Optional ad-hoc `requirements`: list of `{instances: [id, id], minimum_mm: number}`
- Optional `policy`: `linear_tolerance_mm`, `volume_tolerance_mm3`,
  `linear_deflection_mm` (defaults 1e-6, 1e-9, 0.1 respectively)
- For sampling only, `samples: {joint_id: id, values: [number, ...]}`

Unknown fields, mixed Part/assembly envelopes, implicit export destinations and
unsupported actions fail closed. The entire request shares the existing 2 MiB
process input cap. Sampling accepts at most 32 explicit poses and 4096 pair queries.
The kernel remains inside the existing bounded-timeout subprocess; these caps
cannot prove an arbitrary native Boolean operation will be fast.

Sampling requires a **complete explicit base coordinate map**, including fixed
zeroes. Each sample copies that full map and varies only the named movable joint.
Other current coordinates never reset to saved defaults. Each pose reports every
requested and validated effective coordinate. Out-of-limit requests retain their
requested values, have no effective pose, and are not silently clamped.

## Persisted verification intent

Named `verification_presets` live in the assembly document and survive save/reopen.
Each clearance preset contains stable named requirements for explicit instance
pairs, plus a separate numerical policy. Engineering minimum clearance is in mm;
linear query tolerance and tessellation deflection are in mm, while the numerical
common-volume threshold is in mm³. Numerical tolerances are not fit allowances.
An explicit `interference_only` preset has no engineering clearance requirements.

A selected saved preset cannot be mixed with request-level requirements or policy
overrides. Edit the preset explicitly or clear its selection before an ad-hoc
request. Omitted requirements with no active/explicit preset produce measurements
and known violations, but every `passed` flag remains false and successful pair
queries are labeled `measurement_only`. An explicitly supplied
empty requirements array opts into ad-hoc interference-only checking. The response
`verification_basis` records kind, configured flag, selected ID and the entire saved
preset. Preset edits change the canonical digest and invalidate old evidence while
leaving source geometry and physical transforms unchanged. Display replay never
evaluates the saved preset or claims a verification pass.

## Evidence semantics

- `ok` means the requested computation completed. It is not a safety verdict.
- `complete` is computational completeness; threshold contacts may be complete.
- `known_interference` and `known_clearance_violation` retain proven violations,
  even if another pair/sample is incomplete. Such reports remain
  `violations_found` with `complete: false`.
- `passed` requires explicitly configured verification intent and complete results
  with no known violation or threshold contact.
- A display-only replay sets `passed: false`; it never claims a clearance check.
- Motion scope is `only_listed_discrete_poses` and
  `continuous_collision_guarantee: false`. Clear endpoints do not prove a clear
  intermediate path. The regression suite includes that counterexample.

`input_fingerprint` hashes the full decoded JSON request, before canonical model
normalization. It lets a client reject a wrong/late transport reply. The response
also contains the normalized `result.canonical_assembly` and its canonical digest.
`request_fingerprint` binds canonical assembly/source hashes, requested coordinate
map, exact preset selection/requirements/policy/sample inputs, policy version and distribution
versions. A separate type-tagged argument digest prevents a literal dictionary
from impersonating invalid-input explanations; immutable accepted coordinate maps
retain all their values. Cyclic/shared direct-Python containers are recorded with
bounded reference identities instead of expanding recursively. Unsupported or
excessively nested direct API data can raise a request-validation exception before
native work. The JSON process boundary cannot represent Python object references.
`report_fingerprint` additionally binds effective poses, failed source replay
diagnostics, top-level errors and observed native evidence/runtime versions.
Blocked reports retain this context rather than
hashing only the error. A client must compare its current original snapshot and
request before publishing the response; hashes do not themselves perform that
transaction.

The geometric meanings of common volume, surface distance, threshold bands,
containment, witnesses and native disagreement are defined in
[ASSEMBLY_GEOMETRY.md](ASSEMBLY_GEOMETRY.md). Nothing here certifies manufacturing,
loads, materials, fatigue, physical fit, or continuous motion safety.

## Reproducible gates

- `tests/integration/test_assembly_service.py`: actual user-authored canonical
  block reused in three instances, source replay reuse, clearance, full base pose,
  mixed known/unknown evidence, blocked-limit sampling, endpoint counterexample,
  immutable source-update candidate and rejection.
- `tests/integration/test_assembly_presets.py`: named engineering intent survives
  replay, no-preset nonpass, explicit selection, hidden-override rejection and
  requirement edits invalidating evidence without changing geometry or placement.
- `tests/integration/test_assembly_protocol.py`: real subprocess JSON replies,
  request/canonical fingerprints, malformed/duplicate fields, no hidden file path,
  and unchanged legacy Part protocol.
- `tests/unit/test_assembly_policy.py`: strict bounded policy/requirements/samples
  and independent completeness/violation aggregation.
- `examples/reused_blocks.mcad-assembly.json`: inspectable embedded Part source and
  two slider branches. This backend fixture is not evidence of GUI authoring.

## Explicit display-replay admission tolerance

An optional assembly field `replay_tolerance_mm` is a finite number in [1e-9, 1]
mm. Omission retains the legacy 1e-6 mm admission limit and legacy canonical bytes.
It is distinct from geometric validity and from a verification preset's requested
measurement resolution. Native one-solid, closed-shell, mesh, stored-tolerance and
world-coordinate precision gates still run. Nothing repairs or modifies stored
B-rep tolerances automatically.

Replay uses the saved admission value unless the request explicitly supplies its
own `policy.linear_tolerance_mm`. The report's `effective_policy` records the actual
value, and canonical/request/report fingerprints bind it. Check, Sample and STEP
export continue to use their existing verification policy, never this display
setting. A coarser display setting cannot make a fine-resolution check pass.

Load Assembly offers an opt-in override that saves the entered tolerance into the
candidate only after successful fresh replay. The Assembly panel shows the saved
replay tolerance and Set Replay Tolerance edits it transactionally. Save and reopen
use the saved value. Invalid input or too-strict admission leaves the accepted
assembly untouched. Successful edits invalidate prior check authority; replay
remains explicitly UNCHECKED. Changing a clearance preset does not change replay
admission, and replay is not clearance or manufacturing certification.

Focused gates: `tests/integration/test_assembly_replay_tolerance.py` exercises real
valid OCCT solids with explicit stored vertex tolerance, default refusal, opted-in
replay and independent strict-check refusal. Bridge and publication-binding tests
cover wrong policy, stale input, malformed bounds and exact request capture.
`tests/blender_assembly_replay_tolerance_smoke.py` exercises native Load, explicit
policy edit, refusal rollback, save/reload and check-authority invalidation. Its
`MCAD_TOLERANCE_MODEL` input enables the authored complex-enclosure regression;
headless operator evidence does not establish interactive dialog usability.

2026-10-24 bounded native evidence: Blender 5.2.2 LTS completed the smoke with the
original authored ventilated-body/smooth duct-cover assembly (stored tolerances
1.00000001422e-6 and 5.000001e-6 mm). Default Load refused; explicit 1e-5 mm Load
published current display without verification. Malformed and overly strict edits
preserved accepted state. A fresh Check's authority was revoked by a successful
2e-5 mm replay-policy edit. Native Save and Load retained and used that policy;
unrelated scene objects survived. All 18 assertions passed with the explicit
`ASSEMBLY_REPLAY_TOLERANCE_OK` marker and process exit 0. This is source-worktree
headless operator coverage, not ZIP-install, manual GUI or new platform evidence.

## Explicit contact intent (development)

See [intended-contact policy](ASSEMBLY_INTENDED_CONTACT.md) for the optional
named zero-clearance pair exception. Measured clearance pass and threshold flags
remain unchanged; separate authored policy acceptance can permit a fresh STEP
export without claiming exact contact, no penetration, or physical fit. Legacy
defaults stay strict.
