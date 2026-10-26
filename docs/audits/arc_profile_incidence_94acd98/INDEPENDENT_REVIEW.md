# Independent review: isolated shared-ID incidence preflight

Reviewed implementation commit: `94acd98f97e4fb9848bbf19eee5052fec232a83a`.
Baseline: `306820456a3b63c5e3c412f59b1b5c3be6fe13f3`.
Review date: 2026-10-17.

## Decision

Accepted within the narrowly authorized **unused pure incidence-prerequisite** boundary. No mathematical, topology, resource-reporting, or dependency-scope blocker was found. This review does not establish supported profile admission, an extrusion path, native validity, GUI usability, or release qualification. Owner full-project Ruff, formatting and pytest receipts are a separate gate and were pending when this review was sealed.

The four-file delta is exactly the new `arc_profile_incidence.py`, its new unit tests, and the two explicitly approved historical static importer-test functions. No production classifier, service, solver, kernel, publisher or add-on consumes either isolated leaf. All 105 baseline runtime Python files and the delivered 0.5.2 ZIP remain byte-exact. The entire reviewed membership primitive source is unchanged.

## Input and claims

The API uses the existing exact numeric Sketch type and unchanged validation, then unchanged equal-radius core geometry in stable arc-ID order before new form/support gates. The height is a strict built-in finite int/float; a supplied context must be exactly PrimitiveContext and is never reset. Unchanged SketchError and ArcGeometryError propagate. A numeric Sketch is not authority that constraints have been solved or satisfied.

Frozen/slotted result records retain canonical source JSON, original height type/value, original arc roles/coordinates/direction, unchanged core outputs, exact ray/gap quantities, stored versus temporary support order, nominal branch associations, complete returned original root ledgers and resource counters. They are detached data containers, not validators of manufactured evidence or publication capabilities.

The statuses distinguish exact endpoint incidence, bounded positive discrepancy requiring incidence cells, unsupported forms/support, and numerical ambiguity. Neither successful prerequisite status means a closed/admitted profile. In particular, positive-gap nominal branch associations are not claims of cell ownership.

## Topology review

Exactly one arc, no circles, and exactly one chord or two radial lines are required. Joins use the authored IDs. Chord support order is arc start-to-end, independent of stored line direction. Sector supports are center-to-own endpoint and output order follows arc roles, independent of line tuple order. Opposite radial rays are the explicitly allowed straight center continuation.

Extra unused points are within this boundary: they are bounded by unchanged Sketch validation, retained with constraints in source JSON, and create no additional boundary curve. Exact-ID matches succeed without unrelated alias inspection or constraint execution.

Only after exact topology fails, a diagnostic searches equal-coordinate and explicit coincidence neighbors. It may explain unsupported coincidence joins but never welds representatives or changes geometry. Its work is separately bounded by 256 points, bounded constraints and at most three reachability searches, each scanning at most 256 coordinates per visited point. This entity-bounded work is explicitly outside the checked scalar-arithmetic operation count; no wall-clock guarantee is claimed. A valid 256-point, 511-coincidence-constraint payload was exercised, as were mixed coordinate/constraint chains.

## Mathematical review

Let S be the exact dyadic squared norm of an authored center-relative endpoint and r the exact value of the unchanged binary64 canonical radius. For N=10^9 and r>=1, Nr-1 is positive, so squaring preserves both ordered nonnegative bounds:

    |sqrt(S)-r| <= 1/N
    iff (N*r-1)^2 <= N^2*S <= (N*r+1)^2.

The implementation uses only existing checked dyadic arithmetic in the same context, with inclusive comparisons and no widening. Exact zero is S=r^2. Equal rounded endpoint radii, equal norm inputs or zero core residual never substitute for that comparison. Rounded-hypot and subnormal nonzero discrepancies remain on the cell-required path.

For a chord the crossing-sine squared is discriminant/(4*A*r^2), so the required 2/3 lower bound is exactly 9*discriminant>=16*A*r^2. Positive discriminant and the fixed MINUS-to-start/PLUS-to-end association are retained. The approved deterministic diagnostic places nonpositive chord discriminant in SUPPORT/unsupported_profile_nontransverse; later defective complete ledgers use ROOTS/unsupported_profile_contact. Both are nonpassing.

Both radial roots survive. The negative root is outside its finite radial line while preserving independent arc membership, including major-arc interior or the opposite endpoint for semicircles. Exact-zero checking verifies only the prescribed endpoint roots. All four independent finite-line/finite-arc membership combinations survive, including discrepancy-rejected results.

The external oracle uses Fraction quadratic-polynomial signs and vertex ordering, then a global polar cyclic order for arc membership. It does not use production radical-sign or minor/major half-plane classification. Gap references use unscaled rational squared bounds; parameter intervals are independently checked against rational polynomial root order. The suite includes 240 deterministic translated/rotated/perturbed geometry cases and 500 independent dyadic gap comparisons.

Exact Delta equality is unrepresentable for actual dyadic r and S, because rational r+/-1/10^9 retains a factor-5 denominator whose square is not dyadic. Inclusive equality and neighboring rational values were checked in the reference theorem; real sketch tests use adjacent binary64 coordinates bracketing both inward and outward thresholds. Decimal spellings are never mislabeled exact equality fixtures.

## Roots and bounded failure

Every intended support call completes before discrepancy rejection. Returned ledgers are unfiltered and retain original SupportRoot identity. `ledgers_complete` means all intended calls returned, including unresolved/empty/tangent results; it does not mean incidence passed.

If a primitive call exhausts its budget before returning, only previously completed ledgers survive. No empty successful ledger is fabricated. Later exhaustion can retain all support ledgers and only a prefix of gap records; this remains explicitly numerical_ambiguity. Tests cover both distinctions and a reused exhausted context. Only integer_limit and operation_limit are translated; malformed/internal primitive errors propagate.

Fault-injected unresolved, absent, tangent, incomplete, reversed and multiplicity-defective ledgers never pass. Unresolved ledgers remain intact and distinct. These defensive controls do not imply that public detached-record constructors validate arbitrary external evidence.

## Dependency boundary verification

All non-static test ASTs and surrounding test-file content remain exact. The 77 other existing function/class spans were independently compared byte-for-byte. Both changed guards were run on disposable mutation fixtures: the exact new leaf may import primitives, while existing runtime/add-on consumers of either leaf and a same-basename impostor path all fail. The complete real source tree was independently scanned for consumers.

## Frozen pure gates

All gates ran from the exact Git-free source snapshot with a native-dependency import trap and source preservation checks before and after each gate:

- Independent external rational/topology/resource suite: **168 passed**.
- New incidence tests: **194 passed**.
- Existing primitive and membership tests: **329 passed**.
- Existing arc/core/model pure boundary tests: **379 passed**.
- Existing DoF guard tests: **18 passed**.
- Site-packages-disabled import: passed.
- Native import attempts or native processes launched by this review: zero.
- Source/Git/ZIP/manifest matches: **958 files** before and after every gate.
- Historical runtime and delivered-release preservation: passed.

Exact commands, environments, start/end timestamps, exit codes, log digests and source identities are in `FROZEN_GATE_RECEIPTS.json`. The sealed receipt identifies this review and all independent scripts.

## Frozen identities

- ZIP SHA-256: `5c97d93a029fc95f8adc0b50bf30687c9fe22ce91e7c18069196829925920da5`.
- Manifest SHA-256: `c845ad1d196faf23463305e807745549aaaf8a1321f017726984adeb3c07b1d1`.
- Incidence module SHA-256: `e9dd1ad7c2b74d72eec1be89d09f4a10e2e27f2fef3b5c783b510ce7469dbc76`.
- New test SHA-256: `88a7a740e9b084d345ae579fe822b2425f7b9ff5d28daad6f5b2cdb0d5266d11`.
- Unchanged primitive SHA-256: `ebd60e4dd35c98459dd6d688e81322f88adcb1766c0864e16d10b9defea738bd`.
- Delivered 0.5.2 ZIP SHA-256: `d644fbce66b843047a6cb3e3cd775c1af8517a7ff82e3f22ce3888b710d1971f`.

## Explicit exclusions and next boundary

No incidence cells, exits, cell/root ownership, foreign-branch exclusion, clearance, reference closure, angle/area proof, global conversion, native parameterization/postflight, classifier/service/UI activation, GuardedEvidence change, or release-byte change is established. A practical end-to-end sector-path proposal should bind those remaining obligations into a separately reviewed bounded outcome rather than treating this report as a profile token.
