# 1.14.0 Linux development checkpoint

This checkpoint adds responsive explicit Assembly Replay and Edit Gear Pair to
1.13.0. It remains an experimental Linux x86_64 / Blender 5.2.2 LTS workflow,
not a complete Onshape replacement or a manufacturing qualification.

## Added workflow

- Assembly Replay runs native geometry asynchronously through one guarded,
  cancellable owner. The accepted assembly remains visible; viewport navigation
  can continue. Explicit Replay does not perform an interference check.
- Edit Gear Pair recognizes supported generated pairs, prefills their accepted
  parameters, and asynchronously updates both gears, shaft spacing and gear
  relation together. Failed, cancelled and stale candidates do not replace the
  accepted state. Successful edits require a new explicit verification.

## Evidence boundaries

Replay GUI evidence belongs to source d3af02e1bdce2c868dca2f411b0a094a41b3a21b:
actual Escape cancellation, responsive navigation, repeated Replay clicks with
one observed owner, and subsequent successful Current display. Mouse-button
Cancel attempts raced completion and do not independently qualify that input.

Edit GUI evidence belongs to source 10702a64875694e67b04397975db4a3d1b869c7c:
module 2 to 2.5 and teeth 20/40 to 24/40 changed shaft spacing 60 to 80 mm and
ratio -0.5 to -0.6, followed by accepted-value dialog prefills. Dismissal preserved
the accepted bundle. A changed-field Cancel test and a separate-process reload
were not established by that GUI pass. Custom names, nonzero driver angle and
populated document-path preservation have native evidence only.

These are exact development-snapshot results, not GUI reruns on the later
metadata commit. Installed-package qualification is reported separately with the
artifact identity. Headless modal pumping is not interactive GUI evidence.

## Unchanged limits

No full historical-suite pass, solved general topological naming, collision,
strength or print-fit assurance is claimed. Gear profiles remain bounded cubic
approximations, not exact involutes or generated root fillets. Prior failures and
all 42 unresolved source/material declarations remain unresolved. Packaging does
not establish source correspondence, redistribution rights or legal clearance.
Windows Blender admission remains closed; this checkpoint is Linux only.
