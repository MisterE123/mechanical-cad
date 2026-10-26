# Explicit intended-contact policy

This opt-in development capability permits a named pair's numerical contact band
without relabeling its measured clearance result. It does not prove exact contact,
zero physical penetration, fit, strength, or manufacturing suitability.

## Authoring and persistence

A saved `clearance` preset can include `contact_policy: "accept_tolerance_band"`
on an individual named requirement with `minimum_mm: 0`. Other values, explicit
null, positive clearance, unknown pairs, and duplicate pairs are rejected.
Omitting the field preserves existing serialization and strict behavior. There
is no implicit migration, global collision exemption, or ad-hoc contact override.

In Edit Verification Preset, select the two instances, enter zero minimum, and
explicitly enable **Accept intended contact within numerical tolerance band**.
Other saved pairs retain their policy. Disabling the checkbox removes this pair's
exception. Selecting a preset or changing its policy invalidates current evidence;
run Check Pose again. Saving intent alone never establishes acceptance.

## Separate measurement and policy outcomes

The original `passed`, `complete`, `status`, `has_threshold_contacts`, relation,
clearance verdict, measured common volume and boundary distance remain unchanged.
A contact stays `at_threshold`, with measured `passed: false`, even if the new
report-level `policy_accepted` is true. This optional field appears only when the
selected saved preset contains contact intent. Replay never evaluates it.

Policy acceptance requires every listed pose and every instance pair to be
complete, without diagnostics or known interference/clearance violations. Each
explicit contact pair must have measured common volume exactly zero, nonnegative
measured boundary distance no greater than the selected linear tolerance,
`contact_or_near`, zero required clearance, and `at_threshold`. Positive measured
volume, even below the common-volume threshold, remains unacceptable. Missing,
unknown, incomplete, or contradictory evidence cannot authorize export. Unnamed
pairs must meet ordinary `pass_at_pose` clearance; one seat does not exempt any
other pair. A separated assembly can still pass the ordinary clearance policy;
the exception itself is accepted only for the authored contact band.

Linear tolerance (mm) and volume threshold (mm³) are numerical guardrails, not
certified error bounds. A measured zero common volume cannot prove zero physical
penetration. The band may represent contact, a very small gap, or unresolved
numerical geometry. No signed penetration depth is provided. Report Summary and
Pairs show policy acceptance separately, actual measured quantities and tolerances,
and this uncertainty. Sampling checks only listed poses, not continuous motion.

## Export authority

The active saved preset and contact intent participate in the canonical assembly
digest and request/report fingerprints. Clients independently validate every
measurement and recompute policy acceptance against the selected canonical preset.
STEP export permits either the unchanged strict measured pass or explicit policy
acceptance. It still requires current source/runtime authority, a complete fresh
same-invocation saved-pose check, the active preset, no request overrides, and all
existing transaction and destination guards. It exports separate definitions and
instances, not a fused or certified physically fitting assembly. Policy intent is
preserved in canonical JSON/Blender data, not in STEP exchange geometry.

## Focused verification

`tests/unit/test_assembly_intended_contact.py` covers round trips, unchanged strict
defaults, named-pair editing, threshold-band measurement retention, all-pose checks,
wrong/unrelated pairs, stale policy, forged acceptance, contradictory/positive-volume
and incomplete evidence, plus result-2/3 export receipt validation and preservation
of the destination on rejection. Synthetic tests do not qualify native geometry.
`tests/integration/test_assembly_intended_contact_kernel.py` exercises real seated boxes,
strict export rejection, explicitly accepted STEP export/readback, unchanged raw
measurements, and an interfering pose preserving the previous destination.
Blender interactive authoring/Undo/save-reopen and platform qualification remain
separate checks; do not infer them from pure/native service tests.
