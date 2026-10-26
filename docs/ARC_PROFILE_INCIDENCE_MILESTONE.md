# Isolated shared-ID incidence preflight

Status: implemented and independently accepted as an unused pure prerequisite
at `94acd98f97e4fb9848bbf19eee5052fec232a83a`. This pure, data-only module composes the
[exact finite-arc membership layer](ARC_PROFILE_MEMBERSHIP_MILESTONE.md) under the
[approved narrow preflight proposal](architecture/arc_profile_service/INCIDENCE_PREFLIGHT_PROPOSAL.md).
It establishes prerequisites only. The latest usable release remains immutable
0.5.2; no classifier, service, native construction, publisher or UI consumes it.

## Supported inspection

`incidence_preflight` accepts an exact numeric `Sketch`, a strict finite numeric
height, and optionally one existing `PrimitiveContext`. It uses unchanged model
validation and unchanged equal-radius core arc checks. Core arc outputs are
retained in stable authored-ID order, including before unsupported multi-arc
form rejection. A numeric sketch is supplied geometry; its constraints have not
thereby been solved or certified.

The only supported boundary forms are one arc plus its shared-ID chord, or one
arc plus two shared-ID radii to the authored center. Existing bounded unused
points and numeric constraints remain in the canonical source snapshot. They do
not supply additional boundary geometry or establish whole-sketch closure.

- Required endpoint IDs must match exactly. Equal coordinates or coincidence
  chains cannot supply a join. Diagnostic alias traversal occurs only after an
  exact-ID form fails and returns an explicit unsupported-coincidence result.
- Canonical core radius and positive height are inclusively 1–1000 mm, with no
  relaxation of earlier core rules. Exact authored-ray dot product must be <=0.
  Antipodal sector radii remain an allowed straight center continuation.
- A chord is temporarily parameterized from the arc's authored start to end;
  its stored line order remains separately recorded. Sector supports are center
  to each authored endpoint. Reordering stored lines does not change these roles.
- Complete support ledgers preserve every original branch, multiplicity, finite
  line/arc membership and enclosure. Chord transversality uses the exact
  inequality 9*D >= 16*A*r^2 and requires D>0.

## Exact necessary discrepancy test

For S=|p-c|^2, canonical binary64 radius r, and N=10^9, r>=1 implies Nr-1>0.
Therefore the necessary endpoint bound is exactly equivalent to

    |sqrt(S)-r| <= 1/N
    (N*r-1)^2 <= N^2*S <= (N*r+1)^2.

The code uses the existing checked dyadic operations and compares exact values;
it evaluates no rounded gap or new square root. Exact zero is S=r^2. No endpoint
is projected, averaged or rewritten.

The inequality is inclusive mathematically. Positive equality to 1/10^9 cannot
occur for admitted dyadic S and r: sqrt(S)=r±1/10^9 would have a factor-5 rational
denominator, whose square is not dyadic. Tests use a rational reference to check
inclusivity and actual adjacent binary64 endpoints to bracket inward/outward
thresholds. A decimal-spelled 1e-9 perturbation is not labeled exact equality.

## Results and limits

The immutable report captures canonical numeric source JSON, height, core arc
outputs, original IDs/coordinates/direction, squared-gap evidence, complete
returned ledgers, nominal branch associations, and resource counters.

- `exact_endpoint_incidence` means only the prescribed endpoint roots passed
  the exact incidence prerequisites. Retained negative sector roots remain
  outside their finite lines and keep independent arc membership.
- `requires_incidence_cells` means positive discrepancies passed the necessary
  bound. It proves neither cell ownership nor a closed reference region.
- `unsupported` and `numerical_ambiguity` remain nonpassing outcomes with
  completed diagnostic data preserved. Malformed adapter/model/core inputs keep
  their separate exception boundary.

`ledgers_complete` means every intended primitive call returned, even if a
returned ledger is empty, tangent or unresolved. It does not mean incidence
passed. Resource exhaustion retains only completed calls; aggregate ledgers are
incomplete if an intended call did not return. An interrupted call never becomes
an invented empty ledger.
A later failure may retain all ledgers and only one completed discrepancy record.
Its overall numerical status remains nonpassing.

One non-resetting context retains the 100,000 checked-arithmetic operation limit
and 65,536-bit intermediate cap. Model validation, serialization, sorting and
alias diagnostics have separate existing entity/payload bounds. In particular,
at most three alias searches visit at most 256 points, with bounded adjacency
and coordinate scans. Those operations are not counted as exact scalar
arithmetic. Neither bound is a wall-clock guarantee or a Python sandbox.

No discrepancy enclosure/eta/cell, exit count, clearance, angle/area, Jordan
closure, core/native trim correspondence, frame conversion or native postflight
is established. Public record constructors remain detached containers, not
validators for fabricated evidence or production capabilities.

## Deliberate dependency-boundary extension

The primitive module and all 105 baseline runtime Python files remain byte-exact.
The new incidence module is the sole allowed importer of the primitive leaf.
Two historical static-isolation test functions were deliberately extended for
this one path; every other function/class span and every behavioral assertion
is preserved. The guards now also reject imports of either leaf from existing
runtime/classifier/service modules and all add-on files. No broad module-name or
basename exemption was introduced. This explicit extension is recorded in the
implementation commit.

## Qualification

The exact 958-file Git-free snapshot was checked against Git, ZIP and manifest.
All source hashes matched before and after every frozen gate.

| Gate | Result |
| --- | --- |
| Whole-project Ruff and formatting | Pass; 376 Python files formatted |
| Whole-project pytest | 4,541 passed and 19,597 subtests passed; exit 0 |
| New incidence tests | 194 passed |
| Independent exact-reference/adversarial suite | 168 passed |
| Primitive / membership pure suites | 329 passed |
| Independent existing pure boundary / DoF suites | 379 / 18 passed |
| Owner frozen native-import-trapped boundary gate | 962 passed |
| Existing runtime and primitive preservation | All 105 runtime hashes and primitive source exact |

The [independent review](audits/arc_profile_incidence_94acd98/INDEPENDENT_REVIEW.md)
accepts only these prerequisites. The separately sealed
[owner regression supplement](audits/arc_profile_incidence_94acd98/OWNER_REGRESSION_SUPPLEMENT.md)
verifies the full-suite receipts without overwriting the earlier pure review.
The audit includes rational threshold references, 256-point alias diagnostics,
role/direction reversal, rejected shape/scale/core cases, retained partial records,
malformed types and mutation tests of the one-path importer exception.

Existing backend regression is separate from curved-profile/native qualification.
No new Blender, installed-package or GUI qualification is claimed.

## Frozen identities

- Source ZIP SHA-256:
  `5c97d93a029fc95f8adc0b50bf30687c9fe22ce91e7c18069196829925920da5`.
- Source manifest SHA-256:
  `c845ad1d196faf23463305e807745549aaaf8a1321f017726984adeb3c07b1d1`.
- New incidence module SHA-256:
  `e9dd1ad7c2b74d72eec1be89d09f4a10e2e27f2fef3b5c783b510ce7469dbc76`.
- New incidence tests SHA-256:
  `88a7a740e9b084d345ae579fe822b2425f7b9ff5d28daad6f5b2cdb0d5266d11`.
- Unchanged primitive module SHA-256:
  `ebd60e4dd35c98459dd6d688e81322f88adcb1766c0864e16d10b9defea738bd`.

- Independent review SHA-256:
  `e9632c49f55db6f8ec04199b08b4b6d43ae8e085b84fcd2d801711deb2af7320`.
- Independent receipt SHA-256:
  `371144c223d9bee09420f2e4eb345e11bd666b4f2d3bf9e4e462351e4619356c`.
- Independent owner-regression supplement SHA-256:
  `5743cbf9287b2d0fbff85ceb42a7aa05e3eb7fc8137dfd65c2c52a3ab385307f`.
- Owner completion receipt SHA-256:
  `64701af8db4df8b540d72ec5553d77cef9d6c4a66c3ab6c52953d47b7c2843de`.

Per-gate commands, logs, source maps, retained initial fixture failures and exact
reference scripts are preserved under `cad_arc_incidence` in the engineering
evidence workspace. A later documentation commit does not change the tested
implementation identities above.

The [next integrated sector path](architecture/arc_profile_service/SECTOR_IMPLEMENTATION_PROPOSAL.md)
is a separate review/activation boundary, with
source geometry, actual native representation and service behavior each checked
against their own explicit contracts.

## Subsequent sector implementation authorization

After this preflight qualified, the owner approved the complete bounded sector
milestone on 2026-10-17: pure sector certificate/checker and independent audit,
then native adapter/provenance, then explicit data-only solve/Part-v3 validators.
The linked design artifact is preserved exactly as reviewed; its original pending
approval wording records the state when written rather than the current decision.

The approved existing-runtime edit exceptions are additive integrations in
`kernel_ocp.py`, `engine.py`, `sidecar.py` and `backend_contract.py` only.
Canonical/model/solver/add-on-owner guards and legacy v1/v2 wire bytes remain
protected. Independent review of conversion/representation budgets and the
native-face reference criterion is required before native implementation.
Restricted exact frames and zero world origin, mandatory noncardinal,
positive-gap and nonquadrantal controls, unchanged R0/C0 windows, and honest
per-gate rejection remain explicit. The exit is a useful sector/extrusion and
radius-edit core/service example; it does not activate a UI or rebuild 0.5.2.
The present incidence commit implements none of those later gates.
