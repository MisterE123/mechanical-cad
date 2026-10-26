# Constraint-authoring preview verification

Historical evidence for the named 0.5.x checkpoints below. Their implemented and
unavailable-feature lists are not current-source claims, and their test results
do not qualify later releases. Start with [current capabilities and limits](INTEGRATED_MODELING.md)
and consult the exact package's verification receipt for that artifact.

## Delivered 0.5.2 compatibility-safety preview

The exact source/package at `df65fb4` is sealed and delivered. The
[installed 0.5.2 receipt](audits/backend_installed_052.md) records archive hashes,
the full automated gates, independent owner/protocol review and the bounded
actual installed-GUI rejection/recovery matrix. Its dated external receipts
close the candidate-stage GUI gate stated in the frozen source documentation;
this verification-only update does not rebuild or alter those release artifacts.
Arc profiles, result version 3 and UI remain a separate unreleased slice.

## 0.5.1 DoF safeguard

The 0.5.1 candidate adds a pre-native failure gate for cyclic active-coordinate
equalities in the pinned slvs 3.2 backend. It preserves source data and uses the
existing strict failure protocol. The [technical boundary](SOLVER_DOF_GUARD.md)
and [upgrade notes](RELEASE_051.md) define its scope. This source record alone is
not evidence of a completed installed-package qualification; use the corrective
package's accompanying receipt for its exact commit, hashes and executed gates.
No arc implementation is included.

## Delivered 0.5 baseline

The delivered [0.4 verification record](VERIFICATION_04.md) and its exact
source/package remain unchanged. This record separates source/runtime evidence
from artifact-specific qualification. The complete preview's accompanying receipt
identifies the final package hash and actual installed-GUI result.

The 0.5 artifact is now sealed and delivered at source `1a27e74`. The
[installed release receipt](audits/constraint_installed_050.md) records its hashes,
3,085 tests plus 19,597 subtests, 40 native suite entrypoints, two actual process
exit gates, exact installed GUI workflow and fresh-process annotation checks.
This documentation update does not alter those released source/package bytes.

## Environment and scope

Linux x86_64, native Blender **5.2.2 LTS** (`d13f752e3b9c`), CPython 3.12.14,
`cadquery-ocp-novtk==8.0.1.1.0`, and `slvs==3.2`. Minimum Blender is 5.2.
Windows/macOS, other Blender versions, all devices/keymaps and maximum-cap
interactive performance remain unqualified.

This slice adds explicit Points selection, Horizontal/Vertical, Fix here and
confirmed Fix at origin, exact relation inspection, solved-position release,
separately confirmed authored-position conflict recovery, and local Undo/Redo.
Existing Line/Circle dimensions, Rectangle shortcut, Part/assembly workflows and
shared draft recovery remain in place. Underconstraint is shown as remaining DoF;
failed native reports provide diagnostic candidates without geometry authority.

## Reproduce the full gate

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[dev,sketch]'
export MCAD_PYTHON="$PWD/.venv/bin/python"
export BLENDER=/absolute/path/to/blender-5.2.2/blender
bash scripts/run_checks.sh
```

The script runs lint/format, pytest, native Blender suite entrypoints and two
separately CPython-launched real Blender exit/owned-child-reaping gates. A passing
pytest run alone does not establish native interaction or process cleanup.
Targeted constraint commands and exact development results are in
[CONSTRAINT_VERIFICATION.md](CONSTRAINT_VERIFICATION.md).

For an isolated install, set `MCAD_ROOT`, `MCAD_PYTHON`, `MCAD_ADDON_ZIP`,
`BLENDER_USER_SCRIPTS` and `BLENDER_USER_CONFIG` to the exact source, interpreter,
ZIP and fresh temporary directories, then run:

```sh
"$BLENDER" --background --factory-startup --python-exit-code 1 \
  --python tests/blender_install_smoke.py
```

This verifies actual ZIP imports, blank-document creation, Part/assembly and both
sketch-editor dispatch paths. Native OCP/SolveSpace must remain in the sidecar.
Actual Install from Disk, ordinary controls, popup confirmation/cancel and
fresh-process reopen are a separate GUI gate.

## Bounded independent reviews

- Core at `f90b0fc`: pure selection/recovery contracts, legacy byte compatibility,
  exact diagnostic bindings and permanent retirement on observed mismatch.
- Owner/actions at `50e1b76`: exact immutable confirmation, rollback, busy-state
  rejection before mutation, truthful post-commit verification failure, complete
  recheck authority revocation, legacy dispatch and unrelated-data preservation.
- The earlier independent [0.4 reviews](VERIFICATION_04.md) retain their original
  scopes and source identities. They are not blanket approval of new code.

The runtime repairs have passed their bounded independent headless reviews.
Source GUI review on `ff935bc` passed a manually drawn four-line loop, explicit
H/V and endpoint selection, a fully defined solve, same-feature extrusion/edit,
normal release and Fix here, local Undo, inconsistent-solve blocking, confirmed
recovery Apply/Cancel, and save/reopen with retained annotations. A 3 × 2 × 10 mm
solid updated to 4 × 2 × 10 mm (60 → 80 mm³) with unchanged feature IDs.
The review exposed two final corrections: intentionally removed selections now
clear atomically, and contextual rows no longer move Check/Finish/Cancel.
Their fresh installed interaction checks are recorded in the package receipt.

## Remaining limits

Arcs, trim/extend, construction geometry, tangent/equal tools, general Coincident
creation, arbitrary relation-target editing, diameter/reference dimensions,
arbitrary sketch planes, multiple regions/holes and contextual reference geometry
remain unavailable. Native solver capabilities are broader than the exposed UI.
The compact field lacks IME composition and screen-reader integration; dense labels
can overlap. Sketch meshes are isolated only in their owned viewport.

Conflict recovery can move geometry after a fresh solve because it deliberately
retains authored seeds. Normal release uses current solved placement instead.
Neither path silently chooses a relation to delete. The command journal is
separate from canonical feature history and Blender Undo.

Assembly verification still concerns explicit rooted-tree joints and specified
poses, not continuous collision freedom, general closed-loop mates, structural
analysis or manufacturing certification. Portable `.mcad.json` stores canonical
design; `.blend` additionally stores annotations and unfinished draft UI.
