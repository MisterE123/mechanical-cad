# Independent cancellable assembly lifecycle audit

Date: 2026-10-16 UTC. Read-only production audit; isolated repros were created outside the main checkout. Implementation owner applied all fixes and adopted regression scripts.

## Verdict

No open reproducible defect remains in the bounded async/lifecycle paths tested after the owner's fixes. This is not a full application, GUI, platform, or release qualification.

## Findings closed by independent retest

1. **Lost supervision on actual file load.** Nonpersistent supervisor timers disappeared during `open_mainfile`, leaving one cancelling transaction and its busy key retained after worker completion. Both supervisor registrations now persist across loads. Actual save/open plus delayed cleanup passes.
2. **Orphaned subprocess on normal Blender exit.** `quit_blender` exited successfully while the sleeping owned sidecar remained alive with PPid 1. Native `exit_pre` now performs bounded owned-job cancellation; the standalone exit gate confirms the exact emitted child PID is absent after Blender exits. Interactive async operation is explicitly blocked on Blender versions lacking the exit hook.
3. **Native crash on delayed cleanup after disabling the add-on.** Completion attempted to write a retained PropertyGroup after its RNA class/property was unregistered. Blender 5.2.2 segfaulted twice at `assembly_state._failure`, reached through `_finish_failure`. Lifecycle detachment now removes all RNA/runtime recovery references from retained transactions; completion performs process-ownership release only. Native load and unregister delayed-cleanup gates pass without a crash or result consumption.
4. **Retired modal's late Esc remained running.** After global UI cleanup removed the timer and tracking, a late Esc callback returned RUNNING_MODAL for an already-complete pending handle. The new `_ui_closed` guard returns CANCELLED before any pending/RNA access for late Esc, Timer, and navigation events. Deterministic native-hosted callback regression passes. No claim is made that a GUI handler leak was observed.

## Independently executed evidence

Native executable: `<workspace>/tools/blender-lts/blender-5.2.2-linux-x64/blender`, Blender 5.2.2 LTS, build hash d13f752e3b9c. All native invocations used `--background --factory-startup --python-exit-code 1` and explicit success markers.

- `tests/unit/test_sidecar_job.py`: 69 passed. Includes real subprocess timeout, cancellation before/during launch, cancellation during validation, ready/result races, bounded stdout/stderr, JSON preflight resource attacks, tempfile/descriptor cleanup, and process reaping.
- `tests/blender_assembly_pending_smoke.py`: ASSEMBLY_PENDING_SMOKE_OK 358, re-run after detachment changes. Includes one real detached CAD sidecar result; deterministic malformed/late responses; original scene/window/revision binding; corrupted display; pending cancellation; unchanged accepted bytes/objects/poses; publication rollback; removed scenes; and orphan-window supervision.
- `tests/blender_assembly_job_ui_smoke.py`: ASSEMBLY_JOB_UI_SMOKE_OK 39, after retired-modal fix. Deterministic modal manager tests; no GUI usability claim.
- `tests/blender_assembly_job_load_smoke.py`: ASSEMBLY_JOB_LOAD_SMOKE_OK 21. Actual file save/open, persisted supervisor, stale historical evidence, explicit detached transactions, add-on unregister, and later cleanup without registered Scene RNA.
- `tests/blender_assembly_job_undo_smoke.py`: ASSEMBLY_JOB_UNDO_SMOKE_OK 9. Actual native Undo, detached delayed job, stale evidence, retained supervisor, no old response consumption.
- `tests/blender_assembly_job_exit_smoke.py`: ASSEMBLY_JOB_EXIT_SMOKE_OK. Generated trusted sleeping sidecar, actual native quit, and exact child PID absent from Linux /proc. Failed pre-fix repro's owned process was explicitly stopped.

Original isolated reproduction/regression scripts are under `<workspace>/async_audit/`. The production owner copied/adapted the load, Undo, and exit regressions into the repository. The original unregister crash trace was `/tmp/pending.crash.txt`.

## Trust/resource review

No stale late-result publication bypass was found. Main-thread acceptance guards original scene/window, canonical input, working Part, epoch, units, accepted display identity, prior evidence binding, exact detached request fingerprint, action-specific response validation, and final display integrity. Cancellation invalidates unconsumed ready results; only the originating modal may publish, while the supervisor only cleans up. Failed/cancelled attempts preserve previous accepted evidence. UI freshness queries correctly show historical/stale evidence when stored status alone is old.

The transport bounds input to 2 MiB, stdout to 64 MiB and stderr to 64 KiB, with 10 ms size polling and documented possible on-disk overshoot. Timeout is clamped to 1–300 seconds. These are trusted-process transport controls, not a CPU/RSS sandbox or a guarantee against an OS-uninterruptible process. Shutdown waits are deliberately bounded.

## Limits

No GUI or desktop was used. Physical originating-window closure was represented by deterministic native-hosted contexts; actual GUI Esc/navigation, interactive Undo handler removal, multi-window usability, and Python-module hot reload were not certified. Windows/macOS and older Blender behavior were not independently qualified here. Full repository aggregate tests, ZIP install, and packaging are the implementation owner's separate gates.

## Audited source identity

Transport base: b5c78d9. Pending foundation base: 568ece0. The fixes were in the owner's working tree over HEAD b7d7f552ff3973bd6ac84307ec3fcc493c0002a7. SHA-256 identities at final review:

- `sidecar_job.py`: `4785bf2a4cfcaad39997bff7333303326c095fac377ac28655e33776e1d19987`
- `assembly_pending.py`: `68150bb5a6c4d978e6e8dc364c779a97330e6db57e3e1e06c7aae0d11a33ee0c`
- `assembly_job_ui.py`: `f573c48186142ef352cbb8b551b6b8d326d5dbfb12dd6a84dcea9aaaf7579cd4`
- `registration.py`: `4640bd6261d352a490616f2bbe1061d41e29f9aa32f7b605ca22373dc7d77438`
