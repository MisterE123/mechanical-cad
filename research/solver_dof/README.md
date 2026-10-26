# Pinned native DoF defect: reproduction and bounded containment

Captured on 2026-10-17 with CPython 3.12.14, Linux x86_64 and **slvs==3.2**.
These research probes preserve a reproducible reason for the 0.5.1 guard. They
are deliberately separate from production tests and release qualification.
Passing baseline assertions means **a known native defect was reproduced**.

## Result

- Three distinct points and all three distinct pairwise Coincident relations:
  true DoF **2**, native `OKAY / 0`, zero coordinate residual.
- Three distinct nonzero lines connecting three points, all Horizontal:
  true DoF **4**, native `OKAY / 3`, zero coordinate residual. Vertical behaves
  analogously; two distinct same-endpoint H lines produce **2 instead of 3**.
- The released 0.5 adapter accepts these wrong successful counts. The guarded
  adapter rejects the active-coordinate cycles with `solver_dof_indeterminate`
  and no call to `slvs.solve_sketch`. All 31 fixtures preserve authored input.
- In the deliberate **new add-on / old sidecar** pairing, the new strict bridge
  still accepts the old core's wrong count as current. The existing protocol
  does not negotiate this guard capability. Updating only the add-on is
  insufficient; the configured sidecar must actually load the corrected core.

The minimal fixture is [minimal_coincidence_cycle.sketch.json](minimal_coincidence_cycle.sketch.json).
It has no arcs, circles, lines, fixed targets or exact duplicate relations.
Six point coordinates minus four independent equalities leave two translations.
For the H triangle, the three u coordinates and one common v coordinate remain
free; the three horizontal equations have rank two, leaving four DoF.

## Files and exact evidence

- `probe_native_dof.py`: standalone native reproduction with **no CAD imports**;
  eight fixtures × diagnostics on/off = **16** observations.
- `native_dof_evidence.json`: raw status, counts, positions, independent coordinate
  residuals, full input, exact Python/platform/version and native binary SHA-256.
- `probe_dof_regression.py`: explicit-source adapter matrix, 31 fixtures × two
  diagnostic settings = **62** observations per selected source. Each native
  solve runs in a fresh process, bounded to 20 seconds. Research cycle analysis
  only labels evidence; it does not modify or filter any authored relation.
- `released_adapter_evidence.json`: the 62 baseline observations and released
  UI data-path witness. All **623** tracked files under `src` and `blender_addon`
  match Git revision `1a27e74a8f30aeb3fadac8edec935bcf12e3c304` byte-for-byte.
- `guarded_adapter_evidence.json`: the same 62 fixtures against the hotfix source;
  exact source hashes identify what was measured. Noncyclic controls have
  identical native returns and adapter reports to baseline.
- `ui_witness_release.json`: exact extract of the freshly rerun released witness,
  including a true boolean for restored-without-current-solution. It supersedes
  the earlier scratch witness whose corresponding field was null.
- `probe_ui_sidecar_mismatch.py` and `old_sidecar_new_addon_witness.json`: separately
  verified restored 0.5 core plus new add-on bridge; the false 3-DoF result is
  accepted and becomes current. Loaded module hashes identify both paths.
- `probe_equation_budget.py` and `equation_budget_evidence.json`: **15 historical
  raw-native resource/arc probes**, retained to show the larger case that exposed
  the problem. See [their scope and findings](EQUATION_BUDGET_FINDINGS.md).
- `verify_evidence.py`: offline consistency, script-identity and result checks.
  This does not run native code or establish installed-package behavior.
- `*_run.log`: compact outputs; JSON holds the detailed evidence.
- `provenance.json`: hashes of the original scratch inputs and transformations.
  Original scratch work and immutable 0.5 release artifacts were not changed.

Scripts have no hard-coded sibling-checkout dependencies. Paths in recorded JSON
are capture provenance, not paths the verifier tries to open. A mismatched pin
is rejected. The standalone native script can be copied and run outside this
repository; adapter/UI scripts need an explicitly selected compatible source.

## Reproduce

Use a Python environment containing `slvs==3.2`; the original capture used
`../mechanical_cad/.venv/bin/python`. From the repository root, set `PYTHON` to
that interpreter (or another environment with the exact pin):

```sh
export PYTHON=../mechanical_cad/.venv/bin/python
export PYTHONDONTWRITEBYTECODE=1
R=research/solver_dof

# Pure native, independent of this project's guard or any CAD source.
"$PYTHON" "$R/probe_native_dof.py" --output /tmp/native-dof.json

# Hotfix adapter + add-on data path, without replacing the recorded evidence.
PYTHONPATH=src "$PYTHON" "$R/probe_dof_regression.py" \
  --source . --expect guarded --output /tmp/guarded-adapter.json

# Restore a separate baseline from this repository's local Git history.
# No installed package, existing checkout or released archive is modified.
BASELINE=$(mktemp -d)
git archive 1a27e74a8f30aeb3fadac8edec935bcf12e3c304 | tar -x -C "$BASELINE"
"$PYTHON" "$R/probe_dof_regression.py" --source "$BASELINE" \
  --reference-revision 1a27e74a8f30aeb3fadac8edec935bcf12e3c304 \
  --expect baseline --output /tmp/released-adapter.json

# Intentional unsafe pairing. Success means the mismatch was reproduced.
"$PYTHON" "$R/probe_ui_sidecar_mismatch.py" \
  --old-source "$BASELINE" --addon-source . --output /tmp/mismatch.json

# Historical raw-native budget experiment; does not add arc support.
"$PYTHON" "$R/probe_equation_budget.py" --output /tmp/equation-budget.json

# Check the version-controlled recorded evidence and probe identities.
"$PYTHON" "$R/verify_evidence.py"
"$PYTHON" -m ruff check "$R"
"$PYTHON" -m ruff format --check "$R"
```

An individual minimal reproduction is also available:

```sh
"$PYTHON" research/solver_dof/probe_native_dof.py --case coincident_cycle
"$PYTHON" research/solver_dof/probe_native_dof.py --case horizontal_cycle
```

## Upstream source analysis

The pin is the [published slvs 3.2 package](https://pypi.org/project/slvs/3.2/).
The captured installed binary hash is recorded; **we did not rebuild or instrument
that wheel**, so source analysis is explanatory evidence, not proof of its exact
build provenance or a dynamic execution trace.

In upstream v3.2, `SolveBySubstitution` recognizes direct parameter differences.
It checks whether the original parameter handles are equal **before** resolving
prior substitutions. A cycle can resolve both sides to the same representative,
but there is no second equality check before tagging that representative as
substituted. `WriteJacobian(0)` excludes nonzero-tagged parameters; `TestRank`
subtracts Jacobian rank from the resulting parameter count. A triangle of
coordinate equalities can therefore lose a genuinely free representative.
This mechanism is consistent with the measured loss of one DoF per affected
coordinate graph. See [substitution, Jacobian and rank source](https://raw.githubusercontent.com/solvespace/solvespace/v3.2/src/system.cpp)
(`SolveBySubstitution`, lines 91–217; `WriteJacobian`, 21–71; `TestRank`, 230–239).

The convenience wrapper adds entity parameters from the active solve group and
calls `SYS.Solve` with `forceDofCheck=false`. Fixed target entities in group 1 are
excluded from the group-2 active parameter set. The substitution routine requires
both operands to be active. Thus a fixed-target relation is not an edge between
two active coordinates, even if multiple points share equal target positions.
See [Slvs_SolveSketch source](https://raw.githubusercontent.com/solvespace/solvespace/v3.2/src/slvs/lib.cpp).
The installed `slvs/solvespace.pyi` exposes only `solve_sketch(grouph,
calculateFaileds)`; it does not expose a no-substitution/force-rank option.

## UI data-path witness and mismatch

The released reducer draws three lines with shared endpoint identities and
noncollinear authored seeds `(0,0)`, `(40,20)`, `(80,5)`. Two H relations Check
successfully at 4 DoF. Saving/restoring the authoring state revokes current solved
evidence and restores those authored seeds. The actual geometry picker uniquely
selects the third line; its H selection action is eligible. Adding H and Check
then yields a bridge-accepted native `OKAY / 3`, although 4 DoF remain.
The collapsed loop independently fails the profile-overlap check.

This executes the real command reducer, persistence codec, geometry picker,
selection contract, in-process sidecar action and strict result bridge. It is
**not a native Blender GUI test**, not a process-launch/configured-interpreter
check, and not ZIP-install qualification. General Coincident authoring remains
unavailable in the released UI; the H route is the exposed authoring witness.

The mixed-version witness uses the same new add-on path while importing
`mechanical_cad.sidecar` from the hash-verified released source. It deliberately
records that input fingerprints and schema validation accept the old successful
payload. A trusted sidecar path/version/hash check in release qualification is
required; no protocol expansion is made by this research.

## Guard interpretation and limits

The production guard runs **after exact authored-relation deduplication and
before loading/calling the native backend**. Coincident contributes active u and v
edges, H contributes v and V contributes u. Parallel scalar edges from distinct
line identities are cycles. Fixed-target equations, positive distance and circle
radius relations are not active point-coordinate edges. Anchoring a cyclic
system does not exempt it: one consistent offset-seed anchored baseline also
falsely reports inconsistency. Some anchored cycles have correct counts and are
nevertheless conservatively rejected.

No authored state is rewritten, no spanning tree is silently substituted, no
constraint ID is declared uniquely removable, and no replacement rank is invented.
The capability failure leaves current solved geometry unavailable. Exact-duplicate
and fixed-only controls continue through their pre-existing native behavior.

Capturing calls to `slvs.solve_sketch` in these research probes establishes the
absence of that call for rejected cases; the probe itself imports slvs to attach
the recorder. Production tests independently establish the stronger pre-load
boundary. A zero residual and native `OKAY` or `REDUNDANT_OKAY` status do not
certify DoF. No correctness proof for all acyclic nonlinear systems, arbitrary
redundancy, platforms, future solver versions, or UI usability is implied.
