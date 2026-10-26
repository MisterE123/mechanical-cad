# Reversible CAD viewport focus: bounded source evidence

Date: 2026-10-24. Source refinement after the frozen 1.17 Linux checkpoint;
not included in that installer. Blender 5.2.2 LTS, Linux cloud desktop, 1180 × 812
application window. No Windows test host, Windows, ZIP-install, or full-release claim.

## Result

Focus CAD temporarily maximizes the CAD viewport with its sidebar retained.
Restore Layout returns the original editors and their bounds. Nothing joins,
deletes, or resets the source workspace. Focus is explicit, not an automatic
layout migration. Feature history and constraint controls remain accessible.
Short histories initially reserve 2–7 rows rather than seven empty rows.

During a live sketch, native maximize changes area/region identity. A first
prototype demonstrated that retaining the old owner is unsafe. The final action
explicitly checkpoints and suspends first, then exposes the existing Resume
control. Resume preserves authoring geometry/selection but starts unverified;
Check obtains fresh evidence. No owner/currentness guards were relaxed. A failed
checkpoint cancels the layout action. This additional Resume/Check step is a known
interaction cost; seamless guarded auto-resume is not claimed.

The ordinary active-draft Part: Dirty notice is one row with detail/rebuild
controls. Its full explanation distinguishes committed Part status from the
current sketch solve. Failed/unverified states and nonstandard dirty errors are
not compressed. Canonical model/status data are unchanged.

## Automated and actual graphical evidence

- 17 focused native-free tests pass, including eligibility, native action flags,
  labels, active-draft checkpoint/suspension, failure preventing a transition,
  and the exact allowlist for compact dirty notices.
- Ruff passes for the changed Python files; repository Ruff also passed before
  the final bounded fixture refinements.
- The graphical event-loop fixture reports `MCAD_WORKSPACE_FOCUS_OK` and 58 passing
  assertions. It uses a real selected, unsaved line and native solver, four
  Focus/Restore transitions, the existing Resume lifecycle and fresh Checks.
  It verifies exact geometry/selection retention, canonical JSON unchanged,
  prior editor types/bounds restored, unrelated workspace unchanged, honest
  invalidation of old solve evidence, and Esc suspension followed by Resume.
- Real mouse activation of Focus, Resume, Check, and Restore was observed in the
  same native application, plus actual Escape suspension. An existing fixed
  open-line sketch showed 0 DoF separately from compact Part: Dirty. The short
  history and full constraint inspector fit in the focused sidebar. Both pages
  of the diagnostic popup were readable and closing it retained the sketch.
- The final graphical fixture was saved to a new task-owned `.blend`, with no
  active operation. Earlier interrupted test scenes were retained, not discarded.

Development evidence basenames: `workspace_focus_native.json`,
`workspace_focus_resume_notice.png`, `workspace_focus_solved_gui.png`,
`workspace_focus_compact_status_gui.png`, and `workspace_focus_restored_gui.png`.
Screenshots are actual GUI captures, not headless renders or product mockups.

The first fixture run incorrectly attempted selection before its solve completed;
the production idle guard rejected it. The next run exposed the viewport identity
change and an unsupported restore icon; the action now uses explicit suspension
and `FULLSCREEN_EXIT`. Another fixture assumption that Resume automatically solves
was corrected to assert unverified state and request Check explicitly. None of
these test corrections weakened production ownership or solver guards.

## Not established

No full-suite pass, installed-package pass, independent-process reopen qualification,
Windows behavior, multi-window behavior, or broad Undo/Redo qualification is
claimed for this source change. A broad unit run was stopped on request after
124 passes and an unrelated `test_arc_downstream_barriers` import-fixture error
(mock `bpy.props` lacked `IntProperty`). The targeted 17-test result is separate.
The existing native sidebar may truncate some long explanatory labels at narrow
widths, and the viewport header can clip at this window width; sidebar Finish and
Cancel remain visible. This change does not resolve all CAD information density.
