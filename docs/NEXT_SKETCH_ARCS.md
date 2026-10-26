# Next slice: bounded Blender arc authoring

Status: approved staged implementation after immutable 0.5.2, the latest usable
compatibility-safety preview. Arc controls are not yet available in a qualified
installed add-on. The exact [authoring proposal](architecture/arc_authoring/PROPOSAL.md)
and its [independent consistency review](architecture/arc_authoring/INDEPENDENT_DESIGN_REVIEW_SUPPLEMENT.md)
define the active scope.

## Completed prerequisites

- The [directed-arc core](ARC_CORE_MILESTONE.md) preserves canonical point/curve
  identities and raw expressions, with explicit embedded sketch schema 3.
- The [bounded native sector milestone](ARC_SECTOR_NATIVE_MILESTONE.md) qualified
  one arc plus two shared-ID radial lines and its extrusion under fixed limits.
  Its native endpoint mapping is an explicit bounded projection; it never rewrites
  canonical authored coordinates. All 70 prescribed native positive cases and
  the negative gates remain separately recorded.
- The [data-only result-v3 service](ARC_SECTOR_DATA_SERVICE.md) qualifies solve and
  Part replay, including actual radius 5→7 with unchanged IDs and seeds. This is
  not live Blender publication authority. Its known conservative periodic-range
  failure is retained rather than silently repaired.
- The [live General/Part owner boundary](ARC_AUTHORING_OWNER_MILESTONE.md) is
  independently qualified at `a05fc17a7afb7d72ce94ff032764efa1e796ede3`. It admits
  schema-derived result3 through exact fresh requests and the existing atomic
  publisher. Its background owner tests are separate from editor usability.

Core, solver, kernel, numerical bounds and service dispatch remain byte-exact in
this authoring slice. The next code changes are confined to the reviewed add-on,
tests, example and documentation inventory. A required change outside that
boundary needs a separate review.

## Useful first workflow

Start a blank Part. Draw a Center Arc using center/start/end observations, then
two radial lines reusing the exact point IDs. Explicitly apply Fix at origin,
Horizontal/Vertical and a radius driver. Check must genuinely produce the
supported 0-DoF sector. Finish builds its profile; Extrude builds a 10 mm solid.
Editing the same radius 5→7 rebuilds the same features without replacing point,
arc, line or relation IDs or rewriting untouched authored seeds. Save/reopen,
local Undo/Redo, unfinished draft Resume and label placement must work.

The installed-GUI qualification must perform this workflow manually; a prepared
example cannot substitute for drawing. Explicit Reverse sweep changes only the
direction, retains endpoint roles, and visibly selects the complementary region.

This is a bounded **build/edit/save arc preview**. Geometry Check, STEP/STL,
guarded snapshots and Assembly capture/update/actions are visibly unavailable
for every schema-3 source, including arc-empty sources. Ordinary canonical JSON
and Blender persistence remain available. This is not a manufacturing-ready arc
workflow or an export/Assembly capability release.
An already-supported result2 Assembly remains usable when the working Part is
schema3; only capture/update from that unsupported working Part is blocked.

## Exact authoring and compatibility choices

- One arc, no full circle and at most two lines while arc-bearing. The whole
  supported Part contains that one constrained profile and optionally its sole
  extrusion. Shared endpoint IDs are required; equal coordinates or coincidence
  constraints do not silently join distinct IDs.
- Open/incomplete arcs may be checked, inspected and suspended as drafts.
  Arc-bearing canonical Finish requires current pure sector readiness plus a
  distinct successful full replay. Legacy open-line Finish stays available.
- The first Center Arc activation explicitly enables journal 3, UI 2 and saved
  envelope 3. It changes no geometry or history. Only accepted AddArc migrates
  the embedded sketch to schema 3, in one Undo command. Undo can restore the old
  embedded schema while keeping the newer envelope for redo and ID tombstones.
- New center/start/end observations retain their raw pointer coordinates.
  Existing points retain exact PointRefs and authored coordinates. The preview
  shows the support-circle stroke and the observed endpoint discrepancy, with
  explicit Check feedback. There is no hidden projection or constraint.
- The phase-aware Use existing point picker handles initial and later Line/Arc
  phases. It passes one exact ID through the ordinary detached proposal/CAS
  transaction. Ambiguous coincident IDs require explicit selection. Inspector
  selection alone does not accept an endpoint, and Resume never restores capture.
- Radius Dimension reuses the existing exact-text field and relation identity.
  Annotation layout remains version 1, with source-aware finite-sweep leaders.
- Legacy serializers, old operation record shapes, canonical hashes and ordinary
  v1/v2 wire bytes remain exact. Old envelope codecs reject new journal/UI pairs
  on both read and write. Unknown saved bytes remain available for recovery.

These choices supersede the earlier unimplemented projected-new-end gesture and
broader mixed-arc/chord/open-arc canonical Finish/export/Assembly proposals in this
roadmap. They do not alter general canonical arc geometry or expand the qualified
sector domain.

## Live evidence and supported geometry

Extend the existing guarded General/Part path, single supervisor/lease and sole
publication transaction. Default consumers remain result 2; only complete audited
General/Part owners explicitly admit schema-derived result 3. An envelope upgrade
alone does not select a wire version. Any actual embedded schema 3 selects 3,
including empty arcs; Undo to an entirely legacy candidate can select 2.

Exact prepared request/nonce, source, revision, owner, context, backend lifetime
and generation remain bound through solve, trial, downstream replay and Finish.
Publication is once-only. Same-owner clones retain the complete evidence chain.
Saved reports, rollback, history and backend A→B→A cannot revive current authority.
No data-only packet or compatibility adapter can mint a live publication claim.

The first editor workflow stays global XY at zero world origin. The unchanged
native domain requires radius and height 1–1000 mm inclusive, exact endpoint-ray
dot product at most zero, and all existing incidence, representation, trace and
mass checks. The necessary endpoint-discrepancy bound is not sufficient proof of
a profile. No geometric tolerance or resource allowance is widened.

## Known failure and recovery

The retained underconstrained DoF5 witness solves successfully and passes pure
readiness, but the kernel returns a same-length trim shifted by one stored turn.
The strict native representation check rejects it. The UI must distinguish
successful solve, pure readiness and native build failure, preserve raw editable
intent and the prior committed Part, and visibly mark historical display stale.
There is no automatic retry, reseeding, modulo fallback or constraint insertion.

The negative installed-GUI control restores the predeclared witness as pure saved
draft intent through Resume, then uses genuine Check/Finish. Failed canonical
Part loading continues to reject without publication. The separate manually
constrained positive workflow remains mandatory.

## Four implementation gates

1. Completed: dormant pure operation contracts, arc commands,
   journal/UI/envelope codecs and exact legacy-byte controls (`bef37be`).
2. Completed: atomic General/Part owner integration and downstream barriers,
   with independent bypass, one-shot, rollback and revocation review (`a05fc17`).
3. Completed bounded automated qualification: existing-editor Center Arc,
   exact-ID reuse, Reverse, finite display/picking, radius editing, persistence
   and truthful recovery. All fourteen serialized native editor/owner gates
   passed on the independently reviewed exact source. This is not manual GUI
   or installed-package qualification.
4. In progress: exact-source full regression, serialized native and exit/persistence tests,
   independent audit, isolated ZIP install, actual manually drawn GUI workflow,
   mismatch/corrected-settings recovery and fresh-process reopen.

The [owner appendix](architecture/arc_authoring/OWNER_ADMISSION_PROPOSAL.md) and
[authoring appendix](architecture/arc_authoring/AUTHORING_PERSISTENCE_PROPOSAL.md)
contain the finite acceptance rows. They are planned gates, not passed results.
Reuse the sealed native construction evidence only while its exact implementation
and contract stay unchanged. No usable arc release is claimed before the complete
candidate passes these gates.
