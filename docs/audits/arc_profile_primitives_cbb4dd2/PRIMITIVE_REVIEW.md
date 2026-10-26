# Independent isolated arc-profile primitive review

Disposition: ACCEPT the isolated primitive implementation at cbb4dd2c9969b0cc7aa2bfbeb0704dcf9422ff5b within the exact two-file scope below. Independent frozen gates and the separately verified owner full-regression receipt pass. No remaining primitive blocker was found. Integration and all later profile/native/service/UI activation remain blocked.

## Scope and preserved authorities

The reviewed design is the sealed transverse contract SHA-256 befbd79b5105535b3c0fa3efcdadca2433559d2dbd0ba76927b584de6c918fe8, adopted in documentation commit 00025560056c6f973427056e710c4f4a07c6d76a. The only implementation additions under review are src/mechanical_cad/arc_profile_primitives.py and tests/unit/test_arc_profile_primitives.py. The initial preservation gate verified all 105 original runtime files and all 939 pre-design tracked files byte-exact. Final preservation is relative to the adopted documentation commit, with the original 105-file runtime map and delivered 0.5.2 archive hash checked separately.

The preliminary hash gate deliberately failed while the designer was still sealing a final contract. The owner confirmed the final hash above before this implementation review proceeded. Earlier hashes remain in the design receipt; no unreviewed semantic substitution is accepted.

## Formula-by-formula assessment

- Binary64 decoding uses the finite fixed-size float.hex representation, validates the coordinate domain and actual types, bounds mantissa allocation, and retains subnormal exponents. Bounded built-in integers are an explicitly approved convenience because every admitted integer is exactly representable in binary64; bool, subclasses, Decimal, Fraction and nonfinite inputs reject. Exact translation occurs only after individual decoding, so a tiny offset is not lost by rounded subtraction.
- Exact values are canonical odd-mantissa dyadics, with explicit canonical zero. Addition aligns exact exponents, multiplication multiplies exact mantissas, and all arithmetic delegates to guarded integer operations. General rational normalization and gcd are absent. The only rational quotient is private directed division used for interval output; numerator and denominator shifts, divmod, endpoint rounding and a post-division inequality are bounded.
- Dot, cross and discriminant are their exact polynomial formulas. Every allowed arithmetic path returns the exact dyadic result or a resource error. No epsilon, libm root or float discriminant supplies a sign.
- For p+q sqrt(D), a negative D rejects. Zero radical/coefficient cases are explicit. Matching nonzero signs need no squaring. Opposite signs compare p² with q²D and multiply that comparison by sign(p), preserving equality and negative-root cases. This is valid because D is nonnegative and the compared magnitudes are nonnegative; squaring is used only after the sign partition.
- If 2^k <= D < 2^(k+1), sqrt uses grid exponent floor(k/2)-(p-1). Integer isqrt of floor(D/grid²) is exactly the floor of sqrt(D)/grid. Lower and upper values are canonicalized, and their squared inequalities are independently verified with exact arithmetic. A significand carry becomes a larger exponent, rather than a p+1-bit significand. Exact zero is separate. Both normalized endpoint exponents must remain within ±32768. No fixed fractional-bit grid is mislabeled as significant precision.
- Directed rounding uses arithmetic right shift for a lower bound, including negative values. Upward rounding adds one exactly when the discarded remainder is nonzero. Directed division uses Python's floor quotient with a positive divisor, then the corresponding upward increment, and verifies each returned endpoint against the exact numerator/denominator.
- The line/circle quadratic uses exact h=end-start and offset=start-center. A>0 follows from distinct endpoints and exact sum of squares. Negative discriminant yields an empty root tuple; zero yields one DOUBLE with multiplicity two; positive yields distinct MINUS/PLUS identities. Finite-line positions are signs of -B±sqrt(D) and -B-2A±sqrt(D), so equality at t=0 or t=1 is exact and independent of interval width.
- Isolation tries only 64, 128 and 256 significant bits and stops at first strict separation. A failure to separate does not merge or discard roots: the distinct, non-subclass UnresolvedSupportRoots result retains both branches, exact positions and final overlapping enclosures with unresolved_isolation. This type is not a successful isolated root result.
- Result records and nested dyadic/interval/root records are frozen, slot-backed records; root collections are tuples. No native, model, solver, service, classifier, area, angle or UI function is imported or invoked by the new leaf.

## Resource and trust boundary

The hard limits remain 65,536 bits and 100,000 charged integer/scalar operations. Before allocating an arithmetic result, addition checks max operand bits+1, multiplication checks summed operand bits, and shifts check the prospective size. Exact cancellation or a reducible quotient does not waive these conservative prechecks. Normalization is fixed bitwise work with charged operations, not an unbounded gcd or refinement search. Square root invokes bounded integer isqrt; root isolation has at most three fixed attempts.

Input parsing, bit-length inspection, bounded exponent/counter bookkeeping and control flow are outside the charged scalar count. This is an operational work bound, not a wall-clock theorem. The caller must share one context for any later aggregate profile calculation; this primitive-only commit does not implement that caller. Python object mutation/reflection is not claimed to be a sandbox. Future integration must validate its own external inputs and must not manufacture successful records or reset/replace the shared budget to evade a profile limit. Returned result objects are deeply immutable; the public record constructors are not external certificate validators. Their annotations and frozen status alone do not prove semantic completeness of caller-manufactured data. No current production consumer accepts these records.

## Adversarial coverage prepared independently

The separate Fraction-based test oracle is never imported by production. It covers deterministic binary64 bit patterns and normal/subnormal boundaries; exact coordinate translation; randomized dot/cross/quadratics; all radical sign quadrants and equalities; Pell near-cancellations and 2^-1074 perturbations; normalized square-root carries and extreme exponents; 3,000 signed directed rounding/division fixtures; exact resource-boundary rejection; the full 100,000-operation ceiling; deeply immutable results; exact endpoint and tiny-offset memberships; and a near-tangent pair whose roots remain distinct but cannot be isolated at 256 bits.

All 14 retained design examples are checked against production coefficient signs and exact finite-line membership. Their independently retained root enclosures are verified by rational inequalities against the new exact coefficients. No finite-arc membership or later profile property is inferred from that correspondence.

## Pre-freeze findings and requested resolution

1. Shared-context reinitialization: explicitly calling __init__ reset an exhausted object's operation counter despite the documented non-resetting contract. The retained probe demonstrates 2 -> 0 -> 2 operations. Reject reinitialization of an initialized context and retain its original limits/counter.
2. Private precision validation: _round accepted a preconstructed 65,537-bit precision and _divide reached oversized exponent bookkeeping before eventual rejection. Validate the fixed precision choices before helper arithmetic, including zero fast paths.
3. Owner's companion finding: private shift helpers formed bit-count+shift before rejecting a preconstructed oversized shift. Bound the shift itself before bookkeeping addition; reject without consuming an operation.
4. Owner requested a bounded timeout on the new subprocess import test.

All four findings are resolved in the frozen source. Initialization rejects an existing context, ordinary assignment and deletion are blocked, private precision checks precede arithmetic/zero fast paths, shift ceilings precede size addition, and the subprocess test has a 10-second timeout. The independent final regression cases verify these fixes. These were bounded implementation/API hardening findings, not incorrect mathematical roots or signs in admitted public calls.

## Explicitly unqualified work

No finite-arc membership, incidence cell, exit, clearance, angle, area, parameter/frame conversion, inserted native representation, actual endpoint/height discrepancy, R0/C0 comparison, v3 result/service dispatch, capability, Blender UI or release activation is reviewed or approved here. The frozen general arc_geometry policy and all existing runtime source remain independent and unchanged. Passing these primitive gates will not constitute a usable curved profile or native geometry qualification.

## Frozen independent results

Exact primitive source SHA-256: 1a92f9f68fef5f8284efc91f3431abf00d0b0fdab371646303680421a540553a. Exact new test SHA-256: 6837a5600461bc15c65fcf4601249a988ecff4220062da6e12d1c9510fcc5379.

The reviewed Git-free snapshot is primitive-cbb4dd2-source, containing 948 files. Every file matched its source manifest before and after every independent frozen gate. Each of the 948 ZIP file contents also matched that manifest. Source archive SHA-256 is 6b425dfb3d3ca4e504ff7119c8f4abd0ecdab4b6ce6586e65169f195d043f091; manifest SHA-256 is e767b0d3d6d893c4a8cde39b9a74c26e53c0c9c3d59b143e0fc4f281e7544151. The 946 files predating the primitive commit matched documentation commit 0002556. The implementation commit adds exactly its two allowed files.

- 21 independent adversarial parametrized tests passed in 4.41 seconds. Internal deterministic loops exercise thousands of exact-reference fixtures; this is a bounded test matrix, not proof by sampling.
- All 138 new implementation unit tests passed.
- All 379 selected existing pure arc-geometry, schema-v3 and unsupported-consumer boundary tests passed.
- Ruff and format checks passed on both added files.
- A site-packages-disabled fresh process loaded only mechanical_cad and mechanical_cad.arc_profile_primitives from the project and completed an ordinary two-root calculation.
- The native import trap remained clean for all independent pytest gates. No native/OCP/Blender process was launched by this audit.
- All 105 original runtime hashes, the unchanged arc_geometry policy hash, and the delivered 0.5.2 archive SHA-256 d644fbce66b843047a6cb3e3cd775c1af8517a7ff82e3f22ce3888b710d1971f matched. No existing source imports the new leaf.

All independent gates completed with exit 0 and explicit terminal markers. FROZEN_GATE_RECEIPTS.json binds each command, timestamp, source identity, before/after checks and log hash. The final independent review does not claim the complete test suite was run by this reviewer; the owner-run full-suite receipt is a separate evidence source.

## Separately verified owner full regression

The owner-run source-snapshot gates completed with exit 0. This reviewer independently verified COMPLETION.json, each matching result receipt, each log hash and explicit terminal marker, and the actual 948-file snapshot map after completion. Full pytest reports 4,156 tests and 19,597 subtests passed in 117.15 seconds. Repository-wide Ruff and format checks also passed. This is existing whole-project regression evidence, not new curved-profile or native-join qualification. The reviewer did not rerun or launch any native process. Owner receipt hashes are retained in OWNER_REGRESSION_VERIFICATION.json.

Final approval is restricted to exact dyadic/sign arithmetic, bounded sqrt/output rounding, and complete line/circle support-root results with exact finite-line positions. The separately typed unresolved-isolation result remains a failure to establish isolation. No existing runtime file, general arc policy, delivered archive, production import, capability, service, UI or release changed in this primitive commit.
