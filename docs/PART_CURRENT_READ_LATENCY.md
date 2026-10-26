# Bounded Part current-read latency reduction

## Measured bottleneck

The 39-node removable duct cover exercise (four-section inner/outer Lofts and
four counterbored Hole recipes) exposed a client-side bottleneck. Its observed
native Load was 31.97 seconds and grouped Hole diameter edit 89.95 seconds,
with the existing 60-second **per sidecar operation** limit unchanged. These
successful whole-operator timings are not evidence of a kernel timeout.

A fresh guarded replay of that saved model took 4.00 seconds. The saved response
then allowed native-free profiling of the unchanged client. Acceptance took
3.90 seconds. Instrumented revalidation took 9.42 seconds: bounded JSON snapshots
accounted for 5.50 seconds, another response-budget traversal 2.42 seconds, and
deepcopy 0.97 seconds. Mesh-schema validation accounted for 0.34 seconds.
Profiler overhead means these numbers should not be compared to wall-clock UI
operation timings directly.

An uninstrumented same-packet current reader showed:

- `current_part_result`: 8.824 seconds, three complete projections; after the
  change, 2.979 seconds, one projection.
- `current_part_evidence`: 5.787 seconds, two complete projections; after the
  change, 3.054 seconds, one projection.

A final rerun after adding frozen-field mutation guards measured 3.797 seconds
and 3.847 seconds respectively, still exactly one projection each. Shared-host
load was not controlled; native whole-operator results below are the practical
end-to-end evidence rather than a claim of stable microbenchmark throughput.

The subsequent native Blender 5.2.2 background run used the same unchanged model
and Hole diameter edit (3.4 mm). Load took 30.96 seconds versus 31.97 seconds;
Hole edit took 50.45 seconds versus 89.95 seconds (about 44% lower elapsed time).
The operation finished with READY status and process exit 0. A display vertex
mutation was rejected by `face_pick.bound_feature`; restoring its coordinates
was accepted again. Both explicit native result markers were present.

These are single-run diagnostic timings, not a platform performance guarantee.
The residual 50-second edit and largely unchanged Load are still too slow for a
fluid CAD workflow. The next measured target is repeated bounded-response walks
inside guarded validation, not silently weakening validation or adding a cache.

## Scope and retained boundaries

The change shares the one detached validated projection **inside one reader
call only**. It adds no persistent cache and no alternate evidence factory.
Each new read still runs the unchanged guarded receipt, exact-request, typed
result, provenance, output and resource-limit validators. Publication still
consumes its original one-shot token through the unchanged publication path.

The scene, canonical JSON, owner, unit scale and exact retained-record
association are checked before and after the potentially expensive validation.
The backend selection is freshly observed after validation, and retained
publication revocation is rechecked. The original shared receipt identity
validator also runs again against newly observed settings, preserving filesystem
origin existence/containment and root/interpreter/action/phase constraints.
Settings equality alone is not sufficient: independent review caught removal
of the retained solver source during proof, which must refuse authority.
The correction uses a call-local detached receipt, not another response walk.
Frozen evidence/request/selection field
identities are retained only for the duration of the call, rejecting illicit
field replacement during inspection. A returned result remains detached; caller
mutation never changes the next read's evidence.

Blender meshes remain mutable display caches, not canonical data or authority.
Their existing integrity checks remain separate and unchanged. No mesh/display
check is cached, no tolerance changes, no timeout increases, no source-binding
shortcut and no acceptance of saved READY labels are introduced.

## Focused verification

`tests/unit/test_part_current_read_projection.py` covers one-proof reads,
mutation during proof (document, owner, scale, backend generation/lifetime,
status, scene, record replacement/removal, owner token and frozen receipt fields),
detached output, retained-response tampering and rollback of a stale record.
Existing guarded-evidence and geometry publication/rollback tests are also run.
The final focused run passed 201 tests, including 47 new current-reader cases;
Ruff and `git diff --check` passed.

The historical `test_geometry3_owner.py` unsupported-source matrix has 30
failures on unchanged `ca7c1e2`: its expectations predate supported result-3
source variants. This change does not rewrite that matrix. Focused passing
runs exclude its 36 cases, and the baseline failures are recorded separately.
No full suite, installed-package or interactive GUI qualification is claimed.

## Post-review filesystem correction

Independent reviewer reproducer: both removed-solver cases now pass. Nine new
cases cover solver removal, solver symlink repointing outside the selected core,
and core-directory removal during proof across all three readers. All 56
current-reader regressions pass. The corrected real-packet pure readers took
3.050 seconds and 3.297 seconds, each still performing exactly one full proof.
The prior native timings predate this cheap identity-recheck correction; no new
native or GUI qualification is claimed for that correction.
