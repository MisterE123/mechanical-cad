# Assembly authoring automation checkpoint

Date: 2026-10-16. Target: native Blender 5.2.2 LTS, build `d13f752e3b9c`,
Linux x86_64, external CPython 3.12 with pinned OCP/slvs dependencies.

This checkpoint wires user-created Part capture, reusable instances, named literal
frames, fixed/revolute/slider tree joints, explicit source publication, saved
verification presets, bounded evidence pages and portable assembly files into
the Assembly workspace. It is a development checkpoint, not GUI or release
qualification.

## Reproducible checks

Use `scripts/run_checks.sh` with `MCAD_PYTHON` pointing to the project environment
and `BLENDER` pointing to the native binary. The script runs Ruff, pytest and all
listed native integration scripts. Run native suites sequentially.

At this checkpoint:

- Ruff check and format: 136 Python files passed.
- Complete pytest: 1,081 passed.
- Existing Part baseline, module reload, geometry actions, viewport draft,
  suspended-draft persistence and constrained-sketch persistence scripts passed.
- Assembly display boundary: 294 assertions passed.
- Assembly state transactions: 190 assertions passed, including a fresh-process
  saved-file reopen and compound rollback/scene-window identity regressions.
- User-authored assembly operators: 90 assertions passed. The script creates a
  Part through ordinary Part operators, captures and reuses it, authors frames and
  joints, checks saved intent, updates all instances and saves/loads portable data.
- Compact evidence dialog: 888 fake-layout assertions passed across the bounded
  15-joint, 120-pair and 32-pose data limits. Every section uses at most eight
  wrapped content lines plus five fixed rows; diagnostics remain accessible.
- Workspace registration/palette smoke passed.

An independent state/display review additionally exercised 104 supplemental
assertions, including the original double-failure and cloned-scene probes. The
corrections are in commit `8c66a61`; the reviewed numerical/transaction boundaries
remain separate from interactive acceptance.

## Resource and usability qualification

A combined run encountered a sidecar timeout during a late-input injection test
while the cloud desktop retained eleven old Blender QA windows and a separate
16-instance fine-tessellation stress probe was running. That interrupted run is
not counted as a successful complete gate. The stress probe timed out without
publishing geometry. The state suite was rerun independently and passed all 190
assertions; authoring and report suites then passed sequentially.

The maximum schema caps are resource guardrails, not demonstrated interactive
performance limits. In-flight cancellation and explicit requested-workload display
are required before the forthcoming assembly release. Interactive Apply/Cancel,
Undo/Redo, named frame visibility, long-popup readability and exact installed-ZIP
qualification remain separate gates. The immutable 0.2.1 draft-recovery release
contains none of this new registered assembly UI.

## Canonical capture and asynchronous lifecycle follow-on

The first native authoring GUI review exposed a missing schema-2 boundary case:
the viewport's raw working JSON omits optional constraint fields, whereas Part
identity is defined by the core serializer. Commit `5afacba` adds an authoritative
native-free serialization receipt. The exact captured GUI document is a permanent
fixture, and native fresh-process tests cover capture, reuse, reopen, ordinary
formula edit, all-instance update, report hash changes and rejected late responses.
The raw editor JSON, stable feature/entity IDs, references and seeds are retained.

A second confirmed display issue was Blender's default near plane slicing a small
Part close-up. Commit `b7d7f55` lowers only excessive clipping in owned CAD Focus,
using transformed local geometry bounds. Forty-three unit cases and native
framing operators cover units, translation, existing finer settings and unrelated
workspaces. The actual GUI comparison established the cause; the fixed GUI review
is qualified separately.

The cancellable transport (`b5c78d9`) and pending verification foundation
(`568ece0`) have 69 transport tests and 358 native pending-transaction assertions.
An independent lifecycle audit additionally reproduced and drove corrections for:

- Nonpersistent cleanup timer lost during an actual `.blend` load.
- Late recovery attempting to write freed RNA after add-on disable.
- A live sidecar orphaned on normal Blender quit.
- A retired modal handler accepting late events after its timer was removed.

Regression scripts now exercise real load, Undo, disable and native exit. Retained
jobs are detached from every native reference before data invalidation; their
remaining cleanup is process-only. Blender 5.2's `exit_pre` performs bounded owned
child cancellation/reaping. Late modal callbacks terminate without touching RNA.
The actual exit gate confirms the known owned PID no longer exists. Operating-
system uninterruptible cleanup is not claimed solved; incomplete cleanup remains
explicit rather than being counted as termination.

These automated corrections do not establish interactive cancellation usability,
frame visibility, exact final ZIP installation, or completed assembly authoring
acceptance. Those remain separate native GUI gates before packaging.
