# Instance source edit action

Each named Assembly instance now has an Edit Source Part pencil. It opens the
existing embedded-source replacement dialog, not a second editor and not an
immediate replacement. The dialog states how many instances share the selected
source. The replacement checkbox remains unchecked, and the working Part and
Assembly revision/scene/window guards remain in the existing operator.

Drawing the new buttons assigns only cached string properties from the current
Assembly presentation data. It does not assign the existing dynamic Part enum
for each instance. On click the launcher checks idle state and freshly resolves
the Assembly, instance, source Part, source digest and output feature. Missing,
rebound or revised targets fail closed. Opening or cancelling never selects an
instance or updates the Assembly. Update All Instances remains explicit.

## Focused evidence, 2026-10-24

45 focused unit tests passed: instance source dispatch, Assembly workflow UI and
primary actions. Cases include busy, missing, rebound, changed Assembly, changed
source digest and changed output. Changed-file Ruff and diff checks passed.

Actual Blender 5.2.2 GUI, disposable `reused_blocks` fixture: one pencil click on
instance `a` opened the existing dialog with Block selected, a three-instance
shared-source message and replacement unchecked. One Cancel click dismissed it.
Canonical Assembly and working Part JSON matched their before values exactly;
selected instance remained empty. No scrolling or preliminary selection needed.

Evidence directory beside source worktrees: `cad_work_outputs/instance_source`.
`reused_source_dialog.jpg`, `before.json`, `cancel_verified.json`, `gui.log`, and
fixture scripts preserve the observations. The output-feature stale-target guard
was added after this GUI observation and covered by the focused tests; it was
not separately reloaded in the GUI. No Apply/update/export, broad suite, release
packaging or Windows test host qualification is claimed.

Follow-up: launcher now propagates child CANCELLED but otherwise returns FINISHED,
leaving the existing source dialog as sole modal/Undo owner. Seventeen focused
launcher/wording tests pass, including both child return outcomes. Reloaded final
source (including output guard and natural plural wording) in the disposable GUI:
one reused-instance pencil click opened the unchecked replacement dialog, then
Cancel dismissed it normally. Screenshot: `reused_source_dialog_corrected.jpg`.

A later presentation-only refinement uses neutral opening guidance when the
working Part state is conservatively recognized as untouched. Existing or retained
state keeps the replacement warning, and confirmation is still required in both
cases. This wording branch has focused test coverage; the earlier GUI captures
precede that final copy change.
