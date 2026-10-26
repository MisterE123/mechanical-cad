# Assembly quick actions (post-1.17 source development)

The Assembly sidebar starts with accepted-geometry currentness, a compact check
verdict, and one Rebuild / Check / STEP row. Check stays disabled until accepted
geometry is current; the visible instruction says to rebuild before checking.
STEP uses the unchanged export preflight and its existing operator guards.
When unavailable, an adjacent details action explains the exact blocking reason.
The status info button also explains working-Part capture limitations, pending
source edits, last action failure, check scope and historical export receipts.

A working Part is not the accepted Assembly. Available source edits get an
explicit “Working Part edits not included” notice and Update All Instances.
Rebuild does not silently accept them. An unavailable working Part does not
invalidate accepted reusable Parts or disable otherwise-valid Assembly actions.

The instance list remains visible. Reusable Part/frame details, joint/motion
controls, check policy/full reports and advanced precision options are collapsed
initially and remain available through disclosure controls. These presentation
preferences are separate RNA fields, never canonical document fields. Drawing
reads them without assigning values, rebuilding, changing layouts, accepting
sources or rewriting numerical inputs. Expand/collapse does not run a model edit.
No full report is permanently displayed above the instance tree.

Check verdicts distinguish unchecked/historical, measurement-only, measured
preset pass, incomplete, known interference/clearance violations, threshold
uncertainty and explicit contact-policy acceptance. Acceptance is visibly labeled
“not a pass”; it is never promoted to a clearance pass. Samples remain labeled
as samples and are not presented as a current-pose export qualification. Existing
full evidence inspection and all runtime/source/currentness/export guards remain
unchanged. No continuous collision, physical fit or manufacturing guarantee is
claimed.

## Focused verification

- Native-free UI dispatch/status/disclosure tests cover current versus historical
  evidence, malformed reports, policy-versus-measured verdicts, sample-only scope,
  disabled Check/STEP explanations, working-Part versus accepted-Assembly state,
  primary-control ordering and non-mutating drawing.
- Existing Assembly workflow controls and export-owner guard tests are included
  in the bounded test selection. This is not a broad historical-suite pass.
- Real GUI qualification is recorded separately below when completed.

This is later source development. It does not alter the delivered Linux 1.17 or
Windows 1.16 artifacts, and no installer or platform qualification is implied.

## Bounded real GUI evidence, 2026-10-24

The combined, frozen source `c794cf6efbac550b7410b9860f4f0b3c06cc99e9`
was inspected in Blender 5.2.2 LTS on the cloud desktop at 1180 × 812.
This includes this Assembly slice, compact Sketch/Part reports and revised
Loft/Sweep/Hole/Shell glyphs. It is source-loaded GUI evidence, not installed-ZIP,
reopen-across-platform or broader workflow qualification.

- The two-Part seated enclosure's primary actions, whole instance list and closed
  disclosures fit without scrolling. Initially stale geometry disabled Check;
  rebuilding restored current geometry without claiming a check pass.
- A fresh exact Check completed. The top row showed **Contact accepted · not a
  pass** with STEP available. The read-only receipt independently confirms
  `complete=true`, `passed=false`, `policy_accepted=true`, threshold contact true,
  guarded display/report currentness and an empty export-blocking reason.
- The check-policy disclosure arrow expanded and collapsed detailed content.
- The nine-instance/five-Part gearbox showed all instance rows and the primary
  action strip without scrolling in the ordinary split layout. Its current
  geometry remained distinct from historical check evidence, STEP stayed blocked,
  and absence of saved presets offered **Create a check policy**.
- Part showed a compact **Part: Current** row, separately stale geometry-check
  badge and collapsed Part details. All four revised glyphs were visible in the
  actual palette.
- A real resumed Sketch first showed **Unverified · Check sketch** and **Profile:
  unchecked**. One observed Check-icon click obtained fresh solver evidence and
  showed **Fully defined · 0 DoF**, separately from **Profile unavailable · review
  boundary**. Sketch details remained closed. No geometry was committed.

Evidence files are under `cad_work_outputs/assembly_quick_actions/` in the shared
engineering workspace: `enclosure_compact_contact.png`,
`gearbox_compact_initial.png`, `part_compact_status_icons.png`,
`sketch_compact_unverified.png`, `sketch_compact_fully_defined.png`,
`enclosure_checked.json` and `gearbox_initial.json`. The enclosure screenshot is
comparable with the previous `ventilated_enclosure_current/gui_contact_policy.png`.
No numerical baseline scroll count was measured.

**Remaining qualification limits:** native cloud input/observation sometimes
showed prior UI state or focused controls before the eventual operation. Do not
interpret those intervals as isolated application timings or claim one-click
Assembly dispatch counts. The STEP file selector and status popover were not
visually established in this pass; no new STEP was written. Export availability
and unchanged admission guards are covered by focused tests and receipts, not a
successful GUI file-dialog claim. No file was saved over a delivered model.

The final focused Assembly test selection passed **62 tests**; changed-file Ruff
and diff checks passed. This remains a bounded selection, not a full-suite pass.
