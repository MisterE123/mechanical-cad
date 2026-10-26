# 0.3 bounded assembly preview verification

Date: 2026-10-16. Qualified environment: Linux x86_64, native Blender **5.2.2 LTS**
(build `d13f752e3b9c`), CPython 3.12.14 sidecar, cadquery-ocp-novtk 8.0.1.1.0,
and slvs 3.2. The add-on now requires Blender **5.2 or newer** and rejects older
runtimes before registering scene properties or handlers. Later Blender versions
and Windows/macOS remain unqualified.

The immutable [0.2](VERIFICATION_02.md) and [0.2.1](VERIFICATION_021.md) records and
released archives remain separate. Source Git history is supplied with releases.

## Bounded capabilities

Ordinary user-created Parts can be captured as accepted embedded revisions,
reused as named instances, and joined in explicit rooted fixed/revolute/slider
trees. Mate frames are literal local coordinates. Working-Part edits require an
explicit all-instance Update; accepted geometry and verification change together
or roll back together. Saved clearance requirements are separate from query
numerics. Without a selected verification preset, measurements cannot pass.

Check and listed-pose Sample use fresh exact solids. Their interactive workload
confirmation precedes a cancellable process; no partial result is published.
A known violation remains visible if another query is incomplete. Limits are
explicit and requests are never silently clamped. Discrete samples do not prove
continuous collision freedom. See [the workflow](ASSEMBLY_WORKFLOW.md).

## Automated evidence

The released source `1431ecd250a504ddc5b1066b57d8ea31baaabc14` passed the complete
check script: Ruff/format for 163 files, **1,355 pytest tests**, and native 5.2.2
integration suites. The earlier source-GUI basis `2419fc8` separately passed
1,330 pytest tests before the final example and installation gates were added.
These cover the existing Part/draft workflow, disjoint assembly display, atomic model/display transactions,
real schema-2 capture and fresh reopen, saved presets, paged evidence, pending
publication guards, workspace setup and process cleanup.

The [lifecycle audit](audits/async_lifecycle.md) independently reproduced and then
closed load-time supervisor loss, owned-child survival at normal quit, delayed
completion touching unregistered RNA, and retired modal events. Real load/disable,
Undo and exact-owned-PID quit gates now accompany the normal suite. These are
Linux tests; no general OS-uninterruptible-process guarantee is claimed.

The [clevis benchmark](CLEVIS_EXAMPLE.md) adds three editable Parts, one saved
assembly, seven named poses, analytic volume/gap assertions and negative/boundary
controls. Its maintained fixture/generator suite passes 24 scoped tests. Original
2419fc8 evidence and later source revisions are recorded separately. Example
reports do not substitute for user-authored GUI testing.

Run `scripts/run_checks.sh` with `BLENDER` set to the target native binary and
`MCAD_PYTHON` set to the pinned sidecar. Require exit zero and each explicit marker.
The complete release receipt records the exact committed source, whole-suite
results, package hashes and installed-package evidence. The final add-on ZIP also
passed clean native-background installation, Part and Assembly checks, and asset
integrity. The full 38-commit history bundle was restored and tested separately;
16 fresh clevis sidecar requests and six individual STEP/STL exports were checked.
See the [installed GUI receipt](audits/assembly_installed_030.md) for exact hashes.

## Actual native GUI evidence

The [source-loaded GUI audit](audits/assembly_authoring_gui.md) records exact
2419fc8 findings and artifacts. Native mouse/keyboard operations created a 12×8×4 mm
constrained Part, reused it twice with named frames and a slider, selected a saved
2 mm clearance requirement, and checked an 18 mm separation. Sampling positions
0/30 detected 384 mm³ interference at zero while preserving the accepted position.

Changing the working Part width to 16 mm left both instances unchanged until
explicit Update. Cancel preserved all accepted data; Apply updated both to
512 mm³ and invalidated verification. Native Undo/Redo and a fresh-process `.blend`
reopen preserved exact Part/Assembly records. Replay restored display without a
verification claim; a fresh Check measured the expected 14 mm gap.

Real 32-pose requests exercised visible pending state, wheel navigation and Escape
cancellation while preserving previous accepted evidence. An out-of-limit joint
edit failed without modifying the model. Native Part/Sketch glyph hover help was
readable at the tested scale. The source audit does **not** claim mouse-button
Cancel Check, fixed/revolute GUI authoring, exhaustive themes/HiDPI/keymaps or final
ZIP installation; those require their separately named package receipt.

The [exact installed 0.3 GUI gate](audits/assembly_installed_030.md) independently
verified all 567 installed ZIP members against the frozen package. Visible
**Focus Part / Whole Scene** controls preserved every other viewport and all
object hide flags. Native fixed/revolute insertion, explicit angle/limit entry,
honest overlap detection and actual mouse **Cancel Check** passed. Cancellation
preserved exact accepted Part/Assembly, display objects and report bytes/status.
The saved four-instance GUI scene deliberately overlaps as a negative control;
the separate clevis fixture demonstrates the stated positive-clearance example.
F3 did not expose the Focus command in the tested context: use the visible buttons.
This installed gate reused the source-authored Part; it does not relabel the earlier
full creation/update/Undo/reopen review as an installed-package test.

## Remaining product and evidence limits

- The viewport sketch editor remains a four-corner global-XY rectangle. General
  sketch tools, traditional direct editable dimensions and live feature previews
  remain future work.
- Native text keystrokes reach saved draft state only after Blender updates RNA.
  The application does not claim access to its private unconfirmed text buffer.
- Mate frames do not track faces or thickness automatically. General closed-loop
  solving, nested subassemblies and in-viewport joint dragging are unavailable.
- Assembly default layout remains text-heavy; default Outliner/Properties consume
  useful space, names may truncate and assembly axes/icons need broader contrast
  review. These are explicit UX gaps, not a claim of a finished CAD interface.
- Dense maximum-cap performance, every input device/theme/keymap, Windows/macOS
  and later Blender releases are not qualified by this preview.
- There is no structural/load, physical-fit or manufacturing certification, and
  no continuous-collision guarantee. Individual Part export retains its separate
  valid-solid/manifold/float32-fidelity gates.
