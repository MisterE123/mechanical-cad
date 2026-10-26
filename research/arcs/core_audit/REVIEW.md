# Arc-core independent review

## Verdict

Bounded pass after two integration repairs and addition of native ceiling controls. No remaining core correctness/safety defect was reproduced. The preserved snapshot itself had eight full-suite failures; the repaired integration passed the independent targeted recheck. Final whole-suite/commit qualification remains the integration owner's gate.

The immutable preserved ZIP SHA256 is ce95ffb43152965620118fd7eff9e8e1f2681136786cbfdb91e36d52f55a847f, based on ed090271a1c35fdc95d1ecd5d69e3ab8ea550354. Integration is based on d6f13afbda1dbae5516e5fe53cda533902c595b2. All 14 original preserved dirty/new files remained byte-identical to the ZIP. The reviewer changed no main/integration source and made no commits.

## Findings, prioritized and closed

1. P2: preserved part_snapshot.py:112–114 imported engine.validate_result_version. This violated the existing snapshot-only import boundary and failed two real-process tests under their guarded python -S invocation (test_part_snapshot_protocol.py:29–38,55–67,101–110). Integration moved the policy unchanged to result_policy.py, retained its public engine export, and imported the leaf in snapshot/service callers. The original import guard stayed intact. Independently reviewed and rechecked successfully.
2. P2: preserved profile_region.py:150–165 directly required schema_version, while six historical SimpleNamespace profile fixtures omitted it. They therefore raised AttributeError instead of exercising the intended connectivity cases. Valid typed Sketch records were unaffected. Integration made the fixture explicitly schema 1 at test_profile_region.py:11–20; it did not introduce implicit production schema inference. Independently rechecked successfully.
3. P2 qualification gap: sketch_model.py:32,524–529,659–660 enforced 1024 native rows, but test_sketch_v3.py:569–609 checked accounting only. NEXT_SKETCH_ARCS.md:221–223 required a real ceiling probe; research/arcs/solver/FINDINGS.md:167–169 explicitly left it pending. This audit supplied two real native controls. Integration adopted both plus a one-row-over pre-native rejection in test_arc_native_ceiling.py. They qualify bounded controls, not all possible workloads at these caps.

## Independent evidence

- Legacy compatibility: 11 existing Part fixtures, canonical JSON/hash/snapshot, v1/v2 replay envelopes, selected-sketch solve responses, and 80 seeded synthetic v1/v2 native solves were byte-identical across ed09027, the preserved draft, and repaired integration. The final Ruff-clean probe reproduced the same 1,046,933-byte output. SHA256: aac22cbd78f92c6acb28e170b009721cf78894079dc9319e619c90a9b7eac5ad. See results/compatibility_receipt.json. This does not erase intentional 0.5.1 coordinate-cycle rejection.
- Ceiling controls: 256 intrinsic arcs sharing three points returned REDUNDANT_OKAY/5 DoF/zero residual with no fabricated authored diagnostics. A 1024-row/512-scalar fixture contains 256 arcs, 256 distinct fixed relations and 128 acyclic coincident relations. It returned REDUNDANT_OKAY/0 DoF/zero residual. No authored relation is deduplicated away. Both independent probes used native diagnostics. See results/native_ceiling.json and probes/probe_native_ceiling.py.
- Numerical domains: 32 real solves covered radii 1e-6 through 1e6, both directions, minor/major sweeps and far local-coordinate origins. All passed. Preserved and integrated evidence matched. See results/arc_domains.json.
- Branch/radius cases: 32 integrated fixed-chord cases covered exact/near semicircles, both directions, infeasible and enlarged radii. Results were 16 OKAY, 4 REDUNDANT_OKAY, 8 DIDNT_CONVERGE and 4 INCONSISTENT. Success results independently obeyed arc/radius policy. Every failed solve retained the exact original Sketch object with no DoF; diagnostic IDs were real authored constraints. This establishes recoverability of the sampled singular/infeasible cases, not arbitrary branch continuity. See results/arc_branches.json.
- Native false-success rejection: eight independent output injections covered tiny-angle/full-turn, tiny chord, micrometre relative radial mismatch, radius-driver mismatch, coordinate/derived-radius domain overflow, and collapsed endpoints. Every case returned DIDNT_CONVERGE/no DoF with the exact original Sketch object. See results/false_success.json.
- Guard immutability: AST-range source text for solve, _unique_relations and _require_acyclic_coordinate_equalities was identical to d6f13af. Exact hashes are in MANIFEST.json. The guard function body has 41 lines; the integration insertion includes the separate pre-native call. No change to the released guard was accepted.
- Reviewed the result_policy leaf and imports, explicit schema-1 fixture, ADR 0007 and NEXT_SKETCH_ARCS milestone wording. They correctly distinguish low-level record/solver capability from unavailable service/UI paths.

## Test gates observed

- Preserved new core/boundary/native suites: 414 passed.
- Preserved full suite: 8 failed, 3491 passed, 19597 subtests passed in 94.18 s. All eight failures are findings 1 and 2. The original snapshot is not a full-suite pass.
- Preserved source and targeted new tests: Ruff passed.
- Repaired integration, independently run snapshot/profile/ceiling/guard/core-boundary group: 62 passed in 0.61 s.
- Final retained probe scripts: Ruff passed and all five probes reran successfully against integration; compatibility digest remained exact.

## Remaining boundaries

Schema-3 public replay, geometry/export, solve-only, canonical snapshot and assembly consumers remain deliberately fail-closed until matching profile/kernel/evidence support exists. Parsing schema 3 and exposing direct solver APIs must not advertise result-v3 support. No profile/B-rep/provenance, client result-v3, assembly result-v3, journal/UI migration, GUI or installed-package claim was reviewed. Arbitrary branch continuity, general solver rank correctness, and worst-case native runtime at accepted caps remain unestablished. The core milestone remains unreleased.

Reproduction commands and file locations are in README.md. The final exact integration full-suite and source commit freeze are separate release gates.
