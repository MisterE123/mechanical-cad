# General sketch owner audit

An independent native-headless review passed the bounded orchestration and failure
recovery scope at `547c5c287b8b13858c864a0086e538d2883195a1` on Linux with Blender
5.2.2 LTS and the pinned CPython sidecar. The review used an exact Git archive and
did not edit production sources.

## Findings and correction

The initial `2a75732` owner started a native process before ensuring cleanup
supervision. An injected supervisor setup failure could leave its cancelled
handle and global execution lease retained without a timer. Setup now installs
the shared supervisor before acquiring transport or creating a child.

Two controller integration defects were also fixed: Cancel Input now closes the
text controller, and Cancel Check releases its acceptance latch while preserving
raw text. Held terminal events still drain once. Explicit retries create fresh
acceptance tokens; old key repeats never become new acceptances.

## Evidence and limits

The independent repair matrix passed 364 native assertions: 286 owner/staleness/
publication scenarios, 10 setup/retry assertions, 40 actual Undo/Redo/load/disable
assertions, and 28 held-key/compound cancellation checks. Tested cases include exact
raw/base binding, checkpoint CAS, downstream failures, one-shot completed Finish,
late ready-result rejection and canonical/display rollback.

Permanent regressions can be reproduced from the repository with the environment
in [ASYNC_SKETCH.md](../ASYNC_SKETCH.md):

```sh
"$BLENDER" --background --factory-startup --python-exit-code 1 \
  --python "$MCAD_ROOT/tests/blender_general_failure_smoke.py"
"$BLENDER" --background --factory-startup --python-exit-code 1 \
  --python "$MCAD_ROOT/tests/blender_general_session_smoke.py"
```

Check their `GENERAL_FAILURE_SMOKE_OK` and `GENERAL_SESSION_SMOKE_OK` markers.
Later tests may add assertions; the independent counts above belong to the exact
reviewed commit. Subsequent display-only continuity and UI changes require their
own review. This audit does not establish actual mouse/keyboard usability, window
destruction behavior, installed-package compatibility, or non-Linux support.
