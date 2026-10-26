# Native suspended-draft GUI acceptance

Date: 2026-10-16. Platform: cloud Linux X11 desktop, actual native Blender
5.2.2 LTS. This is a **source-checkout GUI gate**, not an installed-ZIP gate.

## Result

Passed the scoped rectangle suspension/recovery workflow after fixing a real
native-RNA pending-input callback defect found by this review. A new native
process was launched after that fix. Actual clicks and keystrokes established
invalid-text recovery, confirmed-but-unapplied text recovery, explicit fresh
solve, same-history Finish, repeated navigation, guard UI, and explicit Discard.
No production files were edited by the GUI reviewer.

The native popup owns mouse routing while open: clicks on the workspace tabs
were consumed by the popup and did not navigate. Therefore pending-input
suspension was exercised with an explicitly labeled developer timer interruption,
not represented as ordinary workspace-click coverage. Keystrokes in Blender's
private, unconfirmed text buffer remain outside this gate. The documented RNA
field-confirmation/focus-loss boundary was exercised.

## Source and execution identity

- Native binary: `<workspace>/tools/blender-lts/blender-5.2.2-linux-x64/blender`.
- Add-on imported and registered from
  `<workspace>/mechanical_cad/blender_addon/mechanical_cad_blender/__init__.py`.
- `MCAD_ROOT` pointed to this checkout and `MCAD_PYTHON` to its `.venv/bin/python`.
  Kernel work remained in the ordinary subprocess sidecar.
- Initial review began on HEAD `dcbf81d1aae0eda7a77378af9b1861cb1bf61365`
  with the draft implementation uncommitted. The fixed fresh GUI process began
  after HEAD `98a61b4edaa6a071c43063e6f1219a3440e0d52b` was created. Concurrent
  assembly commits advanced HEAD to `6261f951c1e37bca727fb01af0a74402a3c29223`
  during review. None of those commits alone identifies the uncommitted draft
  implementation. The following exact content hashes identify the fixed draft
  source loaded in the fresh GUI process, and matched at the end of testing:

| File under add-on package | SHA-256 |
| --- | --- |
| `viewport_sketch.py` | `1c77404a1b53b260b99513f6ef522788ae785246242b99c44c2d193c921f2555` |
| `draft_store.py` | `c4e147b980ed6616b32c9ba60b4c19b5afd812fe61747a9b63eeba6080611ed2` |
| `workspace.py` | `44941af6c214dc7bafe6706dd5f07198c020de351292cc3c6302a1c026d44346` |
| `workspace_ui.py` | `225a687e2d43de5513454c18a915d6ea6209c1329f288f31abea4dc7fec87221` |
| `document_state.py` | `916a3b4b0fa1e76579e6551af2bc65bc04fc1c0a590425c33a5933b0bb6d3726` |

The source manifest, tracked working-tree patches, status, launch scripts, native
logs, and read-only state observations are in the evidence directory below.
This is intentionally not a claim that a clean released commit or an installed
archive passed. Delivered 0.2 release artifacts and other open Blender sessions
were not replaced or discarded.

## Actual workflow and observations

1. Started a fresh factory native process with source registration. Loaded
   `examples/viewport_rectangle.mcad.json` using Blender's Python Console as
   fixture setup, then opened the CAD workspaces through the UI. Canonical
   history was `sketch_1` followed by `extrude_1`, 40 × 30 × 10 mm and
   12,000 mm³. Subsequent editing used actual native controls.
2. Clicked Edit Sketch, Dimensions, entered exact raw width ` 60mm ` (one space
   at each end), then Apply. The native popup and overlay explained the invalid
   arithmetic/unit suffix. No canonical bytes changed.
3. Clicked Part, returned to Sketch, clicked Resume, then Dimensions. Exact
   raw width survived, including the spaces as independently observed in RNA.
   The resumed outline said it was unverified; `validated_json` was empty and
   `solver_report` absent. No old DoF claim was shown as current.
4. Initially, native popup input ` 64 + 2 ` confirmed with Tab and focus loss
   was visibly present but `pending_dimensions` stayed null. This was reported
   as an acceptance blocker, not passed. The implementation worker reproduced
   the callback RNA wrapper lacking Python-only ownership attributes and fixed
   ownership with a transient RNA token. The reviewer closed only its own saved
   QA process and launched a fresh source process; no hot reload of an active
   popup was used.
5. In that fresh process, reopened the saved invalid draft and typed the exact
   pending width ` 64 + 2 `, Tab, and clicked a non-field Position label.
   Read-only observation then showed pending width ` 64 + 2 `, height `30.0`,
   fixed-position true, separately from last-applied width ` 60mm `.
6. A developer timer, armed through the native Console, waited for that exact
   native pending value and then called session suspension with reason
   `QA developer-triggered popup interruption`. The saved snapshot retained
   exact pending text. After closing the old native popup, Resume reacquired
   exactly two draw handles. Finish was disabled; reopened Dimensions showed
   the pending expression. This is **developer-triggered interruption coverage**.
7. Corrected width to `60` in that native popup and clicked Apply. Real sidecar
   solve returned okay, 0 remaining DoF, width60/height30. Clicked Finish.
   Blender returned to Part with READY state, empty draft slot, zero modal draw
   handles, original `sketch_1` → `extrude_1` history, and volume18,000 mm³.
   The downstream feature was updated rather than duplicated or recreated.
8. Began another edit of the same corrected rectangle. Completed three full
   actual Part → Sketch → Resume cycles. Each suspension released all draw
   handles (0); each Resume reacquired2, with no duplicate outline, no validated
   candidate and no trusted solver report. The orange diagonal was the existing
   committed mesh wireframe, not an extra modal overlay.
9. Saved-draft UI guards were exercised: New/Open and Check clicks did not
   execute; document menu, Edit Sketch, New Sketch, Extrude/Cut, named parameter
   controls, and STEP/STL exports were disabled. Opening the export submenu did
   not export. Exact canonical and raw draft bytes remained unchanged. These
   guard observations were made before the callback-only fix; that fix did not
   change guard behavior. No claim is made that disabled UI clicks independently
   prove every programmatic operator path.
10. Applied another invalid raw ` 60mm ` and suspended normally. A labeled
    developer Console probe appended a single trailing space to canonical JSON
    without changing its model meaning. The panel immediately explained that
    the draft belonged to a different committed revision, required restoring
    its exact original document or explicit Discard, and disabled Resume. Both
    external canonical bytes and the complete raw snapshot remained exact.
    This tests exact-base rejection; it is not a natural-Undo GUI claim.
11. Clicked Discard Draft. The snapshot cleared, modal handles stayed0, and the
    externally modified canonical bytes were unchanged. Only after recording
    that result did a developer cleanup restore the probe-only trailing space.
12. Clicked Check on the corrected Part. Native report: geometry checks passed
    for `extrude_1`, B-rep volume18,000 mm³, one valid solid, seam-welded
    tessellation closed and oriented. Saved a distinct final native QA file.

## Evidence and checkpoints

Evidence root: `/workspace/shared/cad_artifacts/draft-resume/`.
All screenshots are actual native desktop captures, without compositing or
retouching. Early captures were initially named `.png`, but the capture API
returned JPEG bytes. Byte-identical `.jpg` copies are the correctly labeled
versions; use these for delivery. Some full-desktop captures include the desktop
dock. It is not a CAD UI element.

- `01_invalid_width.jpg`: failed raw width Apply.
- `02_resumed_invalid_dimensions.jpg`: reopened invalid raw width after Resume.
- `03_unapplied_native_input_focus_loss.jpg`: pre-fix pending-input bug evidence,
  **not** proof of pending persistence.
- `04_suspended_part_recovery.jpg`: Part recovery panel with Return to Sketch and
  Discard, explicitly unverified draft.
- `05_document_guard_menu.jpg`: disabled document/authoring controls.
- `06_fixed_pending_confirmed.jpg`: fixed fresh-process confirmed pending input.
- `07_pending_resumed_dimensions.jpg`: despite its initial filename, this shows
  the resumed pending state with disabled Finish **before** reopening Dimensions.
- `08_pending_reopened_exact.jpg`: reopened native pending Dimensions after the
  labeled developer interruption.
- `09_corrected_part_same_history.jpg`: corrected downstream Part.
- `10_third_resume_unverified.jpg`: third actual navigation/Resume cycle.
- `11_stale_base_recovery.jpg`: exact-base mismatch recovery explanation.
- `12_explicit_discard.jpg`: explicit discard confirmation.
- `13_corrected_part_geometry_check.jpg`: final real geometry check/volume.
- `events.jsonl`, `guard_snapshot.json`: initial native observations.
- `fixed/events.jsonl`, `fixed/latest.json`, `fixed/heartbeat.txt`: fixed-process
  read-only observations. The heartbeat verified observation continued while
  native popup was open.
- `fixed/corrected.json`, `fixed/before-stale.json`,
  `fixed/after-stale-reject.json`, `fixed/after-discard.json`,
  `fixed/final-save.json`: machine-readable checkpoint assertions.

Native files, distinct from delivered examples:

- `/workspace/shared/cad_artifacts/draft-resume-qa.blend`: suspended invalid raw
  ` 60mm ` on the original40 ×30 ×10 mm canonical part. It was genuinely
  reopened in the fresh fixed-source native process. Its Part area was saved as
  a Console during checkpointing; switch it back to3D View or use Sketch.
- `/workspace/shared/cad_artifacts/draft-resume-corrected-qa.blend`: final READY
  60 ×30 ×10 mm part, empty draft, front CAD tabs, Part3D View, geometry passed.
  Saved from the real GUI scene using a delayed native save operator after
  returning from Console. The unrelated default Cube, Camera and Light remain
  present and unchanged; the viewport uses local view for the CAD part.

## Boundaries and follow-on gate

This establishes the Linux native source workflow described above. It does not
establish Windows/macOS, every window/layout, natural Undo/Redo interaction, or
unconfirmed private text-buffer recovery. Automated native suites are separate
reports and were not counted as mouse/keyboard proof here. Installed-ZIP testing
must name the exact archive, manifest/version, and installed module path in its
own receipt. No external publication or upload was performed by this reviewer.
