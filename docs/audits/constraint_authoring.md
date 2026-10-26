# Bounded constraint-authoring audits

Date: 2026-10-16. These are independent source/read-only and native-headless
checks on Linux x86_64 with Blender 5.2.2 LTS (`d13f752e3b9c`), CPython 3.12.14,
OCP 8.0.1.1.0 and libslvs 3.2. Actual mouse/keyboard use and exact package install
are separate qualifications.

## Pure core and diagnostic ownership

The final audited core is `f90b0fc`. Its review covered explicit endpoint picking,
ordinary solved-position release, authored-position recovery, old codec bytes,
immutable failed-solve diagnostics and their exact owner/request/input bindings.

An observed source or saved-slot mismatch initially hid diagnostics temporarily;
restoring the old bytes could revive them. Repairs permanently retire that
capability on observed mismatch through the getter, Check, tool eligibility and
checkpoint paths. Fresh native work is required to obtain new evidence.

Independent checks passed 24 cases and six native A→B→A observer paths. The frozen
full suite passed 3,071 tests plus 19,597 subtests. Relevant owner/persistence/job/
lease/view-isolation native suites also passed. Legacy serialization stayed exact.

## Owner actions and confirmation

The final audited action runtime before the separately reviewed presentation
delta is `50e1b76`. The review exercised original prepared confirmations, selection
and source changes, replacement owners, cancellation, real failed native solves,
Undo/Redo, repeated clicks, registration failure, legacy dispatch and unrelated
Blender data preservation.

Four findings were repaired and independently retested:

1. Local Undo could mutate its journal before another operation's execution lease
   rejected the automatic Check. The shared idle guard now rejects before mutation.
2. A committed local command could return cancellation after Check startup failed,
   leaving old success wording. Authored success and verification failure are now
   separate: intent is retained and Undoable, the error persists, and Finish is
   unavailable until explicit successful verification.
3. Invalid native Undo/Redo icon names stopped the inspector from drawing. Valid
   target-runtime icons and an actual RNA-enum contract now cover 179 production
   literal/registry entries.
4. A failed or cancelled replacement Check cleared owner evidence but retained
   the command layer's solved flag. Both capabilities now retire together, with
   an explicitly unverified retained outline and no change to authored bytes.

Independent matrices passed 57 action/identity/registry cases, 35 recovery-popup
cases, 45 post-commit startup-failure cases and 42 replacement-Check failure/cancel/
retry cases. The existing native actions201, UI169, diagnostics58, selection10,
legacy dispatch116, busy-history106 and expanded startup57 suites passed on the
same frozen runtime. Pure draft74 passed. These counts describe separate bounded
checks, not general correctness or cross-platform certification.

## Reproduce project regressions

```sh
export MCAD_ROOT="$PWD"
export MCAD_PYTHON="$PWD/.venv/bin/python"
export BLENDER=/absolute/path/to/blender-5.2.2/blender
for test in diagnostics selection actions ui history_busy launch_failure selection_release; do
  "$BLENDER" --background --factory-startup --python-exit-code 1 \
    --python "tests/blender_constraint_${test}_smoke.py"
done
"$BLENDER" --background --factory-startup --python-exit-code 1 \
  --python tests/blender_ui_icon_contract.py
"$MCAD_PYTHON" -m pytest -q tests/unit/test_constraint_selection.py \
  tests/unit/test_constraint_diagnostics.py tests/unit/test_general_sketch_draft.py \
  tests/unit/test_general_authoring.py tests/integration/test_general_sketch_draft_native.py
```

Run a specific frozen commit in a clean checkout when reproducing its exact
historical counts. Current tests include later regression additions. The full
release script and exact installed receipt are documented in [VERIFICATION.md](../VERIFICATION.md).

No audit claims native GUI focus/scale usability, installed-package correctness,
maximum-cap responsiveness, other operating systems, continuous collision or
structural validation. Arcs and the broader constraint-editor roadmap remain
outside this slice.
