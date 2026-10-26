# Preview a shared Part revision in its Assembly

Post-1.29 source development; frozen 1.28/1.29 installers are unchanged.

`Update All Instances` now opens an explicit, transient whole-Assembly review.
The accepted solid display stays visible while gold wire geometry shows the new
Part shape and every candidate instance placement. The panel lists all affected
instances (paged without changing selection), accepted/new revision prefixes,
and a single **Apply all instances** action. Cancel/Esc keeps the accepted source,
instances and display. View navigation remains available. This is a geometry and
mate-placement preview, not contact, collision or dynamics verification.

The working Part is canonicalized only on explicit invocation. A detached
candidate is built with the existing `update_source` operation. Pending replay
uses the existing native lease and guarded nonpublishing transport, never the
report/publication-on-poll path. The owner is bound to accepted Assembly, raw
working Part, scene, window, view layer, viewport, backend/configuration, units
and history. Changes revoke readiness; missing/ambiguous stable faces refuse
rather than guess repair. Closing, loading, Undo, or cancellation removes the
transient owner. Joint and source-update previews exclude one another.

Apply freshly replays the exact candidate. Before staging any display, an exact
strict-JSON SHA-256 comparison covers all six validated result fields
(`canonical_assembly`, `assembly_digest`, `source_hashes`, `instances`, `parts`,
`source_replays`) plus complete `base_pose`. Entire meshes, topology, datum policy,
resolved mate frames and source feature replays are included. No tolerances,
list sorting, field omissions or pose-only fallback are used. The digest is an
extra restriction, not evidence authority: existing guarded transport,
currentness and atomic publication remain mandatory. The immutable digest and
bounded ghost edges are computed once per completed replay, not during draw.
Explicit programmatic `execute` retains its existing guarded update semantics;
interactive `invoke` previews first. No saved schema or protocol changes.

## Bounded source verification

- Final combined focused source-owner/transport/publication/motion/layout checks:
  **266 passed**; Ruff clean. No behavioral assertions removed.
- Real kernel repeated identical source updates have identical fingerprints;
  changed geometry with unchanged spatial transforms has a different fingerprint.
- Blender 5.2.2: 32 owner checks, 10 independent-process reopen checks, and 20
  face-mate checks. Height 10→20 moves the attached top frame and child ghost by
  10 mm, while accepted placement stays unchanged until Apply. A valid replacement
  solid with the old semantic face removed refuses with repair guidance and no
  ready ghost, digest or publication. A separate ambiguous/split-face case was not
  fabricated or qualified.
- Earlier actual GUI preview and Cancel preserved canonical Assembly, working
  Part and accepted report. Reviewer found the launcher incorrectly registered
  an undoable completion before child Apply; fixed to return CANCELLED on
  delegation. Corrected actual GUI Cancel retains the exact canonical Assembly,
  working Part and accepted report with empty completed-operator history; no
  Repeat Last source-update entry. Fresh GUI Apply changes all shared widths
  10→20 and leaves exactly one child-modal history entry. Undo restores the exact
  original Assembly/working Part; Redo restores the exact applied Assembly.
  History restoration correctly requires fresh display replay; explicit Rebuild
  after Redo restored current geometry without changing accepted canonical data.
  Exact GUI-saved file independently reopened with 10 checks: canonical bytes,
  width 20, volume 2000, complete three-instance pose and unchanged slider values
  after explicit Replay; no transient preview survives file opening.
  GUI file SHA-256: `970a51b83daa4e7a6c3978e83935775fb2c287c102c6152a2e339817245b580e`.
- The sidebar pending label/cancel route was corrected after observing its old
  motion-specific wording; this final wording is covered by pure layout tests,
  not the earlier live screenshot. No publication semantics changed.
- First GUI initial load exceeded the existing 60-second timeout under concurrent
  QA; evidence retained. Subsequent initial loads were 27.48 and 23.67 seconds
  using a 180-second QA-only preference. Product defaults are unchanged. This
  host's responsiveness is a limitation, not a release performance guarantee.
  Two observed async preview phases took 18.29 and 38.84 seconds (excluding
  explicit canonicalization before the pending owner was observed).

The full aggregate, Windows and exact-installed package checks are not rerun for
this source checkpoint. Existing broader failures and native allocator limits
remain open. The separately paused slider GUI Apply/Undo is not exercised by
this independent source-revision workflow.

A wider sidebar/status test file also exposed eight AST-harness failures in
preferences/help/workspace fixtures (missing namespace/import helpers); 43 cases
passed. The source-preview sidebar cases pass. Those unrelated fixture functions
were not repaired in this milestone; full raw logs remain in cumulative evidence.
