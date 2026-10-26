# Constraint authoring verification

The bounded slice shipped as 0.5 at `1a27e74`; its exact artifact and installed
GUI results are in [the release receipt](audits/constraint_installed_050.md).
The development records below retain their original source identities and scopes.
Tested automation uses Linux
x86_64, official native Blender 5.2.2 LTS (`d13f752e3b9c`), CPython 3.12.14,
`cadquery-ocp-novtk==8.0.1.1.0` and `slvs==3.2`.

## Implemented boundaries

- Explicit point-only selection coexists with generic geometry selection. It
  never silently chooses one of two distinct overlapping point IDs. Inspector
  Start/End/Center controls name the exact authored point.
- H/V and fixed relations use the existing stable-ID command journal. Exact
  duplicate actions preserve the original relation and current solve evidence.
- Fix here uses freshly revalidated current solved coordinates. Fix at origin
  has a separate prepared confirmation and may move connected geometry.
- Normal relation removal uses current solved release seeds. Explicit recovery
  uses exact authored seeds only when no current solution exists; neither path
  deletes geometry. See [the seed contract](CONSTRAINT_RECOVERY_CONTRACT.md).
- Failed native reports are immutable request/session/command/raw-revision-bound
  inspection candidates. Observing a broken owner/context/source/slot binding
  permanently retires them until another Check. They supply no geometry, DoF,
  release authority, or Finish permission.
- Inspector selection is UI-only and checkpointed atomically over the same
  command object. Confirmation retains the original prepared intent; stale
  owner, selection, input, source, evidence or slot rejects without reinterpreting
  the user's action. See [actions](CONSTRAINT_ACTIONS.md) and
  [inspector](CONSTRAINT_INSPECTOR.md).

## Reproduce

From the checkout with pinned development/sketch extras installed:

```sh
export MCAD_ROOT="$PWD"
export MCAD_PYTHON="$PWD/.venv/bin/python"
export BLENDER=/absolute/path/to/blender-5.2.2/blender
"$MCAD_PYTHON" -m pytest -q
"$MCAD_PYTHON" -m ruff check .
"$MCAD_PYTHON" -m ruff format --check .
for name in diagnostics selection actions ui history_busy launch_failure selection_release; do
  "$BLENDER" --background --factory-startup --python-exit-code 1 \
    --python "tests/blender_constraint_${name}_smoke.py"
done
"$BLENDER" --background --factory-startup --python-exit-code 1 \
  --python tests/blender_ui_icon_contract.py
"$BLENDER" --background --factory-startup --python-exit-code 1 \
  --python tests/blender_palette_positions_smoke.py
```

The complete `bash scripts/run_checks.sh` includes these nine new native tests
alongside the unchanged Part, Rectangle, general owner, assembly, persistence,
lease, cancellation and real-process exit gates. A Blender executable is required
for the native tests; `pytest` alone is not equivalent.

For a frozen source archive, set `MCAD_ROOT` to that archive, `MCAD_PYTHON` to an
interpreter with the pinned backend dependencies, and run the test script inside
the archive. That interpreter does not make Blender import OCP or SolveSpace.

## Recorded development results

The preceding source candidate `8f6dd33` passed the full pytest suite: **3,071 tests plus 19,597
subtests**. Ruff and format checks passed. A combined 14-entrypoint native run
passed, including:

- Constraint action seam: 201 assertions, real four-line 0-DoF solve, no-jump
  release/Fix here, actual conflicts/recovery, restored inconsistent drafts,
  stale confirmations, and analytic rectangular and circle extrusions.
- Constraint inspector/operator seam: 169 assertions, including prepared native
  dialog confirmation/cancel, exact-ID selection, checkpoint failure rollback,
  origin and recovery controls, local Undo/Redo and bounded pagination.
- Diagnostic owner binding: 58 assertions with actual failed solves, raw A→B→A,
  source/slot observer retirement, explicit retries and no false solve authority.
- Point selection adapter: 10 assertions; generic endpoint/line tie preserved,
  explicit Points route works, native evidence and command history unchanged.
- Existing general owner 85, failure recovery 29, overlay 58, New/Edit/Resume
  dispatch 116, view isolation 205, execution lease 155 and sketch job lifecycle
  141 assertions; shared owner, general authoring and workspace suites also pass.

The follow-on repair candidate `ff935bc` passed repeat action 201, inspector 169,
general owner 85, failure 29 and new local-history busy 106 checks. Verification
startup failure 45 checks cover a missing executable, failed supervisor setup and
an actual transport spawn error. The native icon contract validates 179 production
literal/registry entries against the target Blender RNA enum. This caught the
invalid Undo/Redo icon names that had escaped the mocked layout test. These
repairs subsequently passed the bounded independent action review at `50e1b76`;
the final installed interaction gate is recorded separately below.

The subsequent `50e1b76` correction also retires command-layer authority when a
replacement Check begins. Failed startup or cancellation cannot leave Finish
available without the corresponding complete owner evidence. The expanded native
startup/recheck suite passes 57 checks; pure draft tests pass 74, and the six
owner/action/diagnostic/busy native suites pass again. Authored snapshot bytes,
local history and a clearly unverified retained outline remain intact.

These are native-headless contract checks, not human mouse/keyboard usability.
Source GUI review, independent action audit, full release gate and clean installed
ZIP review are separate from these checks; all four closed for the sealed 0.5
artifact identified in the release receipt.

The separate core audit is bounded to `f90b0fc`: exact failure-diagnostic observer
retirement, pure recovery/selection contracts and unchanged legacy codec bytes.
Its 24 independent cases and six native A→B→A observer paths pass, together with
the full 3,071-test suite. This does not qualify later action/UI behavior.

## Final 0.5 gate

Exact source `1a27e74` passed Ruff, 3,085 tests plus 19,597 subtests, all 40 native
entrypoints and both separately launched real exit/owned-child-reaping gates.
The actual installed-background test passed general dispatch 116, actions 201 and
inspector 170 assertions. A final 60-assertion independent selection-transaction
review passed on both `c13ea25` and the identical final three-module source.
The fixed-slot palette has 2,427 native layout assertions and an actual installed
GUI check across selection/input states. Clean Preferences installation, manual
constraint authoring/recovery, same-Part update and fresh-process annotation
restoration passed; 26 durable receipt invariants also passed. See the receipt
for exact hashes, reproduction steps and the remaining manual-test limitations.


## Scope kept explicit

Circle radius and line distance remain the exposed driving dimensions. General
Coincident creation is deferred despite its symbolic preflight helper. Existing
coincident constraints and explicitly reused endpoint IDs remain supported.
Arcs, trim/extend, construction geometry, tangent/equal tools, reference/diameter
dimensions, arbitrary workplanes, multiple regions and holes remain future work.
This milestone does not claim a full constraint editor, general assembly solver,
continuous collision or structural analysis.
