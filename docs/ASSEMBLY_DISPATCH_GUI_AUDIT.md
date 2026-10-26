# Focused Assembly dispatch GUI audit (2026-10-24)

## Results

Actual Blender 5.2.2 LTS GUI on a disposable three-block assembly confirmed:

- Top Details invokes its popup correctly. Native panel context is
  `INVOKE_REGION_WIN`; the inherited EXEC hypothesis is not supported.
- Set up standard checks saves the strict preset. One subsequent Check click
  invokes the asynchronous check directly, without a workload confirmation,
  and reaches **Measured pass**, enabling STEP.
- One enabled STEP click invokes a separate **Blender File View** window.
  Inspecting only the bound main window misses this dialog. Cancel closes it;
  the instrumented export `execute` was never called, so this audit did not
  write a STEP file.
- Escape during setup cancels the candidate; the setup button remains and
  no preset is selected. Escape during Check leaves **Check again** and STEP
  disabled. A later Check succeeds normally.
- No scrolling was used in these first-use/check/export flows. We do not
  report a total click count because popup dismissal consumed one earlier
  setup attempt without dispatch.

## Evidence and source

Evidence directory: `cad_work_outputs/assembly_dispatch/` beside the source
worktrees. Screenshots: `details_native.png`, `step_selector_native.png`,
`setup_cancelled.png`, `compact_measured_pass.png`. `dispatch.jsonl` records
actual invoke/execute entry and layout context using external wrappers that
call the original methods unchanged. `bootstrap.py` prepares the disposable
fixture; it is not production code.

Initial dispatch checks ran source a878880. The final compact screenshot and
both cancellation flows ran a878880 plus d378c64 (compact Sketch/Part ordering)
and 31dea0f (short labels). The visible long Check label was clipped in this
ordinary sidebar width, so it is now **Check**, retaining the operator's
**Check Current Pose** title/tooltip. The strict setup hint also fits now.

Setup cancellation exposed a misleading generic candidate message, **Gear
creation cancelled**, despite no gear operation. Commit c330090 changes it to
**Assembly update cancelled**. That wording change has focused unit coverage
but was not reloaded visually. No transaction or cancellation semantics changed.

47 focused unit tests passed (primary actions and pending admission/cancellation);
changed-file Ruff and diff checks passed. No broad suite, packaging, publication,
or delivered-artifact modification. This audit does not replace previous
enclosure/nine-instance screenshots and does not requalify STEP file writing,
Sketch/Part workflows, or arbitrary narrow sidebar widths.
