# Next bounded Blender arc authoring slice

Status: parent-approved bounded design, with the independent review amendments below incorporated. No implementation or UI activation has begun.
Baseline: clean `ce5b50bb011b3949a6599c7cbc28d31024805e0a`.
The data-only sector service is independently qualified; 0.5.2 remains the
latest delivered usable release.

## Recommended useful outcome

A person starts a blank Part, draws one Center Arc and two radial lines using
its exact center/start/end IDs, explicitly applies Fix at origin, H/V and a
radius driver, and obtains a genuine 0-DoF quarter-sector. Finish builds its
profile; the ordinary Extrude tool builds a 10 mm solid. Editing the same radius
from 5 to 7 rebuilds the same sketch and extrusion with unchanged identities and
untouched point seeds. Canonical JSON and `.blend` save/reopen work, including
unfinished drafts, local Undo/Redo and retained radius-label placement.

This must pass as a manually drawn installed-GUI workflow. The existing prepared
example is a separate formula/parameter control, never a substitute for drawing.
Reverse sweep selects the complementary directed region without swapping points
or IDs. The quarter-sector volumes remain the qualified 196.34954084936206 and
384.84510006474966 mm³; native validity, trace and existing mass checks still run.

## Explicit scope choices for approval

1. **One finishable sector.** One arc, no full circle and at most two lines while
   arc-bearing; one constrained profile plus optionally its sole extrusion in the
   whole Part graph. Shared IDs are required. A second arc, third line, cut or
   unrelated feature graph is rejected before acceptance. Unsupported imported
   arc-bearing schema-3 authoring content has explicit refused editor/Resume entry with its
   bytes retained, rather than a new general repair editor.
2. **Incomplete arcs stay drafts.** They may solve, be inspected and be suspended
   or resumed. Canonical Finish of an arc-bearing sketch requires current pure
   sector readiness and a distinct successful full native replay. Successful
   solve alone never saves an open arc into the Part. Existing line-only open
   sketch Finish remains unchanged.
3. **Explicit draft-format opt-in.** First Center Arc activation discloses and
   atomically enables journal3/UI2/envelope3. Old canonical geometry/history stay
   exact. Only accepted AddArc upgrades embedded sketch1/2 to sketch3, together
   with the entity, in one Undo command. Undo restores the old sketch schema;
   the capable envelope stays newer while redo/tombstones may still exist.
4. **Raw authoring seeds.** A new third-click endpoint stores its observed local
   pointer coordinate; an existing endpoint stores an exact PointRef and keeps
   its authored coordinates. No circle projection is written by the tool.
   Provisional stroke/end-marker discrepancy is visible until Check. This
   deliberately supersedes the old, unimplemented projected-end gesture proposal.
5. **Keep layout1.** Radius annotation identity remains the exact constraint
   kind/refs signature, with current-source arc validation and finite-sweep
   leaders. Its placements carry no geometry authority. No redundant persisted
   radius, sweep, endpoint order or target-kind field is added.
6. **Build/edit/save first.** Dedicated Geometry Check, STEP/STL, guarded snapshots
   and Assembly capture/update/actions remain unavailable for schema3. UI and
   direct-call preflight reject before launch, current-state mutation or file/source
   writes. Part replay is not relabeled a Geometry Check receipt. If an export-ready
   first arc release is required, that is an explicit larger service-contract
   scope choice, not an implicit addition to this proposal.

## Live capability boundary

Extend the existing General/Part guarded path; do not import `service_v3` into
live owners or promote its copied dictionaries. Reuse the qualified strict v3
validators and the existing single transport, supervisor, owner and publication
transaction. No second arc publisher, nonce registry, timer or lease manager.

- Old consumers remain v2 by default. New capable General/Part readers and sinks
  explicitly opt into expected version3 derived from the complete exact candidate.
  Snapshot uses its own explicit action contract, never a wildcard version.
- Any embedded schema3 selects result3, even with an empty arcs array. An envelope
  upgrade alone selects nothing. Actual Undo back to an entirely legacy candidate
  can select2. Never downgrade, strip arcs or retry another backend/version.
- Capture one prepared G and fresh nonce per operation. Bind expected version,
  full G, owner identity, backend generation/lifetime, exact base/candidate,
  command/input revisions, context/units and layout CAS through every handoff.
- Initial solve, trial and downstream replay retain their exact complete chain.
  Same-owner clones transfer that chain; they cannot remint it. Publication is
  once-only. Current reads revalidate; rollback, history, saved flags and A→B→A
  cannot revive revoked authority.
- Cut over request creation, General validators/diagnostics/view data, pending
  jobs, PartPublicationIntent, the sole Part write sink and current readers
  together. Rectangle remains explicitly2 even after generic evidence supports3.
  All nine existing action families retain their v2 behavior and failure semantics.
- Static/AST negative integration checks cover every publisher/current reader,
  wrappers and error fallbacks. A naming-only private boundary is insufficient.

The source core, canonical/solver leaves, numerical policies, native kernel,
qualified projection, budgets and server capability set are expected byte-exact.
Any discovered need to change them stops that dependent scope for review.

## Journal, gestures and persistence

The exact command/envelope fields are in the authoring appendix. New AddArc and
ReverseArcSweep are ordinary typed local commands. AddArc reserves point IDs in
center/start/end role order and then one arc ID; failed acceptance consumes no
allocation. Reverse changes only direction. Delete-v3 declares its arc/constraint
cascade without deleting shared points or lines merely because an arc was removed.
Imported IDs, pruning, branching and tombstones retain the no-reuse guarantee.

Old envelope1/2 decoders and writers remain strictly old-version. Generalizing
shared restoration must not let journal3 pass through an old envelope, including
an empty legacy UI. Capable drafts passed to old writers must reject. Prefer
conservative expected-old defaults and explicit new-codec version selection;
any narrow old-codec guard must be declared in the reviewed file inventory.
Unknown/malformed versions or fields retain original bytes for recovery.

The three-click proposal persists raw observations without allocating entity IDs
or restoring pointer capture, native work or queued acceptance. Continue explicitly
reacquires input. Center/Start/End and radius selection use exact source kind/IDs;
finite arc picking cannot select the complementary full-circle span. A phase-aware
Use existing point action opens a bounded exact ID/role picker for the initial and
later Line/Arc phases. The chosen PointRef goes directly through the ordinary
detached proposal/CAS transaction, without cursor repicking or hidden snapping.
Inspector selection alone remains selection. Drawing and picking use existing
aggregate budgets and never call the native backend.

## Known native limit and recovery

The retained DoF5 case genuinely solves and passes pure readiness, but OCCT returns
an equivalent interval shifted by one stored binary64 turn. The unchanged exact
range guard rejects that representation. This remains a real limitation; no
kernel change, modulo fallback, tolerance widening or automatic repair is proposed.

The UI must separately show successful solve/DoF, pure profile readiness and native
build failure. It keeps the exact editable draft/raw dimension text and original
committed Part; any historical display is visibly stale. Finish does not close or
commit a failed draft. Explicit edit, Check, Undo, Suspend or Cancel remain available.
The negative GUI witness enters as exact saved draft intent through ordinary
Resume, then genuine Check and Finish; failed canonical replay cannot publish
that witness through Part file load. It carries no restored native authority.
The positive workflow remains manually drawn.
Disclosed Fix at origin/H/V/radius steps are the ordinary qualified positive path,
not hidden constraints or a promise to fix every possible underconstrained case.

## Four finite implementation/qualification gates

A. **Pure contracts and persistence.** Implement strict version dispatch, typed
   arc commands, codec transitions, bounded finite geometry and exact legacy-byte
   controls. Existing live selection stays v2 while consumers are incomplete.
B. **Atomic live owner integration.** Complete the General/Part handoffs and all
   explicit downstream barriers, then freeze for independent bypass/transaction/
   revocation review and genuine native Blender owner tests. No UI exposure before
   that review passes.
C. **Existing editor integration.** Add Center Arc, Reverse sweep, direct radius
   targeting, finite display/picking and truthful recovery using the same owners.
   No arbitrary-plane/multi-region redesign or new kernel research.
D. **Exact candidate qualification.** Full Ruff/format/pytest, all existing and
   new serialized native/exit/persistence gates, independent exact-source review,
   isolated ZIP install, manually drawn GUI workflow, old/mismatched backend and
   corrected-settings recovery, and two-process reopen. Retain every failure and
   collect each child before the next native process. Only a passed exact candidate
   can be described as a usable bounded arc preview; no existing release is replaced.

The appendices declare 60 owner-boundary rows and 38 authoring/persistence rows.
Before execution, map overlaps to one finite case manifest without claiming the
same case as multiple independent successes. Existing regression suites remain
mandatory. Reuse sealed kernel results only while their exact implementation and
contract stay unchanged; do not rerun those 70 construction cases just to inflate
this owner/UI gate.

## Review artifacts and approved boundary

- `OWNER_ADMISSION_PROPOSAL.md`: exact per-action policy, G/nonce chain, sinks,
  source file inventory, recovery, and owner acceptance ledger.
- `AUTHORING_PERSISTENCE_PROPOSAL.md`: exact versions/commands, gesture and
  annotation rules, source file inventory, manual workflow and UI ledger.

Parent approval on 2026-10-17 covers the six explicit choices above and the named
add-on, test/example and documentation edits, in the four gates, conditional on
the independent consistency review. Its exact-point and saved-draft-witness
amendments are incorporated here and in the appendices. Qualification uses the
already selected pinned runtime and isolated candidate profiles; no dependency,
OS/security, user-computer, hosting or GitHub change is included. Core/service
scope expansion, open-arc canonical Finish, export/Assembly3 or periodic-policy
changes require a separately reviewed decision. This is a bounded build/edit/save
arc preview; blocked export and Assembly controls must be visible. No
manufacturing-ready arc workflow claim is authorized. Sealed artifacts stay untouched.
